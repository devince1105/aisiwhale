import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { CHARACTER_DIR, CHARACTERS, characterFor, OWN_FIGURE_HEIGHT, OWN_FIGURES, ownFigure, POSE_CLIP, REQUIRED_CLIPS } from "./characters";

interface Gltf {
  meshes?: { primitives: { attributes: { POSITION: number } }[] }[];
  accessors?: { max?: number[]; min?: number[] }[];
  animations?: { name: string }[];
  skins?: unknown[];
  images?: { uri?: string; bufferView?: number }[];
}

function gltf(character: string): Gltf {
  const bytes = readFileSync(join(process.cwd(), "public", CHARACTER_DIR, `${character}.glb`));
  expect(bytes.readUInt32LE(0)).toBe(0x46546c67); // "glTF"
  return JSON.parse(bytes.subarray(20, 20 + bytes.readUInt32LE(12)).toString("utf8")) as Gltf;
}

describe("character assets (Kenney Mini Characters, CC0)", () => {
  it("every character is a skinned GLB with every clip the office plays", () => {
    for (const character of CHARACTERS) {
      const json = gltf(character);
      expect(json.skins?.length, character).toBeGreaterThan(0);
      const clips = new Set(json.animations?.map((a) => a.name));
      for (const clip of REQUIRED_CLIPS) expect(clips.has(clip), `${character} has ${clip}`).toBe(true);
      // the shared texture next to it
      for (const image of json.images ?? []) {
        expect(() => readFileSync(join(process.cwd(), "public", CHARACTER_DIR, decodeURIComponent(image.uri!)))).not.toThrow();
      }
    }
  });

  it("every own figure (D-196) is a skinned GLB on the pack's bones, with every clip", () => {
    for (const figure of OWN_FIGURES) {
      const json = gltf(figure) as Gltf & { nodes: { name?: string }[] };
      expect(json.skins?.length, figure).toBe(1);
      const nodes = new Set(json.nodes.map((n) => n.name));
      for (const bone of ["root", "torso", "head", "arm-left", "arm-right", "leg-left", "leg-right"]) {
        expect(nodes.has(bone), `${figure} has ${bone}`).toBe(true);
      }
      const clips = new Set(json.animations?.map((a) => a.name));
      for (const clip of REQUIRED_CLIPS) expect(clips.has(clip), `${figure} has ${clip}`).toBe(true);
      // built to Tifa's proportions, so one height scales them all to the standees' (D-201)
      const top = Math.max(...(json.meshes ?? []).flatMap((m) => m.primitives.map((p) => json.accessors![p.attributes.POSITION].max![1])));
      expect(top, figure).toBeCloseTo(OWN_FIGURE_HEIGHT, 2);
      // the baked atlas (D-197) travels inside the GLB: nothing beside it to fetch
      for (const image of json.images ?? []) {
        expect(image.uri, figure).toBeUndefined();
        expect(image.bufferView, figure).toBeTypeOf("number");
      }
    }
    expect(ownFigure("tifa")).toBe("tifa");
    expect(ownFigure("ada")).toBe("ada");
    expect(ownFigure("rei")).toBe("rei");
    expect(ownFigure("sayla")).toBeNull();
    expect(ownFigure(null)).toBeNull();
  });

  it("every pose has a clip; the clips are the pack's", () => {
    expect(Object.keys(POSE_CLIP).sort()).toEqual(["sit_idle", "sit_read", "sit_think", "sit_type", "slump", "stand", "walk"]);
    expect(REQUIRED_CLIPS).toEqual(["emote-no", "emote-yes", "idle", "interact-right", "pick-up", "sit", "walk"]);
  });

  it("each agent always wears the same character; avatar_key can choose one", () => {
    const ids = Array.from({ length: 60 }, (_, i) => `01a0b4${String(i).padStart(2, "0")}-0000-7000-8000-00000000000${i % 10}`);
    const picked = ids.map((id) => characterFor(id));
    expect(ids.map((id) => characterFor(id))).toEqual(picked); // stable
    expect(new Set(picked).size).toBeGreaterThan(6); // varied
    expect(characterFor(ids[0], "character-female-c")).toBe("character-female-c");
    expect(characterFor(ids[0], "default")).toBe(picked[0]);
  });
});
