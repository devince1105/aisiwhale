// @vitest-environment jsdom
// A reader's watchlist (D-060): signed out, a way to sign in; signed in, a button that puts a
// stock on the list and takes it off, and a page that lists it with the stocks still to add.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  sessionStorage.clear(); // the list beside a stock starts hidden (D-066)
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
    if (url.includes("/api/public/figures/"))
      return Response.json(
        url.endsWith("/taiex")
          ? null
          : { key: "jpytwd", as_of: "2026-09-25", value: 0.2017, change: 0, change_pct: 0, source: "Tiingo", close_only: true, bars: [] },
      );
    if (url.includes("/api/public/gold"))
      return Response.json({ as_of: "2026-09-25", usd_per_oz: 4284.91, change: 19.82, change_pct: 0.46, twd_per_gram: 4375, source: "Tiingo", bars: [] });
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

  it("beside a stock, hidden until asked for, and open from stock to stock once asked (D-066)", async () => {
    list = [NVDA];
    const { unmount } = render(<WatchlistSide lang="zh-TW" current="us:NVDA" />);
    const toggle = await screen.findByRole("button", { name: "觀察清單" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("link", { current: "page" })).toBeNull();
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "收起清單" }).getAttribute("aria-expanded")).toBe("true");
    expect(screen.getAllByRole("link", { current: "page" }).length).toBeGreaterThan(0);
    unmount();
    render(<WatchlistSide lang="zh-TW" current="us:NVDA" />); // the next stock: still open
    expect(await screen.findByRole("button", { name: "收起清單" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "收起清單" }));
    expect(sessionStorage.getItem("autora:watchlist-side")).toBeNull();
  });

  it("beside a stock, marks the one on show; nothing when the list is empty", async () => {
    list = [NVDA];
    const { unmount } = render(<WatchlistSide lang="zh-TW" current="us:NVDA" />);
    fireEvent.click(await screen.findByRole("button", { name: "觀察清單" }));
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
    fireEvent.click(screen.getByRole("button", { name: "觀察清單" }));
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
    // 已觀察 once, in the title row beside 編輯清單, not again in the stock's own header
    expect(pane.querySelector("[data-testid=watch-button]")).toBeNull();
    // an icon, its words the name and the hover label (D-093)
    const watched = await screen.findByRole("button", { name: "已觀察" });
    expect(watched.querySelector("svg")).toBeTruthy();
    expect(screen.getByRole("button", { name: "編輯清單" }).getAttribute("aria-pressed")).toBe("false");
    expect(screen.queryByTestId("watchlist")).toBeNull(); // not the settings
  });

  it("an index has its figure and no chart; picking one goes in the address", async () => {
    params = new URLSearchParams("s=taiex");
    list = [NVDA, { symbol: "TAIEX", market: "market", key: "taiex", name: "加權指數" }];
    render(<WatchlistPage lang="zh-TW" />);
    const pane = await screen.findByTestId("watch-pane");
    expect(pane.textContent).toContain("加權指數");
    expect(await within(pane).findByText(/歷史資料還在準備中/)).toBeTruthy(); // no history yet
    // the list is hidden until asked for (D-075): the one picked has the page
    expect(screen.queryByRole("button", { name: /輝達/ })).toBeNull();
    // the list's button is an icon in the title row (D-093)
    fireEvent.click(screen.getByRole("button", { name: "展開清單" }));
    fireEvent.click(screen.getAllByRole("button", { name: /輝達/ })[0]);
    expect(replace).toHaveBeenCalledWith("/news/zh-TW/watchlist?s=us%3ANVDA", { scroll: false });
    // open: a column on the right, scrolled on its own (D-092)
    expect(screen.getByTestId("watch-board").className).toContain("lg:grid-cols-[minmax(0,1fr)_16rem]");
    expect(document.getElementById("watchlist-side-list")!.className).toContain("lg:scroll-column");
    expect(screen.getByTestId("watchlist-page").className).not.toContain("max-w-[46rem]"); // wide
    fireEvent.click(screen.getByRole("button", { name: "收起清單" }));
    expect(screen.getByTestId("watch-board").className).not.toContain("16rem]");
    // hidden: the same reading column as every other page (D-076)
    expect(screen.getByTestId("watchlist-page").className).toContain("mx-auto max-w-[46rem]");
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
    // the settings in the centred reading column, as before (not the wide board's)
    expect(screen.getByTestId("watchlist-page").className).toContain("mx-auto max-w-[46rem]");
  });

  it("the settings in drawers, each counted; 移除 is a trash can", async () => {
    params = new URLSearchParams("edit=1");
    list = [NVDA, { symbol: "TAIEX", market: "market", key: "taiex", name: "加權指數" }];
    render(<WatchlistPage lang="zh-TW" />);
    const drawers = within(await screen.findByTestId("watchlist"));
    expect(drawers.getByRole("button", { name: "美股1" }).getAttribute("aria-expanded")).toBe("true");
    expect(drawers.getByRole("button", { name: "台股1" })).toBeTruthy(); // the TAIEX, with the stocks (D-191)
    const remove = drawers.getByRole("button", { name: "移除「輝達」" });
    expect(remove.querySelector("svg")).toBeTruthy();
    fireEvent.click(remove);
    await waitFor(() => expect(calls).toContain("DELETE /NVDA"));
  });

  it("beside a stock, the list is only to look at, with a way to its settings", async () => {
    list = [NVDA];
    render(<WatchlistSide lang="zh-TW" current="us:NVDA" />);
    fireEvent.click(await screen.findByRole("button", { name: "觀察清單" }));
    const edit = await screen.findByTestId("watchlist-edit-link");
    expect(edit.getAttribute("href")).toBe("/news/zh-TW/watchlist?edit=1");
    expect(screen.queryByRole("button", { name: /拖曳/ })).toBeNull();
  });
});

describe("spot gold on the watchlist (D-071)", () => {
  it("picked, it shows its price, a gram in NT$ and its chart, as a stock shows its page", async () => {
    list = [{ symbol: "XAU", market: "market", key: "xau", name: "黃金" }];
    params = new URLSearchParams("s=xau");
    render(<WatchlistPage lang="zh-TW" />);
    const gold = await screen.findByTestId("gold-board");
    expect(gold.textContent).toContain("4,284.91");
    expect(gold.textContent).toContain("約新台幣／公克 4,375");
    expect(screen.queryByText(/沒有個股走勢圖/)).toBeNull();
  });
});

describe("the other figures' charts, and currencies (D-072)", () => {
  it("a currency shows its chart; a figure whose history is not there yet says so", async () => {
    list = [
      { symbol: "JPYTWD", market: "market", key: "jpytwd", name: "日圓" },
      { symbol: "TAIEX", market: "market", key: "taiex", name: "加權指數" },
    ];
    params = new URLSearchParams("s=jpytwd");
    const { unmount } = render(<WatchlistPage lang="zh-TW" />);
    expect(await screen.findByTestId("figure-chart")).toBeTruthy();
    unmount();
    params = new URLSearchParams("s=taiex");
    render(<WatchlistPage lang="zh-TW" />);
    expect(await screen.findByText(/歷史資料還在準備中/)).toBeTruthy();
  });

  it("a currency found by name is added as a figure, with no stock page", async () => {
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/public/securities"))
        return Response.json([{ symbol: "EURTWD", market: "market", name: "歐元", name_en: "Euro", exchange: "Tiingo", kind: "fx" }]);
      if (url.includes("/api/public/markets")) return Response.json([]);
      return Response.json([]);
    });
    render(<WatchlistPage lang="zh-TW" />);
    fireEvent.change(await screen.findByRole("searchbox", { name: "搜尋股票" }), { target: { value: "歐元" } });
    const results = await screen.findByTestId("search-results", {}, { timeout: 2000 });
    expect(results.textContent).toContain("EUR/TWD・匯率");
    expect(results.querySelector("a[href*='/stocks/']")).toBeNull();
  });
});

describe("a stock from an article (D-077)", () => {
  it("is shown on the watchlist page though not on the list, with 加入觀察 beside it", async () => {
    list = [{ symbol: "TAIEX", market: "market", key: "taiex", name: "加權指數" }];
    params = new URLSearchParams("s=us:NVDA");
    render(<WatchlistPage lang="zh-TW" />);
    const pane = await screen.findByTestId("watch-pane");
    expect(await within(pane).findByText("輝達")).toBeTruthy();
    expect(screen.getByRole("button", { name: /加入觀察/ })).toBeTruthy();
  });
});

describe("a figure from an article (D-079)", () => {
  it("opens though not on the list: its name, its chart, 加入觀察", async () => {
    list = [NVDA];
    params = new URLSearchParams("s=jpytwd");
    render(<WatchlistPage lang="zh-TW" />);
    const pane = await screen.findByTestId("watch-pane");
    expect(pane.textContent).toContain("日圓");
    expect(await within(pane).findByTestId("figure-chart")).toBeTruthy();
    params = new URLSearchParams("s=nonsense");
    cleanup();
    render(<WatchlistPage lang="zh-TW" />);
    expect((await screen.findByTestId("watch-pane")).textContent).toContain("輝達"); // unknown: the first
  });
});

describe("a grain's world price (D-080)", () => {
  it("charts its months only, and is found by its name as a world monthly price", async () => {
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/public/securities"))
        return Response.json([{ symbol: "MAIZE", market: "market", name: "玉米（IMF 月價）", name_en: "Corn", exchange: "IMF", kind: "commodity" }]);
      return Response.json([]);
    });
    render(<WatchlistPage lang="zh-TW" />);
    fireEvent.change(await screen.findByRole("searchbox", { name: "搜尋股票" }), { target: { value: "玉米" } });
    const results = await screen.findByTestId("search-results", {}, { timeout: 2000 });
    expect(results.textContent).toContain("IMF・國際月價");
    expect(results.querySelector("a[href*='/stocks/']")).toBeNull();
  });
});
