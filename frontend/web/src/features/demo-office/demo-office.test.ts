// The public site's demo office (D-155): the script is valid stream, made up through and through,
// and the player plays it the way the socket would — then cleans up after itself.
import { parseEvent } from "@autora/event-schema";
import { afterEach, describe, expect, it, vi } from "vitest";

import { avatarPhoto } from "@/people";
import { currentSection } from "@/features/site/SectionNav";
import { words } from "@/features/site/i18n";
import { createRealtimeStore } from "@/stores/realtime";

import { createDemoPlayer, demoSnapshot, stamp, type Script } from "./player";
import scriptJson from "./script.json";

const SCRIPT = scriptJson as Script;
const ROLES = ["ceo", "editor_in_chief", "news_intelligence", "researcher", "analyst", "writer", "editor", "marketing"];

describe("the demo script", () => {
  it("is one company's stream: every event, stamped, is one the schema accepts, in time order", () => {
    const at = new Date("2026-10-02T00:00:00Z");
    SCRIPT.events.forEach((event, i) => {
      const parsed = parseEvent(stamp(event, SCRIPT, i + 1, at));
      expect(parsed.ok, `${event.event_type} #${i}: ${parsed.ok ? "" : parsed.error}`).toBe(true);
      if (i) expect(event.t).toBeGreaterThanOrEqual(SCRIPT.events[i - 1].t);
    });
    expect(SCRIPT.events.length).toBeGreaterThan(100);
  });

  it("is a loop of a few minutes", () => {
    expect(SCRIPT.loop_ms).toBeGreaterThanOrEqual(150_000);
    expect(SCRIPT.loop_ms).toBeLessThanOrEqual(260_000);
    expect(SCRIPT.events.at(-1)!.t).toBeLessThan(SCRIPT.loop_ms);
  });

  it("has the newsroom's eight desks, and only its own people act", () => {
    expect(SCRIPT.agents.map((a) => a.role).sort()).toEqual([...ROLES].sort());
    const ids = new Set(SCRIPT.agents.map((a) => a.id));
    for (const event of SCRIPT.events) if (event.agent_id) expect(ids.has(event.agent_id)).toBe(true);
  });

  it("is made up: none of the company's staff, no photos, no real reporting", () => {
    const text = JSON.stringify(SCRIPT).toLowerCase();
    for (const real of ["tifa", "ada wong", "ayanami", "makinami", "shinobu", "mizuno", "chun-li", "sayla", "蒂法", "綾波", "春麗"]) {
      expect(text).not.toContain(real.toLowerCase());
    }
    for (const agent of SCRIPT.agents) {
      expect(agent.avatar_key.startsWith("demo_")).toBe(true);
      expect(avatarPhoto(agent.avatar_key)).toBeNull();
    }
    // no link, no money, no real company id
    expect(text).not.toMatch(/https?:|www\.|nt\$|twd|usd\s*\d|01a0d2c7/);
    // what people see of the work is demo text: task names are 示範報導 or the day's fixed jobs
    const shown = SCRIPT.events.filter((e) => e.event_type === "TASK_CREATED").map((e) => String(e.payload.display_name));
    for (const name of shown) expect(name).toMatch(/示範報導 [A-Z]|^(規劃今日方針|市場晨報|安排今日版面)$/);
  });
});

describe("the player", () => {
  afterEach(() => vi.useRealTimers());

  function play() {
    vi.useFakeTimers({ now: new Date("2026-10-02T00:00:00Z") });
    const store = createRealtimeStore();
    const player = createDemoPlayer({ store: store.getState(), script: SCRIPT });
    return { store, player };
  }

  it("starts with everybody at their desk, as a snapshot would", () => {
    const { store, player } = play();
    player.start();
    const company = store.getState().company!;
    expect(company.companyId).toBe(SCRIPT.company_id);
    expect(Object.keys(company.agents)).toHaveLength(8);
    expect(store.getState().connection.status).toBe("live");
    player.stop();
  });

  it("plays the events at their times, stamped as happening now", () => {
    const { store, player } = play();
    player.start();
    vi.advanceTimersByTime(60_000);
    const company = store.getState().company!;
    expect(company.lastSeq).toBe(SCRIPT.events.filter((e) => e.t <= 60_000).length);
    const last = company.recentEvents.at(-1)!;
    expect(Math.abs(new Date(last.occurred_at).getTime() - Date.now())).toBeLessThan(5_000);
    expect(store.getState().dropped).toBe(0);
    player.stop();
  });

  it("starts over at the end of the loop", () => {
    const { store, player } = play();
    player.start();
    vi.advanceTimersByTime(SCRIPT.loop_ms + 1_000);
    expect(store.getState().company!.lastSeq).toBeLessThan(SCRIPT.events.length);
    player.stop();
  });

  it("plays nothing while paused, and picks up where it was", () => {
    const { store, player } = play();
    player.start();
    vi.advanceTimersByTime(30_000);
    const seen = store.getState().company!.lastSeq;
    player.pause();
    vi.advanceTimersByTime(60_000);
    expect(store.getState().company!.lastSeq).toBe(seen);
    player.resume();
    vi.advanceTimersByTime(30_000);
    expect(store.getState().company!.lastSeq).toBe(SCRIPT.events.filter((e) => e.t <= 60_000).length);
    player.stop();
  });

  it("leaves the store empty and no timer behind when it stops", () => {
    const { store, player } = play();
    player.start();
    vi.advanceTimersByTime(10_000);
    player.stop();
    expect(store.getState().company).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("an idle snapshot is a valid one", () => {
    const store = createRealtimeStore();
    expect(() => store.getState().hydrate(demoSnapshot(SCRIPT, new Date()))).not.toThrow();
  });
});

describe("the site's way to it", () => {
  it("is a tab of its own, in both languages", () => {
    expect(currentSection("zh-TW", "/news/zh-TW/office", null)).toBe("office");
    expect(currentSection("en", "/news/en/office", null)).toBe("office");
    expect(words("zh-TW").office.link).toBe("AI 編輯部");
    expect(words("en").office.badge).toBe("Demo");
  });
});
