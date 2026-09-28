// @vitest-environment jsdom
// D-091: 新聞情緒 — the week's headlines about a stock, their tone counted, never a forecast.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PublicArticleSummary, PublicSentiment } from "./api";
import { ArticleList } from "./ArticleList";
import { arcs, NewsSentiment } from "./NewsSentiment";

vi.mock("next/navigation", () => ({ usePathname: () => "/news/zh-TW", useSearchParams: () => new URLSearchParams() }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const TSMC: PublicSentiment = {
  key: "tw:2330",
  name: "台積電",
  positive: 6,
  neutral: 3,
  negative: 1,
  total: 10,
  heat: 1.24,
  headlines: [
    {
      title: "台積電A16預計量產",
      url: "https://tw.stock.yahoo.com/n/1",
      source: "Yahoo股市",
      published_at: "2026-09-28T01:00:00Z",
      sentiment: "positive",
      reason: "量產時程明確",
    },
    {
      title: "台積電遭調降評等",
      url: "https://tw.stock.yahoo.com/n/3",
      source: "Yahoo股市",
      published_at: "2026-09-27T01:00:00Z",
      sentiment: "negative",
      reason: null,
    },
  ],
};

describe("新聞情緒 (D-091)", () => {
  it("the ring's arcs follow the counts, and a tone with none has no arc", () => {
    expect(arcs({ positive: 6, neutral: 3, negative: 1 })).toEqual([
      ["positive", 60, 0],
      ["neutral", 30, 60],
      ["negative", 10, 90],
    ]);
    expect(arcs({ positive: 2, neutral: 0, negative: 2 }).map(([tone]) => tone)).toEqual(["positive", "negative"]);
    expect(arcs({ positive: 0, neutral: 0, negative: 0 })).toEqual([]);
  });

  it("counts the tones, says how busy the week was, lists the headlines and what it is not", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(Response.json(TSMC))));
    render(<NewsSentiment symbol="2330" lang="zh-TW" />);
    const section = within(await screen.findByTestId("news-sentiment"));
    expect(section.getAllByText("60%")).toHaveLength(2); // the ring's centre and the legend: the positive share
    expect(section.getByText("本週 10 則・為平常的 1.2 倍")).toBeTruthy();
    const first = section.getByRole("link", { name: /台積電A16預計量產/ });
    expect(first.getAttribute("href")).toBe("https://tw.stock.yahoo.com/n/1");
    expect(first.textContent).toContain("正面");
    expect(section.getByText(/量產時程明確/)).toBeTruthy();
    expect(section.getByText(/不是股價預測，也不構成投資建議/)).toBeTruthy();
  });

  it("off the strip, or nothing read yet: no section", async () => {
    const answered = vi.fn(() => Promise.resolve(Response.json(null)));
    vi.stubGlobal("fetch", answered);
    render(<NewsSentiment symbol="6488" lang="zh-TW" />);
    await vi.waitFor(() => expect(answered).toHaveBeenCalled());
    expect(screen.queryByTestId("news-sentiment")).toBeNull();
  });

  it("the sidebar's table: the most covered, how many, the positive share — each to its chart", () => {
    const story = { article_id: "a", lang: "zh-TW", slug: "s", path: "/p", title: "t", summary: null, published_at: "2026-09-27T01:00:00Z", access: "free", stocks: [] } as PublicArticleSummary;
    render(
      <ArticleList
        articles={[story]}
        lang="zh-TW"
        calendar={{ month: "2026-09", days: [] }}
        sentiment={[TSMC, { ...TSMC, key: "us:NVDA", name: "輝達", positive: 1, neutral: 1, negative: 2, total: 4 }]}
      />,
    );
    const rows = within(screen.getByTestId("sentiment-table")).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.textContent)).toEqual(["台積電1060%", "輝達425%"]);
    expect(within(rows[0]).getByRole("link").getAttribute("href")).toBe("/news/zh-TW/watchlist?s=tw%3A2330");
  });
});
