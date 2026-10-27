import { describe, expect, it } from "vitest";

import type { ActivityState, AgentState, TaskView } from "@/stores/realtime";

import { courierState } from "../agents/courier";
import { assignSeats, meetingSeat } from "../scene/layout";
import { routeFor, WALK_SPEED } from "./CueRunner";
import { CueQueue, type ActiveWalk } from "./director";
import { MEETING_LINGER_MS, MeetingDirector, meetingNow, meetingWalk, type MeetingView } from "./meeting";

const NOW = new Date("2026-10-28T07:10:00Z");
const ago = (ms: number) => new Date(NOW.getTime() - ms).toISOString();
const RUN = "00000000-0000-4000-8000-0000000000aa";

const agent = (id: string, role: string, state: ActivityState = "IDLE", taskId: string | null = null): AgentState => ({
  id,
  role,
  display_name: id,
  avatar_key: "default",
  department_id: null,
  department_key: null,
  office_zone_key: null,
  business_unit_key: null,
  activity: { state, stored_state: state, detail: {}, since: ago(5_000), run_id: null, task_id: taskId, last_event_seq: 1 },
  liveProgress: null,
});

const task = (id: string, name: string, role: string, state: string, over: Partial<TaskView> = {}): TaskView => ({
  id,
  name,
  display_name: name,
  required_role: role,
  state,
  depends_on: [],
  workflow_run_id: RUN,
  attempt: 0,
  run_id: null,
  agent_id: null,
  since: ago(20_000),
  last_event_seq: 1,
  ...over,
});

const AGENTS: Record<string, AgentState> = Object.fromEntries(
  [agent("tifa", "ceo"), agent("ada", "editor_in_chief"), agent("ami", "editor"), agent("shinobu", "writer"), agent("chunli", "marketing")].map((a) => [a.id, a]),
);

/** A meeting with three speakers (in the order the backend made them, not speaking order). */
const TASKS: Record<string, TaskView> = Object.fromEntries(
  [
    task("t-writer", "statement_writer", "writer", "RUNNING", { agent_id: "shinobu" }),
    task("t-chief", "statement_editor_in_chief", "editor_in_chief", "SUCCEEDED", { agent_id: "ada" }),
    task("t-editor", "statement_editor", "editor", "READY"),
    task("t-chair", "chair_meeting", "ceo", "PENDING"),
    task("t-apply", "apply_minutes", "system", "PENDING"),
    task("t-other", "draft", "writer", "RUNNING", { workflow_run_id: "00000000-0000-4000-8000-0000000000bb" }),
  ].map((t) => [t.id, t]),
);

describe("who is in the weekly meeting (D-260)", () => {
  it("its chair and its speakers, in speaking order, while any of its tasks is open", () => {
    expect(meetingNow(TASKS, AGENTS, NOW)).toEqual({ workflowRunId: RUN, chair: "tifa", members: ["ada", "shinobu", "ami"] });
  });

  it("somebody the company has put on other work stays at it; so does somebody paused", () => {
    const agents = { ...AGENTS, ami: agent("ami", "editor", "WORKING", "t-other"), ada: agent("ada", "editor_in_chief", "PAUSED") };
    expect(meetingNow(TASKS, agents, NOW)?.members).toEqual(["shinobu"]);
    // speaking at the meeting is a run too, and keeps her there
    const speaking = { ...AGENTS, shinobu: agent("shinobu", "writer", "THINKING", "t-writer") };
    expect(meetingNow(TASKS, speaking, NOW)?.members).toContain("shinobu");
  });

  it("over once every task is done: a little longer at the table, then nobody", () => {
    const done = (finishedAgo: number) =>
      Object.fromEntries(Object.values(TASKS).map((t) => [t.id, { ...t, state: "SUCCEEDED", since: ago(finishedAgo) }]));
    expect(meetingNow(done(10_000), AGENTS, NOW)?.chair).toBe("tifa");
    expect(meetingNow(done(MEETING_LINGER_MS + 1_000), AGENTS, NOW)).toBeNull();
    expect(meetingNow({ "t-other": TASKS["t-other"] }, AGENTS, NOW)).toBeNull();
  });
});

const walking = (cue: ReturnType<typeof meetingWalk>, releasedAt?: number): ActiveWalk => ({ cue, startedAt: 0, durationMs: 1, releasedAt });

function view(walks: Record<string, ActiveWalk | undefined>): MeetingView {
  return { walk: (id) => walks[id], seated: (id) => id !== "nodesk" };
}

describe("the meeting director (D-260)", () => {
  const members = ["tifa", "ada", "shinobu", "ami", "nodesk"].map((id) => ({ id }));

  it("sends the chair to the chair's seat and the others to the side chairs, cutting other walks short", () => {
    const director = new MeetingDirector();
    const step = director.tick({ workflowRunId: RUN, chair: "tifa", members: ["ada", "shinobu", "nodesk"] }, members, view({}));
    expect(step.cues).toEqual([
      { kind: "abort_walks", agentId: "tifa", seq: 0 },
      meetingWalk("tifa", 0),
      { kind: "abort_walks", agentId: "ada", seq: 0 },
      meetingWalk("ada", 1),
      { kind: "abort_walks", agentId: "shinobu", seq: 0 },
      meetingWalk("shinobu", 2),
    ]);
    expect(step.events.map((e) => e.text)).toEqual(["到會議室主持週會", "到會議室開週會", "到會議室開週會"]);
  });

  it("keeps everybody's chair for the whole meeting; a newcomer takes the first one free", () => {
    const director = new MeetingDirector();
    director.tick({ workflowRunId: RUN, chair: "tifa", members: ["ada", "shinobu"] }, members, view({}));
    // ada went back to other work; shinobu is on her way; ami joins
    const step = director.tick(
      { workflowRunId: RUN, chair: "tifa", members: ["shinobu", "ami"] },
      members,
      view({ tifa: walking(meetingWalk("tifa", 0)), ada: walking(meetingWalk("ada", 1)), shinobu: walking(meetingWalk("shinobu", 2)) }),
    );
    expect(step.release).toEqual(["ada"]);
    expect(step.cues).toEqual([{ kind: "abort_walks", agentId: "ami", seq: 0 }, meetingWalk("ami", 1)]);
  });

  it("when it is over, everybody at the table walks back, once", () => {
    const director = new MeetingDirector();
    const there = { tifa: walking(meetingWalk("tifa", 0)), ada: walking(meetingWalk("ada", 1)) };
    expect(director.tick(null, members, view(there)).release).toEqual(["tifa", "ada"]);
    const back = { tifa: walking(meetingWalk("tifa", 0), 10), ada: walking(meetingWalk("ada", 1), 10) };
    expect(director.tick(null, members, view(back))).toEqual({ cues: [], release: [], events: [] });
  });
});

describe("a seat at the meeting table on the floor (D-260)", () => {
  const members = Object.values(AGENTS).map((a) => ({ id: a.id, role: a.role, name: a.id, character: "character-male-a" as const, department: null, office_zone_key: null, business_unit: null }));
  const { seats } = assignSeats(members);

  it("is walked to, sat in, and stays sat in: a new run does not take her back to her desk", () => {
    const route = routeFor(meetingWalk("shinobu", 2), { members, seats })!;
    const target = meetingSeat(2).target;
    expect(typeof target === "object" && "spot" in target && route.path.at(-1)).toEqual(typeof target === "object" && "spot" in target && target.spot);
    expect([route.sitting, route.meeting, route.returnAfter]).toEqual([true, true, true]);

    const queue = new CueQueue();
    queue.apply([meetingWalk("shinobu", 2)], 0);
    queue.step(0, () => route.durationMs);
    queue.apply([{ kind: "abort_walks", agentId: "shinobu", seq: 9 }], 100);
    expect(queue.walk("shinobu")?.cue.target).toEqual({ meeting: 2 });
  });

  it("released, the walk back starts then — or as soon as she gets there", () => {
    const route = routeFor(meetingWalk("shinobu", 2), { members, seats })!;
    const oneWay = (route.length / WALK_SPEED) * 1000;
    const queue = new CueQueue();
    queue.apply([meetingWalk("shinobu", 2)], 0);
    queue.step(0, () => route.durationMs);
    const sitting = oneWay + 60_000;
    expect(courierState(route, sitting).phase).toBe("handover");

    expect(queue.release("shinobu", sitting, oneWay)).toBe(true);
    expect(queue.release("shinobu", sitting + 5, oneWay)).toBe(false);
    expect(queue.walk("shinobu")!.durationMs).toBe(Math.round(sitting + oneWay));
    expect(courierState(route, sitting + 1_000, sitting).phase).toBe("returning");
    expect(courierState(route, sitting + oneWay + 1, sitting).phase).toBe("done");

    // released on the way: she sits down, and gets up again at once
    expect(courierState(route, oneWay / 2, oneWay / 3).phase).toBe("going");
    expect(courierState(route, oneWay + 1, oneWay / 3).phase).toBe("returning");
    queue.step(sitting + oneWay + 1, () => null);
    expect(queue.walk("shinobu")).toBeUndefined();
  });
});
