// @vitest-environment jsdom
// VIP given by an admin for internal testing (D-228, P2-B): the requests the page sends, and a
// comp's status and its revoke, which asks for a reason before anything is sent.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// revokeComp is the real one, except where a test says what it answers
vi.mock("@/api/queries", async (original) => {
  const actual = await original<typeof import("@/api/queries")>();
  return { ...actual, revokeComp: vi.fn(actual.revokeComp) };
});

import { createApiClient } from "@/api/client";
import { compsQuery, grantComp, revokeComp, type Comp } from "@/api/queries";

import { compStatus, CompsTable, localInput } from "./CompsPage";

afterEach(cleanup);

const FUTURE = "2099-01-01T00:00:00Z";
const COMP: Comp = {
  id: "g1",
  reader_id: "r1",
  email: "tester@example.com",
  source: "admin_comp",
  started_at: "2026-10-06T00:00:00Z",
  expires_at: FUTURE,
  reason: "內測鯨幣流程",
  actor: { kind: "human", id: "admin:a1" },
  revoked_at: null,
  revoked_by: null,
  revoke_reason: null,
  running: true,
};
const REVOKED: Comp = {
  ...COMP,
  id: "g2",
  running: false,
  revoked_at: "2026-10-07T00:00:00Z",
  revoked_by: { kind: "human", id: "admin:a1" },
  revoke_reason: "測完了",
};
const LAPSED: Comp = { ...COMP, id: "g3", running: false, expires_at: "2026-10-05T00:00:00Z" };

function recorder() {
  const requests: { method: string; url: string; body: unknown }[] = [];
  const api = createApiClient({
    baseUrl: "http://api",
    fetch: (async (r: Request) => {
      requests.push({ method: r.method, url: r.url, body: r.method === "GET" ? null : await r.json() });
      return new Response(r.method === "GET" ? "[]" : JSON.stringify(COMP), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as typeof fetch,
  });
  return { api, requests };
}

describe("the comps page's requests", () => {
  it("lists, grants and revokes where the API expects them", async () => {
    const { api, requests } = recorder();
    await compsQuery("aisiwhale", true, {}, api).queryFn!({} as never);
    await grantComp({ email: "tester@example.com", until: FUTURE, reason: "內測", company: "aisiwhale" }, api);
    await revokeComp("g1", "測完了", api);
    expect(requests).toEqual([
      { method: "GET", url: "http://api/api/admin/memberships/comps?company=aisiwhale&running=true&limit=50", body: null },
      {
        method: "POST",
        url: "http://api/api/admin/memberships/comps",
        body: { email: "tester@example.com", until: FUTURE, reason: "內測", company: "aisiwhale" },
      },
      { method: "POST", url: "http://api/api/admin/memberships/comps/g1/revoke", body: { reason: "測完了" } },
    ]);
  });
});

describe("a comp in the table", () => {
  function show(comps: Comp[], onRevoked = vi.fn()) {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <CompsTable comps={comps} onRevoked={onRevoked} />
      </QueryClientProvider>,
    );
  }

  it("says what it is doing now, as the server said it", () => {
    expect([COMP, REVOKED, LAPSED].map(compStatus)).toEqual(["有效中", "已撤銷", "已到期"]);
    show([COMP, REVOKED, LAPSED]);
    expect(screen.getByTestId("comp-g2").textContent).toContain("撤銷理由：測完了");
    expect(within(screen.getByTestId("comp-g1")).getByRole("button", { name: "撤銷" })).toBeTruthy();
    expect(within(screen.getByTestId("comp-g2")).queryByRole("button", { name: "撤銷" })).toBeNull();
    expect(within(screen.getByTestId("comp-g3")).queryByRole("button", { name: "撤銷" })).toBeNull();
  });

  it("asks why before it can be revoked", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    show([COMP]);
    fireEvent.click(screen.getByRole("button", { name: "撤銷" }));
    const confirm = screen.getByRole("button", { name: "確認撤銷" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.change(screen.getByPlaceholderText("撤銷理由（必填）"), { target: { value: "  " } });
    expect(confirm.disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(screen.queryByRole("button", { name: "確認撤銷" })).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
    fetchMock.mockRestore();
  });

  it("says when there is nothing to show", () => {
    show([]);
    expect(screen.getByText("沒有授予紀錄。")).toBeTruthy();
  });
});

describe("the date a comp ends", () => {
  it("is offered in the browser's own time, days from now", () => {
    const now = new Date(2026, 9, 6, 9, 5);
    expect(localInput(30, now)).toBe("2026-11-05T09:05");
  });
});

describe("ending several at once (AD-05)", () => {
  it("revokes only the checked ones still running, each with the one reason", async () => {
    const sent: [string, string][] = [];
    vi.mocked(revokeComp).mockImplementation(async (id, reason) => {
      sent.push([id, reason]);
      return COMP;
    });
    const onRevoked = vi.fn();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <CompsTable comps={[COMP, { ...COMP, id: "g4", email: "b@example.com" }, REVOKED]} onRevoked={onRevoked} />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "全選這一頁" }));
    fireEvent.click(screen.getByRole("button", { name: "撤銷選取的授予" }));
    const ask = screen.getByRole("dialog", { name: "撤銷 2 筆 VIP 授予？" });
    expect(ask.textContent).toContain("tester@example.com、b@example.com");
    fireEvent.change(within(ask).getByPlaceholderText("撤銷理由（必填，套用到每一筆）"), { target: { value: "測完了" } });
    fireEvent.click(within(ask).getByRole("button", { name: "確認撤銷" }));
    await vi.waitFor(() => expect(onRevoked).toHaveBeenCalled());
    expect(sent).toEqual([
      ["g1", "測完了"],
      ["g4", "測完了"],
    ]);
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    vi.mocked(revokeComp).mockRestore();
  });
});
