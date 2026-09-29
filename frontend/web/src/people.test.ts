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
