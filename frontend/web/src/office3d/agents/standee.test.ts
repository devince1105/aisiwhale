// D-118: the Q-version standees — upright, facing the camera, in front of the chair.
import { Group, Quaternion, Vector3 } from "three";
import { describe, expect, it } from "vitest";

import { figureBackPhoto, figurePhoto } from "@/people";

import { aspectOf, CARD_FORWARD, faceCamera, seesBack, SIDEWAYS, standeeLift, stepFor, viewFor } from "./Standee";

describe("a standee", () => {
  it("turns to the camera about the vertical only, whatever way its desk faces", () => {
    const seat = new Group();
    seat.rotation.y = 1.2; // the desk's own facing
    const card = new Group();
    seat.add(card);
    seat.updateMatrixWorld(true);
    const looking = new Vector3(-1, -1.15, -1).normalize(); // the isometric camera
    faceCamera(card, looking);
    seat.updateMatrixWorld(true);
    const normal = new Vector3(0, 0, 1).applyQuaternion(card.getWorldQuaternion(new Quaternion()));
    expect(normal.y).toBeCloseTo(0); // upright: never leans back
    expect(normal.x).toBeCloseTo(Math.SQRT1_2);
    expect(normal.z).toBeCloseTo(Math.SQRT1_2); // facing the viewer
  });

  it("stands a step toward the camera, in front of its chair's back", () => {
    const seat = new Group();
    seat.rotation.y = -0.7;
    const card = new Group();
    seat.add(card);
    seat.updateMatrixWorld(true);
    faceCamera(card, new Vector3(-1, -1.15, -1).normalize());
    seat.updateMatrixWorld(true);
    const moved = card.getWorldPosition(new Vector3());
    expect(moved.y).toBeCloseTo(0);
    expect(moved.length()).toBeCloseTo(CARD_FORWARD);
    expect(moved.x).toBeGreaterThan(0);
    expect(moved.z).toBeGreaterThan(0);
  });

  it("sinks behind the desk when seated, bobs when walking or typing", () => {
    expect(standeeLift("stand", 3)).toBe(0);
    expect(standeeLift("sit_idle", 3)).toBeLessThan(0);
    expect(standeeLift("walk", 0.1)).toBeGreaterThan(0);
    expect(standeeLift("sit_type", 0.1)).not.toBe(standeeLift("sit_idle", 0.1));
  });

  it("for the staff with a picture, front and back", () => {
    expect(figurePhoto("chunli")).toBe("/figures/chunli.webp");
    expect(figureBackPhoto("chunli")).toBe("/figures-back/chunli.webp");
    expect(figurePhoto("default")).toBeNull();
    expect(figureBackPhoto("default")).toBeNull();
  });

  it("shows her back when the camera is behind her, her front otherwise (D-123)", () => {
    const iso = new Vector3(-1, -1.15, -1).normalize(); // the camera at the front right
    const atDesk = new Group();
    atDesk.rotation.y = Math.PI; // facing her monitors (-z): the camera is at her back
    atDesk.updateMatrixWorld(true);
    expect(seesBack(atDesk, iso, false)).toBe(true);
    const ceo = new Group(); // a turned desk: she faces the room's front, and the camera
    ceo.updateMatrixWorld(true);
    expect(seesBack(ceo, iso, true)).toBe(false);
  });

  it("does not flicker when seen edge-on", () => {
    const side = new Group();
    side.rotation.y = Math.PI / 2; // facing +x
    side.updateMatrixWorld(true);
    const edgeOn = new Vector3(0, -1, -1).normalize(); // looking along -z: she is side-on
    expect(seesBack(side, edgeOn, false)).toBe(false);
    expect(seesBack(side, edgeOn, true)).toBe(true);
  });

  it("sits in a seated picture when seated, the right side to the camera (D-124)", () => {
    const all = { stand: "s", standBack: "sb", sit: "t", sitBack: "tb" };
    expect(viewFor(all, { seated: true, back: false })).toBe("sit");
    expect(viewFor(all, { seated: true, back: true })).toBe("sitBack");
    expect(viewFor(all, { seated: false, back: true })).toBe("standBack");
    expect(viewFor(all, { seated: false, back: false })).toBe("stand");
    // what is missing is stood in for
    expect(viewFor({ stand: "s" }, { seated: true, back: true })).toBe("stand");
    expect(viewFor({ stand: "s", sit: "t" }, { seated: true, back: true })).toBe("sit");
    // in the chair, whichever side is seen; standing and seen from the front, a step out of it
    expect(stepFor("sit")).toBe(0);
    expect(stepFor("sitBack")).toBe(0);
    expect(stepFor("stand")).toBe(CARD_FORWARD);
  });

  it("a seated picture has her feet on the floor, below the chair's seat", () => {
    expect(standeeLift("sit_idle", 1, true)).toBeLessThan(-0.15);
    expect(standeeLift("sit_idle", 1, true)).toBeGreaterThan(-0.25);
    expect(standeeLift("stand", 1, true)).toBe(0);
  });

  it("walking across the screen, the side view: its two frames in turn (D-125)", () => {
    const all = { stand: "s", standBack: "sb", sit: "t", sitBack: "tb", walk: ["w1", "w2"] as const };
    expect(viewFor(all, { seated: false, back: true, walking: true, across: 0.7, stride: 0 })).toBe("walk1");
    expect(viewFor(all, { seated: false, back: true, walking: true, across: -0.7, stride: 7 })).toBe("walk2");
    expect(viewFor(all, { seated: false, back: true, walking: true, across: 0.2 })).toBe("standBack");
    expect(viewFor({ stand: "s" }, { seated: false, back: false, walking: true, across: 0.7 })).toBe("stand");
    expect(stepFor("walk1")).toBe(0);
  });

  it("standing seen from the side, the side picture that faces her way (D-126)", () => {
    const all = { stand: "s", standBack: "sb", sit: "t", walk: ["w1", "w2"] as const, standSide: ["l", "r"] as const };
    expect(viewFor(all, { seated: false, back: false, across: 0.7 })).toBe("sideRight");
    expect(viewFor(all, { seated: false, back: true, across: -0.7 })).toBe("sideLeft");
    expect(viewFor(all, { seated: false, back: false, across: 0.3 })).toBe("stand");
    // seated, the seat's own pictures; walking, the walk
    expect(viewFor(all, { seated: true, back: false, across: 0.7 })).toBe("sit");
    expect(viewFor(all, { seated: false, back: false, walking: true, across: 0.7 })).toBe("walk1");
    // no walking pictures: walking across, she is shown standing side-on
    expect(viewFor({ stand: "s", standSide: ["l", "r"] }, { seated: false, back: false, walking: true, across: -0.7 })).toBe("sideLeft");
    expect(stepFor("sideLeft")).toBe(0);
  });

  it("under the isometric camera a walk along a corridor is seen from the side, facing the way she goes", () => {
    const iso = new Vector3(-1, -1.15, -1).normalize(); // from the front right
    const walker = new Group();
    for (const [heading, right] of [
      [Math.PI / 2, true], // toward +x: up and to the right on screen
      [-Math.PI / 2, false], // toward -x
      [0, false], // toward +z: down and to the left
      [Math.PI, true], // toward -z: up and to the right
    ] as const) {
      walker.rotation.y = heading;
      walker.updateMatrixWorld(true);
      const aspect = aspectOf(walker, iso)!;
      expect(Math.abs(aspect.across)).toBeGreaterThanOrEqual(SIDEWAYS);
      expect(aspect.across > 0).toBe(right);
    }
  });

  it("thinking at her desk, hand on chin, seen from the front (D-127)", () => {
    const all = { stand: "s", sit: "t", sitBack: "tb", thinkSit: "k" };
    expect(viewFor(all, { seated: true, back: false, thinking: true })).toBe("thinkSit");
    expect(viewFor(all, { seated: true, back: true, thinking: true })).toBe("sitBack");
    expect(viewFor(all, { seated: true, back: false })).toBe("sit");
    expect(stepFor("thinkSit")).toBe(0);
  });
});
