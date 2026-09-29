import { Color } from "three";
import { describe, expect, it } from "vitest";

import { SERVER_LIGHT_ROWS, serverLightSpots } from "./furniture";
import { allSeats, obstacles, SERVER_RACKS, SERVER_ROOM } from "./layout";
import { beaconColor, healthOf, ledColor } from "./ServerLights";

const hex = (c: Color) => `#${c.getHexString()}`;

describe("the server room (D-121)", () => {
  it("stands behind the R&D desk, the innermost of the front row, its door toward it", () => {
    const rnd = allSeats().find((seat) => seat.role === "engineer")!;
    const front = allSeats().filter((seat) => seat.desk[1] === rnd.desk[1] && seat.zone !== "ceo");
    expect(Math.min(...front.map((seat) => seat.desk[0]))).toBe(rnd.desk[0]);
    expect(SERVER_ROOM.minZ).toBeGreaterThan(rnd.chair[1]);
    expect(Math.abs(SERVER_ROOM.doorX - rnd.desk[0])).toBeLessThan(0.6);
  });

  it("its racks and every light are inside it", () => {
    const { leds, beacons } = serverLightSpots();
    expect(leds).toHaveLength(SERVER_RACKS.xs.length * 2 * 2 * SERVER_LIGHT_ROWS);
    for (const [x, , z] of [...leds, ...beacons]) {
      expect(x).toBeGreaterThan(SERVER_ROOM.minX);
      expect(x).toBeLessThan(SERVER_ROOM.maxX);
      expect(z).toBeGreaterThan(SERVER_ROOM.minZ);
      expect(z).toBeLessThan(SERVER_ROOM.maxZ);
    }
    expect(obstacles().map((o) => o.name)).toContain("server glass (side)");
  });

  it("the lights say how the system is: green when live, amber while connecting, red when lost", () => {
    const c = new Color();
    expect(healthOf("live")).toBe("ok");
    expect(healthOf("reconnecting")).toBe("starting");
    expect(healthOf("offline")).toBe("down");
    const seen = (health: "ok" | "starting" | "down", index: number, busy = false) =>
      new Set(Array.from({ length: 200 }, (_, i) => hex(ledColor(health, index, i * 0.05, busy, c))));
    // a status light (not the first of its column): green or briefly dark, never another colour
    const status = seen("ok", 1);
    expect(status).toContain("#3ee07a");
    expect([...status].every((h) => h === "#3ee07a" || h === "#1d2320")).toBe(true);
    // the activity light is dark while nothing happens, and flickers blue when events come in
    expect(seen("ok", 0)).toEqual(new Set(["#1d2320"]));
    expect(seen("ok", 0, true)).toContain("#4aa8ff");
    expect(seen("starting", 1)).toContain("#ffb020");
    expect(seen("down", 1)).toContain("#ff3b3b");
    expect(hex(beaconColor("ok", 0, c))).not.toBe("#1d2320");
  });
});
