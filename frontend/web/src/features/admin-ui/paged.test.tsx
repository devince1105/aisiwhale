// @vitest-environment jsdom
// AD-04 on the screen: a list loaded a page at a time says how many of how many and fetches the
// next page on request; the command palette shows the server's matches after its own.
import { infiniteQueryOptions, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Page } from "@/api/queries";

import { buildCommands, searchCommands } from "./commands";
import { CommandPalette } from "./CommandPalette";
import { usePaged } from "./usePaged";

afterEach(cleanup);

const PAGES: Record<string, Page<string>> = {
  first: { items: ["a", "b"], next_cursor: "c2", total: 3 },
  c2: { items: ["c"], next_cursor: null, total: 3 },
};

function Letters({ fetchPage }: { fetchPage: (cursor: string | null) => Promise<Page<string>> }) {
  const list = usePaged(
    infiniteQueryOptions({
      queryKey: ["letters"] as const,
      queryFn: ({ pageParam }) => fetchPage(pageParam),
      initialPageParam: null as string | null,
      getNextPageParam: (last: Page<string>) => last.next_cursor ?? null,
    }),
  );
  return (
    <>
      <p data-testid="items">{list.items?.join(",") ?? "loading"}</p>
      {list.footer}
    </>
  );
}

describe("a list a page at a time", () => {
  it("shows how many of how many, and loads the next page until there is none", async () => {
    const fetchPage = vi.fn(async (cursor: string | null) => PAGES[cursor ?? "first"]);
    render(
      <QueryClientProvider client={new QueryClient()}>
        <Letters fetchPage={fetchPage} />
      </QueryClientProvider>,
    );
    expect((await screen.findByText("顯示 2 / 共 3 筆")).textContent).toBeTruthy();
    expect(screen.getByTestId("items").textContent).toBe("a,b");
    fireEvent.click(screen.getByRole("button", { name: "載入更多" }));
    expect(await screen.findByText("顯示 3 / 共 3 筆")).toBeTruthy();
    expect(screen.getByTestId("items").textContent).toBe("a,b,c");
    expect(screen.queryByRole("button", { name: "載入更多" })).toBeNull();
    expect(fetchPage.mock.calls).toEqual([[null], ["c2"]]);
  });
});

describe("the palette's search on the server", () => {
  const base = () =>
    buildCommands({
      companyId: "c1",
      companies: [],
      recent: [],
      go: vi.fn(),
      toggleSidebar: vi.fn(),
      showHelp: vi.fn(),
      signOut: vi.fn(),
    });

  it("lists the matches after its own, and opens one", () => {
    const go = vi.fn();
    const onQuery = vi.fn();
    const remote = searchCommands(
      { articles: [{ id: "a1", title: "台股創新高" }], stories: [{ id: "s1", title: "台股五萬點" }] },
      go,
    );
    render(<CommandPalette commands={base()} onClose={vi.fn()} onQuery={onQuery} remote={remote} />);
    const box = screen.getByRole("combobox");
    fireEvent.change(box, { target: { value: "台股" } });
    expect(onQuery).toHaveBeenLastCalledWith("台股");
    expect(screen.getByRole("group", { name: "搜尋結果" }).textContent).toContain("台股創新高");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["台股創新高文章", "台股五萬點題材"]);
    fireEvent.keyDown(box, { key: "ArrowDown" });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(go).toHaveBeenCalledWith("/admin/newsroom/stories/s1");
  });

  it("says it is searching rather than that nothing was found", () => {
    render(<CommandPalette commands={base()} onClose={vi.fn()} searching />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "鯨" } });
    expect(screen.getByRole("listbox").textContent).toBe("搜尋中…");
  });

  it("shows no matches for an empty box", () => {
    const remote = searchCommands({ articles: [{ id: "a1", title: "x" }], stories: [] }, vi.fn());
    render(<CommandPalette commands={base()} onClose={vi.fn()} remote={remote} />);
    expect(screen.queryByRole("group", { name: "搜尋結果" })).toBeNull();
  });
});
