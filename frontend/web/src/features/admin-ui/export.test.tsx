// @vitest-environment jsdom
// AD-13: 匯出 CSV beside a table — the list's search and order sent without its page, the file
// saved under the name the API gave, and a toast that says how many rows (and when it was cut).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

let search = new URLSearchParams("company=c1&q=台積電&sort=title&cursor=abc");
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/admin/newsroom/stories",
  useSearchParams: () => search,
}));

import { createApiClient } from "@/api/client";
import { exportStories, type Exported } from "@/api/queries";

import { ListToolbar } from "./DataTable";
import { ToastProvider } from "./Toast";
import { useListState } from "./useListState";

const saved: string[] = [];
beforeEach(() => {
  search = new URLSearchParams("company=c1&q=台積電&sort=title&cursor=abc");
  saved.length = 0;
  URL.createObjectURL = vi.fn(() => "blob:x");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    saved.push(this.download);
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function Toolbar({ run }: { run: () => Promise<Exported> }) {
  const list = useListState<"title" | "-score">([], ["title", "-score"]);
  return <ListToolbar list={list} onExport={run} />;
}

const show = (run: () => Promise<Exported>) =>
  render(
    <ToastProvider>
      <Toolbar run={run} />
    </ToastProvider>,
  );

it("asks for the list's search and order without its page, and saves the file under its name", async () => {
  const urls: string[] = [];
  const api = createApiClient({
    baseUrl: "http://api",
    fetch: (async (request: Request) => {
      urls.push(request.url);
      return new Response("﻿狀態,題材\r\n", {
        headers: {
          "content-type": "text/csv; charset=utf-8",
          "content-disposition": "attachment; filename*=UTF-8''stories-20261007-2030.csv",
          "x-export-rows": "1",
          "x-export-total": "1",
        },
      });
    }) as typeof fetch,
  });
  const done = await exportStories("c1", "SELECTED", { q: "台積電", sort: "-score" }, api);
  expect(done).toEqual({ rows: 1, total: 1 });
  const url = new URL(urls[0]);
  expect(url.pathname).toBe("/api/companies/c1/stories/export");
  expect(Object.fromEntries(url.searchParams)).toEqual({ state: "SELECTED", q: "台積電", sort: "-score" });
  expect(saved).toEqual(["stories-20261007-2030.csv"]);
});

it("says how many rows, that it was cut, or that it failed", async () => {
  let answer: () => Promise<Exported> = async () => ({ rows: 1234, total: 1234 });
  show(() => answer());
  fireEvent.click(screen.getByRole("button", { name: "匯出 CSV" }));
  await screen.findByText("已匯出 1,234 筆");

  answer = async () => ({ rows: 10000, total: 12000 });
  fireEvent.click(screen.getByRole("button", { name: "匯出 CSV" }));
  await screen.findByText("已匯出前 10,000 筆（共 12,000 筆，請加上篩選條件分批匯出）");

  answer = async () => {
    throw new Error("403 Forbidden");
  };
  fireEvent.click(screen.getByRole("button", { name: "匯出 CSV" }));
  expect((await screen.findByRole("alert")).textContent).toContain("匯出失敗：403 Forbidden");
  await waitFor(() => expect(screen.getByRole("button", { name: "匯出 CSV" }).hasAttribute("disabled")).toBe(false));
});

it("is not there for a list that does not export", () => {
  render(<ToolbarWithout />);
  expect(screen.queryByRole("button", { name: "匯出 CSV" })).toBeNull();
});

function ToolbarWithout() {
  const list = useListState([], []);
  return <ListToolbar list={list} />;
}
