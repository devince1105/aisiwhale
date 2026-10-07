// @vitest-environment jsdom
// P3-C-2: Whale Coins in the back office — opening the page checks the ledger and writes nothing;
// an adjustment is asked for with what it will change, past the cap only when overridden, and a
// retry is the same request.
import { QueryClient, QueryClientProvider, queryOptions } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const calls = vi.hoisted(() => ({
  reconcile: { ok: true, problems: [] as string[], totals: { entries: 0, held_by_readers: 1234 } as Record<string, number> },
  wallet: null as unknown,
  walletError: null as Error | null,
  adjust: vi.fn(),
}));

vi.mock("@/api/queries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/queries")>();
  return {
    ...actual,
    coinReconcileQuery: () =>
      queryOptions({ queryKey: ["coins", "reconcile"], queryFn: async () => calls.reconcile }),
    coinWalletQuery: (company: string, email: string, cursor: string | null) =>
      queryOptions({
        queryKey: ["coins", "wallet", company, email, cursor],
        queryFn: async () => {
          if (calls.walletError) throw calls.walletError;
          return calls.wallet as never;
        },
        retry: false,
      }),
    adjustCoins: calls.adjust,
  };
});

import { CompanyCoins, preview } from "./CoinsAdminPage";

const COMPANY = { id: "c1", slug: "aisiwhale", name: "艾矽鯨", agents: 0 } as never;

function wallet(balance = 90, tier: "free" | "vip" = "free", cap = 100) {
  return {
    reader_id: "r1",
    email: "reader@example.com",
    tier,
    cap,
    balance,
    history: {
      items: [
        {
          id: "t1",
          kind: "ADMIN_ADJUSTMENT",
          amount: 90,
          balance_after: 90,
          occurred_at: "2026-10-07T07:00:00Z",
          requested: null,
          cap: 100,
          idempotency_key: "adj:x",
          reverses_txn_id: null,
          ref_type: null,
          ref_id: null,
          actor: { kind: "human", id: "admin:a1" },
          reason: "setup",
          meta: { override_cap: false },
        },
      ],
      next_cursor: null,
      total: 1,
    },
  };
}

function show() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <CompanyCoins company={COMPANY} />
    </QueryClientProvider>,
  );
}

async function lookUp(email = "Reader@Example.com") {
  fireEvent.change(screen.getByLabelText("讀者 Email"), { target: { value: email } });
  fireEvent.click(screen.getByRole("button", { name: "查詢" }));
  return screen.findByTestId("coins-wallet");
}

function fill(amount: string, reason = "goodwill") {
  fireEvent.change(screen.getByLabelText("數量（正數加、負數扣）"), { target: { value: amount } });
  fireEvent.change(screen.getByLabelText("理由（必填，讀者看不到）"), { target: { value: reason } });
}

beforeEach(() => {
  calls.reconcile = { ok: true, problems: [], totals: { entries: 0, held_by_readers: 1234 } };
  calls.wallet = wallet();
  calls.walletError = null;
  calls.adjust.mockReset();
  calls.adjust.mockResolvedValue({});
});
afterEach(cleanup);

describe("what an adjustment would do", () => {
  it("says the balance after, past the cap only going up, below zero only going down", () => {
    expect(preview({ balance: 90, cap: 100 }, 10)).toEqual({ after: 100, pastCap: false, belowZero: false });
    expect(preview({ balance: 90, cap: 100 }, 11)).toEqual({ after: 101, pastCap: true, belowZero: false });
    expect(preview({ balance: 1005, cap: 1000 }, -5)).toEqual({ after: 1000, pastCap: false, belowZero: false });
    expect(preview({ balance: 3, cap: 100 }, -4)).toEqual({ after: -1, pastCap: false, belowZero: true });
  });
});

describe("opening the page", () => {
  it("checks the ledger and writes nothing", async () => {
    show();
    const card = await screen.findByTestId("coins-reconcile");
    await waitFor(() => expect(card.textContent).toContain("帳務一致"));
    expect(card.textContent).toContain("1,234 幣");
    expect(calls.adjust).not.toHaveBeenCalled();
  });

  it("lists every problem when the ledger does not add up", async () => {
    calls.reconcile = { ok: false, problems: ["wallet of reader r1 says 11, entries 10"], totals: { entries: 0 } };
    show();
    const card = await screen.findByTestId("coins-reconcile");
    await waitFor(() => expect(card.textContent).toContain("帳務不一致"));
    expect(card.textContent).toContain("wallet of reader r1 says 11, entries 10");
  });
});

describe("a reader's wallet", () => {
  it("is found by address: tier, cap, balance and the movements with who and why", async () => {
    show();
    const card = await lookUp();
    expect(card.textContent).toContain("reader@example.com");
    expect(card.textContent).toContain("上限 100");
    expect(card.textContent).toContain("90 幣");
    const row = screen.getByTestId("coin-t1");
    expect(row.textContent).toContain("平台調整");
    expect(row.textContent).toContain("admin:a1");
    expect(row.textContent).toContain("setup");
  });

  it("says when nobody has the address", async () => {
    calls.walletError = new Error("404 Not Found: no reader has this address");
    show();
    fireEvent.change(screen.getByLabelText("讀者 Email"), { target: { value: "nobody@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "查詢" }));
    expect((await screen.findByRole("alert")).textContent).toContain("找不到讀者 nobody@example.com");
  });
});

describe("an adjustment", () => {
  it("is not offered for 0, more than 10,000 either way, or no reason", async () => {
    show();
    await lookUp();
    const submit = screen.getByRole("button", { name: "調整" }) as HTMLButtonElement;
    for (const [amount, reason] of [["0", "x"], ["10001", "x"], ["-10001", "x"], ["5", "  "], ["1.5", "x"]]) {
      fill(amount, reason);
      expect(submit.disabled).toBe(true);
    }
    fill("10000", "x");
    expect(submit.disabled).toBe(false);
  });

  it("asks first, saying what will change, then sends it once with its request id", async () => {
    show();
    await lookUp();
    fill("10");
    fireEvent.click(screen.getByRole("button", { name: "調整" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toContain("目前 90 → 調整後 100");
    expect(dialog.textContent).toContain("理由：goodwill");
    expect(calls.adjust).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "確認調整" }));
    await waitFor(() => expect(calls.adjust).toHaveBeenCalledTimes(1));
    const [body] = calls.adjust.mock.calls[0];
    expect(body).toMatchObject({ email: "reader@example.com", amount: 10, reason: "goodwill", override_cap: false, company: "aisiwhale" });
    expect(body.request_id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("asks in a form of its own, never one inside the adjustment form", async () => {
    // a form within a form: a real browser submits the inner one natively — a reload, no
    // adjustment — which is how the first version failed in production (jsdom does not submit)
    show();
    await lookUp();
    fill("1");
    fireEvent.click(screen.getByRole("button", { name: "調整" }));
    const dialog = await screen.findByRole("dialog");
    expect(document.querySelectorAll("form form")).toHaveLength(0);
    const confirm = within(dialog).getByRole("button", { name: "確認調整" }) as HTMLButtonElement;
    expect(confirm.form).not.toBeNull();
    expect(dialog.contains(confirm.form)).toBe(true);
    expect(confirm.form?.closest("form[aria-label='調整鯨幣']")).toBeNull();
  });

  it("past the cap: says so, and asks again in red only when overridden", async () => {
    show();
    await lookUp();
    fill("11");
    expect(screen.getByRole("status").textContent).toContain("會超過一般會員上限 100；要超過請勾選 override");
    fireEvent.click(screen.getByLabelText("超過上限（override）"));
    fireEvent.click(screen.getByRole("button", { name: "調整" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByTestId("override-warning").textContent).toBe("這會超過一般會員上限 100，確定要 override 嗎？");
    fireEvent.click(within(dialog).getByRole("button", { name: "確認調整" }));
    await waitFor(() => expect(calls.adjust).toHaveBeenCalledTimes(1));
    expect(calls.adjust.mock.calls[0][0]).toMatchObject({ amount: 11, override_cap: true });
  });

  it("a retry after a failure is the same request; the next adjustment is a new one", async () => {
    calls.adjust.mockRejectedValueOnce(new Error("503 Service Unavailable")).mockResolvedValue({});
    show();
    await lookUp();
    fill("5");
    fireEvent.click(screen.getByRole("button", { name: "調整" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "確認調整" }));
    expect((await within(dialog).findByRole("alert")).textContent).toContain("503");
    fireEvent.click(within(dialog).getByRole("button", { name: "確認調整" }));
    await waitFor(() => expect(calls.adjust).toHaveBeenCalledTimes(2));
    const [first, second] = calls.adjust.mock.calls.map(([body]) => body.request_id);
    expect(second).toBe(first);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    fill("6");
    fireEvent.click(screen.getByRole("button", { name: "調整" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "確認調整" }));
    await waitFor(() => expect(calls.adjust).toHaveBeenCalledTimes(3));
    expect(calls.adjust.mock.calls[2][0].request_id).not.toBe(first);
  });
});
