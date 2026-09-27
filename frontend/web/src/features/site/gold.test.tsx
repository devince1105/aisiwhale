// @vitest-environment jsdom
// D-070: the 黃金 tab's reference price and chart.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchGold, type PublicGold } from "./api";
import { ArticleList } from "./ArticleList";

const charted: Record<string, unknown>[] = [];
vi.mock("./StockChart", () => ({
  StockChart: (props: Record<string, unknown>) => {
    charted.push(props);
    return <div data-testid="stock-chart" />;
  },
}));

const GOLD: PublicGold = {
  as_of: "2026-09-25",
  usd_per_oz: 4805.12,
  change: 55.12,
  change_pct: 1.1604,
  twd_per_gram: 4906.4,
  source: "Tiingo",
  bars: [
    { d: "2026-09-24", o: 4700, h: 4760, l: 4690, c: 4750, v: 0 },
    { d: "2026-09-25", o: 4750, h: 4810, l: 4700, c: 4805.12, v: 0 },
  ],
};

afterEach(() => {
  cleanup();
  charted.length = 0;
});

describe("黃金's reference price and chart (D-070)", () => {
  it("shows the price, its change, a gram in NT$, and the chart without volume", () => {
    render(<ArticleList articles={[]} lang="zh-TW" section="gold" gold={GOLD} />);
    const board = within(screen.getByTestId("gold-board"));
    expect(board.getByText("4,805.12").className).toContain("text-rise");
    expect(board.getByText(/\+55\.12 \(1\.16%\)/)).toBeTruthy();
    expect(board.getByTestId("gold-twd").textContent).toBe("約新台幣／公克 4,906");
    expect(board.getByText(/並非臺灣銀行黃金存摺牌價/)).toBeTruthy();
    expect(board.getByRole("link", { name: /臺灣銀行黃金牌價/ }).getAttribute("href")).toBe(
      "https://rate.bot.com.tw/gold?Lang=zh-TW",
    );
    expect(charted[0]).toMatchObject({ market: "gold", source: "Tiingo", volume: false });
    expect((charted[0].bars as unknown[]).length).toBe(2);
  });

  it("a fall reads as one; without a rate, no NT$; an older page, no board", () => {
    render(
      <ArticleList articles={[]} lang="zh-TW" section="gold" gold={{ ...GOLD, change: -20, change_pct: -0.41, twd_per_gram: null }} />,
    );
    expect(screen.getByText(/−20\.00 \(0\.41%\)/).className).toContain("text-fall");
    expect(screen.queryByTestId("gold-twd")).toBeNull();
    cleanup();
    render(<ArticleList articles={[]} lang="zh-TW" section="gold" gold={GOLD} page={2} pages={2} />);
    expect(screen.queryByTestId("gold-board")).toBeNull();
  });

  it("is asked of the API, and a failure is no board rather than no page", async () => {
    const answered = vi.fn<typeof fetch>(() =>
      Promise.resolve(new Response(JSON.stringify(GOLD), { headers: { "Content-Type": "application/json" } })),
    );
    expect((await fetchGold("zh-TW", { baseUrl: "http://api", fetch: answered }))?.usd_per_oz).toBe(4805.12);
    expect((answered.mock.calls[0]![0] as Request).url).toBe("http://api/api/public/gold?lang=zh-TW");
    const down = vi.fn<typeof fetch>(() => Promise.reject(new Error("down")));
    expect(await fetchGold("zh-TW", { baseUrl: "http://api", fetch: down })).toBeNull();
  });
});
