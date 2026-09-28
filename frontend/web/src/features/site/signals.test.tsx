// @vitest-environment jsdom
// D-096: 分析師評等與技術指標 — what analysts say, counted, and the chart's figures; no call of
// the site's own.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PublicRatings } from "./api";
import { halfRing, StockSignals } from "./StockSignals";
import { rsi, technicals } from "./technicals";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const bar = (c: number, i: number) => ({ d: `2026-01-${String((i % 28) + 1).padStart(2, "0")}`, o: c, h: c + 1, l: c - 1, c, v: 1 });

const NVDA: PublicRatings = {
  symbol: "NVDA",
  via: null,
  source: "Finnhub",
  latest: { period: "2026-09-01", strong_buy: 24, buy: 41, hold: 3, sell: 1, strong_sell: 0, total: 69 },
  previous: { period: "2026-08-01", strong_buy: 23, buy: 41, hold: 3, sell: 1, strong_sell: 0, total: 68 },
};

describe("技術指標 (D-096)", () => {
  it("RSI: all rises 100, all falls 0, a flat line 50; too few closes none", () => {
    expect(rsi(Array.from({ length: 20 }, (_, i) => i))).toBe(100);
    expect(rsi(Array.from({ length: 20 }, (_, i) => 20 - i))).toBe(0);
    expect(rsi(Array(20).fill(5))).toBe(50);
    expect(rsi([1, 2, 3])).toBeNull();
    // up 1, down 1, alternately: about as much gained as lost (the last move, down, weighs most)
    const even = rsi(Array.from({ length: 41 }, (_, i) => 10 + (i % 2)))!;
    expect(even).toBeGreaterThan(45);
    expect(even).toBeLessThan(50);
  });

  it("averages only with their days; the 52-week range only with a year", () => {
    const month = technicals(Array.from({ length: 30 }, (_, i) => bar(100 + i, i)))!;
    expect(month.averages.map((a) => a.days)).toEqual([20]);
    expect(month.averages[0].value).toBeCloseTo(119.5); // 110..129
    expect(month.averages[0].gap).toBeCloseTo(129 / 119.5 - 1);
    expect(month.range).toBeNull();
    const year = technicals(Array.from({ length: 300 }, (_, i) => bar(100 + (i % 50), i)))!;
    expect(year.averages.map((a) => a.days)).toEqual([20, 60, 200]);
    expect(year.range).toEqual({ low: 99, high: 150, at: (149 - 99) / 51 });
    expect(technicals([bar(1, 0)])).toBeNull();
  });
});

describe("分析師評等 (D-096)", () => {
  it("the half ring: parts sized by the counts, none for a kind nobody gave, gaps between", () => {
    const parts = halfRing(NVDA.latest);
    expect(parts.map(([kind]) => kind)).toEqual(["sell", "hold", "buy", "strong_buy"]);
    expect(parts[0][1]).toBe(0);
    expect(parts[parts.length - 1][2]).toBeCloseTo(180);
    const [, from, to] = parts[2];
    expect(to - from).toBeCloseTo((41 / 69) * (180 - 6));
    expect(halfRing({ ...NVDA.latest, strong_buy: 0, buy: 0, hold: 0, sell: 0 })).toEqual([]);
  });

  it("counts, the change on last month, the source — and no verdict", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(Response.json(NVDA))));
    render(<StockSignals symbol="NVDA" lang="zh-TW" figures={technicals(Array.from({ length: 30 }, (_, i) => bar(100 + i, i)))} />);
    const card = within(await screen.findByTestId("analyst-ratings"));
    expect(card.getByText("69")).toBeTruthy();
    expect(card.getByText("2026 年 9 月")).toBeTruthy();
    expect(card.getByText("強力買入").parentElement!.textContent).toBe("強力買入24+1");
    expect(card.getByText(/資料來源：Finnhub/)).toBeTruthy();
    const technical = screen.getByTestId("technicals");
    expect(technical.textContent).toContain("20 日均線");
    expect(technical.textContent).toContain("股價高於 7.9%");
    expect(technical.textContent).not.toContain("投資建議"); // in the footer, once (D-097)
    // the site's own call nowhere: no 建議買入, no 買入 as a verdict of its own
    expect(screen.getByTestId("stock-signals").textContent).not.toMatch(/建議(買|賣)|看多|看空|評等：/);
  });

  it("TSMC through its ADR, said so; a stock with neither shows nothing", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(Response.json({ ...NVDA, symbol: "2330", via: "TSM" }))));
    render(<StockSignals symbol="2330" lang="zh-TW" figures={null} />);
    expect((await screen.findByTestId("analyst-ratings")).textContent).toContain("以美國存託憑證（TSM）的評等");
    cleanup();
    const answered = vi.fn(() => Promise.resolve(Response.json(null)));
    vi.stubGlobal("fetch", answered);
    render(<StockSignals symbol="6488" lang="zh-TW" figures={null} />);
    await vi.waitFor(() => expect(answered).toHaveBeenCalled());
    expect(screen.queryByTestId("stock-signals")).toBeNull();
  });
});
