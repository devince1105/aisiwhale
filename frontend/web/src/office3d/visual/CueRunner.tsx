// Feeds new events to the director and runs the cues (T-407). One CueDirector per scene: it
// subscribes to the store, turns events it has not seen into cues (the first snapshot and a
// company switch make none), and a frame hook steps the queue. Walks get their route and length
// from the floor plan; the courier (T-408) walks them, the screens and lamps show the effects.
import { useFrame } from "@react-three/fiber";
import { createContext, useContext, useEffect, useMemo, useRef, type ReactNode } from "react";

import { effectiveState, realtimeStore, serverNow, type RealtimeStoreState } from "@/stores/realtime";

import type { Roster } from "../agents/roster";
import { useRoster } from "../agents/roster";
import { APPROVAL_DESK, doorOf, loungeSeat, pantrySpot, seatsForRole, serverSpot, walkPath, type Seat, type Vec2 } from "../scene/layout";
import type { WalkCue } from "./cues";
import { cuesFor, CueQueue } from "./director";
import { LifeDirector } from "./life";
import { ROLE_LABEL } from "./mapping";
import { officeLog } from "./officeLog";

/** Walking speed (m/s) and how long the courier stays at the other desk. */
export const WALK_SPEED = 1.4;
export const HANDOVER_MS = 1200;

type Store = { getState(): RealtimeStoreState; subscribe(listener: (state: RealtimeStoreState) => void): () => void };

export class CueDirector {
  readonly queue = new CueQueue();
  private companyId: string | null = null;
  private lastSeq = 0;
  private readonly unsubscribe: () => void;

  constructor(
    store: Store = realtimeStore,
    private readonly clock: () => number = () => performance.now(),
  ) {
    this.onState(store.getState());
    this.unsubscribe = store.subscribe((state) => this.onState(state));
  }

  private onState(state: RealtimeStoreState): void {
    const company = state.company;
    if (!company) {
      this.companyId = null;
      this.queue.clear();
      return;
    }
    if (company.companyId !== this.companyId) {
      // a snapshot is history, not news: nothing to animate
      this.companyId = company.companyId;
      this.lastSeq = company.lastSeq;
      this.queue.clear();
      return;
    }
    if (company.lastSeq <= this.lastSeq) return;
    const now = serverNow(state);
    for (const event of company.recentEvents) {
      if (event.seq === null || event.seq <= this.lastSeq) continue;
      const cues = cuesFor(event, company.agents, now);
      this.queue.apply(cues, this.clock());
      logWork(event, cues, company.agents);
    }
    this.lastSeq = company.lastSeq;
  }

  dispose(): void {
    this.unsubscribe();
  }
}

/** The work, told short for the office log (D-136): a run started or finished, work carried. */
function logWork(
  event: { event_type: string; occurred_at: string; agent_id: string | null; payload: unknown },
  cues: readonly { kind: string }[],
  agents: Record<string, { display_name: string }>,
): void {
  const agentId = event.agent_id;
  if (!agentId || !agents[agentId]) return;
  const p = (event.payload ?? {}) as Record<string, unknown>;
  const at = Date.parse(event.occurred_at);
  const add = (text: string) => officeLog.getState().add({ at, agentId, text, kind: "work" });
  if (event.event_type === "AGENT_RUN_STARTED") add(`開始工作${typeof p.task_name === "string" ? `：${p.task_name}` : ""}`);
  if (event.event_type === "AGENT_RUN_COMPLETED") add("完成工作");
  for (const cue of cues) {
    if (cue.kind !== "walk") continue;
    const target = (cue as WalkCue).target;
    if ("place" in target) add("把稿子送到接待櫃檯，等您核准");
    else if ("role" in target) add(`把工作交給${ROLE_LABEL[target.role] ?? target.role}`);
    else if ("door" in target) add("把工作送到隔壁部門");
  }
}

export interface Route {
  path: Vec2[];
  /** One way, metres. */
  length: number;
  durationMs: number;
  /** What the courier faces while handing over (the colleague's chair, the approval desk). */
  lookAt: Vec2;
  returnAfter: boolean;
  /** How long it stays at the far end (D-136: a coffee lasts longer than a hand-over). */
  dwellMs: number;
  /** Whether a document is carried there (work) or nothing (an idle moment). */
  carrying: boolean;
  /** Whether it sits down at the far end (a lounge seat, D-136) rather than standing. */
  sitting?: boolean;
}

/** Where an idle moment goes (D-136), and what it faces there. */
function lifeRoute(cue: WalkCue, from: Seat, roster: Pick<Roster, "members" | "seats">): { path: Vec2[]; lookAt: Vec2 } | null {
  if (!("life" in cue.target)) return null;
  const { life, peer, slot } = cue.target;
  if (life === "stretch") {
    // up behind the chair, a step back, and sit again
    const back = from.turn ? -1 : 1;
    return { path: [from.chair, [from.chair[0], from.chair[1] + back * 0.6]], lookAt: from.desk };
  }
  if (life === "chat") {
    const seat = peer ? roster.seats.get(peer) : undefined;
    if (!seat || seat.key === from.key) return null;
    return { path: walkPath(from, seat), lookAt: seat.chair };
  }
  const place = life === "coffee" ? pantrySpot(slot) : life === "lounge" ? loungeSeat(slot) : serverSpot();
  return { path: walkPath(from, place.target), lookAt: place.lookAt };
}

/** Where a walk goes and how long it takes (there and back, with the hand-over). */
export function routeFor(cue: WalkCue, roster: Pick<Roster, "members" | "seats">): Route | null {
  const from = roster.seats.get(cue.agentId);
  if (!from) return null;
  const dwellMs = cue.dwellMs ?? HANDOVER_MS;
  const carrying = cue.carry === "document";
  if ("life" in cue.target) {
    const life = lifeRoute(cue, from, roster);
    if (!life) return null;
    const length = pathLength(life.path);
    const walking = (length / WALK_SPEED) * 1000 * (cue.returnAfter ? 2 : 1);
    return {
      path: life.path,
      length,
      durationMs: Math.round(walking + dwellMs),
      lookAt: life.lookAt,
      returnAfter: cue.returnAfter,
      dwellMs,
      carrying,
      sitting: cue.target.life === "lounge",
    };
  }
  let to: Seat | "approval" | { door: string };
  if ("place" in cue.target) to = "approval";
  else if ("door" in cue.target) to = { door: cue.target.door };
  else {
    const role = cue.target.role;
    const colleague = roster.members.find((m) => m.role === role && m.id !== cue.agentId && roster.seats.has(m.id));
    const seat = colleague ? roster.seats.get(colleague.id) : seatsForRole(role, 1)[0];
    if (!seat || seat.key === from.key) return null;
    to = seat;
  }
  const path = walkPath(from, to);
  const length = pathLength(path);
  const walking = (length / WALK_SPEED) * 1000 * (cue.returnAfter ? 2 : 1);
  const lookAt =
    to === "approval"
      ? APPROVAL_DESK.center
      : "door" in to
        ? doorOf(to.door).point // it hands the work over at the room's door and comes back
        : to.chair;
  return { path, length, durationMs: Math.round(walking + dwellMs), lookAt, returnAfter: cue.returnAfter, dwellMs, carrying };
}

function pathLength(path: readonly Vec2[]): number {
  let length = 0;
  for (let i = 1; i < path.length; i++) length += Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]);
  return length;
}

const CueContext = createContext<CueDirector | null>(null);

declare global {
  interface Window {
    /** Who is walking right now (agent ids), for browser tests; not an API. */
    __autoraOfficeCues?: { walking: string[]; walks: number };
  }
}

/** How often the idle moments are looked at (ms). */
const LIFE_EVERY = 2000;

function Runner({ director }: { director: CueDirector }) {
  const roster = useRoster();
  const latest = useRef(roster);
  latest.current = roster;
  const probe = useRef("");
  const life = useMemo(() => new LifeDirector(), []);
  const lastLife = useRef(0);
  useFrame(() => {
    const now = performance.now();
    if (now - lastLife.current >= LIFE_EVERY) {
      lastLife.current = now;
      // idle moments (D-136): only the idle get up, a couple at a time
      const state = realtimeStore.getState();
      const agents = state.company?.agents ?? {};
      const at = serverNow(state);
      const members = latest.current.members.filter((m) => latest.current.seats.has(m.id));
      const walkingNow = (id: string) => Boolean(director.queue.walk(id)) || director.queue.queued(id).length > 0;
      const away = members.filter((m) => {
        const target = director.queue.walk(m.id)?.cue.target;
        return target && "life" in target && target.life !== "stretch";
      }).length;
      const { cues, events } = life.tick(now, members, {
        idle: (id) => {
          const activity = agents[id]?.activity;
          return !activity || effectiveState(activity, at) === "IDLE";
        },
        walking: walkingNow,
        away,
      });
      if (cues.length) director.queue.apply(cues, now);
      for (const e of events) officeLog.getState().add({ at: Date.now(), agentId: e.agentId, text: e.text, kind: "life" });
    }
    director.queue.step(now, (cue) => routeFor(cue, latest.current)?.durationMs ?? null);
    const walking = latest.current.members.filter((m) => director.queue.walk(m.id)).map((m) => m.id);
    const key = walking.join(",");
    if (key !== probe.current && typeof window !== "undefined") {
      const walks = (window.__autoraOfficeCues?.walks ?? 0) + walking.filter((id) => !probe.current.includes(id)).length;
      window.__autoraOfficeCues = { walking, walks };
      probe.current = key;
    }
  }, -1);
  return null;
}

export function CueProvider({ children, director: given }: { children: ReactNode; director?: CueDirector }) {
  const director = useMemo(() => given ?? new CueDirector(), [given]);
  useEffect(() => () => void (given ? undefined : director.dispose()), [given, director]);
  return (
    <CueContext.Provider value={director}>
      <Runner director={director} />
      {children}
    </CueContext.Provider>
  );
}

/** The scene's cues, or null outside a CueProvider (tests of single components). */
export function useCues(): CueDirector | null {
  return useContext(CueContext);
}
