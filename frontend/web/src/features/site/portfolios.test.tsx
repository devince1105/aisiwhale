// @vitest-environment jsdom
// HD-06: the holdings dashboard — the 持股觀察 tab's cards and a person page — in Taiwan's words.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { PublicPortfolio, PublicPortfolioCard } from "./api";
import { words } from "./i18n";
import { CEOS, KINDS, PortfolioCards, PortfolioView, quarterOf, signedPct, WatchTabs } from "./Portfolios";

afterEach(cleanup);

const BUFFETT: PublicPortfolioCard = {
  slug: "buffett",
  name: "巴菲特",
  kind: "person",
  entity: "波克夏海瑟威",
  period: "2026-06-30",
  filed: "2026-08-14",
  return_pct: 0.1385,
  return_start: "2025-09-30",
  return_through: "2026-10-05",
  coverage: 0.934,
  pending: 0,
  holdings: [
    { symbol: "AAPL", name: "蘋果", weight: 0.22 },
    { symbol: "AXP", name: "AMERICAN EXPRESS CO", weight: 0.171 },
    { symbol: "KO", name: "COCA COLA CO", weight: 0.109 },
    { symbol: "BAC", name: "BANK AMER CORP", weight: 0.1 },
    { symbol: "CVX", name: "CHEVRON CORP NEW", weight: 0.06 },
  ],
  others_weight: 0.34,
  moves: [
    { symbol: "GOOGL", name: "Alphabet", change: "increased", shares: 78791167, previous_shares: 54249798, shares_change_pct: 45.24, value_change_usd: 8770000000 },
    { symbol: "OXY", name: "OCCIDENTAL PETE CORP", change: "sold_out", shares: 0, previous_shares: 264941431, shares_change_pct: null, value_change_usd: -1e10 },
  ],
  trades: [],
  reports_waiting: 0,
};

const NVIDIA: PublicPortfolioCard = {
  ...BUFFETT,
  slug: "nvidia",
  name: "輝達",
  kind: "company",
  entity: "輝達",
  return_pct: null,
  return_start: "2025-09-30",
  return_through: null,
  coverage: 0.049,
  pending: 3,
  moves: [],
};

describe("the 持股觀察 tab's cards", () => {
  it("says whose holdings, the simulated return, the two moves and when it was filed", () => {
    render(<PortfolioCards cards={[BUFFETT, NVIDIA]} lang="zh-TW" />);
    const [buffett, nvidia] = screen.getAllByTestId("portfolio-card");
    expect(buffett.getAttribute("href")).toBe("/news/zh-TW/holdings/people/buffett");
    expect(within(buffett).getByRole("heading").textContent).toBe("巴菲特持股");
    const ret = within(buffett).getByText("+13.85%");
    expect(ret.className).toContain("text-rise"); // red is up, in Taiwan
    expect(within(buffett).getByText("近一年報酬率（模擬）")).toBeTruthy();
    expect(within(buffett).getByText("GOOGL").parentElement?.textContent).toBe("GOOGL+45.24%加碼");
    expect(within(buffett).getByText("OXY").parentElement?.textContent).toBe("OXY出清");
    expect(within(buffett).getByText(/申報日 2026年8月14日/).parentElement?.textContent).toContain("2026 年第 2 季");
    expect(within(buffett).getByRole("img", { name: "巴菲特的前五大持股" })).toBeTruthy();

    // faces from Wikimedia Commons: Buffett's own; NVIDIA's card its chief's, as the brokers' do
    expect(buffett.querySelector("image")?.getAttribute("href")).toBe("/people/buffett.jpg");
    expect(nvidia.querySelector("image")?.getAttribute("href")).toBe("/ceos/nvda.jpg");
    expect(screen.getByText("人物照片的來源列在各人的頁面。")).toBeTruthy();

    // NVIDIA's 13F is the company's, not Jensen Huang's; its return is still being checked
    expect(within(nvidia).getByRole("heading").textContent).toBe("輝達（公司）持股");
    expect(within(nvidia).getByText("整理中")).toBeTruthy();
    expect(within(nvidia).getByText("最近一季沒有買賣。")).toBeTruthy();
  });

  it("in English", () => {
    render(<PortfolioCards cards={[{ ...BUFFETT, name: "Warren Buffett" }, { ...NVIDIA, name: "NVIDIA" }]} lang="en" />);
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(["Warren Buffett's holdings", "NVIDIA (the company)'s holdings"]);
    expect(screen.getByText("Calculating")).toBeTruthy();
    expect(screen.getAllByText("Q2 2026", { exact: false }).length).toBe(2);
  });
});

const PAGE: PublicPortfolio = {
  ...BUFFETT,
  long_value_usd: 299253556246,
  positions: [
    { symbol: "AAPL", name: "蘋果", change: "unchanged", shares: 227917808, previous_shares: 227917808, shares_change_pct: null, value_usd: 65_800_000_000, weight: 0.22 },
    { symbol: "BKNG", name: "BOOKING HOLDINGS INC", change: null, shares: 25000, previous_shares: 1000, shares_change_pct: null, value_usd: 120_000_000, weight: 0.0004 },
    { symbol: "OXY", name: "OCCIDENTAL PETE CORP", change: "sold_out", shares: 0, previous_shares: 264941431, shares_change_pct: null, value_usd: 0, weight: 0 },
  ],
  positions_total: 31,
  locked: true,
  trades_total: 0,
  reports: [],
  stretches: [
    { start: "2025-09-30", end: "2025-12-31", growth: 1.02, coverage: 1 },
    { start: "2025-12-31", end: "2026-10-05", growth: 0.97, coverage: 0.934 },
  ],
  quarters: [
    { period: "2026-06-30", filed: "2026-08-14", filings: ["https://www.sec.gov/Archives/edgar/data/1067983/000119312526352200/0001193125-26-352200-index.htm"] },
  ],
};

describe("a person page", () => {
  it("has the table, its changes (a possible split waits), the method and the filings", () => {
    render(<PortfolioView portfolio={PAGE} lang="zh-TW" loginHref="/news/zh-TW/login?next=x" />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("巴菲特持股");
    const table = screen.getByTestId("portfolio-table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[1].textContent)).toEqual(["不變", "待確認", "出清"]);
    expect(within(rows[0]).getByRole("link", { name: "AAPL" }).getAttribute("href")).toBe("/news/zh-TW/stocks/AAPL");
    // three rows of 31 here: the rest a free sign-in away (D-159)
    expect(screen.getByText(/登入（免費）就能看完整 31 檔持股。/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "登入" }).getAttribute("href")).toBe("/news/zh-TW/login?next=x");
    expect(screen.getByText("+2.00%")).toBeTruthy();
    expect(screen.getByText("−3.00%").className).toContain("text-fall");
    expect(screen.getByText("怎麼算")).toBeTruthy();
    expect(screen.getByText(/不是投資人的實際績效/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "SEC ↗" }).getAttribute("href")).toContain("0001193125-26-352200");
    expect(screen.getByRole("link", { name: "持股觀察" }).getAttribute("href")).toBe("/news/zh-TW?section=watch");
    // a photo in the public domain is credited all the same, and said to be cropped
    expect(screen.getByTestId("photo-credit").textContent).toBe(
      "照片：USA International Trade Administration，公有領域，維基共享資源（已裁切）",
    );
  });

  it("credits who is pictured when it is not the card's own subject, with the licence", () => {
    render(<PortfolioView portfolio={{ ...PAGE, slug: "nvidia", name: "輝達", kind: "company" }} lang="zh-TW" loginHref="/x" />);
    const credit = screen.getByTestId("photo-credit");
    expect(credit.textContent).toBe("照片：黃仁勳（輝達執行長）；Peter Dasilva，CC BY 4.0，維基共享資源（已裁切）");
    expect(within(credit).getByRole("link", { name: "CC BY 4.0" }).getAttribute("href")).toBe(
      "https://creativecommons.org/licenses/by/4.0/",
    );
    expect(screen.getByText("這是公司本身的投資部位，不是負責人個人的持股。")).toBeTruthy();
  });
});

describe("the Magnificent Seven's chief executives", () => {
  it("named as Taiwan's press names them, each photo credited", () => {
    expect(Object.fromEntries(Object.entries(CEOS).map(([ticker, ceo]) => [ticker, ceo.zh]))).toEqual({
      AAPL: "John Ternus",
      MSFT: "納德拉",
      GOOGL: "皮查伊",
      AMZN: "賈西",
      META: "祖克柏",
      NVDA: "黃仁勳",
      TSLA: "馬斯克",
    });
    for (const ceo of Object.values(CEOS)) {
      expect(ceo.photo.page).toMatch(/^https:\/\/commons\.wikimedia\.org\/wiki\/File:/);
      expect(ceo.photo.supplied).toBeUndefined(); // every one from Commons, credited
      expect(ceo.photo.license === null || /^CC BY \d\.\d$/.test(ceo.photo.license ?? "")).toBe(true); // no ShareAlike
    }
  });
});

describe("Taiwan's words, not the screenshot's", () => {
  // the broker's screenshots were mainland Chinese (D-217): none of these on our pages
  // (新建倉 is the site's own, as on the stock pages; 清倉 is not: 出清)
  const MAINLAND = ["持倉", "持仓", "增倉", "減倉", "清倉", "萬億", "收益", "搜索", "特朗普", "英偉達", "佩洛西", "數據", "信息", "默認", "視頻"];

  function texts(value: unknown): string[] {
    if (typeof value === "string") return [value];
    if (typeof value === "function") {
      const fn = value as (...args: unknown[]) => unknown;
      return texts(fn("巴菲特", "person")).concat(texts(fn("輝達", "company")), texts(fn(2026, 2)));
    }
    if (Array.isArray(value)) return value.flatMap(texts);
    if (value && typeof value === "object") return Object.values(value).flatMap(texts);
    return [];
  }

  it("every string of the dashboard is in Taiwan's usage", () => {
    const all = texts(words("zh-TW").portfolio).join("\n");
    for (const term of MAINLAND) expect(all, term).not.toContain(term);
    expect(all).toContain("報酬率");
  });
});

describe("the numbers", () => {
  it("signs a percentage the way a quote does, and names a quarter", () => {
    expect([signedPct(0.1894), signedPct(-0.0128), signedPct(0)]).toEqual(["+18.94%", "−1.28%", "0.00%"]);
    expect([quarterOf("zh-TW", "2026-06-30"), quarterOf("en", "2025-12-31")]).toEqual(["2026 年第 2 季", "Q4 2025"]);
  });
});

describe("持股觀察's tabs", () => {
  it("separates the big names, the big holders and the stories", () => {
    render(<WatchTabs lang="zh-TW" view="groups" />);
    const tabs = within(screen.getByTestId("watch-tabs")).getAllByRole("link");
    expect(tabs.map((tab) => [tab.textContent, tab.getAttribute("href"), tab.getAttribute("aria-current")])).toEqual([
      ["名人持股", "/news/zh-TW?section=watch", null],
      ["機構持股", "/news/zh-TW?section=watch&view=groups", "page"],
      ["新聞", "/news/zh-TW?section=watch&view=news", null],
    ]);
    // a person's or an official's card among the big names; a company's or a fund's among the groups
    expect([KINDS.people, KINDS.groups]).toEqual([
      ["person", "official"],
      ["company", "fund", "manager", "foundation"],
    ]);
  });

  it("a photo the site's operator supplied says so (Commons has none of 段永平)", () => {
    render(<PortfolioView portfolio={{ ...PAGE, slug: "duan-yongping", name: "段永平" }} lang="zh-TW" loginHref="/x" />);
    expect(screen.getByTestId("photo-credit").textContent).toBe("照片：網站經營者提供");
    expect(document.querySelector("image")?.getAttribute("href")).toBe("/people/duan-yongping.jpg");
  });
});

const TRUMP: PublicPortfolioCard = {
  ...BUFFETT,
  slug: "trump",
  name: "川普",
  kind: "official",
  entity: "美國總統（OGE 278-T 申報）",
  period: null,
  filed: "2026-09-22",
  return_pct: null,
  return_start: null,
  return_through: null,
  coverage: null,
  holdings: [],
  others_weight: 0,
  moves: [],
  trades: [
    { symbol: "AVGO", name: "博通", kind: "purchase", traded_on: "2026-07-31", amount_text: "$250,001 - $500,000", owner: null, option: false, report_url: "https://oge.test/09.pdf#page=3" },
    { symbol: "META", name: "Meta", kind: "sale", traded_on: "2026-07-27", amount_text: "$50,001 - $100,000", owner: null, option: false, report_url: null },
  ],
  reports_waiting: 1,
};

describe("the officials (HD-07)", () => {
  it("a card lists the latest checked trades, the amounts as the forms' ranges, and what waits", () => {
    render(<PortfolioCards cards={[TRUMP, { ...TRUMP, slug: "pelosi", name: "裴洛西", trades: [], filed: null, reports_waiting: 0 }]} lang="zh-TW" />);
    const [trump, pelosi] = screen.getAllByTestId("portfolio-card");
    expect(within(trump).getByRole("heading").textContent).toBe("川普的股票交易");
    expect(within(trump).getByText("AVGO").parentElement?.textContent).toBe("AVGO買進US$250,001–500,000");
    expect(within(trump).getByText("賣出").className).toContain("text-fall");
    expect(within(trump).getByText(/申報日 2026年9月22日/).parentElement?.textContent).toContain("1 份申報待人工核對");
    expect(trump.querySelector("image")?.getAttribute("href")).toBe("/people/trump.jpg");
    expect(within(pelosi).getByText("還沒有已核對的交易申報。")).toBeTruthy();
  });

  it("a page has the trades, who owns each, and the reports with their status", () => {
    const page: PublicPortfolio = {
      ...PAGE,
      ...TRUMP,
      positions: [],
      positions_total: 0,
      locked: true,
      trades_total: 24,
      reports: [
        { form: "278 Transaction", received_on: "2026-10-01", status: "pending", url: "https://oge.test/10.pdf" },
        { form: "278 Transaction", received_on: "2026-09-22", status: "approved", url: "https://oge.test/09.pdf" },
      ],
    };
    render(<PortfolioView portfolio={page} lang="zh-TW" loginHref="/news/zh-TW/login?next=y" />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("川普的股票交易");
    const rows = within(screen.getByTestId("official-trades")).getAllByRole("row").slice(1);
    expect(within(rows[0]).getAllByRole("cell").map((c) => c.textContent)).toEqual([
      "2026年7月31日", "AVGO博通", "買進", "US$250,001–500,000", "本人",
    ]);  // prettier-ignore
    expect(screen.getByText("登入（免費）就能看完整 24 筆交易。")).toBeTruthy();
    expect(screen.getByText("待人工核對")).toBeTruthy();
    expect(screen.getByText("已核對")).toBeTruthy();
    expect(screen.getByTestId("photo-credit").textContent).toBe(
      "照片：Daniel Torok – The White House，公有領域，維基共享資源（已裁切）",
    );
    expect(screen.getByText(/經人工對照原件核對後才顯示/)).toBeTruthy();
  });
});

