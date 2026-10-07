// @vitest-environment jsdom
// HD-11: 機構排行 and an institution's page — Taiwan's amounts (兆, 億), the units said where they
// matter, the ranking's links keeping the search, the top ten on 持股觀察, a page's sign-in split.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type {
  PublicInstitution,
  PublicInstitutionHolding,
  PublicRankRow,
  PublicRanking,
} from "./api";
import {
  bigUsd,
  InstitutionView,
  RankingView,
  rankingHref,
  TopRanking,
} from "./Institutions";

afterEach(cleanup);

const row = (over: Partial<PublicRankRow>): PublicRankRow => ({
  rank: 1,
  cik: "2012383",
  name: "貝萊德",
  filed_name: "BlackRock, Inc.",
  value_usd: 6_729_538_649_155,
  previous_value_usd: 5_723_531_457_401,
  change_usd: 1_006_007_191_754,
  change_pct: 17.58,
  entries: 49_968,
  filed: "2026-08-07",
  in_thousands: false,
  in_doubt: false,
  group: null,
  profile: null,
  ...over,
});

const RANKING: PublicRanking = {
  period: "2026-06-30",
  previous_period: "2026-03-31",
  periods: ["2026-06-30", "2026-03-31"],
  filers: 8899,
  total: 120,
  rows: [
    row({}),
    row({
      rank: 15,
      cik: "80255",
      name: "普徠仕",
      filed_name: "PRICE T ROWE ASSOCIATES INC /MD/",
      value_usd: 999_124_702_000,
      change_usd: 134_198_000_000,
      change_pct: 15.52,
      in_thousands: true,
    }),
    row({
      rank: 47,
      cik: "1067983",
      name: "波克夏海瑟威",
      profile: "buffett",
      change_usd: null,
      change_pct: null,
    }),
  ],
};

describe("amounts as Taiwan's press writes them", () => {
  it("in 兆 and 億 with two places, or US$ in English", () => {
    expect(bigUsd("zh-TW", 6_729_538_649_155)).toBe("6.73 兆");
    expect(bigUsd("zh-TW", 999_124_702_000)).toBe("9,991.25 億");
    expect(bigUsd("zh-TW", 134_198_000_000, true)).toBe("+1,341.98 億");
    expect(bigUsd("zh-TW", -91_234_567_890, true)).toBe("−912.35 億");
    expect(bigUsd("zh-TW", 450_000_000)).toBe("4.50 億");
    expect(bigUsd("en", 6_729_538_649_155)).toBe("US$6.73T");
    expect(bigUsd("en", -91_234_567_890, true)).toBe("−US$91.23B");
  });
});

describe("機構排行", () => {
  it("lists the quarter's filers with the units said where they need saying", () => {
    render(<RankingView ranking={RANKING} lang="zh-TW" params={{}} />);
    const rows = within(screen.getByTestId("ranking-table")).getAllByTestId(
      "rank-row",
    );
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringContaining("貝萊德"),
      expect.stringContaining("普徠仕"),
      expect.stringContaining("波克夏海瑟威"),
    ]);
    expect(rows[1]!.textContent).toContain("以千美元申報，已換算");
    expect(rows[2]!.textContent).toContain("上季未申報");
    expect(
      within(rows[0]!)
        .getByRole("link", { name: "貝萊德" })
        .getAttribute("href"),
    ).toBe("/news/zh-TW/holdings/institutions/2012383?period=2026-06-30");
    expect(
      within(rows[2]!).getByRole("link", { name: "卡片" }).getAttribute("href"),
    ).toBe("/news/zh-TW/holdings/people/buffett");
    expect(
      screen.getByText(/2026 年第 2 季申報 13F 的 8,899 家機構/),
    ).toBeTruthy();
    expect(screen.getByText("共 120 家・第 1 頁，共 3 頁")).toBeTruthy();
  });

  it("keeps the search, the quarter and the sort in every link", () => {
    const params = {
      q: "rowe",
      period: "2026-03-31",
      sort: "change" as const,
      page: 2,
    };
    render(
      <RankingView
        ranking={{ ...RANKING, period: "2026-03-31" }}
        lang="zh-TW"
        params={params}
      />,
    );
    const change = screen.getByRole("link", { name: /季增減/ });
    expect(change.getAttribute("href")).toBe(
      rankingHref("zh-TW", { ...params, order: "asc", page: 1 }),
    );
    expect(change.getAttribute("aria-current")).toBe("true");
    expect(
      screen.getByRole("link", { name: "上一頁" }).getAttribute("href"),
    ).toBe(
      "/news/zh-TW/holdings/institutions?period=2026-03-31&q=rowe&sort=change",
    );
    const quarters = within(
      screen.getByRole("navigation", { name: "季度" }),
    ).getAllByRole("link");
    expect(
      quarters.map((q) => [q.textContent, q.getAttribute("aria-current")]),
    ).toEqual([
      ["2026 年第 2 季", null],
      ["2026 年第 1 季", "page"],
    ]);
    const form = screen.getByRole("search");
    expect(form.getAttribute("action")).toBe(
      "/news/zh-TW/holdings/institutions",
    );
    expect(
      (form.querySelector('input[name="period"]') as HTMLInputElement).value,
    ).toBe("2026-03-31");
    expect(
      (form.querySelector('input[name="q"]') as HTMLInputElement).defaultValue,
    ).toBe("rowe");
  });

  it("says when nothing matches, or the quarter is still being read", () => {
    render(
      <RankingView
        ranking={{ ...RANKING, rows: [], total: 0 }}
        lang="zh-TW"
        params={{ q: "無此機構" }}
      />,
    );
    expect(screen.getByText("找不到「無此機構」。")).toBeTruthy();
    cleanup();
    render(
      <RankingView
        ranking={{ ...RANKING, rows: [], total: 0 }}
        lang="zh-TW"
        params={{}}
      />,
    );
    expect(screen.getByText("這一季的資料還在整理中，稍後再看。")).toBeTruthy();
  });

  it("its first ten under the institutions' cards, with the way to all of it", () => {
    render(<TopRanking ranking={RANKING} lang="zh-TW" />);
    const top = screen.getByTestId("top-ranking");
    expect(
      within(top).getByRole("heading", { name: "機構持股排行前 10 名" }),
    ).toBeTruthy();
    expect(
      within(top)
        .getByRole("link", { name: /看完整排行/ })
        .getAttribute("href"),
    ).toBe("/news/zh-TW/holdings/institutions");
    expect(within(top).getAllByTestId("rank-row")).toHaveLength(3);
  });
});

const holding = (
  over: Partial<PublicInstitutionHolding>,
): PublicInstitutionHolding => ({
  symbol: "NVDA",
  name: "輝達",
  cusip: "67066G104",
  title_of_class: "COM",
  change: "increased",
  shares: 1_941_918_386,
  previous_shares: 1_900_000_000,
  value_usd: 388_558_000_000,
  previous_value_usd: 300_000_000_000,
  weight_pct: 5.79,
  traded_usd: 8_000_000_000,
  split: null,
  ...over,
});

const PAGE: PublicInstitution = {
  cik: "2012383",
  name: "貝萊德",
  filed_name: "BlackRock, Inc.",
  group: null,
  profile: null,
  period: "2026-06-30",
  periods: ["2026-06-30", "2026-03-31"],
  rank: 1,
  value_usd: 6_729_538_649_155,
  previous_value_usd: 5_723_531_457_401,
  change_usd: 1_006_007_191_754,
  entries: 49_968,
  filed: "2026-08-07",
  in_thousands: false,
  in_doubt: false,
  filings: [
    {
      accession: "0002012383-26-003238",
      form: "13F-HR",
      filed: "2026-08-07",
      url: "https://www.sec.gov/Archives/edgar/data/2012383/000201238326003238/0002012383-26-003238-index.htm",
      in_thousands: false,
    },
  ],
  status: "ready",
  computed_at: "2026-10-07T08:00:00Z",
  previous_period: "2026-03-31",
  stock_value_usd: 6_706_500_000_000,
  previous_stock_value_usd: 5_695_000_000_000,
  stocks: 5455,
  net_bought_usd: 125_600_000_000,
  counts: {
    new: 280,
    increased: 3437,
    decreased: 1254,
    sold_out: 238,
    unchanged: 484,
    uncertain: 40,
  },
  top: [
    holding({}),
    holding({
      symbol: "KLAC",
      name: "KLA",
      cusip: "482480100",
      split: "10:1",
      traded_usd: 71_378_715,
    }),
    holding({
      symbol: null,
      name: "HONEYWELL INTL INC",
      cusip: "438516205",
      change: "new",
      traded_usd: null,
    }),
  ],
  top_total: 50,
  bought: [
    holding({
      symbol: null,
      name: "SPACE EXPLORATION TECHN CORP",
      change: "new",
      traded_usd: 8_720_000_000,
    }),
  ],
  sold: [
    holding({
      symbol: "INTC",
      name: "英特爾",
      change: "decreased",
      traded_usd: -2_940_000_000,
    }),
  ],
  locked: false,
};

describe("an institution's page", () => {
  it("its figures, its holdings with splits and corporate actions, its buys and sells", () => {
    render(
      <InstitutionView
        page={PAGE}
        lang="zh-TW"
        loginHref="/news/zh-TW/login"
      />,
    );
    const figures = screen.getByTestId("institution-figures").textContent;
    expect(figures).toContain("6.73 兆");
    expect(figures).toContain("+1.01 兆");
    expect(figures).toContain("+1,256.00 億");
    expect(screen.getByText("2026 年第 2 季的 13F 申報・第 1 名")).toBeTruthy();
    const table = screen.getByTestId("institution-table");
    expect(table.textContent).toContain("拆股 10:1");
    expect(table.textContent).toContain("公司行動，不估");
    expect(
      within(table).getByRole("link", { name: "NVDA" }).getAttribute("href"),
    ).toBe("/news/zh-TW/stocks/NVDA");
    const moves = screen.getAllByTestId("move").map((m) => m.textContent);
    expect(moves).toEqual([
      expect.stringContaining("+87.20 億"),
      expect.stringContaining("−29.40 億"),
    ]);
    expect(screen.queryByText(/登入（免費）/)).toBeNull();
  });

  it("the ten largest for anybody, and the rest a sign-in away", () => {
    render(
      <InstitutionView
        page={{ ...PAGE, locked: true, bought: [], sold: [] }}
        lang="zh-TW"
        loginHref="/news/zh-TW/login?next=x"
      />,
    );
    expect(
      screen.getByText(/登入（免費）就能看前 50 大持股與買賣明細。/),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "登入" }).getAttribute("href"),
    ).toBe("/news/zh-TW/login?next=x");
    expect(screen.queryByRole("heading", { name: "買進最多" })).toBeNull();
  });

  it("one never opened says to come back; one filed in thousands says so", () => {
    render(
      <InstitutionView
        page={{
          ...PAGE,
          status: "queued",
          top: [],
          top_total: 0,
          in_thousands: true,
        }}
        lang="zh-TW"
        loginHref="/news/zh-TW/login"
      />,
    );
    expect(screen.getByTestId("queued").textContent).toBe(
      "這家機構的持股明細正在整理，幾分鐘後再看。",
    );
    expect(
      screen.getByText(/以千美元申報（2023 年起應以美元申報）/),
    ).toBeTruthy();
    expect(screen.queryByTestId("institution-table")).toBeNull();
  });

  it("in Taiwan's words: 持股, 加碼, 出清, 兆 — not the mainland's", () => {
    render(
      <>
        <RankingView ranking={RANKING} lang="zh-TW" params={{}} />
        <InstitutionView
          page={PAGE}
          lang="zh-TW"
          loginHref="/news/zh-TW/login"
        />
      </>,
    );
    const text = document.body.textContent ?? "";
    for (const word of [
      "持倉",
      "增倉",
      "減倉",
      "清倉",
      "萬億",
      "數據",
      "信息",
      "默認",
      "搜索",
      "收益",
    ]) {
      expect(text).not.toContain(word);
    }
  });
});
