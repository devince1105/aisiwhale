// The weekly meeting in the office (D-260): while the company's weekly meeting runs, the people
// in it sit at the meeting table. It is read from the meeting's own tasks — every member with a
// seat speaks (statement_<role>), the CEO chairs (chair_meeting), the minutes are applied
// (apply_minutes) — so it is state, not a cue: a page opened in the middle of the meeting shows it,
// and one opened after it does not invent one. Someone the company has put on other work goes back
// to it; when the meeting is over everybody walks back to their desks.
import { effectiveState, type AgentState, type TaskView } from "@/stores/realtime";

import { MEETING_SEATS } from "../scene/layout";
import { isMeetingWalk, type VisualCue, type WalkCue } from "./cues";
import type { ActiveWalk } from "./director";

export const CHAIR_TASK = "chair_meeting";
const APPLY_TASK = "apply_minutes";
const STATEMENT = /^statement_/;
const FINISHED = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);
const BUSY = new Set(["THINKING", "WORKING", "REVIEWING", "WAITING"]);

/** They stay at the table this long after the minutes are applied: the meeting closes, people
 * gather their things — and a meeting of a minute or two is still seen. */
export const MEETING_LINGER_MS = 45_000;
/** The longest anybody sits there waiting for a meeting that does not end. */
export const MEETING_MAX_MS = 30 * 60_000;

/** The speaking order, which is also who sits nearest the chair (the backend's MEETING_ROLES). */
const ORDER = ["editor_in_chief", "news_intelligence", "researcher", "analyst", "writer", "editor", "marketing", "finance", "strategist", "business"];

export const isMeetingTask = (name: string) => STATEMENT.test(name) || name === CHAIR_TASK || name === APPLY_TASK;

export interface MeetingNow {
  workflowRunId: string;
  /** Who chairs it, when they are there. */
  chair: string | null;
  /** Who else is at the table, in speaking order. */
  members: string[];
}

/**
 * The meeting in session at ``now``, if any: one whose tasks are not all finished, or whose last
 * finished less than MEETING_LINGER_MS ago. Its people are its speakers and its chair — the agent
 * that ran the task, or the one holding its role — less anybody on other work right now.
 */
export function meetingNow(tasks: Record<string, TaskView>, agents: Record<string, AgentState>, now: Date): MeetingNow | null {
  const runs = new Map<string, TaskView[]>();
  for (const task of Object.values(tasks)) {
    if (!task.workflow_run_id || !isMeetingTask(task.name)) continue;
    runs.set(task.workflow_run_id, [...(runs.get(task.workflow_run_id) ?? []), task]);
  }
  const live = [...runs.entries()].filter(
    ([, run]) => run.some((t) => !FINISHED.has(t.state)) || latest(run) > now.getTime() - MEETING_LINGER_MS,
  );
  if (!live.length) return null;
  // the latest, should two ever overlap
  const [workflowRunId, run] = live.sort(([, a], [, b]) => latest(b) - latest(a))[0];

  const holder = (task: TaskView): AgentState | undefined =>
    (task.agent_id ? agents[task.agent_id] : undefined) ?? Object.values(agents).find((a) => a.role === task.required_role);
  const elsewhere = (agent: AgentState): boolean => {
    const activity = agent.activity;
    if (!activity) return false;
    const state = effectiveState(activity, now);
    if (state === "PAUSED") return true;
    const task = activity.task_id ? tasks[activity.task_id] : undefined;
    return BUSY.has(state) && !(task && isMeetingTask(task.name));
  };

  const chairTask = run.find((t) => t.name === CHAIR_TASK);
  const chairAgent = chairTask ? holder(chairTask) : undefined;
  const chair = chairAgent && !elsewhere(chairAgent) ? chairAgent.id : null;
  const members: string[] = [];
  const speakers = run
    .filter((t) => STATEMENT.test(t.name))
    .sort((a, b) => rank(a.required_role) - rank(b.required_role) || a.required_role.localeCompare(b.required_role));
  for (const task of speakers) {
    const agent = holder(task);
    if (!agent || agent.id === chair || members.includes(agent.id) || elsewhere(agent)) continue;
    members.push(agent.id);
  }
  return { workflowRunId, chair, members };
}

const latest = (run: TaskView[]) => Math.max(...run.map((t) => Date.parse(t.since)));
const rank = (role: string) => (ORDER.includes(role) ? ORDER.indexOf(role) : ORDER.length);

export interface MeetingView {
  /** The walk this agent is on, if any. */
  walk(agentId: string): ActiveWalk | undefined;
  /** Whether the floor has a desk for it (somebody without one is not drawn). */
  seated(agentId: string): boolean;
}

export interface MeetingStep {
  cues: VisualCue[];
  /** Agents whose seat at the table is over: their walk back starts now. */
  release: string[];
  /** One line each for the office log. */
  events: { agentId: string; text: string }[];
}

/**
 * Sends the meeting's people to the table and back (D-260). ``tick`` is given the meeting in
 * session (``meetingNow``) and asks for walks: to the table for whoever should be there and is not
 * on the way, and back for whoever sits there and should not. A walk somewhere else (a coffee, a
 * hand-over) is cut short for the meeting. A chair, once taken, is kept for the whole meeting: the
 * chair's is the CEO's, and the side chairs go to the others in speaking order, a newcomer taking
 * the first one free.
 */
export class MeetingDirector {
  private run: string | null = null;
  private readonly chairs = new Map<string, number>();

  tick(meeting: MeetingNow | null, members: readonly { id: string }[], view: MeetingView): MeetingStep {
    const step: MeetingStep = { cues: [], release: [], events: [] };
    if (meeting && meeting.workflowRunId !== this.run) {
      this.run = meeting.workflowRunId;
      this.chairs.clear();
    }
    const wanted = new Set([...(meeting?.chair ? [meeting.chair] : []), ...(meeting?.members ?? [])]);
    const drawn = new Set(members.filter((m) => view.seated(m.id)).map((m) => m.id));

    // back to their desks first, so their chairs are free for anybody arriving now
    for (const id of drawn) {
      const walk = view.walk(id);
      if (wanted.has(id) || !isMeetingWalk(walk?.cue) || walk?.releasedAt !== undefined) continue;
      step.release.push(id);
      step.events.push({ agentId: id, text: "週會結束，回到座位" });
      this.chairs.delete(id);
    }
    for (const id of meeting ? [meeting.chair, ...meeting.members] : []) {
      if (!id || !drawn.has(id)) continue;
      // there, on the way, or still walking back from an earlier seat
      if (isMeetingWalk(view.walk(id)?.cue)) continue;
      const slot = this.chairFor(id, id === meeting?.chair);
      if (slot === null) continue; // a table this size: the rest stay at their desks
      step.cues.push({ kind: "abort_walks", agentId: id, seq: 0 }, meetingWalk(id, slot));
      step.events.push({ agentId: id, text: slot === 0 ? "到會議室主持週會" : "到會議室開週會" });
    }
    return step;
  }

  private chairFor(id: string, chairing: boolean): number | null {
    const kept = this.chairs.get(id);
    if (kept !== undefined) return kept;
    const taken = new Set(this.chairs.values());
    const slot = chairing ? (taken.has(0) ? null : 0) : (Array.from({ length: MEETING_SEATS - 1 }, (_, i) => i + 1).find((s) => !taken.has(s)) ?? null);
    if (slot !== null) this.chairs.set(id, slot);
    return slot;
  }
}

export function meetingWalk(agentId: string, slot: number): WalkCue {
  return { kind: "walk", agentId, target: { meeting: slot }, carry: "none", returnAfter: true, dwellMs: MEETING_MAX_MS, seq: 0 };
}
