// @vitest-environment jsdom
// AD-10's bell: how many wait, the oldest with those about to run out marked, the way to the
// inbox, one's own switch for the daily email; it closes on Esc or a click elsewhere.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/queries", async (original) => {
  const actual = await original<typeof import("@/api/queries")>();
  return { ...actual, savePrefs: vi.fn(async (prefs: { approvals_digest: boolean }) => prefs) };
});

import type { Schemas } from "@/api/client";
import { approvalsQuery, pendingCountQuery, prefsQuery, savePrefs } from "@/api/queries";

import { NotificationBell } from "./NotificationBell";

afterEach(cleanup);

const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString();
const minutesOn = (m: number) => new Date(Date.now() + m * 60_000).toISOString();

type ApprovalOut = Schemas["ApprovalOut"];
const approval = (over: Pick<ApprovalOut, "id" | "summary" | "created_at" | "expires_at">): ApprovalOut => ({
  company_id: "c1",
  kind: "article",
  ref_type: "task",
  ref_id: "t1",
  task_id: null,
  run_id: null,
  action: null,
  payload: {},
  requested_by: { kind: "system", id: "test" },
  state: "PENDING",
  decided_by: null,
  decided_at: null,
  reason: null,
  ...over,
});

function bell(personal = true, waiting = 2) {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } });
  client.setQueryData(pendingCountQuery("c1").queryKey, waiting);
  client.setQueryData(approvalsQuery("c1").queryKey, {
    pages: [
      {
        items: [
          approval({ id: "a1", summary: "核准發布：台股創新高", created_at: minutesAgo(300), expires_at: minutesOn(40) }),
          approval({ id: "a2", summary: "核准發布：美股收黑", created_at: minutesAgo(20), expires_at: minutesOn(600) }),
        ],
        total: 2,
      },
    ],
    pageParams: [null],
  });
  client.setQueryData(prefsQuery().queryKey, { approvals_digest: true });
  render(
    <QueryClientProvider client={client}>
      <NotificationBell companyId="c1" personal={personal} />
    </QueryClientProvider>,
  );
}

describe("the bell", () => {
  it("counts what waits and lists the oldest, marking what runs out soon", () => {
    bell();
    const button = screen.getByRole("button", { name: "通知：2 件等待審批" });
    expect(screen.getByTestId("bell-count").textContent).toBe("2");
    fireEvent.click(button);
    const panel = screen.getByRole("dialog", { name: "通知" });
    const [old, fresh] = within(panel).getAllByRole("listitem");
    expect(old.textContent).toContain("台股創新高");
    expect(old.textContent).toContain("已等 5 小時");
    expect(within(old).getByText("快到期")).toBeTruthy();
    expect(within(fresh).queryByText("快到期")).toBeNull();
    expect(within(panel).getByRole("link", { name: "前往審批收件匣" }).getAttribute("href")).toBe("/admin/approvals?company=c1");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("nothing waiting: no number, and says so", () => {
    bell(true, 0);
    expect(screen.queryByTestId("bell-count")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "通知" }));
    expect(screen.getByRole("dialog").textContent).toContain("沒有等待審批的項目");
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("one's own switch for the daily email; the token has none", async () => {
    bell();
    fireEvent.click(screen.getByRole("button", { name: /通知/ }));
    const daily = screen.getByRole("checkbox", { name: "每日 email 摘要" }) as HTMLInputElement;
    expect(daily.checked).toBe(true);
    fireEvent.click(daily);
    await waitFor(() => expect(savePrefs).toHaveBeenCalledWith({ approvals_digest: false }));
    await waitFor(() => expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false));
    cleanup();
    bell(false);
    fireEvent.click(screen.getByRole("button", { name: /通知/ }));
    expect(screen.queryByRole("checkbox")).toBeNull();
  });
});
