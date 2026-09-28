// @vitest-environment jsdom
// D-084: the front page's calendar — a reader pages back through the stories by date.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchCalendar, type PublicArticleSummary } from "./api";
import { ArticleCalendar, monthGrid } from "./ArticleCalendar";
import { ArticleList } from "./ArticleList";
import { listHref } from "./links";

vi.mock("next/navigation", () => ({ usePathname: () => "/news/zh-TW", useSearchParams: () => new URLSearchParams() }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const DAYS = [
  { day: "2026-09-24", count: 2 },
  { day: "2026-09-25", count: 1 },
];

describe("the calendar (D-084)", () => {
  it("lays a month out a week a row, Sunday first", () => {
    const september = monthGrid("2026-09"); // 2026-09-01 is a Tuesday
    expect(september.slice(0, 3)).toEqual([null, null, "2026-09-01"]);
    expect(september.filter(Boolean)).toHaveLength(30);
    expect(monthGrid("2026-02").filter(Boolean)).toHaveLength(28);
  });

  it("an address for a day keeps the tab, and a page after it", () => {
    expect(listHref("zh-TW", "tw", 1, "2026-09-24")).toBe("/news/zh-TW?section=tw&date=2026-09-24");
    expect(listHref("zh-TW", null, 2, "2026-09-24")).toBe("/news/zh-TW?date=2026-09-24&page=2");
    expect(listHref("zh-TW", null)).toBe("/news/zh-TW");
  });

  it("is closed until asked for; a day with stories is a link with a dot, one without is not", () => {
    vi.useFakeTimers({ now: new Date("2026-09-28T04:00:00Z"), shouldAdvanceTime: true });
    render(<ArticleCalendar lang="zh-TW" section="tw" selected={null} initialMonth="2026-09" initialDays={DAYS} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /依日期瀏覽/ }));
    const panel = within(screen.getByRole("dialog", { name: "報導日曆" }));
    expect(panel.getByText("2026年9月")).toBeTruthy();
    const links = panel.getAllByRole("gridcell").filter((cell) => cell.tagName === "A");
    expect(links.map((a) => [a.textContent, a.getAttribute("href"), a.getAttribute("aria-label")])).toEqual([
      ["24", "/news/zh-TW?section=tw&date=2026-09-24", "9月24日，2 篇報導"],
      ["25", "/news/zh-TW?section=tw&date=2026-09-25", "9月25日，1 篇報導"],
    ]);
    expect(panel.getByText("23").tagName).toBe("SPAN"); // no stories: not a link
    // this month is the latest: no months from the future
    expect((panel.getByRole("button", { name: "下個月" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("another month is asked of the API; the day shown is filled, and can be cleared", async () => {
    vi.useFakeTimers({ now: new Date("2026-09-28T04:00:00Z"), shouldAdvanceTime: true });
    const asked: string[] = [];
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      asked.push(url);
      return Response.json([{ day: "2026-08-14", count: 3 }]);
    });
    render(<ArticleCalendar lang="zh-TW" section={null} selected="2026-09-24" initialMonth="2026-09" initialDays={DAYS} />);
    fireEvent.click(screen.getByRole("button", { name: /2026年9月24日/ }));
    const panel = within(screen.getByRole("dialog"));
    expect(panel.getByRole("gridcell", { name: /9月24日/ }).getAttribute("aria-current")).toBe("date");
    expect(panel.getByRole("link", { name: "清除日期" }).getAttribute("href")).toBe("/news/zh-TW");
    fireEvent.click(panel.getByRole("button", { name: "上個月" }));
    await waitFor(() => expect(panel.getByRole("gridcell", { name: /8月14日，3 篇/ })).toBeTruthy());
    expect(asked[0]).toContain("/api/public/articles/calendar?lang=zh-TW&month=2026-08");
  });

  it("the list says when a day has none, and pages within the day", () => {
    const summary = { article_id: "a", lang: "zh-TW", slug: "s", path: "/p", title: "t", summary: null, published_at: "2026-09-24T01:00:00Z", access: "free", stocks: [] } as PublicArticleSummary;
    render(<ArticleList articles={[]} lang="zh-TW" day="2026-09-23" calendar={{ month: "2026-09", days: DAYS }} />);
    expect(screen.getByText("這一天沒有這個分類的報導。")).toBeTruthy();
    cleanup();
    render(<ArticleList articles={[summary]} lang="zh-TW" day="2026-09-24" page={1} pages={2} calendar={{ month: "2026-09", days: DAYS }} />);
    expect(screen.getByRole("link", { name: "下一頁" }).getAttribute("href")).toBe("/news/zh-TW?date=2026-09-24&page=2");
  });

  it("the calendar's days are asked of the API; a failure is no marks", async () => {
    const answered = vi.fn<typeof fetch>(() =>
      Promise.resolve(new Response(JSON.stringify(DAYS), { headers: { "Content-Type": "application/json" } })),
    );
    expect(await fetchCalendar("zh-TW", "2026-09", { baseUrl: "http://api", fetch: answered, section: ["holdings", "figures"] })).toHaveLength(2);
    expect((answered.mock.calls[0]![0] as Request).url).toBe(
      "http://api/api/public/articles/calendar?lang=zh-TW&month=2026-09&section=holdings&section=figures",
    );
    const down = vi.fn<typeof fetch>(() => Promise.reject(new Error("down")));
    expect(await fetchCalendar("zh-TW", "2026-09", { baseUrl: "http://api", fetch: down })).toEqual([]);
  });
});

describe("the front page's sidebar (D-085, D-086)", () => {
  const story = (n: number, section: string): PublicArticleSummary =>
    ({ article_id: `a${n}`, lang: "zh-TW", slug: `s${n}`, path: `/news/zh-TW/articles/s${n}`, title: `第 ${n} 篇`, summary: null, published_at: "2026-09-27T01:00:00Z", access: "free", section, stocks: [] }) as PublicArticleSummary;

  it("the calendar without a title or a hint; 熱門文章 numbered, each to its story", () => {
    render(
      <ArticleList
        articles={[story(1, "tw")]}
        lang="zh-TW"
        calendar={{ month: "2026-09", days: DAYS }}
        popular={[story(7, "us"), story(3, "gold")]}
      />,
    );
    const side = within(screen.getByTestId("front-sidebar"));
    expect(side.queryByRole("heading", { name: "報導日曆" })).toBeNull();
    expect(side.queryByText(/有圓點的日子/)).toBeNull();
    expect(side.getByRole("heading", { name: "熱門文章" })).toBeTruthy();
    const popular = within(side.getByTestId("popular"));
    expect(popular.getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "1第 7 篇美股・2026年9月27日",
      "2第 3 篇黃金・2026年9月27日",
    ]);
    expect(popular.getByRole("link", { name: "第 7 篇" }).getAttribute("href")).toBe("/news/zh-TW/articles/s7");
  });

  it("市場概況: the strip's main figures, each to its chart on the watchlist page (D-087)", () => {
    const quote = (key: string, value: number, change_pct: number | null, change: number | null = null) =>
      ({ key, value, change, change_pct, as_of: "2026-09-25", basis: "close", source: "FRED" }) as never;
    render(
      <ArticleList
        articles={[story(1, "tw")]}
        lang="zh-TW"
        calendar={{ month: "2026-09", days: DAYS }}
        markets={[quote("tw:2330", 2475, -1), quote("us10y", 5.18, null, 0.07), quote("taiex", 48024.6, -0.28), quote("btc", 84712, 0.86)]}
      />,
    );
    const rows = within(screen.getByTestId("market-overview")).getAllByRole("link");
    expect(rows.map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      ["加權指數48,024.60−0.28%", "/news/zh-TW/watchlist?s=taiex"],
      ["美國10年期公債5.18%+0.07", "/news/zh-TW/watchlist?s=us10y"],
      ["比特幣84,712+0.86%", "/news/zh-TW/watchlist?s=btc"],
    ]); // stocks are not in it; the figures in its own order
    expect(rows[0].querySelector(".text-fall, [class*=text-fall]")).toBeTruthy();
  });

  it("財經行事曆: the coming days, a stock's earnings a link to its chart (D-088)", () => {
    render(
      <ArticleList
        articles={[story(1, "tw")]}
        lang="zh-TW"
        calendar={{ month: "2026-09", days: DAYS }}
        events={[
          { day: "2026-09-30", kind: "macro", key: "release:53", name: "美國 GDP", detail: null },
          { day: "2026-09-30", kind: "earnings", key: "us:MU", name: "美光 財報", detail: "2026Q4 盤前" },
          { day: "2026-10-02", kind: "macro", key: "release:50", name: "美國就業報告（非農就業）", detail: null },
        ]}
      />,
    );
    const events = within(screen.getByTestId("events"));
    expect(events.getAllByText(/^\d+\/\d+（.）$/).map((d) => d.textContent)).toEqual(["9/30（三）", "10/2（五）"]);
    expect(events.getByRole("link", { name: "美光 財報" }).getAttribute("href")).toBe("/news/zh-TW/watchlist?s=us%3AMU");
    expect(events.queryByRole("link", { name: "美國 GDP" })).toBeNull(); // data has no chart
    expect(events.getByText("2026Q4 盤前")).toBeTruthy();
  });

  it("nothing read yet: no 熱門文章 block", () => {
    render(<ArticleList articles={[story(1, "tw")]} lang="zh-TW" calendar={{ month: "2026-09", days: DAYS }} />);
    expect(screen.queryByTestId("popular")).toBeNull();
  });
});
