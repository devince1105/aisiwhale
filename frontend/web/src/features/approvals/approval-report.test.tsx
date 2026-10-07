// @vitest-environment jsdom
// AD-12's report: the totals as tiles (rates of what was decided, hours or minutes), what waits
// too long, the same by kind (named, not the token) and by who decided; the window on the address.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

let search = new URLSearchParams("company=c1");
const push = vi.fn((href: string) => (search = new URLSearchParams(href.split("?")[1] ?? "")));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: push, back: vi.fn() }),
  usePathname: () => "/admin/approvals/report",
  useSearchParams: () => search,
}));
vi.mock("@/features/company/CompanyScope", async (original) => {
  const actual = await original<typeof import("@/features/company/CompanyScope")>();
  return { ...actual, CompanyScope: ({ children }: { children: (c: { id: string; name: string }) => React.ReactNode }) => children({ id: "c1", name: "艾矽鯨" }) };
});

import { approvalReportQuery, type ApprovalReport } from "@/api/queries";

import { ApprovalReportPage } from "./ApprovalReportPage";

afterEach(cleanup);

const NONE = { decided: 0, approved: 0, returned: 0, rejected: 0, expired: 0, median_hours: null, p90_hours: null };
const REPORT: ApprovalReport = {
  since: "2026-09-07T00:00:00Z",
  days: 30,
  total: { decided: 5, approved: 3, returned: 1, rejected: 1, expired: 1, median_hours: 2, p90_hours: 7.6 },
  kinds: [
    { kind: "article", decided: 4, approved: 3, returned: 1, rejected: 0, expired: 1, median_hours: 3, p90_hours: 7.6 },
    { kind: "command", decided: 1, approved: 0, returned: 0, rejected: 1, expired: 0, median_hours: 0.5, p90_hours: 0.5 },
  ],
  deciders: [{ actor: { kind: "human", id: "operator" }, label: "操作者權杖", decided: 4, approved: 2, returned: 1, rejected: 1 }],
  pending: 2,
  stuck_hours: 24,
  stuck: [{ id: "a1", kind: "article", summary: "核准發布：等了兩天", waited_hours: 48, expires_at: null }],
  stuck_total: 1,
};

function page(reports: Record<number, ApprovalReport>) {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } });
  for (const [days, report] of Object.entries(reports)) client.setQueryData(approvalReportQuery("c1", Number(days)).queryKey, report);
  return render(
    <QueryClientProvider client={client}>
      <ApprovalReportPage />
    </QueryClientProvider>,
  );
}

it("shows the totals, what waits too long, by kind and by who decided", () => {
  search = new URLSearchParams("company=c1");
  page({ 30: REPORT });
  const tiles = screen.getByRole("region", { name: "總覽" });
  expect(within(tiles).getByText("60%")).toBeTruthy(); // 3 of 5 approved
  expect(within(tiles).getByText("退回 20%・駁回 20%")).toBeTruthy();
  expect(within(tiles).getByText("2.0 小時")).toBeTruthy();
  expect(within(tiles).getByText("P90 7.6 小時")).toBeTruthy();

  const waiting = screen.getByRole("region", { name: "等待中" });
  expect(within(waiting).getByText("等待中 2 件，超過 24 小時 1 件")).toBeTruthy();
  expect(within(waiting).getByText("核准發布：等了兩天")).toBeTruthy();
  expect(within(waiting).getByRole("link", { name: "到審批收件匣處理" }).getAttribute("href")).toBe("/admin/approvals?company=c1");

  const kinds = within(screen.getByRole("region", { name: "依種類" })).getAllByRole("row");
  expect(within(kinds[1]).getByText("文章")).toBeTruthy();
  expect(within(kinds[1]).getByText("75%")).toBeTruthy();
  expect(within(kinds[2]).getByText("指令")).toBeTruthy();
  expect(within(kinds[2]).getAllByText("30 分鐘")).toHaveLength(2); // under an hour, in minutes

  const deciders = within(screen.getByRole("region", { name: "依決定者" })).getAllByRole("row");
  expect(within(deciders[1]).getByText("操作者權杖")).toBeTruthy();
  expect(within(deciders[1]).getByText("50%")).toBeTruthy();
});

it("keeps the window on the address, and says when there is nothing", () => {
  search = new URLSearchParams("company=c1");
  const empty: ApprovalReport = { ...REPORT, days: 7, total: NONE, kinds: [], deciders: [], pending: 0, stuck: [], stuck_total: 0 };
  const { rerender } = page({ 30: REPORT, 7: empty });
  expect(screen.getByRole("button", { name: "近 30 天" }).getAttribute("aria-pressed")).toBe("true");
  fireEvent.click(screen.getByRole("button", { name: "近 7 天" }));
  expect(push).toHaveBeenLastCalledWith(expect.stringContaining("days=7"), { scroll: false });
  rerender(<></>);
  page({ 7: empty });
  expect(screen.getByRole("button", { name: "近 7 天" }).getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByText("近 7 天沒有決定或逾時的審批。")).toBeTruthy();
  expect(screen.getByText("沒有等超過 24 小時的審批。")).toBeTruthy();
  expect(within(screen.getByRole("region", { name: "總覽" })).getAllByText("—").length).toBeGreaterThan(0);
});
