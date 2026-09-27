// @vitest-environment jsdom
// A reader's watchlist (D-060): signed out, a way to sign in; signed in, a button that puts a
// stock on the list and takes it off, and a page that lists it with the stocks still to add.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WatchButton, WatchlistPage, WatchlistSide } from "./Watchlist";
import { resetWatchlist } from "./watchlistStore";

const NVDA = { symbol: "NVDA", market: "us", key: "us:NVDA", name: "輝達" };
const QUOTES = [
  { key: "us:NVDA", value: 225.07, change: 0.49, change_pct: 0.22, as_of: "2026-09-25", basis: "latest", source: "Finnhub", currency: "USD" },
  { key: "tw:2330", value: 2475, change: -25, change_pct: -1, as_of: "2026-09-24", basis: "close", source: "TWSE", currency: "TWD" },
  { key: "taiex", value: 48024.6, change: 1, change_pct: 0.28, as_of: "2026-09-24", basis: "close", source: "TWSE" },
];

const FOUND = [{ symbol: "6488", market: "tw", name: "環球晶", name_en: null, exchange: "TPEx", kind: "stock" }];

let list: (typeof NVDA)[] | null;
const calls: string[] = [];

beforeEach(() => {
  resetWatchlist();
  calls.length = 0;
  list = [];
  vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? (typeof input === "object" && "method" in input ? input.method : "GET");
    if (url.includes("/api/public/markets")) return Response.json(QUOTES);
    if (url.includes("/api/public/quotes")) {
      const keys = decodeURIComponent(url.split("keys=")[1] ?? "").split(",");
      return Response.json(QUOTES.filter((q) => keys.includes(q.key)));
    }
    if (url.includes("/api/public/securities")) return Response.json(FOUND);
    calls.push(`${method} ${url.replace(/^.*\/api\/me\/watchlist/, "")}`);
    if (list === null) return new Response(null, { status: 401 });
    if (method === "POST") list.push(NVDA);
    if (method === "DELETE") list = list.filter((s) => !url.endsWith(`/${s.symbol}`));
    return method === "GET" ? Response.json(list) : new Response(null, { status: 204 });
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the watch button", () => {
  it("signed out, leads to signing in", async () => {
    list = null;
    render(<WatchButton symbol="NVDA" lang="zh-TW" />);
    const link = await screen.findByRole("link", { name: "☆ 加入觀察" });
    expect(link.getAttribute("href")).toMatch(/^\/news\/zh-TW\/login\?next=/);
  });

  it("signed in, puts the stock on the list and takes it off", async () => {
    render(<WatchButton symbol="NVDA" lang="zh-TW" />);
    fireEvent.click(await screen.findByRole("button", { name: "☆ 加入觀察" }));
    await screen.findByRole("button", { name: "★ 已觀察" });
    fireEvent.click(screen.getByRole("button", { name: "★ 已觀察" }));
    await screen.findByRole("button", { name: "☆ 加入觀察" });
    expect(calls.filter((c) => !c.startsWith("GET"))).toEqual(["POST /NVDA", "DELETE /NVDA"]);
  });
});

describe("the watchlist", () => {
  it("lists the reader's stocks with prices, and offers the stocks not on it (not the index)", async () => {
    list = [NVDA];
    render(<WatchlistPage lang="zh-TW" />);
    const rows = await screen.findByTestId("watchlist");
    await waitFor(() => expect(rows.textContent).toContain("225.07"));
    expect(rows.textContent).toContain("輝達");
    const addable = await screen.findByTestId("addable");
    expect(addable.textContent).toContain("台積電");
    expect(addable.textContent).not.toContain("輝達");
    expect(addable.textContent).not.toContain("加權");
  });

  it("asks a signed-out reader to sign in", async () => {
    list = null;
    render(<WatchlistPage lang="zh-TW" />);
    expect(await screen.findByTestId("watchlist-signed-out")).toBeTruthy();
  });

  it("beside a stock, marks the one on show; nothing when the list is empty", async () => {
    list = [NVDA];
    const { unmount } = render(<WatchlistSide lang="zh-TW" current="us:NVDA" />);
    const current = await screen.findAllByRole("link", { current: "page" });
    expect(current.length).toBeGreaterThan(0);
    unmount();
    resetWatchlist();
    list = [];
    render(<WatchlistSide lang="zh-TW" current="us:NVDA" />);
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(screen.queryByTestId("watchlist-side")).toBeNull();
  });
});

describe("finding any stock", () => {
  it("searches by what the reader types, and puts a result on the list", async () => {
    render(<WatchlistPage lang="zh-TW" />);
    fireEvent.change(await screen.findByRole("searchbox", { name: "搜尋股票" }), { target: { value: "環球" } });
    const results = await screen.findByTestId("search-results", {}, { timeout: 2000 });
    expect(results.textContent).toContain("環球晶");
    expect(results.textContent).toContain("6488.TWO・TPEx・股票");
    expect(results.querySelector("a")!.getAttribute("href")).toBe("/news/zh-TW/stocks/6488");
    fireEvent.click(screen.getByRole("button", { name: "＋ 加入" }));
    await waitFor(() => expect(calls).toContain("POST /6488"));
  });
});
