// D-112: a person's name in the reader's language, not both.
import { describe, expect, it } from "vitest";

import { personName } from "./people";

describe("a name in one language", () => {
  it("Chinese in a Chinese interface, English in an English one", () => {
    expect(personName("Tifa｜蒂法")).toBe("蒂法"); // the back office is Chinese
    expect(personName("Ada Wong｜艾達・王", "zh-TW")).toBe("艾達・王");
    expect(personName("Ada Wong｜艾達・王", "en")).toBe("Ada Wong");
    expect(personName("Ada Wong | 艾達・王", "en")).toBe("Ada Wong");
  });

  it("a name with one part as it is; nothing as nothing", () => {
    expect(personName("Wren")).toBe("Wren");
    expect(personName(null)).toBe("");
  });
});

describe("a head photo (D-113)", () => {
  it("for the staff who have one; none for the rest", async () => {
    const { avatarPhoto } = await import("./people");
    expect(avatarPhoto("tifa")).toBe("/avatars/tifa.jpg");
    expect(avatarPhoto("default")).toBeNull();
    expect(avatarPhoto(null)).toBeNull();
  });
});

describe("the office's figure for someone with a photo (D-113)", () => {
  it("a woman's, the same one each time; the others as before", async () => {
    const { characterFor } = await import("@/office3d/assets/characters");
    for (const id of ["a1", "b2", "c3", "d4", "e5"]) {
      expect(characterFor(id, "rei")).toContain("female");
      expect(characterFor(id, "rei")).toBe(characterFor(id, "rei"));
    }
    expect(characterFor("a1", "character-male-b")).toBe("character-male-b");
  });
});
