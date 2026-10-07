// @vitest-environment jsdom
// HD-12: Taiwan's three institutional investors — a stock page's days in 張 and its foreign
// ownership, and a trading day's ranking with the groups and sides kept in its links.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { PublicFlowRanking, PublicTwFlows } from "./api";
import {
  lots,
  MarketSwitch,
  TwFlowsSection,
  twRankingHref,
  TwRankingView,
} from "./TwFlows";

afterEach(cleanup);

const TSMC: PublicTwFlows = {
  days: [
    {
      day: "2026-10-06",
      foreign: -1_672_231,
      trust: 154_586,
      dealer: 395_975,
      total: -1_121_670,
      foreign_ratio: 69.2,
    },
    {
      day: "2026-10-05",
      foreign: 2_400_000,
      trust: 0,
      dealer: -10_000,
      total: 2_390_000,
      foreign_ratio: 69.18,
    },
  ],
  sums: [
    {
      days: 5,
      foreign: 12_345_000,
      trust: -600_000,
      dealer: 50_000,
      total: 11_795_000,
    },
    {
      days: 20,
      foreign: -40_123_456,
      trust: 1_000_000,
      dealer: 0,
      total: -39_123_456,
    },
  ],
  foreign_ratio: 69.2,
  foreign_ratio_day: "2026-10-06",
  foreign_ratio_change: -0.35,
  exchange: "TWSE",
};

describe("a Taiwan stock's 三大法人", () => {
  it("counts in 張, signed", () => {
    expect(lots("zh-TW", -1_672_231)).toBe("−1,672");
    expect(lots("zh-TW", 154_586)).toBe("+155");
    expect(lots("zh-TW", 400)).toBe("0");
    expect(lots("zh-TW", null)).toBe("—");
  });

  it("its days, its sums and its foreign ownership", () => {
    render(<TwFlowsSection flows={TSMC} lang="zh-TW" />);
    expect(
      screen.getByRole("heading", { name: "三大法人買賣超" }),
    ).toBeTruthy();
    expect(screen.getByTestId("foreign-ratio").textContent).toContain("69.20%");
    expect(screen.getByTestId("foreign-ratio").textContent).toContain(
      "近 20 日 −0.35 個百分點",
    );
    const rows = within(screen.getByTestId("flow-days"))
      .getAllByRole("row")
      .slice(1);
    expect(rows[0]!.textContent).toContain("−1,672");
    expect(rows[0]!.textContent).toContain("+155");
    expect(rows[0]!.textContent).toContain("−1,122");
    expect(within(rows[0]!).getByText("−1,672").className).toContain(
      "text-fall",
    );
    const sums = screen.getByTestId("flow-sums").textContent;
    expect(sums).toContain("近 5 日 +12,345");
    expect(sums).toContain("近 20 日 −40,123");
    expect(screen.getByText("單位：張（1 張 = 1,000 股）")).toBeTruthy();
  });

  it("says when there is nothing yet", () => {
    render(<TwFlowsSection flows={null} lang="zh-TW" />);
    expect(screen.getByText("這檔股票還沒有三大法人的資料。")).toBeTruthy();
  });
});

const RANKING: PublicFlowRanking = {
  day: "2026-10-06",
  days: ["2026-10-06", "2026-10-05"],
  group: "foreign",
  side: "buy",
  rows: [
    {
      rank: 1,
      symbol: "2454",
      name: "聯發科",
      exchange: "TWSE",
      net: 3_000_000,
      foreign_ratio: 55.95,
    },
    {
      rank: 2,
      symbol: "6488",
      name: "環球晶",
      exchange: "TPEx",
      net: 500_000,
      foreign_ratio: 36.25,
    },
  ],
};

describe("the Taiwan ranking", () => {
  it("lists the day's most bought, each linked to its page", () => {
    render(<TwRankingView ranking={RANKING} lang="zh-TW" params={{}} />);
    expect(
      screen.getByRole("heading", { level: 1, name: "台股三大法人買賣超排行" }),
    ).toBeTruthy();
    const rows = screen.getAllByTestId("tw-rank-row");
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringContaining("聯發科2454+3,000"),
      expect.stringContaining("環球晶6488+500"),
    ]);
    expect(
      within(rows[0]!)
        .getByRole("link", { name: "聯發科" })
        .getAttribute("href"),
    ).toBe("/news/zh-TW/stocks/2454");
  });

  it("keeps the group, the side and the day in its links", () => {
    render(
      <TwRankingView
        ranking={{
          ...RANKING,
          day: "2026-10-05",
          group: "trust",
          side: "sell",
        }}
        lang="zh-TW"
        params={{ day: "2026-10-05", group: "trust", side: "sell" }}
      />,
    );
    expect(
      screen.getByRole("link", { name: "自營商" }).getAttribute("href"),
    ).toBe(
      "/news/zh-TW/holdings/institutions/tw?day=2026-10-05&group=dealer&side=sell",
    );
    expect(
      screen.getByRole("link", { name: "買超" }).getAttribute("href"),
    ).toBe("/news/zh-TW/holdings/institutions/tw?day=2026-10-05&group=trust");
    expect(
      screen.getByRole("link", { name: "賣超" }).getAttribute("aria-current"),
    ).toBe("page");
    expect(twRankingHref("zh-TW")).toBe("/news/zh-TW/holdings/institutions/tw");
  });

  it("says when nothing has been read yet", () => {
    render(
      <TwRankingView
        ranking={{
          day: null,
          days: [],
          group: "foreign",
          side: "buy",
          rows: [],
        }}
        lang="zh-TW"
        params={{}}
      />,
    );
    expect(
      screen.getByText("還沒有三大法人的資料，交易日下午公布後更新。"),
    ).toBeTruthy();
  });

  it("switches between the US filers and Taiwan's institutional investors", () => {
    render(<MarketSwitch lang="zh-TW" market="tw" />);
    expect(
      screen.getByRole("link", { name: "美股（13F）" }).getAttribute("href"),
    ).toBe("/news/zh-TW/holdings/institutions");
    expect(
      screen
        .getByRole("link", { name: "台股（三大法人）" })
        .getAttribute("aria-current"),
    ).toBe("page");
  });
});
