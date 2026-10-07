// @vitest-environment jsdom
// AD-08: the production board. Every pair of columns is either one of the person's moves (moves.json)
// or refused; a card offers only its moves; a move asks first, shows the card where it is going
// at once, and puts it back with the reason when the API refuses.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/features/admin-ui/Toast";

import { Board, type BoardCard } from "./Board";
import { MOVES, moveFor, targetsFrom, type Move } from "./moves";
import { useBoardMoves } from "./useBoardMoves";

afterEach(cleanup);

const ARTICLE = ["DRAFT", "IN_REVIEW", "APPROVED", "PUBLISHED", "ARCHIVED", "REJECTED"];
const ALLOWED = new Set([
  "IN_REVIEW>APPROVED",
  "IN_REVIEW>DRAFT",
  "IN_REVIEW>REJECTED",
  "PUBLISHED>ARCHIVED",
  "ARCHIVED>PUBLISHED",
  "PUBLISHED>DRAFT",
  "ARCHIVED>DRAFT",
]);

describe("the moves", () => {
  it.each(ARTICLE.flatMap((from) => ARTICLE.filter((to) => to !== from).map((to) => [from, to] as const)))(
    "article %s → %s",
    (from, to) => {
      expect(moveFor("article", from, to) !== null).toBe(ALLOWED.has(`${from}>${to}`));
    },
  );

  it("a story only starts; a draft, an approved and a rejected article do not move by hand", () => {
    expect(MOVES.story.map((m) => `${m.from}>${m.to}`)).toEqual(["DISCOVERED>IN_PRODUCTION", "SELECTED>IN_PRODUCTION"]);
    expect(targetsFrom("article", "DRAFT")).toEqual([]);
    expect(targetsFrom("article", "APPROVED")).toEqual([]);
    expect(targetsFrom("article", "REJECTED")).toEqual([]);
    expect(targetsFrom("article", "IN_REVIEW")).toEqual(["APPROVED", "DRAFT", "REJECTED"]);
  });
});

const COLUMNS = [
  { key: "DRAFT", label: "草稿", tone: "work" as const },
  { key: "IN_REVIEW", label: "待核准", tone: "review" as const },
  { key: "PUBLISHED", label: "已發布", tone: "ok" as const },
  { key: "ARCHIVED", label: "已下架", tone: "neutral" as const },
];
const card = (id: string, column: string, title = id): BoardCard => ({ id, column, title, href: `/admin/newsroom/articles/${id}` });

describe("the board", () => {
  it("a card offers only its moves; one with none has no handle and no menu", () => {
    const onMove = vi.fn();
    render(
      <Board
        label="文章看板"
        columns={COLUMNS}
        cards={{ DRAFT: [card("d1", "DRAFT", "草稿一")], IN_REVIEW: [], PUBLISHED: [card("p1", "PUBLISHED", "已發布一")], ARCHIVED: undefined }}
        totals={{ PUBLISHED: 120 }}
        targets={(c) => targetsFrom("article", c.column)}
        onMove={onMove}
      />,
    );
    const published = screen.getByRole("region", { name: "已發布" });
    expect(published.textContent).toContain("1 / 120");
    const menu = within(published).getByRole("combobox", { name: "把「已發布一」移到" });
    expect(within(menu).getAllByRole("option").map((o) => o.textContent)).toEqual(["移動到…", "已下架", "草稿"]);
    fireEvent.change(menu, { target: { value: "ARCHIVED" } });
    expect(onMove).toHaveBeenCalledWith(expect.objectContaining({ id: "p1" }), "ARCHIVED");

    const draft = screen.getByRole("region", { name: "草稿" });
    expect(within(draft).queryByRole("combobox")).toBeNull();
    expect(within(draft).queryByRole("button", { name: /拖曳/ })).toBeNull();
    expect(screen.getByRole("region", { name: "已下架" }).textContent).toContain("載入中…");
  });
});

/** A board whose lists the test controls, moved through useBoardMoves. */
function Harness({ run, lists }: { run: (card: BoardCard, move: Move, reason: string | null) => Promise<unknown>; lists: Record<string, BoardCard[]> }) {
  const [done, setDone] = useState(0);
  const moves = useBoardMoves({
    entity: "article",
    columnLabel: (key) => COLUMNS.find((c) => c.key === key)!.label,
    run,
    onDone: () => setDone((n) => n + 1),
  });
  return (
    <>
      <span data-testid="done">{done}</span>
      <Board label="文章看板" columns={COLUMNS} cards={moves.place(lists)} targets={moves.targets} onMove={moves.ask} busy={moves.busy} />
      {moves.dialog}
    </>
  );
}

describe("a move", () => {
  const lists = () => ({ DRAFT: [], IN_REVIEW: [], PUBLISHED: [card("p1", "PUBLISHED", "台股創新高")], ARCHIVED: [] });

  it("asks why, shows the card where it is going until the list catches up, says it was done", async () => {
    let finish: () => void = () => undefined;
    const run = vi.fn(() => new Promise<void>((resolve) => (finish = resolve)));
    const { rerender } = render(
      <ToastProvider>
        <Harness run={run} lists={lists()} />
      </ToastProvider>,
    );
    fireEvent.change(screen.getByRole("combobox", { name: "把「台股創新高」移到" }), { target: { value: "ARCHIVED" } });
    const ask = screen.getByRole("dialog", { name: "下架「台股創新高」？" });
    expect(ask.textContent).toContain("已發布 → 已下架");
    expect((within(ask).getByRole("button", { name: "下架" }) as HTMLButtonElement).disabled).toBe(true); // a reason first
    fireEvent.change(within(ask).getByPlaceholderText("理由（必填）"), { target: { value: "用字要改" } });
    fireEvent.click(within(ask).getByRole("button", { name: "下架" }));

    expect(run).toHaveBeenCalledWith(expect.objectContaining({ id: "p1" }), expect.objectContaining({ action: "unpublish" }), "用字要改");
    const archived = screen.getByRole("region", { name: "已下架" });
    expect(archived.textContent).toContain("台股創新高");
    expect(archived.textContent).toContain("處理中…");
    expect(screen.getByRole("region", { name: "已發布" }).textContent).not.toContain("台股創新高");

    await act(async () => finish());
    await waitFor(() => expect(screen.getByTestId("done").textContent).toBe("1"));
    expect(screen.getByText("已下架：台股創新高").closest("[role=status]")).toBeTruthy(); // dnd-kit has its own status region
    // the list now has it where it went: the board shows the list's
    rerender(
      <ToastProvider>
        <Harness run={run} lists={{ ...lists(), PUBLISHED: [], ARCHIVED: [card("p1", "ARCHIVED", "台股創新高")] }} />
      </ToastProvider>,
    );
    expect(screen.getByRole("region", { name: "已下架" }).textContent).not.toContain("處理中");
  });

  it("puts it back and says why when the API refuses", async () => {
    const run = vi.fn(() => Promise.reject(new Error("409 already archived")));
    render(
      <ToastProvider>
        <Harness run={run} lists={lists()} />
      </ToastProvider>,
    );
    fireEvent.change(screen.getByRole("combobox", { name: "把「台股創新高」移到" }), { target: { value: "DRAFT" } });
    fireEvent.change(screen.getByPlaceholderText("要改什麼（必填，寫手照這段改）"), { target: { value: "改標題" } });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "修改文章" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("沒有修改文章「台股創新高」：409 already archived"));
    expect(screen.getByRole("region", { name: "已發布" }).textContent).toContain("台股創新高");
    expect(screen.getByRole("region", { name: "草稿" }).textContent).not.toContain("台股創新高");
  });

  it("calling it off moves nothing", () => {
    const run = vi.fn();
    render(
      <ToastProvider>
        <Harness run={run} lists={lists()} />
      </ToastProvider>,
    );
    fireEvent.change(screen.getByRole("combobox", { name: "把「台股創新高」移到" }), { target: { value: "ARCHIVED" } });
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(run).not.toHaveBeenCalled();
    expect(screen.getByRole("region", { name: "已發布" }).textContent).toContain("台股創新高");
  });
});
