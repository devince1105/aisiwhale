// The back rooms' doors are a way in: no post of the glass front stands in one.
import { describe, expect, it } from "vitest";

import { GLASS_FRONTS, glassFrontPosts } from "./furniture";
import { DOORS } from "./layout";

describe("the back rooms' glass fronts", () => {
  it("leave every doorway clear: no post stands in a door or crowds its frame", () => {
    for (const front of GLASS_FRONTS)
      for (const x of glassFrontPosts(front))
        for (const door of DOORS) expect(Math.abs(x - door.x), `post at ${x} by ${door.name}`).toBeGreaterThanOrEqual(door.width / 2 + 0.15);
  });

  it("still post both ends of each front, and between the doors", () => {
    for (const front of GLASS_FRONTS) {
      const posts = glassFrontPosts(front);
      expect(posts[0]).toBeCloseTo(front[0]);
      expect(posts[posts.length - 1]).toBeCloseTo(front[1]);
      expect(posts.length).toBeGreaterThanOrEqual(4);
    }
  });
});
