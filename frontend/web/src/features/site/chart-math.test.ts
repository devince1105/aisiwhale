// The stock chart's arithmetic (D-059): weeks and months from days, and moving averages.
import { describe, expect, it } from "vitest";

import { group, movingAverage, type Bar } from "./chartMath";

const bar = (d: string, o: number, h: number, l: number, c: number, v: number): Bar => ({ d, o, h, l, c, v });

const DAYS = [
  bar("2026-09-17", 10, 12, 9, 11, 100), // Thursday
  bar("2026-09-18", 11, 13, 10, 12, 200), // Friday
  bar("2026-09-21", 12, 15, 11, 14, 300), // Monday: a new week
  bar("2026-09-22", 14, 14, 8, 9, 400),
  bar("2026-10-01", 9, 10, 7, 8, 500), // a new month
];

describe("grouping bars", () => {
  it("keeps days as they are", () => {
    expect(group(DAYS, "day")).toEqual(DAYS);
  });

  it("makes a week of first open, highest high, lowest low, last close and summed volume", () => {
    const weeks = group(DAYS, "week");
    expect(weeks.map((w) => w.d)).toEqual(["2026-09-18", "2026-09-22", "2026-10-01"]);
    expect(weeks[0]).toEqual(bar("2026-09-18", 10, 13, 9, 12, 300));
    expect(weeks[1]).toEqual(bar("2026-09-22", 12, 15, 8, 9, 700));
  });

  it("makes months, dated by their last trading day", () => {
    expect(group(DAYS, "month")).toEqual([
      bar("2026-09-22", 10, 15, 8, 9, 1000),
      bar("2026-10-01", 9, 10, 7, 8, 500),
    ]);
  });
});

describe("moving averages", () => {
  it("average the last n closes, and say nothing before there are n", () => {
    expect(movingAverage(DAYS, 2)).toEqual([null, 11.5, 13, 11.5, 8.5]);
    expect(movingAverage(DAYS, 250).every((v) => v === null)).toBe(true);
  });
});
