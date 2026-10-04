// D-115: the photographed members of the office dressed as themselves.
import { describe, expect, it } from "vitest";

import { CHARACTERS, characterFor } from "../assets/characters";
import { OUTFITS, type Paint } from "../assets/outfits";
import { cellOf, hiddenBy, ruleFor, SPARE_CELLS } from "./dress";

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

describe("what an outfit leaves off (D-183)", () => {
  it("no figure on female-f carries its backpack: the bag behind the back, not the back", () => {
    const onF = Object.entries(OUTFITS).filter(([, outfit]) => outfit.model === "character-female-f");
    expect(onF.map(([key]) => key).sort()).toEqual(["demo_rinka", "demo_ririka", "mari", "tifa"]);
    for (const [key] of onF) {
      const { model, hide = [] } = OUTFITS[key];
      expect(model).toBe("character-female-f");
      expect(hiddenBy(hide, "2:5", "torso", -0.233)).toBe(true); // the bag's back
      expect(hiddenBy(hide, "3:7", "torso", -0.213)).toBe(true); // its flap
      expect(hiddenBy(hide, "2:5", "torso", -0.153)).toBe(true); // its face against her back
      expect(hiddenBy(hide, "3:3", "torso", -0.153)).toBe(false); // her clothes there
      expect(hiddenBy(hide, "2:5", "torso", 0.096)).toBe(false); // the straps in front
      expect(hiddenBy(hide, "2:5", "arm-left", -0.2)).toBe(false); // nothing but the torso
    }
  });

  it("everybody else wears what the figure has", () => {
    const others = Object.entries(OUTFITS).filter(([, outfit]) => outfit.model !== "character-female-f");
    expect(others.filter(([, outfit]) => outfit.hide?.length)).toEqual([]);
  });
});
