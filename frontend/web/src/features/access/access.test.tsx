// @vitest-environment jsdom
// AD-09 on the pages: what a role may not do is not offered — pages it may not open, board moves,
// decisions — and the owners' page lets people in, changes their role and takes them out.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/admin/settings/access",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/api/queries", async (original) => {
  const actual = await original<typeof import("@/api/queries")>();
  return { ...actual, changeRole: vi.fn(), takeOut: vi.fn(), letIn: vi.fn() };
});

import { changeRole, letIn, takeOut, type AccessList } from "@/api/queries";
import { buildCommands } from "@/features/admin-ui/commands";
import { navFor } from "@/features/admin-ui/nav";
import { PermissionsProvider, useCan } from "@/features/admin-ui/permissions";
import { ToastProvider } from "@/features/admin-ui/Toast";
import { ApprovalInbox } from "@/features/approvals/ApprovalInbox";
import type { ApprovalCard } from "@/features/approvals/model";
import { ADMIN_ME_KEY } from "@/features/auth/TokenGate";
import { MOVES, MOVE_NEEDS } from "@/features/board/moves";

import { AccessPage } from "./AccessPage";

afterEach(cleanup);

const EDITOR = ["newsroom:edit", "approvals:decide", "projects:manage", "workflows:run"];
const can = (allowed: string[]) => (key: string) => allowed.includes(key);

describe("what a role is offered", () => {
  it("pages it may not open are not in the sidebar, the palette or g", () => {
    const keys = navFor(can(EDITOR)).flatMap((g) => g.items.map((i) => i.key));
    expect(keys).not.toContain("audit");
    expect(keys).not.toContain("access");
    expect(keys).toContain("articles");
    expect(navFor(can([])).some((g) => g.label === "系統")).toBe(false); // an empty group goes too
    const commands = buildCommands({
      companyId: "c1",
      companies: [],
      recent: [],
      go: vi.fn(),
      toggleSidebar: vi.fn(),
      showHelp: vi.fn(),
      signOut: vi.fn(),
      nav: navFor(can(EDITOR)),
    });
    expect(commands.some((c) => c.label === "操作紀錄")).toBe(false);
    expect(navFor(can(["audit:view", "access:manage"])).flatMap((g) => g.items.map((i) => i.key))).toEqual(
      expect.arrayContaining(["audit", "access"]),
    );
  });

  it("everything is shown outside a signed-in page; inside, only what the role has", () => {
    let seen: ((key: string) => boolean) | null = null;
    function Probe() {
      seen = useCan();
      return null;
    }
    render(<Probe />);
    expect(seen!("anything")).toBe(true);
    cleanup();
    render(
      <PermissionsProvider permissions={["newsroom:edit"]}>
        <Probe />
      </PermissionsProvider>,
    );
    expect([seen!("newsroom:edit"), seen!("approvals:decide")]).toEqual([true, false]);
  });

  it("every board move needs a key a role can have", () => {
    for (const move of [...MOVES.article, ...MOVES.story]) {
      expect(["approvals:decide", "newsroom:edit"]).toContain(MOVE_NEEDS[move.action]);
    }
  });

  it("a viewer reads an approval but is not offered the decision", () => {
    const card: ApprovalCard = {
      id: "ap1",
      state: "PENDING",
      kind: "文章",
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
    render(
      <PermissionsProvider permissions={[]}>
        <ApprovalInbox state="PENDING" onState={vi.fn()} cards={[card]} loadError={null} decide={vi.fn()} live refresh={vi.fn()} />
      </PermissionsProvider>,
    );
    const shown = screen.getByTestId("approval-ap1");
    expect(within(shown).getByText("發布〈台股創新高〉")).toBeTruthy();
    expect(within(shown).queryByRole("button", { name: "核准" })).toBeNull();
    expect(within(shown).getByText(/只能檢視，不能決定審批/)).toBeTruthy();
  });
});

const ACCESS: AccessList = {
  owners: ["boss@aisiwhale.test"],
  members: [
    {
      reader_id: "r1",
      email: "ed@aisiwhale.test",
      role: "editor",
      granted_by: { kind: "human", id: "admin:boss" },
      created_at: "2026-10-07T07:00:00Z",
      updated_at: "2026-10-07T07:00:00Z",
    },
    {
      reader_id: "r2",
      email: "me@aisiwhale.test",
      role: "owner",
      granted_by: { kind: "human", id: "operator" },
      created_at: "2026-10-07T07:00:00Z",
      updated_at: "2026-10-07T07:00:00Z",
    },
  ],
  roles: {
    owner: ["access:manage", "approvals:decide", "newsroom:edit"],
    editor: ["approvals:decide", "newsroom:edit"],
    finance: [],
    viewer: [],
  },
};

function page(): ReactNode {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } });
  client.setQueryData(["access"], ACCESS);
  client.setQueryData(ADMIN_ME_KEY, { via: "email", email: "me@aisiwhale.test", role: "owner" });
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AccessPage />
      </ToastProvider>
    </QueryClientProvider>
  );
}

describe("the owners' page", () => {
  it("shows the owners, the people let in and what each role may do", () => {
    render(page());
    expect(screen.getByRole("region", { name: "擁有者" }).textContent).toContain("boss@aisiwhale.test");
    const table = screen.getByRole("table", { name: "管理員" });
    expect(within(table).getByRole("combobox", { name: "ed@aisiwhale.test 的角色" })).toHaveProperty("value", "editor");
    // nobody changes or removes their own role here
    const mine = within(table).getByText("me@aisiwhale.test").closest("tr")!;
    expect(within(mine).queryByRole("combobox")).toBeNull();
    expect(within(mine).queryByRole("button", { name: "移除" })).toBeNull();
    const matrix = screen.getByRole("table", { name: "角色權限表" });
    const decide = within(matrix).getByText(/審批：核准/).closest("tr")!;
    expect(within(decide).getAllByRole("cell").map((c) => c.getAttribute("aria-label"))).toEqual(["可以", "可以", "不可以", "不可以"]);
  });

  it("changes a role, takes somebody out after asking, lets somebody in", async () => {
    vi.mocked(changeRole).mockResolvedValue({ ...ACCESS.members[0], role: "viewer" });
    vi.mocked(takeOut).mockResolvedValue(undefined);
    vi.mocked(letIn).mockResolvedValue(ACCESS.members[0]);
    render(page());
    fireEvent.change(screen.getByRole("combobox", { name: "ed@aisiwhale.test 的角色" }), { target: { value: "viewer" } });
    await waitFor(() => expect(changeRole).toHaveBeenCalledWith("r1", "viewer"));
    expect(await screen.findByText("ed@aisiwhale.test 現在是檢視")).toBeTruthy();

    fireEvent.click(within(screen.getByText("ed@aisiwhale.test").closest("tr")!).getByRole("button", { name: "移除" }));
    expect(takeOut).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole("dialog", { name: "移除 ed@aisiwhale.test？" })).getByRole("button", { name: "移除" }));
    await waitFor(() => expect(takeOut).toHaveBeenCalledWith("r1"));

    const form = screen.getByRole("form", { name: "加入管理員" });
    fireEvent.change(within(form).getByRole("textbox"), { target: { value: " new@aisiwhale.test " } });
    fireEvent.change(within(form).getByRole("combobox"), { target: { value: "finance" } });
    fireEvent.submit(form);
    await waitFor(() => expect(letIn).toHaveBeenCalledWith("new@aisiwhale.test", "finance"));
  });
});
