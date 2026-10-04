// D-115: the photographed members of the office dressed as themselves.
import { describe, expect, it } from "vitest";

import { CHARACTERS, characterFor } from "../assets/characters";
import { LEFT_OFF, OUTFITS, type Paint } from "../assets/outfits";
import { cellOf, hiddenBy, ruleFor, SPARE_CELLS, type Corner } from "./dress";

describe("an outfit", () => {
  it("each is made on a real figure, with room in the palette for all its colours", () => {
    for (const [key, outfit] of Object.entries(OUTFITS)) {
      expect(CHARACTERS, key).toContain(outfit.model);
      expect(outfit.paints.length, key).toBeLessThanOrEqual(SPARE_CELLS.length);
      for (const paint of outfit.paints) {
        for (const cell of paint.cells) expect(cell, key).toMatch(/^[0-3]:(1[0-5]|[0-9])$/);
        expect(paint.color, key).toMatch(/^#[0-9a-f]{6}$/);
      }
    }
    expect(characterFor("any-id", "tifa")).toBe(OUTFITS.tifa.model);
    expect(characterFor("any-id", "default")).not.toBe(undefined);
  });

  it("the spare cells are the palette's black ones, never a colour a figure uses", () => {
    // rows 2 and 3 hold every colour; row 1 starts with the pink pair
    expect(SPARE_CELLS.every(([row, col]) => row === 0 || (row === 1 && col >= 2))).toBe(true);
  });
});

describe("which rule repaints a vertex", () => {
  const paints: Paint[] = [
    { cells: ["3:1"], parts: ["head"], notFace: true, color: "#a9cdee" },
    { cells: ["2:11"], parts: ["body"], bones: ["arm-left", "arm-right"], color: "#cbb6ee" },
    { cells: ["2:11"], parts: ["body"], color: "#2a2a34" },
  ];

  it("by its cell, its mesh and its bone, the first that fits", () => {
    expect(ruleFor(paints, "head", "3:1", null, [0, 0.7, 0.1])).toBe(0); // hair
    expect(ruleFor(paints, "body", "3:1", "torso", [0, 0.3, 0])).toBe(-1); // same cell, other mesh
    expect(ruleFor(paints, "body", "2:11", "arm-left", [0, 0.3, 0])).toBe(1);
    expect(ruleFor(paints, "body", "2:11", "leg-left", [0, 0.1, 0])).toBe(2);
  });

  it("leaves the face's features alone when they share the hair's cell", () => {
    expect(ruleFor(paints, "head", "3:1", null, [0.05, 0.46, 0.16])).toBe(-1); // an eye
    expect(ruleFor(paints, "head", "3:1", null, [0.13, 0.62, 0.168])).toBe(0); // the fringe
  });

  it("a UV's cell: 16 columns, 4 rows, row 0 at the top", () => {
    expect(cellOf(0.07, 0.8)).toBe("3:1");
    expect(cellOf(0.99, 0.99)).toBe("3:15");
    expect(cellOf(1, 1)).toBe("3:15");
  });
});

describe("what a figure leaves off (D-183 – D-186)", () => {
  it("female-f's backpack, whoever wears it: the bag sticking out of her back, not her back", () => {
    const hide = LEFT_OFF["character-female-f"]!;
    const at = (z: number, cell = "2:5", bone: string | null = "torso"): Corner => ({ cell, bone, z });
    expect(hiddenBy(hide, [at(-0.213), at(-0.213), at(-0.213)])).toBe(true); // the bag's back
    expect(hiddenBy(hide, [at(-0.213), at(-0.133), at(-0.133)])).toBe(true); // its sides, to her back
    expect(hiddenBy(hide, [at(-0.233, "3:7"), at(-0.233, "3:7"), at(-0.213, "3:7")])).toBe(true); // its buckle
    expect(hiddenBy(hide, [at(-0.133), at(-0.133), at(-0.133)])).toBe(false); // her back itself
    expect(hiddenBy(hide, [at(-0.133), at(0.096), at(0.096)])).toBe(false); // her top, round to the front
    expect(hiddenBy(hide, [at(-0.153, "3:3"), at(-0.213), at(-0.213)])).toBe(false); // her belt
    expect(hiddenBy(hide, [at(-0.213, "2:5", "arm-left"), at(-0.213), at(-0.213)])).toBe(false); // the torso only
    // everybody on it: Tifa, Mari, and the demo's 月城凜雪 and 工藤莉花
    const onF = Object.entries(OUTFITS).filter(([, outfit]) => outfit.model === "character-female-f");
    expect(onF.map(([key]) => key).sort()).toEqual(["demo_rinka", "demo_ririka", "mari", "tifa"]);
  });

  it("female-a's swords, whoever wears it: blade and hilt on the arms, not the arms", () => {
    const hide = LEFT_OFF["character-female-a"]!;
    const at = (cell: string, bone: string | null = "arm-left"): Corner => ({ cell, bone, z: 0 });
    expect(hiddenBy(hide, [at("2:11"), at("2:11"), at("3:7")])).toBe(true); // blade to hilt
    expect(hiddenBy(hide, [at("2:11", "arm-right"), at("2:11", "arm-right"), at("2:11", "arm-right")])).toBe(true);
    expect(hiddenBy(hide, [at("2:11"), at("3:13"), at("3:13")])).toBe(false); // where it meets her hand
    expect(hiddenBy(hide, [at("2:15"), at("2:15"), at("2:15")])).toBe(false); // her sleeve
    expect(hiddenBy(hide, [at("2:11", "leg-left"), at("2:11", "leg-left"), at("2:11", "leg-left")])).toBe(false); // her legs' blue
  });

  it("no other figure leaves anything off", () => {
    expect(Object.keys(LEFT_OFF).sort()).toEqual(["character-female-a", "character-female-f"]);
  });
});
