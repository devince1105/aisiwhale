// D-136: idle moments — only the idle, a couple at a time, a few an hour, never IT-less server walks.
import { describe, expect, it } from "vitest";

import { LifeDirector, MAX_AWAY, type LifeMember } from "./life";

const members: LifeMember[] = [
  { id: "a", name: "雪拉", role: "news_intelligence" },
  { id: "b", name: "綾波零", role: "researcher" },
  { id: "c", name: "真希波", role: "analyst" },
  { id: "d", name: "春麗", role: "marketing" },
  { id: "e", name: "蒂法", role: "ceo" },
];

/** A random sequence that repeats, so a test sees the same moments every time. */
function seeded(seed = 7) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) / 2147483647);
}

const allIdle = { idle: () => true, walking: () => false, away: 0 };
const MIN = 60_000;

describe("idle moments (D-136)", () => {
  it("nobody gets up the moment the office opens; somebody does within minutes", () => {
    const life = new LifeDirector(seeded());
    expect(life.tick(0, members, allIdle).cues).toEqual([]);
    const later = life.tick(5 * MIN, members, allIdle);
    expect(later.cues.length).toBeGreaterThan(0);
    expect(later.cues.length).toBeLessThanOrEqual(MAX_AWAY + members.length); // stretches stay at the desk
    for (const cue of later.cues) {
      expect(cue.carry).toBe("none");
      expect(cue.returnAfter).toBe(true);
      expect(cue.dwellMs).toBeGreaterThan(0);
    }
  });

  it("only the idle, and not while walking; never more than a couple away at once", () => {
    const life = new LifeDirector(seeded());
    life.tick(0, members, allIdle);
    const busy = life.tick(5 * MIN, members, { idle: () => false, walking: () => false, away: 0 });
    expect(busy.cues).toEqual([]);
    const crowded = life.tick(6 * MIN, members, { idle: () => true, walking: () => false, away: MAX_AWAY });
    expect(crowded.cues.every((c) => "life" in c.target && c.target.life === "stretch")).toBe(true);
  });

  it("a few times an hour each, not every tick", () => {
    const life = new LifeDirector(seeded());
    let count = 0;
    for (let t = 0; t <= 60 * MIN; t += 2000) count += life.tick(t, members, allIdle).cues.length;
    expect(count).toBeGreaterThanOrEqual(members.length); // each at least once
    expect(count).toBeLessThanOrEqual(members.length * 8); // and not constantly
  });

  it("the server room is IT's; a chat is with somebody idle, by name", () => {
    const life = new LifeDirector(seeded(3));
    const kinds = new Set<string>();
    for (let t = 0; t <= 300 * MIN; t += 2000) {
      const { cues, events } = life.tick(t, members, allIdle);
      for (const cue of cues) if ("life" in cue.target) kinds.add(cue.target.life);
      for (const cue of cues) if ("life" in cue.target && cue.target.peer) expect(cue.target.peer).not.toBe("e");
      for (const e of events) if (e.kind === "chat") expect(e.text).toMatch(/^到.+的座位聊兩句$/);
    }
    expect(kinds.has("server")).toBe(false);
    expect(kinds.has("coffee")).toBe(true);
  });
});
