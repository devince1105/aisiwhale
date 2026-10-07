// @vitest-environment jsdom
// P3-C: a reader's Whale Coins — the page, and "鯨幣 N" in the avatar menu. What they show is
// what the API said: the balance, the month, the movements; nothing is worked out here.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { monthState, type CoinWallet } from "./coins";
import { CoinsPage } from "./CoinsPage";
import { MemberBadge } from "./MemberBadge";

const MOVEMENT = {
  id: "m1",
  kind: "MONTHLY_GRANT",
  amount: 500,
  balance_after: 550,
  occurred_at: "2026-10-07T07:00:00Z",
  month: "2026-10",
  ref_type: null,
  ref_id: null,
};

function wallet(over: Partial<CoinWallet> = {}): CoinWallet {
  return {
    balance: 550,
    tier: "vip",
    monthly: { amount: 500, cap: 1000, month: "2026-10", granted: true, grants_on: true },
    history: { items: [MOVEMENT], next_cursor: null, total: 1 },
    ...over,
  };
}

function respond(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("what the month says", () => {
  it("is coming while grants are off, given once written, next visit otherwise", () => {
    const off = wallet({ monthly: { amount: 50, cap: 100, month: "2026-10", granted: false, grants_on: false } });
    const due = wallet({ monthly: { amount: 50, cap: 100, month: "2026-10", granted: false, grants_on: true } });
    expect([monthState(off), monthState(wallet()), monthState(due)]).toEqual(["coming", "given", "next-visit"]);
  });
});

describe("the coins page", () => {
  it("shows the balance, the tier's terms, the month and the movements", async () => {
    vi.mocked(globalThis.fetch).mockImplementation(() => respond(wallet()));
    render(<CoinsPage lang="zh-TW" />);
    const balance = await screen.findByTestId("coins-balance");
    expect(balance.textContent).toContain("550");
    expect(balance.textContent).toContain("VIP 會員・每月 500 幣，持有上限 1000 幣");
    expect(screen.getByTestId("coins-month").textContent).toBe("本月已發放。");
    const row = within(screen.getByTestId("coins-history")).getByRole("listitem");
    expect(row.textContent).toContain("每月發放");
    expect(row.textContent).toContain("+500");
    expect(row.textContent).toContain("餘額 550");
    expect(screen.getByRole("link", { name: "詳見服務條款" }).getAttribute("href")).toBe("/news/zh-TW/terms");
    const [url, init] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(String(url)).toContain("/api/me/coins");
    expect((init as RequestInit).credentials).toBe("include");
  });

  it("before grants are on: nothing held, and monthly coins are coming", async () => {
    vi.mocked(globalThis.fetch).mockImplementation(() =>
      respond(
        wallet({
          balance: 0,
          tier: "free",
          monthly: { amount: 50, cap: 100, month: "2026-10", granted: false, grants_on: false },
          history: { items: [], next_cursor: null, total: 0 },
        }),
      ),
    );
    render(<CoinsPage lang="zh-TW" />);
    expect((await screen.findByTestId("coins-balance")).textContent).toContain("0");
    expect(screen.getByTestId("coins-month").textContent).toBe("每月發放即將開放。");
    expect(screen.getByText("還沒有任何鯨幣紀錄。")).toBeTruthy();
  });

  it("says a month at the cap gave nothing, and an adjustment is the platform's", async () => {
    const items = [
      { ...MOVEMENT, id: "z", amount: 0, balance_after: 1000 },
      { ...MOVEMENT, id: "a", kind: "ADMIN_ADJUSTMENT", amount: -5, balance_after: 995, month: null },
    ];
    vi.mocked(globalThis.fetch).mockImplementation(() =>
      respond(wallet({ history: { items, next_cursor: null, total: 2 } })),
    );
    render(<CoinsPage lang="zh-TW" />);
    const rows = within(await screen.findByTestId("coins-history")).getAllByRole("listitem");
    expect(rows[0].textContent).toContain("已達上限，未發放");
    expect(rows[1].textContent).toContain("平台調整");
    expect(rows[1].textContent).toContain("-5");
  });

  it("loads the next page with the cursor it was given", async () => {
    const second = { ...MOVEMENT, id: "m2", kind: "SPEND", amount: -5, balance_after: 545, month: null };
    vi.mocked(globalThis.fetch)
      .mockImplementationOnce(() => respond(wallet({ history: { items: [MOVEMENT], next_cursor: "c1", total: 2 } })))
      .mockImplementationOnce(() => respond(wallet({ history: { items: [second], next_cursor: null, total: 2 } })));
    render(<CoinsPage lang="zh-TW" />);
    fireEvent.click(await screen.findByRole("button", { name: "載入更多" }));
    await waitFor(() => expect(within(screen.getByTestId("coins-history")).getAllByRole("listitem")).toHaveLength(2));
    expect(String(vi.mocked(globalThis.fetch).mock.calls[1][0])).toContain("cursor=c1");
    expect(screen.queryByRole("button", { name: "載入更多" })).toBeNull();
  });

  it("sends a visitor who is not signed in to sign in, and back here", async () => {
    const replace = vi.fn();
    Object.defineProperty(window, "location", { value: { replace }, writable: true });
    vi.mocked(globalThis.fetch).mockImplementation(() => respond({ detail: "sign in" }, 401));
    render(<CoinsPage lang="en" />);
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith(`/news/en/login?next=${encodeURIComponent("/news/en/coins")}`),
    );
  });

  it("says so when the coins cannot be read", async () => {
    vi.mocked(globalThis.fetch).mockImplementation(() => respond({}, 500));
    render(<CoinsPage lang="en" />);
    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
  });

  it("in English", async () => {
    vi.mocked(globalThis.fetch).mockImplementation(() => respond(wallet()));
    render(<CoinsPage lang="en" />);
    expect((await screen.findByTestId("coins-balance")).textContent).toContain("VIP member・500 a month, up to 1000 held");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("My Whale Coins");
  });
});

describe("鯨幣 N in the avatar menu", () => {
  const ME = {
    reader_id: "r",
    email: "reader@example.com",
    email_verified: true,
    member_until: null,
    tier: "free",
    capabilities: ["coins", "read_sign_in_sections", "watchlist"],
  };

  function api(coins: () => Promise<Response>, me: unknown = ME) {
    vi.mocked(globalThis.fetch).mockImplementation((input) =>
      String(input).includes("/api/me/coins") ? coins() : respond(me),
    );
  }

  const coinCalls = () => vi.mocked(globalThis.fetch).mock.calls.filter(([url]) => String(url).includes("/api/me/coins"));

  it("asks for the balance only when the menu opens, and links to the page", async () => {
    api(() => respond(wallet({ balance: 50 })));
    render(<MemberBadge lang="zh-TW" />);
    const avatar = await screen.findByRole("button", { name: "帳號：reader@example.com" });
    expect(coinCalls()).toHaveLength(0);
    fireEvent.click(avatar);
    const link = await screen.findByTestId("coins-link");
    await waitFor(() => expect(link.textContent).toBe("鯨幣 50"));
    expect(link.getAttribute("href")).toBe("/news/zh-TW/coins");
    expect(String(coinCalls()[0][0])).toContain("limit=1");
  });

  it("says only 鯨幣 when the balance cannot be read", async () => {
    api(() => respond({}, 500));
    render(<MemberBadge lang="zh-TW" />);
    fireEvent.click(await screen.findByRole("button", { name: "帳號：reader@example.com" }));
    const link = await screen.findByTestId("coins-link");
    await waitFor(() => expect(coinCalls()).toHaveLength(1));
    expect(link.textContent).toBe("鯨幣");
  });

  it("is not offered without the coins capability", async () => {
    api(() => respond(wallet()), { ...ME, capabilities: ["watchlist"] });
    render(<MemberBadge lang="zh-TW" />);
    fireEvent.click(await screen.findByRole("button", { name: "帳號：reader@example.com" }));
    expect(screen.queryByTestId("coins-link")).toBeNull();
    expect(coinCalls()).toHaveLength(0);
  });
});
