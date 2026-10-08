// @vitest-environment jsdom
// P4 (D-249): a COIN story's paywall, its badge on a list, and the wallet naming what was
// unlocked. What it costs, what the reader holds and whether it was theirs are the API's.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const router = vi.hoisted(() => ({ refresh: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

import { CoinBadge } from "./CoinBadge";
import { CoinsPage } from "./CoinsPage";
import { CoinUnlock } from "./CoinUnlock";
import { MembersOnly } from "./MembersOnly";
import { forgetUnlocked } from "./unlocks";

const ARTICLE = "0199a000-0000-7000-8000-000000000001";
const PATH = "/news/zh-TW/articles/coin-story";

function respond(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
}

function wallet(balance: number, items: unknown[] = []) {
  return {
    balance,
    tier: "free",
    monthly: { amount: 50, cap: 300, month: "2026-10", granted: true, grants_on: true },
    history: { items, next_cursor: null, total: items.length },
  };
}

/** The API: the wallet holds ``balance``; an unlock answers ``unlock`` (status, body). */
function api(balance: number | "signed-out", unlock: [number, unknown] = [201, {}]) {
  vi.mocked(globalThis.fetch).mockImplementation((input, init) => {
    const url = String(input);
    if (url.includes("/api/me/coins")) return balance === "signed-out" ? respond({ detail: "sign in" }, 401) : respond(wallet(balance));
    if (url.includes("/api/me/unlocks/") && init?.method === "POST") return respond(unlock[1], unlock[0]);
    return respond({}, 404);
  });
}

function show() {
  render(<CoinUnlock lang="zh-TW" path={PATH} articleId={ARTICLE} price={5} company="aisiwhale" />);
}

function unlockCalls() {
  return vi.mocked(globalThis.fetch).mock.calls.filter(([url, init]) => String(url).includes("/api/me/unlocks/") && init?.method === "POST");
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
  router.refresh.mockReset();
  router.push.mockReset();
  forgetUnlocked();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a COIN story's paywall", () => {
  it("says what it costs and what the reader holds, and asks before spending", async () => {
    api(50, [201, { article_id: ARTICLE, unlocked: true, already: false, price: 5, balance: 45 }]);
    show();
    const wall = screen.getByTestId("coin-only");
    expect(wall.textContent).toContain("這篇需要 5 鯨幣解鎖");
    expect((await screen.findByTestId("coin-balance")).textContent).toBe("你目前有 50 幣");

    fireEvent.click(screen.getByRole("button", { name: "用 5 幣解鎖" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toContain("用 5 幣解鎖這篇？");
    expect(dialog.textContent).toContain("目前 50 幣 → 解鎖後 45 幣");
    expect(unlockCalls()).toHaveLength(0);

    fireEvent.click(within(dialog).getByRole("button", { name: "確認解鎖" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalledTimes(1));
    const [[url, init]] = unlockCalls();
    expect(String(url)).toContain(`/api/me/unlocks/${ARTICLE}`);
    expect((init as RequestInit).credentials).toBe("include");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("asks with two buttons and no form, so it is never a form inside another", async () => {
    api(50);
    render(
      <form>
        <CoinUnlock lang="zh-TW" path={PATH} articleId={ARTICLE} price={5} />
      </form>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "用 5 幣解鎖" }));
    expect(document.querySelectorAll("form form")).toHaveLength(0);
    for (const button of within(screen.getByRole("dialog")).getAllByRole("button")) {
      expect((button as HTMLButtonElement).type).toBe("button"); // never submits an outer form
    }
  });

  it("cancelling spends nothing", async () => {
    api(50);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "用 5 幣解鎖" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "取消" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(unlockCalls()).toHaveLength(0);
  });

  it("not signed in: the button signs in and comes back to the story", async () => {
    api("signed-out");
    show();
    const link = await screen.findByRole("link", { name: "登入後解鎖" });
    expect(link.getAttribute("href")).toBe(`/news/zh-TW/login?next=${encodeURIComponent(PATH)}`);
    expect(screen.queryByRole("button", { name: "用 5 幣解鎖" })).toBeNull();
  });

  it("too few coins: how many more, and the wallet", async () => {
    api(3);
    show();
    expect((await screen.findByRole("status")).textContent).toContain("還差 2 幣");
    expect(screen.getByRole("link", { name: "查看我的鯨幣" }).getAttribute("href")).toBe("/news/zh-TW/coins");
    expect(screen.queryByRole("button", { name: "用 5 幣解鎖" })).toBeNull();
  });

  it("spent elsewhere meanwhile: the server's 402 says how many more", async () => {
    api(5, [402, { detail: "not enough coins", need: 5, held: 1 }]);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "用 5 幣解鎖" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "確認解鎖" }));
    expect((await screen.findByRole("status")).textContent).toContain("還差 4 幣");
    expect(router.refresh).not.toHaveBeenCalled();
  });

  it("a failure says so and stays open to try again", async () => {
    api(50, [500, {}]);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "用 5 幣解鎖" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "確認解鎖" }));
    expect((await within(screen.getByRole("dialog")).findByRole("alert")).textContent).toContain("暫時無法解鎖");
    expect(router.refresh).not.toHaveBeenCalled();
  });

  it("is what MembersOnly shows for a COIN lock", async () => {
    api(50);
    render(<MembersOnly lang="en" path={PATH} lock="coin" articleId={ARTICLE} coinPrice={7} />);
    expect(screen.getByTestId("coin-only").textContent).toContain("Unlock this story for 7 Whale Coins");
    expect(screen.queryByTestId("members-only")).toBeNull();
    expect(await screen.findByRole("button", { name: "Unlock for 7 coins" })).toBeTruthy();
  });
});

describe("a COIN story on a list", () => {
  it("says what it costs, or 已解鎖 for a reader who unlocked it — asking once for all of them", async () => {
    vi.mocked(globalThis.fetch).mockImplementation(() => respond([{ article_id: ARTICLE, price_paid: 5, unlocked_at: "2026-10-08T00:00:00Z" }]));
    render(
      <>
        <CoinBadge articleId={ARTICLE} price={5} lang="zh-TW" />
        <CoinBadge articleId="0199a000-0000-7000-8000-000000000002" price={9} lang="zh-TW" />
      </>,
    );
    const [mine, other] = screen.getAllByTestId("coin-badge");
    expect(mine.textContent).toBe("5 幣");
    await waitFor(() => expect(mine.textContent).toBe("已解鎖"));
    expect(other.textContent).toBe("9 幣");
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledTimes(1);
  });

  it("not signed in: the price", async () => {
    vi.mocked(globalThis.fetch).mockImplementation(() => respond({ detail: "sign in" }, 401));
    render(<CoinBadge articleId={ARTICLE} price={5} lang="en" />);
    await waitFor(() => expect(vi.mocked(globalThis.fetch)).toHaveBeenCalled());
    expect(screen.getByTestId("coin-badge").textContent).toBe("5 coins");
  });
});

describe("the wallet", () => {
  it("names the story a spend unlocked, with a link while it is on the site", async () => {
    const spend = (id: string, path: string | null) => ({
      id, kind: "SPEND", amount: -5, balance_after: 45, occurred_at: "2026-10-08T00:00:00Z", month: null,
      ref_type: "article", ref_id: ARTICLE, article: { title: `Story ${id}`, path },
    });
    vi.mocked(globalThis.fetch).mockImplementation(() => respond(wallet(45, [spend("a", PATH), spend("b", null)])));
    render(<CoinsPage lang="zh-TW" />);
    const [on, off] = await screen.findAllByTestId("coin-article");
    expect(on.textContent).toBe("Story a");
    expect(on.getAttribute("href")).toBe(PATH);
    expect(off.textContent).toBe("Story b");
    expect(off.getAttribute("href")).toBeNull();
  });
});
