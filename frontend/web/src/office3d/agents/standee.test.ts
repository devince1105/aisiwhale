// D-118: the Q-version standees — upright, facing the camera, in front of the chair.
import { Group, Quaternion, Vector3 } from "three";
import { describe, expect, it } from "vitest";

import { figureBackPhoto, figurePhoto } from "@/people";

import { CARD_FORWARD, faceCamera, seesBack, standeeLift } from "./Standee";

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
});
