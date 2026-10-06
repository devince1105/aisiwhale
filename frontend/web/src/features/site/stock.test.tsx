// @vitest-environment jsdom
// D-049: a stock's page — its figure, the investors' 13F positions, our stories — and the strip's
// links to it.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchStock, type PublicHolder, type PublicStock } from "./api";
import { MarketStrip } from "./MarketStrip";
import { stockPage } from "./quote";
import { StockView } from "./StockView";

// not signed in: the site's own strip, and no list (D-060, D-062)
vi.mock("./watchlistStore", () => ({ useWatchlist: () => ({ status: "signedOut" }), setWatched: vi.fn() }));

afterEach(cleanup);

const holder = (over: Partial<PublicHolder>): PublicHolder => ({
  investor: "段永平",
  filer: "H&H International Investment, LLC",
  period: "2026-06-30",
  previous_period: "2026-03-31",
  change: "decreased",
  title_of_class: "COM",
  put_call: "",
  shares: 6280675,
  previous_shares: 13843775,
  value_usd: 1256700261,
  portfolio_pct: 6.58,
  filing_url: "https://www.sec.gov/Archives/edgar/data/1759760/000175976026000007/0001759760-26-000007-index.htm",
  ...over,
});

const NVDA: PublicStock = {
  us_listing: "NVDA",
  tracks_13f: true,
  symbol: "NVDA",
  market: "us",
  name: "輝達",
  quote: {
    key: "us:NVDA",
    value: 225.17,
    change: 0.59,
    change_pct: 0.26,
    as_of: "2026-09-25",
    basis: "last",
    source: "Finnhub",
    open: 225.26,
    high: 226.94,
    low: 223.13,
    previous_close: 224.58,
    market_cap: 5.412e12,
    currency: "USD",
  },
  holders: [
    holder({}),
    holder({ investor: "麥可・貝瑞", filer: "Scion", change: "new", put_call: "PUT", shares: 1000000, previous_shares: 0 }),
  ],
  trades: [
    {
      person: "川普",
      kind: "sale",
      traded_on: "2026-02-05",
      amount_min: 250001,
      amount_max: 500000,
      amount_text: "$250,001 - $500,000",
      late: true,
      received_on: "2026-05-12",
      report_url: "https://extapps2.oge.gov/r.pdf#page=2",
      option: false,
    },
    {
      person: "川普",
      kind: "purchase",
      traded_on: "2026-01-26",
      amount_min: 50000001,
      amount_max: null,
      amount_text: "Over $50,000,000",
      late: false,
      received_on: "2026-05-12",
      report_url: "https://extapps2.oge.gov/r.pdf#page=3",
      option: false,
    },
  ],
  articles_total: 1,
  articles: [
    {
      article_id: "a1",
      lang: "zh-TW",
      slug: "hh",
      stocks: [],
      path: "/news/zh-TW/articles/hh",
      title: "段永平 H&H 最新 13F：減持輝達逾五成",
      summary: null,
      published_at: "2026-09-25T00:00:00Z",
      access: "free",
      section: "holdings",
    },
  ],
};

describe("a stock's page", () => {
  it("shows its figure, who holds it and what they did, and our stories", () => {
    render(<StockView stock={NVDA} lang="zh-TW" />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("輝達NVDA");
    expect(document.body.textContent).toContain("225.17+0.26% ↑");
    const [duan, burry] = screen.getAllByTestId("holder");
    expect(duan!.textContent).toContain("段永平減碼");
    expect(duan!.textContent).toContain("前季 13,843,775");
    expect(duan!.textContent).toContain("6.58%");
    expect(within(duan!).getByRole("link", { name: /申報/ }).getAttribute("href")).toBe(NVDA.holders[0]!.filing_url);
    expect(screen.getByRole("link", { name: /減持輝達逾五成/ }).getAttribute("href")).toBe("/news/zh-TW/articles/hh");
    expect(document.body.textContent).not.toContain("不構成投資建議"); // in the footer, once (D-097)
    // an option is a bet on the stock, not a holding of it
    expect(burry!.textContent).toContain("新建倉・賣權（看跌）");
    expect(burry!.textContent).toContain("標的股數");
    expect(burry!.querySelector(".text-rise")).toBeNull();
  });

  it("gives the market value under the price; the day's figures are the chart's", () => {
    render(<StockView stock={NVDA} lang="zh-TW" />);
    expect(screen.getByTestId("market-cap").textContent).toBe("總市值 US$5.4兆");
    expect(screen.getByTestId("market-cap").parentElement!.textContent).toContain("Finnhub"); // above its source
    expect(document.querySelector("article header dl")).toBeNull(); // no open/high/low card
    cleanup();
    // an ETF has no market value: no line
    const etf = { ...NVDA.quote!, key: "tw:0050", market_cap: null, currency: "TWD" };
    render(<StockView stock={{ ...NVDA, quote: etf }} lang="zh-TW" />);
    expect(screen.queryByTestId("market-cap")).toBeNull();
  });

  it("lists public figures' trades, as ranges, each with the page of its report", () => {
    render(<StockView stock={NVDA} lang="zh-TW" />);
    const [sold, bought] = screen.getAllByTestId("trade");
    expect(sold!.textContent).toContain("川普賣出US$250,001 – US$500,000");
    expect(sold!.textContent).toContain("逾 30 天才申報");
    expect(within(sold!).getByRole("link").getAttribute("href")).toBe("https://extapps2.oge.gov/r.pdf#page=2");
    expect(bought!.textContent).toContain("買進US$50,000,000 以上");
    expect(document.body.textContent).toContain("經人工對照原件核准後才顯示");
    cleanup();
    render(<StockView stock={{ ...NVDA, trades: [] }} lang="zh-TW" />);
    // not compiled here: pointed to the trackers that publish them (D-052)
    expect(document.body.textContent).toContain("艾矽鯨不自行整理");
    const links = within(screen.getByTestId("trackers")).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "https://open-cabinet.org/officials/trump-donald-j",
      "https://www.capitoltrades.com/politicians/P000197",
    ]);
    expect(links[0]!.getAttribute("rel")).toContain("nofollow");
  });

  it("a member's spouse's option is shown as the spouse's, and as an option", () => {
    const option = {
      person: "裴洛西",
      kind: "purchase",
      traded_on: "2026-07-24",
      amount_min: 1000001,
      amount_max: 5000000,
      amount_text: "$1,000,001 - $5,000,000",
      late: null,
      received_on: "2026-08-21",
      report_url: "https://disclosures-clerk.house.gov/r.pdf#page=1",
      owner: "SP",
      option: true,
      note: "Purchased 50 call options with a strike price of $100.",
    };
    render(<StockView stock={{ ...NVDA, trades: [option] }} lang="zh-TW" />);
    const [trade] = screen.getAllByTestId("trade");
    expect(trade!.textContent).toContain("裴洛西（配偶）買進選擇權US$1,000,001 – US$5,000,000");
    expect(trade!.textContent).toContain("Purchased 50 call options with a strike price of $100.");
    expect(trade!.textContent).not.toContain("逾 30 天");
  });

  it("an over-the-counter stock reads .TWO; no page cites 13F in a notice of its own (D-097: the footer's)", () => {
    render(
      <StockView
        stock={{ ...NVDA, symbol: "6488", market: "tw", name: "環球晶", holders: [], us_listing: null, tracks_13f: false, exchange: "TPEx" }}
        lang="zh-TW"
      />,
    );
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("環球晶6488.TWO");
    expect(document.body.textContent).not.toContain("持股來自 SEC 13F");
    cleanup();
    render(<StockView stock={NVDA} lang="zh-TW" />);
    expect(document.body.textContent).not.toContain("持股來自 SEC 13F");
  });

  it("a Taiwan stock with an ADR shows the ADR's holders; one without has no US sections", () => {
    render(
      <StockView stock={{ ...NVDA, symbol: "2330", market: "tw", name: "台積電", quote: null, us_listing: "TSM" }} lang="zh-TW" />,
    );
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("台積電2330.TW");
    expect(document.body.textContent).toContain("美國存託憑證（TSM）的持有人");
    expect(document.body.textContent).toContain("目前沒有報價。");
    cleanup();
    render(
      <StockView
        stock={{ ...NVDA, symbol: "2454", market: "tw", name: "聯發科", holders: [], articles: [], us_listing: null }}
        lang="zh-TW"
      />,
    );
    // no US listing: 13F and officials' trades can say nothing about it, so they are not shown
    expect(screen.queryByRole("heading", { name: "大戶持股（13F）" })).toBeNull();
    expect(screen.queryByTestId("trackers")).toBeNull();
    expect(document.body.textContent).toContain("還沒有提到這檔股票的報導。");
  });

  it("is asked of the API by symbol, and a symbol without a page is null", async () => {
    const found = vi.fn<typeof fetch>(() =>
      Promise.resolve(new Response(JSON.stringify(NVDA), { headers: { "Content-Type": "application/json" } })),
    );
    expect((await fetchStock("NVDA", "zh-TW", { baseUrl: "http://api", fetch: found, company: "c" }))?.name).toBe("輝達");
    expect((found.mock.calls[0]![0] as Request).url).toBe("http://api/api/public/stocks/NVDA?lang=zh-TW&company=c");
    const missing = vi.fn<typeof fetch>(() => Promise.resolve(new Response("{}", { status: 404 })));
    expect(await fetchStock("XYZ", "en", { baseUrl: "http://api", fetch: missing })).toBeNull();
    await fetchStock("NVDA", "zh-TW", { baseUrl: "http://api", fetch: found, articlesOffset: 10 });
    expect((found.mock.calls[1]![0] as Request).url).toBe("http://api/api/public/stocks/NVDA?lang=zh-TW&articles_offset=10");
  });

  it("pages through our stories that name it, ten at a time (D-066)", () => {
    const { rerender } = render(<StockView stock={NVDA} lang="zh-TW" />);
    expect(screen.queryByRole("navigation", { name: "分頁" })).toBeNull(); // one story: one page
    rerender(<StockView stock={{ ...NVDA, articles_total: 23 }} lang="zh-TW" />);
    const pages = within(screen.getByRole("navigation", { name: "分頁" }));
    expect(pages.getByRole("link", { name: "下一頁" }).getAttribute("href")).toBe("/news/zh-TW/stocks/NVDA?page=2#coverage");
    expect(pages.getByText("第 1／3 頁")).toBeTruthy();
    rerender(
      <StockView
        stock={{ ...NVDA, articles_total: 23 }}
        lang="zh-TW"
        coverage={{ page: 3, to: (n) => `/news/zh-TW/watchlist?s=us%3ANVDA&page=${n}#coverage` }}
      />,
    );
    expect(screen.getByRole("link", { name: "上一頁" }).getAttribute("href")).toBe("/news/zh-TW/watchlist?s=us%3ANVDA&page=2#coverage");
    rerender(<StockView stock={{ ...NVDA, articles: [], articles_total: 23 }} lang="zh-TW" coverage={{ page: 9, to: String }} />);
    expect(screen.getByText("這一頁沒有報導了。")).toBeTruthy(); // past the last page, not "none yet"
  });
});

describe("the strip's way to a stock", () => {
  it("links a stock to its page, and nothing else", () => {
    expect(stockPage("us:NVDA", "en")).toBe("/news/en/stocks/NVDA");
    expect(stockPage("tw:0050", "zh-TW")).toBe("/news/zh-TW/stocks/0050");
    expect(stockPage("taiex", "zh-TW")).toBeNull();
    render(<MarketStrip quotes={[NVDA.quote!, { ...NVDA.quote!, key: "btc", source: "CoinGecko", basis: "24h" }]} lang="zh-TW" />);
    const items = within(screen.getByTestId("market-strip")).getAllByRole("listitem");
    expect(within(items[0]!).getByRole("link").getAttribute("href")).toBe("/news/zh-TW/stocks/NVDA");
    expect(within(items[1]!).queryByRole("link")).toBeNull();
  });
});
