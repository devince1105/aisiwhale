// @vitest-environment jsdom
// AD-05: the back office's table and the address it lives in — sorting by a header, checking rows
// and acting on them, two densities; the search, filters, page and saved views written to the
// address, so a reload or a shared link shows the same view and back undoes a change.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let search = new URLSearchParams();
const push = vi.fn((href: string) => (search = new URLSearchParams(href.split("?")[1] ?? "")));
const replace = vi.fn((href: string) => (search = new URLSearchParams(href.split("?")[1] ?? "")));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace }),
  usePathname: () => "/admin/newsroom/articles",
  useSearchParams: () => search,
}));

import { DataTable, ListToolbar, Pager, sortControl, type Column } from "./DataTable";
import { useListState, type ListState } from "./useListState";

type Row = { id: string; title: string; views: number };
const ROWS: Row[] = [
  { id: "a", title: "台股創新高", views: 7 },
  { id: "b", title: "美股收黑", views: 3 },
];
const COLUMNS: Column<Row>[] = [
  { key: "title", header: "標題", sort: "title", cell: (r) => r.title },
  { key: "views", header: "瀏覽", align: "right", cell: (r) => r.views },
  { key: "updated", header: "更新", sort: "updated_at", cell: () => "today" },
];
const SORTS = ["-updated_at", "updated_at", "title"] as const;
type Sort = (typeof SORTS)[number];

beforeEach(() => {
  search = new URLSearchParams("company=c1");
  push.mockClear();
  replace.mockClear();
  window.localStorage.clear();
});
afterEach(cleanup);

/** A table page as the newsroom's are put together, and its list state for the test to read. */
let state: ListState<Sort, "state">;
function Page({ next = "n1", total = 120 }: { next?: string | null; total?: number }) {
  const list = useListState(["state"], SORTS);
  state = list;
  return (
    <>
      <ListToolbar
        list={list}
        views="articles"
        filters={[{ key: "state", label: "狀態", options: [{ value: "PUBLISHED", label: "已發布" }] }]}
      />
      <DataTable
        label="文章"
        rows={ROWS}
        columns={COLUMNS}
        rowKey={(r) => r.id}
        empty="沒有"
        sort={sortControl(list, SORTS, "-updated_at")}
        bulk={[{ label: "下架", run: bulkRun }]}
      />
      <Pager list={list} shown={ROWS.length} total={total} nextCursor={next} />
    </>
  );
}
const bulkRun = vi.fn();
const show = (props: { next?: string | null; total?: number } = {}) => render(<Page {...props} />);
const again = () => {
  cleanup();
  show();
};

describe("the address keeps the table's state", () => {
  it("search on Enter, filter, sort: each back to the first page, the company kept", () => {
    search = new URLSearchParams("company=c1&cursor=x&prev=0&from=51");
    show();
    const box = screen.getByRole("searchbox", { name: "搜尋" });
    fireEvent.change(box, { target: { value: "  台股 " } });
    expect(replace).not.toHaveBeenCalled(); // not per letter
    fireEvent.submit(box.closest("form")!);
    expect(replace).toHaveBeenLastCalledWith("/admin/newsroom/articles?company=c1&q=%E5%8F%B0%E8%82%A1", { scroll: false });

    again();
    fireEvent.change(screen.getByRole("combobox", { name: "狀態" }), { target: { value: "PUBLISHED" } });
    expect(search.get("state")).toBe("PUBLISHED");
    again();
    fireEvent.click(screen.getByRole("button", { name: "標題" }));
    expect(Object.fromEntries(search)).toEqual({ company: "c1", q: "台股", state: "PUBLISHED", sort: "title" });

    // a reload: the same view, with chips that take each part off
    again();
    expect((screen.getByRole("searchbox") as HTMLInputElement).value).toBe("台股");
    const chips = screen.getByRole("list", { name: "目前的篩選" });
    expect(chips.textContent).toContain("搜尋：台股");
    expect(chips.textContent).toContain("狀態：已發布");
    fireEvent.click(within(chips).getByRole("button", { name: "取消「狀態：已發布」" }));
    expect(search.get("state")).toBeNull();
    expect(search.get("q")).toBe("台股");
  });

  it("the header sorts both ways where the server can, and says which", () => {
    show();
    const updated = screen.getByRole("columnheader", { name: /更新/ });
    expect(updated.getAttribute("aria-sort")).toBe("descending"); // the server's default
    fireEvent.click(within(updated).getByRole("button"));
    expect(search.get("sort")).toBe("updated_at");
    again();
    expect(screen.getByRole("columnheader", { name: /更新/ }).getAttribute("aria-sort")).toBe("ascending");
    expect(screen.getByRole("columnheader", { name: "瀏覽" }).querySelector("button")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /標題/ }));
    expect(search.get("sort")).toBe("title"); // only ascending exists, so it stays
  });

  it("pages forward and back without history: the cursors are on the address", () => {
    show();
    expect(screen.getByRole("navigation", { name: "分頁" }).textContent).toContain("第 1–2 筆，共 120 筆");
    expect(screen.queryByRole("button", { name: "上一頁" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "下一頁" }));
    expect(push).toHaveBeenCalledTimes(1);
    expect(Object.fromEntries(search)).toEqual({ company: "c1", prev: "0", cursor: "n1", from: "51" });

    cleanup();
    show({ next: "n2" });
    expect(screen.getByRole("navigation", { name: "分頁" }).textContent).toContain("第 51–52 筆");
    fireEvent.click(screen.getByRole("button", { name: "下一頁" }));
    expect(Object.fromEntries(search)).toEqual({ company: "c1", prev: "0.n1", cursor: "n2", from: "101" });

    again();
    fireEvent.click(screen.getByRole("button", { name: "上一頁" }));
    expect(Object.fromEntries(search)).toEqual({ company: "c1", prev: "0", cursor: "n1", from: "51" });
    again();
    fireEvent.click(screen.getByRole("button", { name: "上一頁" }));
    expect(Object.fromEntries(search)).toEqual({ company: "c1" });

    search = new URLSearchParams("company=c1&prev=0.n1&cursor=n2&from=101&q=x");
    again();
    fireEvent.click(screen.getByRole("button", { name: "第一頁" }));
    expect(Object.fromEntries(search)).toEqual({ company: "c1", q: "x" });
  });
});

describe("saved views (我的篩選器)", () => {
  it("names the search and filters, applies and deletes them, in this browser only", () => {
    search = new URLSearchParams("company=c1&q=台股&state=PUBLISHED&cursor=n1&from=51&prev=0");
    show();
    expect(state.view).toBe("q=%E5%8F%B0%E8%82%A1&state=PUBLISHED"); // not the page, not the company
    fireEvent.click(screen.getByRole("button", { name: "儲存目前的篩選" }));
    fireEvent.change(screen.getByRole("textbox", { name: "篩選器名稱" }), { target: { value: "台股已發布" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));
    expect(JSON.parse(window.localStorage.getItem("autora.admin.views.articles")!)).toEqual([
      { name: "台股已發布", view: "q=%E5%8F%B0%E8%82%A1&state=PUBLISHED" },
    ]);

    search = new URLSearchParams("company=c1&sort=title");
    again();
    fireEvent.click(screen.getByRole("button", { name: "台股已發布" }));
    expect(Object.fromEntries(search)).toEqual({ company: "c1", q: "台股", state: "PUBLISHED" });

    again();
    expect(screen.getByRole("button", { name: "台股已發布" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "刪除篩選器「台股已發布」" }));
    expect(window.localStorage.getItem("autora.admin.views.articles")).toBe("[]");
  });
});

describe("the table", () => {
  it("checks rows, acts on the checked, and keeps one density for every table", () => {
    show();
    expect(screen.queryByRole("toolbar", { name: "批次動作" })).toBeNull();
    fireEvent.click(screen.getAllByRole("checkbox", { name: "選取這一列" })[1]);
    const bar = screen.getByRole("toolbar", { name: "批次動作" });
    expect(bar.textContent).toContain("已選 1 筆");
    fireEvent.click(screen.getByRole("checkbox", { name: "全選這一頁" }));
    fireEvent.click(within(bar).getByRole("button", { name: "下架" }));
    expect(bulkRun).toHaveBeenCalledWith(ROWS);
    fireEvent.click(within(screen.getByRole("toolbar", { name: "批次動作" })).getByRole("button", { name: "取消選取" }));
    expect(screen.queryByRole("toolbar", { name: "批次動作" })).toBeNull();

    const cell = () => screen.getByRole("cell", { name: "美股收黑" });
    expect(cell().className).toContain("py-2.5");
    act(() => fireEvent.click(screen.getByRole("button", { name: "緊湊" })));
    expect(cell().className).toContain("py-1");
    expect(window.localStorage.getItem("autora.admin.density")).toBe("compact");
    again();
    expect(cell().className).toContain("py-1");
  });

  it("says when it is empty, and when it failed", () => {
    const { rerender } = render(<DataTable label="t" rows={[]} columns={COLUMNS} rowKey={(r) => r.id} empty="還沒有文章。" />);
    expect(screen.getByText("還沒有文章。")).toBeTruthy();
    rerender(<DataTable label="t" rows={undefined} columns={COLUMNS} rowKey={(r) => r.id} empty="x" error="500 壞了" />);
    expect(screen.getByRole("alert").textContent).toBe("500 壞了");
  });
});
