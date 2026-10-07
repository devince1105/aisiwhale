// @vitest-environment jsdom
// The back office's shared pieces (AD-01) and shell (AD-02): the navigation map knows every page,
// the confirm dialog asks before it acts, and the sidebar shows where you are, keeps the company,
// counts what waits for you and remembers being collapsed.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { existsSync } from "node:fs";
import { join } from "node:path";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
let pathname = "/admin/newsroom/articles";
let search = new URLSearchParams("company=c1");
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => pathname,
  useSearchParams: () => search,
}));

import { queryKeys } from "@/api/queries";

import { AdminShell } from "./AdminShell";
import { ConfirmDialog } from "./Dialog";
import { activeNav, ADMIN_NAV, crumbsFor } from "./nav";
import { PageHeader } from "./PageHeader";
import { StatusLozenge } from "./StatusLozenge";

const COMPANIES = [
  { id: "c1", slug: "aisiwhale", name: "艾矽鯨", agents: 8 },
  { id: "c2", slug: "echo", name: "Echo Demo", agents: 2 },
];

beforeEach(() => {
  push.mockReset();
  pathname = "/admin/newsroom/articles";
  search = new URLSearchParams("company=c1");
  window.localStorage.clear();
  vi.stubGlobal("fetch", async () => Response.json([]));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function withQueries(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } });
  client.setQueryData(queryKeys.companies(), COMPANIES);
  client.setQueryData(queryKeys.approvals("c1", "PENDING"), [{ id: "a1" }, { id: "a2" }, { id: "a3" }]);
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>);
}

describe("the navigation map", () => {
  it("names a page that exists for every item", () => {
    const app = join(process.cwd(), "src/app");
    for (const item of ADMIN_NAV.flatMap((g) => g.items)) {
      expect(existsSync(`${app}${item.href}/page.tsx`), item.href).toBe(true);
    }
  });

  it("finds the item of a page and of the pages below it", () => {
    expect(activeNav("/admin/newsroom/articles")?.item.key).toBe("articles");
    expect(activeNav("/admin/newsroom/articles/a1")?.item.key).toBe("articles");
    expect(activeNav("/admin/trace/r1")?.item.key).toBe("timeline");
    expect(activeNav("/admin/newsroomx")).toBeNull();
    expect(activeNav("/admin/login")).toBeNull();
  });

  it("makes breadcrumbs that link back to the list from a detail page", () => {
    expect(crumbsFor("/admin/newsroom/articles")).toEqual([{ label: "新聞室" }, { label: "文章" }]);
    expect(crumbsFor("/admin/newsroom/articles/a1")).toEqual([
      { label: "新聞室" },
      { label: "文章", href: "/admin/newsroom/articles" },
    ]);
  });

  it("the page header shows them, keeping the company", () => {
    pathname = "/admin/newsroom/articles/a1";
    render(<PageHeader title="一篇文章" actions={<button type="button">動作</button>} />);
    const crumbs = screen.getByRole("navigation", { name: "麵包屑" });
    expect(within(crumbs).getByRole("link", { name: "文章" }).getAttribute("href")).toBe("/admin/newsroom/articles?company=c1");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("一篇文章");
    expect(screen.getByRole("button", { name: "動作" })).toBeTruthy();
  });
});

describe("the status lozenge", () => {
  it("wears its tone", () => {
    render(<StatusLozenge tone="danger">失敗</StatusLozenge>);
    expect(screen.getByText("失敗").dataset.tone).toBe("danger");
  });
});

describe("the confirm dialog", () => {
  it("acts only when confirmed, with the reason it asked for", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog title="撤銷？" confirmLabel="確認撤銷" reason={{ placeholder: "理由" }} onConfirm={onConfirm} onCancel={onCancel}>
        不能復原。
      </ConfirmDialog>,
    );
    const dialog = screen.getByRole("dialog", { name: "撤銷？" });
    const confirm = within(dialog).getByRole("button", { name: "確認撤銷" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.change(within(dialog).getByPlaceholderText("理由"), { target: { value: "  測完了 " } });
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledWith("測完了");
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("Esc, a click outside and 取消 all call it off", () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog title="下架？" confirmLabel="確定" onConfirm={vi.fn()} onCancel={onCancel} />);
    const dialog = screen.getByRole("dialog");
    fireEvent(dialog, new Event("cancel", { cancelable: true })); // what the browser fires on Esc
    fireEvent.click(dialog); // the backdrop
    fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
    expect(onCancel).toHaveBeenCalledTimes(3);
  });
});

describe("the shell", () => {
  const shell = () =>
    withQueries(
      <AdminShell email="admin@aisiwhale.test" onSignOut={vi.fn()}>
        <main>page</main>
      </AdminShell>,
    );

  it("shows every section, marks the current one and keeps the company in its links", async () => {
    shell();
    const sidebar = screen.getByTestId("admin-sidebar");
    for (const item of ADMIN_NAV.flatMap((g) => g.items)) {
      expect(within(sidebar).getByRole("link", { name: new RegExp(item.label) })).toBeTruthy();
    }
    const current = within(sidebar).getByRole("link", { name: "文章" });
    expect(current.getAttribute("aria-current")).toBe("page");
    expect(current.getAttribute("href")).toBe("/admin/newsroom/articles?company=c1");
    expect(within(sidebar).getByRole("link", { name: "題材" }).getAttribute("aria-current")).toBeNull();
    expect(await within(sidebar).findByTestId("nav-count-approvals")).toHaveProperty("textContent", "3");
    expect(screen.getByTestId("admin-who").textContent).toBe("admin@aisiwhale.test");
  });

  it("switches company to the same section's list", async () => {
    pathname = "/admin/newsroom/articles/a1";
    shell();
    const select = (await screen.findByRole("combobox", { name: "公司" })) as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe("c1"));
    fireEvent.change(select, { target: { value: "c2" } });
    expect(push).toHaveBeenCalledWith("/admin/newsroom/articles?company=c2");
  });

  it("collapses to icons and remembers it", () => {
    shell();
    fireEvent.click(screen.getByRole("button", { name: "收合側欄" }));
    expect(window.localStorage.getItem("autora.admin.sidebar")).toBe("1");
    expect(screen.queryByRole("combobox", { name: "公司" })).toBeNull();
    // the labels are gone; each icon still names its page
    expect(within(screen.getByTestId("admin-sidebar")).getByRole("link", { name: "文章" })).toBeTruthy();
    cleanup();
    shell();
    expect(screen.getByRole("button", { name: "展開側欄" })).toBeTruthy();
  });

  it("opens the same menu in a drawer on a phone", () => {
    shell();
    fireEvent.click(screen.getByRole("button", { name: "開啟選單" }));
    const drawer = screen.getByRole("dialog", { name: "後台選單" });
    expect(within(drawer).getByRole("link", { name: "VIP 授予" })).toBeTruthy();
    fireEvent.click(within(drawer).getByRole("button", { name: "關閉" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
