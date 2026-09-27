// @vitest-environment jsdom
// A reader's watchlist (D-060): signed out, a way to sign in; signed in, a button that puts a
// stock on the list and takes it off, and a page that lists it with the stocks still to add.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// the page's address: ?s= the one picked, ?edit=1 its settings (D-064)
let params = new URLSearchParams();
const replace = vi.fn((href: string) => {
  params = new URLSearchParams(href.split("?")[1] ?? "");
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => params,
}));

import { MarketStrip } from "./MarketStrip";
import { WatchButton } from "./WatchButton";
import { WatchlistPage, WatchlistSide } from "./Watchlist";
import { loadWatchlist, reorderWatchlist, resetWatchlist, useWatchlist } from "./watchlistStore";

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
  params = new URLSearchParams("edit=1"); // most of these are about the settings
  replace.mockClear();
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
    if (url.includes("/history")) return Response.json({ symbol: "NVDA", market: "us", source: "Tiingo", bars: [], preparing: false });
    if (url.includes("/api/public/stocks/")) return Response.json({ symbol: "NVDA", market: "us", name: "輝達", quote: QUOTES[0], holders: [], trades: [], articles: [] });
    calls.push(`${method} ${url.replace(/^.*\/api\/me\/watchlist/, "")}`);
    if (list === null) return new Response(null, { status: 401 });
    if (method === "PUT") {
      const keys: string[] = JSON.parse(String(init?.body)).keys;
      calls[calls.length - 1] += ` ${keys.join(",")}`;
      list = keys.map((key) => list!.find((item) => item.key === key)!).filter(Boolean);
    }
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
  it("lists the reader's stocks with prices, and offers what else the strip has", async () => {
    list = [NVDA];
    render(<WatchlistPage lang="zh-TW" />);
    const rows = await screen.findByTestId("watchlist");
    await waitFor(() => expect(rows.textContent).toContain("225.07"));
    expect(rows.textContent).toContain("輝達");
    const addable = await screen.findByTestId("addable");
    expect(addable.textContent).toContain("台積電");
    expect(addable.textContent).not.toContain("輝達");
    expect(addable.textContent).toContain("加權指數"); // the strip's index can be kept too (D-062)
  });

  it("asks a signed-out reader to sign in, and shows the list a new one starts as", async () => {
    list = null;
    render(<WatchlistPage lang="zh-TW" />);
    expect(await screen.findByTestId("watchlist-signed-out")).toBeTruthy();
    const sample = await screen.findByTestId("watchlist-sample");
    expect(sample.textContent).toContain("加權指數");
    expect(sample.textContent).toContain("台積電");
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

describe("the strip and the list together (D-062)", () => {
  it("a signed-in reader's strip is their list, in its order", async () => {
    list = [{ ...NVDA }, { symbol: "TAIEX", market: "market", key: "taiex", name: "加權指數" }];
    render(<MarketStrip quotes={QUOTES as never} lang="zh-TW" />);
    await waitFor(() => {
      const names = [...screen.getByTestId("market-strip").querySelectorAll("li:not([aria-hidden]) .font-semibold")].map(
        (n) => n.textContent,
      );
      expect(names).toEqual(["輝達", "加權指數"]); // 台積電 is not on their list: not on their strip
    });
  });

  it("signed out, the strip is the site's, and the list beside a stock is a sample of it", async () => {
    list = null;
    render(<MarketStrip quotes={QUOTES as never} lang="zh-TW" />);
    expect(screen.getByTestId("market-strip-waiting")).toBeTruthy(); // not the site's first
    expect((await screen.findByTestId("market-strip")).textContent).toContain("台積電");
    cleanup();
    render(<WatchlistSide lang="zh-TW" current="us:NVDA" />);
    const side = await screen.findByTestId("watchlist-side");
    await waitFor(() => expect(side.textContent).toContain("觀察清單範例"));
    expect(side.textContent).toContain("加權指數");
  });
});

describe("the reader's own order (D-063)", () => {
  it("each stock has a handle to drag it by, named for it", async () => {
    list = [NVDA, { symbol: "TAIEX", market: "market", key: "taiex", name: "加權指數" }];
    render(<WatchlistPage lang="zh-TW" />);
    expect(await screen.findByRole("button", { name: "拖曳調整「輝達」的順序" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "拖曳調整「加權指數」的順序" })).toBeTruthy();
  });

  it("a new order shows at once and is kept", async () => {
    list = [NVDA, { symbol: "TAIEX", market: "market", key: "taiex", name: "加權指數" }];
    await loadWatchlist("zh-TW");
    function Names() {
      const state = useWatchlist("zh-TW");
      return <p data-testid="names">{state.status === "ready" ? state.items.map((i) => i.name).join(",") : ""}</p>;
    }
    render(<Names />);
    expect(screen.getByTestId("names").textContent).toBe("輝達,加權指數");
    const kept = reorderWatchlist(["taiex", "us:NVDA"]);
    await waitFor(() => expect(screen.getByTestId("names").textContent).toBe("加權指數,輝達"));
    expect(await kept).toBe(true);
    expect(calls).toContain("PUT  taiex,us:NVDA");
  });
});

describe("the watchlist page to watch (D-064)", () => {
  it("opens on the list with the first one picked, its figure beside it", async () => {
    params = new URLSearchParams();
    list = [NVDA, { symbol: "TAIEX", market: "market", key: "taiex", name: "加權指數" }];
    render(<WatchlistPage lang="zh-TW" />);
    const pane = await screen.findByTestId("watch-pane");
    // the stock's whole page, not a link to it
    await waitFor(() => expect(pane.querySelector("article h1")?.textContent).toContain("輝達"));
    expect(pane.querySelector('a[href="/news/zh-TW/stocks/NVDA"]')).toBeNull();
    expect(screen.queryByTestId("watchlist")).toBeNull(); // not the settings
  });

  it("an index has its figure and no chart; picking one goes in the address", async () => {
    params = new URLSearchParams("s=taiex");
    list = [NVDA, { symbol: "TAIEX", market: "market", key: "taiex", name: "加權指數" }];
    render(<WatchlistPage lang="zh-TW" />);
    const pane = await screen.findByTestId("watch-pane");
    expect(pane.textContent).toContain("加權指數");
    expect(pane.textContent).toContain("沒有個股走勢圖");
    fireEvent.click(screen.getAllByRole("button", { name: /輝達/ })[0]);
    expect(replace).toHaveBeenCalledWith("/news/zh-TW/watchlist?s=us%3ANVDA", { scroll: false });
  });

  it("編輯清單 opens the settings, and 完成 closes them", async () => {
    params = new URLSearchParams();
    list = [NVDA];
    const { rerender } = render(<WatchlistPage lang="zh-TW" />);
    fireEvent.click(await screen.findByTestId("watchlist-edit"));
    expect(replace).toHaveBeenCalledWith("/news/zh-TW/watchlist?edit=1", { scroll: false });
    rerender(<WatchlistPage lang="zh-TW" />);
    expect(await screen.findByTestId("watchlist")).toBeTruthy();
    expect(screen.getByTestId("watchlist-edit").textContent).toBe("完成");
  });

  it("beside a stock, the list is only to look at, with a way to its settings", async () => {
    list = [NVDA];
    render(<WatchlistSide lang="zh-TW" current="us:NVDA" />);
    const edit = await screen.findByTestId("watchlist-edit-link");
    expect(edit.getAttribute("href")).toBe("/news/zh-TW/watchlist?edit=1");
    expect(screen.queryByRole("button", { name: /拖曳/ })).toBeNull();
  });
});
