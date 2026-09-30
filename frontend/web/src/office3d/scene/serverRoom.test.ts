import { Color } from "three";
import { describe, expect, it } from "vitest";

import { SERVER_LIGHT_ROWS, serverLightSpots } from "./furniture";
import { DECOR, ENTRANCE, GLASS_WALLS, obstacles, ROOM, SERVER_RACKS, SERVER_ROOM, SMALL_MEETING, TALK_ROOM } from "./layout";
import { beaconColor, healthOf, ledColor } from "./ServerLights";

const hex = (c: Color) => `#${c.getHexString()}`;

describe("the server room (D-121)", () => {
  it("stands by the entrance where the reception was, a small meeting room beside it (D-132)", () => {
    expect(SERVER_ROOM.maxX).toBe(ROOM.maxX);
    expect(ENTRANCE.minZ - SERVER_ROOM.maxZ).toBeLessThan(0.3); // just inside the way in
    expect(TALK_ROOM.maxX).toBe(SERVER_ROOM.minX);
    expect(SMALL_MEETING.maxX).toBe(TALK_ROOM.minX);
    // six racks, in two rows facing each other across the aisle its door opens onto
    expect(SERVER_RACKS.rows.length * SERVER_RACKS.zs.length).toBe(6);
    const [a, b] = SERVER_RACKS.rows.map((row) => row.x).sort();
    expect(SERVER_ROOM.doorX).toBeGreaterThan(a + SERVER_RACKS.depth / 2);
    expect(SERVER_ROOM.doorX).toBeLessThan(b - SERVER_RACKS.depth / 2);
    // the doors open onto the back walkway, inside the company, never onto the waiting area
    for (const room of ["server", "small meeting", "talk"]) {
      expect(GLASS_WALLS.find((wall) => wall.name === `${room} back`)?.door, room).toBeDefined();
      expect(GLASS_WALLS.find((wall) => wall.name === `${room} front`)?.door, room).toBeUndefined();
    }
    expect(GLASS_WALLS.find((wall) => wall.name === "server back")!.door!.at).toBe(SERVER_ROOM.doorX);
    // two small rooms of one size, each a table for two; the rest of the row is the server room's
    expect(TALK_ROOM.maxX - TALK_ROOM.minX).toBeCloseTo(SMALL_MEETING.maxX - SMALL_MEETING.minX);
    expect(SERVER_ROOM.maxX - SERVER_ROOM.minX).toBeGreaterThan(TALK_ROOM.maxX - TALK_ROOM.minX);
    expect(DECOR.filter((item) => item.kind === "small_meeting")).toHaveLength(2);
  });

  it("its racks and every light are inside it", () => {
    const { leds, beacons } = serverLightSpots();
    expect(leds).toHaveLength(SERVER_RACKS.rows.length * SERVER_RACKS.zs.length * 2 * 2 * SERVER_LIGHT_ROWS);
    for (const [x, , z] of [...leds, ...beacons]) {
      expect(x).toBeGreaterThan(SERVER_ROOM.minX);
      expect(x).toBeLessThan(SERVER_ROOM.maxX);
      expect(z).toBeGreaterThan(SERVER_ROOM.minZ);
      expect(z).toBeLessThan(SERVER_ROOM.maxZ);
    }
    expect(obstacles().map((o) => o.name)).toContain("server back (before door)");
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
