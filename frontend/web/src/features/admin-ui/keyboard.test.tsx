// @vitest-environment jsdom
// The back office's keyboard (AD-03): the command palette finds and runs, the shortcuts go where
// they say and keep out of the way of typing, j / k walk a list and Enter opens the row, and an
// approval card approves from the keyboard only after asking.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
let pathname = "/admin/dashboard";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams("company=c1"),
}));

import { queryKeys } from "@/api/queries";
import { ApprovalInbox } from "@/features/approvals/ApprovalInbox";
import type { ApprovalCard } from "@/features/approvals/model";

import { AdminShell } from "./AdminShell";
import { buildCommands, pick, type CommandContext } from "./commands";
import { CommandPalette } from "./CommandPalette";
import { ROW } from "./hotkeys";
import { PageHeader } from "./PageHeader";
import { recentVisits } from "./recent";

const COMPANIES = [
  { id: "c1", slug: "aisiwhale", name: "艾矽鯨", agents: 8 },
  { id: "c2", slug: "echo", name: "Echo Demo", agents: 2 },
];

beforeEach(() => {
  push.mockReset();
  pathname = "/admin/dashboard";
  window.localStorage.clear();
  vi.stubGlobal("fetch", async () => Response.json([]));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function context(overrides: Partial<CommandContext> = {}): CommandContext {
  return {
    companyId: "c1",
    companies: COMPANIES,
    recent: [],
    go: vi.fn(),
    toggleSidebar: vi.fn(),
    showHelp: vi.fn(),
    signOut: vi.fn(),
    ...overrides,
  };
}

function shell(children: ReactNode = <main>page</main>) {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } });
  client.setQueryData(queryKeys.companies(), COMPANIES);
  client.setQueryData(queryKeys.approvals("c1", "PENDING"), []);
  return render(
    <QueryClientProvider client={client}>
      <AdminShell email="admin@aisiwhale.test" onSignOut={vi.fn()}>
        {children}
      </AdminShell>
    </QueryClientProvider>,
  );
}

const key = (k: string, init: KeyboardEventInit = {}, target: Element = document.body) =>
  fireEvent.keyDown(target, { key: k, bubbles: true, ...init });

describe("what the palette offers", () => {
  it("every page with its g shortcut, the other companies, the actions; the recent first", () => {
    const commands = buildCommands(context({ recent: [{ href: "/admin/newsroom/articles/a1", title: "台股創新高", section: "文章" }] }));
    expect(commands[0]).toMatchObject({ group: "最近瀏覽", label: "台股創新高", hint: "文章" });
    expect(commands.find((c) => c.id === "go:approvals")).toMatchObject({ keys: "g i", label: "審批收件匣" });
    expect(commands.filter((c) => c.group === "切換公司").map((c) => c.label)).toEqual(["Echo Demo"]); // not the one shown
  });

  it("finds by every word, in the label or the hint, labels starting with it first", () => {
    const commands = buildCommands(context());
    expect(pick(commands, "文章").map((c) => c.label)[0]).toBe("文章");
    expect(pick(commands, "新聞室 來").map((c) => c.label)).toEqual(["來源"]);
    expect(pick(commands, "ECHO").map((c) => c.label)).toEqual(["Echo Demo"]);
    expect(pick(commands, "沒有這種東西")).toEqual([]);
    expect(pick(commands, "  ")).toHaveLength(commands.length);
  });

  it("the commands go where they say, keeping the company", () => {
    const go = vi.fn();
    const commands = buildCommands(context({ go }));
    commands.find((c) => c.id === "go:articles")!.run();
    commands.find((c) => c.id === "company:c2")!.run();
    expect(go.mock.calls).toEqual([["/admin/newsroom/articles?company=c1"], ["/admin/dashboard?company=c2"]]);
  });
});

describe("the palette", () => {
  it("narrows as you type, walks with the arrows and runs with Enter", () => {
    const go = vi.fn();
    const onClose = vi.fn();
    render(<CommandPalette commands={buildCommands(context({ go }))} onClose={onClose} />);
    const box = screen.getByRole("combobox", { name: "搜尋頁面、公司或動作" });
    fireEvent.change(box, { target: { value: "新聞室" } });
    const options = screen.getAllByRole("option");
    expect(options.map((o) => o.textContent?.replace(/g\s?\w$/, ""))).toEqual(["題材新聞室", "文章新聞室", "來源新聞室"].map((t) => t));
    expect(options[0].getAttribute("aria-selected")).toBe("true");
    expect(box.getAttribute("aria-activedescendant")).toBe(options[0].id);
    fireEvent.keyDown(box, { key: "ArrowDown" });
    expect(screen.getAllByRole("option")[1].getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(box, { key: "ArrowUp" });
    fireEvent.keyDown(box, { key: "ArrowUp" }); // wraps to the last
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onClose).toHaveBeenCalled();
    expect(go).toHaveBeenCalledWith("/admin/newsroom/sources?company=c1");
  });

  it("Enter while an IME is still choosing runs nothing", () => {
    const go = vi.fn();
    render(<CommandPalette commands={buildCommands(context({ go }))} onClose={vi.fn()} />);
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Enter", isComposing: true });
    expect(go).not.toHaveBeenCalled();
  });

  it("says when nothing matches", () => {
    render(<CommandPalette commands={buildCommands(context())} onClose={vi.fn()} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "zzz" } });
    expect(screen.getByRole("listbox").textContent).toContain("找不到「zzz」");
  });
});

describe("the shortcuts", () => {
  it("⌘K and / open the palette, ? the help; a click on the top bar's box too", () => {
    shell();
    key("k", { metaKey: true });
    expect(screen.getByRole("dialog", { name: "指令面板" })).toBeTruthy();
    key("k", { ctrlKey: true }); // toggles it shut again
    expect(screen.queryByRole("dialog")).toBeNull();
    key("/");
    expect(screen.getByRole("dialog", { name: "指令面板" })).toBeTruthy();
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("option", { name: /鍵盤快捷鍵/ }));
    expect(screen.getByRole("dialog", { name: "鍵盤快捷鍵" }).textContent).toContain("審批收件匣");
    fireEvent.click(screen.getByRole("button", { name: "關閉" }));
    fireEvent.click(screen.getByRole("button", { name: /搜尋或跳頁/ }));
    expect(screen.getByRole("dialog", { name: "指令面板" })).toBeTruthy();
  });

  it("g then a letter goes to the page, with the company; too slow, and it is nothing", () => {
    shell();
    key("?");
    expect(screen.getByRole("dialog", { name: "鍵盤快捷鍵" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "關閉" }));
    key("g");
    key("i");
    expect(push).toHaveBeenCalledWith("/admin/approvals?company=c1");
    vi.useFakeTimers();
    key("g");
    vi.advanceTimersByTime(2000);
    key("a");
    expect(push).toHaveBeenCalledTimes(1);
  });

  it("keeps out of the way of typing", () => {
    shell(
      <main>
        <input aria-label="欄位" />
      </main>,
    );
    const field = screen.getByRole("textbox", { name: "欄位" });
    key("/", {}, field);
    key("g", {}, field);
    key("i", {}, field);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(push).not.toHaveBeenCalled();
    key("k", { metaKey: true }, field); // ⌘K still works from a field
    expect(screen.getByRole("dialog", { name: "指令面板" })).toBeTruthy();
  });

  it("j and k walk the rows, Enter opens the selected one", () => {
    shell(
      <main>
        <ul>
          {["a1", "a2", "a3"].map((id) => (
            <li key={id} {...ROW} data-testid={id}>
              <a href={`/admin/newsroom/articles/${id}`}>{id}</a>
            </li>
          ))}
        </ul>
      </main>,
    );
    const clicks: string[] = [];
    document.querySelectorAll("a").forEach((a) =>
      a.addEventListener("click", (e) => {
        e.preventDefault();
        clicks.push(a.getAttribute("href")!);
      }),
    );
    key("j");
    expect(document.activeElement).toBe(screen.getByTestId("a1"));
    key("j");
    key("j");
    key("j"); // stays on the last
    expect(document.activeElement).toBe(screen.getByTestId("a3"));
    key("k", {}, document.activeElement!);
    expect(document.activeElement).toBe(screen.getByTestId("a2"));
    key("Enter", {}, document.activeElement!);
    expect(clicks).toEqual(["/admin/newsroom/articles/a2"]);
  });
});

describe("recent pages", () => {
  it("a detail page is remembered with its section; a list page is not", () => {
    pathname = "/admin/newsroom/articles/a9";
    render(<PageHeader title="台股創新高" />);
    pathname = "/admin/newsroom/articles";
    render(<PageHeader title="文章列表" />);
    expect(recentVisits()).toEqual([{ href: "/admin/newsroom/articles/a9", title: "台股創新高", section: "文章" }]);
  });
});

describe("an approval card from the keyboard", () => {
  const CARD: ApprovalCard = {
    id: "ap1",
    state: "PENDING",
    kind: "文章發布",
    action: null,
    requester: "艾達",
    waiting: "5 分鐘",
    expires: null,
    summary: "發布〈台股創新高〉",
    details: {},
    withCeo: false,
    taskId: null,
    runId: null,
    canSendBack: true,
    returnsLeft: 2,
    article: null,
    officialReport: null,
    command: null,
    decision: null,
  };

  function inbox(decide = vi.fn(async () => ({ ok: true }))) {
    render(
      <ApprovalInbox
        state="PENDING"
        onState={vi.fn()}
        cards={[CARD]}
        loadError={null}
        decide={decide as never}
        live
        refresh={vi.fn()}
      />,
    );
    return decide;
  }

  it("a asks first, and approves only when confirmed", async () => {
    const decide = inbox();
    const card = screen.getByTestId("approval-ap1");
    card.focus();
    key("a", {}, card);
    const ask = screen.getByRole("dialog", { name: "核准這則？" });
    expect(ask.textContent).toContain("發布〈台股創新高〉");
    expect(decide).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.click(within(ask).getByRole("button", { name: "核准" }));
    });
    expect(decide).toHaveBeenCalledWith("ap1", "approve", null);
  });

  it("r goes to the opinion box; a typed there is text", () => {
    const decide = inbox();
    const card = screen.getByTestId("approval-ap1");
    card.focus();
    key("r", {}, card);
    const box = within(card).getByRole("textbox");
    expect(document.activeElement).toBe(box);
    key("a", {}, box);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(decide).not.toHaveBeenCalled();
  });
});
