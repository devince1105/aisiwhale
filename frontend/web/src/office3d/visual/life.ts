// Idle moments (D-136): what the office's people do between tasks, so an office with nothing to
// do does not look switched off. A coffee in the pantry, a word at a colleague's desk, a stretch
// behind the chair, IT's look round the server room.
//
// It is decoration and says so: only somebody the company records as idle gets up, never more
// than a couple at once, a few times an hour each; their tag keeps saying 閒置, with an icon for
// what they are doing; and the moment a run starts for them, the director's abort_walks takes
// them back to their desk — state beats animation, as for every walk. Nothing here is sent
// anywhere or recorded by the company: it is the page's own, and the office log marks it as such.
import type { LifeKind, WalkCue } from "./cues";

export interface LifeMember {
  id: string;
  name: string;
  role: string;
}

export interface LifeView {
  /** The company records this agent as idle (no run, nothing waiting). */
  idle(id: string): boolean;
  /** Already walking, or with a walk queued (work or an idle moment). */
  walking(id: string): boolean;
  /** How many are away on an idle moment right now. */
  away: number;
}

export interface LifeEvent {
  agentId: string;
  kind: LifeKind;
  text: string;
}

/** Never more than this many away from their desks on an idle moment at once. */
export const MAX_AWAY = 2;
const MINUTE = 60_000;
/** The first moment comes soon after the office opens, then a few an hour for each person. */
const FIRST = [20_000, 4 * MINUTE] as const;
const BETWEEN = [8 * MINUTE, 20 * MINUTE] as const;
const RETRY = 30_000;
const DWELL: Record<LifeKind, readonly [number, number]> = {
  out: [120_000, 240_000],
  lounge: [40_000, 70_000],
  coffee: [25_000, 45_000],
  chat: [15_000, 30_000],
  stretch: [6_000, 10_000],
  server: [20_000, 40_000],
};
/** IT (the engineer's desk) looks after the server room; everybody drinks coffee. */
const IT_ROLE = "engineer";
const CEO_ROLE = "ceo";

const between = (random: () => number, [lo, hi]: readonly [number, number]) => lo + random() * (hi - lo);

function pick(random: () => number, weights: readonly (readonly [LifeKind, number])[]): LifeKind {
  const total = weights.reduce((sum, [, w]) => sum + w, 0);
  let roll = random() * total;
  for (const [kind, w] of weights) {
    roll -= w;
    if (roll < 0) return kind;
  }
  return weights[weights.length - 1][0];
}

export class LifeDirector {
  private readonly due = new Map<string, number>();

  constructor(private readonly random: () => number = Math.random) {}

  /** The idle moments that start now: their walks, and a line each for the office log. */
  tick(now: number, members: readonly LifeMember[], view: LifeView): { cues: WalkCue[]; events: LifeEvent[] } {
    const cues: WalkCue[] = [];
    const events: LifeEvent[] = [];
    let away = view.away;
    for (const member of members) {
      const due = this.due.get(member.id);
      if (due === undefined) {
        this.due.set(member.id, now + between(this.random, FIRST));
        continue;
      }
      if (now < due) continue;
      if (!view.idle(member.id) || view.walking(member.id) || away >= MAX_AWAY) {
        this.due.set(member.id, now + RETRY);
        continue;
      }
      const it = member.role === IT_ROLE;
      let kind = pick(
        this.random,
        it
          ? [["server", 0.35], ["coffee", 0.2], ["stretch", 0.15], ["chat", 0.1], ["lounge", 0.1], ["out", 0.1]]
          : [["coffee", 0.3], ["chat", 0.25], ["stretch", 0.2], ["lounge", 0.13], ["out", 0.12]],
      );
      let peer: LifeMember | undefined;
      if (kind === "chat") {
        // a word with a colleague on the floor, not a visit to the CEO's office
        const free = members.filter(
          (m) => m.id !== member.id && m.role !== CEO_ROLE && view.idle(m.id) && !view.walking(m.id),
        );
        peer = free.length ? free[Math.floor(this.random() * free.length)] : undefined;
        if (!peer) kind = "stretch";
      }
      cues.push({
        kind: "walk",
        agentId: member.id,
        target: {
          life: kind,
          peer: peer?.id,
          slot: kind === "coffee" ? Math.floor(this.random() * 3) : kind === "lounge" ? Math.floor(this.random() * 5) : undefined,
        },
        carry: "none",
        returnAfter: true,
        dwellMs: Math.round(between(this.random, DWELL[kind])),
        seq: 0,
      });
      events.push({ agentId: member.id, kind, text: lifeText(kind, peer?.name, this.random()) });
      away += kind === "stretch" ? 0 : 1; // a stretch stays at the desk
      this.due.set(member.id, now + between(this.random, BETWEEN));
    }
    return { cues, events };
  }
}

export const LIFE_ICON: Record<LifeKind, string> = { coffee: "☕", chat: "💬", stretch: "🙆", server: "🔧", lounge: "🛋️", out: "🚶" };

/** ``roll`` (0–1) picks between the restroom and a short errand for a step out. */
export function lifeText(kind: LifeKind, peer?: string, roll = 0): string {
  switch (kind) {
    case "coffee":
      return "去茶水間倒杯咖啡";
    case "chat":
      return peer ? `到${peer}的座位聊兩句` : "找同事聊兩句";
    case "stretch":
      return "起身伸展一下";
    case "server":
      return "去機房巡一下";
    case "lounge":
      return "到等候區沙發坐一下";
    case "out":
      return roll < 0.7 ? "去洗手間" : "臨時外出一下";
  }
}
