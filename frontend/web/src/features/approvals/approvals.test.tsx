// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { eventToQueryKeys } from "@/api/invalidation";
import type { AgentState } from "@/realtime/reducer";

import { ApprovalInbox, type ApprovalInboxProps } from "./ApprovalInbox";
import { approvalCard, commandChoice, type Approval } from "./model";

// A real pending approval: the echo writer's echo_note, with the company policy override
// echo_note/writer = needs_approval (seed_echo.py --approval on), from GET /api/approvals.
const [pending] = JSON.parse(
  readFileSync(join(process.cwd(), "src/features/approvals/__fixtures__/pending.json"), "utf8"),
) as Approval[];
const writerId = String(pending.requested_by.id);
const agents = {
  [writerId]: { id: writerId, role: "writer", display_name: "Wren", avatar_key: "default", activity: null, liveProgress: null },
} as Record<string, AgentState>;
const NOW = new Date(Date.parse(pending.created_at) + 90_000);

afterEach(cleanup);

describe("model", () => {
  it("a pending tool call: who asks, what will run, how long it has waited", () => {
    const card = approvalCard(pending, agents, NOW);
    expect(card).toMatchObject({
      state: "PENDING",
      kind: "工具呼叫",
      action: "echo_note",
      requester: "Wren",
      details: { text: "writer on approval inbox" },
      waiting: "1 分 30 秒",
      taskId: pending.task_id,
      runId: pending.run_id,
      decision: null,
    });
    expect(card.expires).toMatchObject({ at: pending.expires_at, soon: false, then: "expire" });
    expect(card.expires!.in).toMatch(/小時/);
    expect(card.withCeo).toBe(false);
    // an article nobody decided goes to the CEO at the deadline (D-157); other requests expire,
    // and so does one she already had
    const article = { ...pending, action: "approve_article" };
    expect(approvalCard(article, agents, NOW).expires!.then).toBe("ceo");
    const withHer = approvalCard({ ...article, payload: { delegated: { task_id: "t" } } }, agents, NOW);
    expect(withHer).toMatchObject({ withCeo: true, expires: { then: "expire" } });
    expect(approvalCard({ ...article, payload: { delegated_before: true } }, agents, NOW).expires!.then).toBe("expire");
    // unknown agent: still says who, by id
    expect(approvalCard(pending, {}, NOW).requester).toBe(`代理 ${writerId.slice(0, 8)}`);
  });

  it("a decided one says by whom and why", () => {
    const decided = {
      ...pending,
      state: "REJECTED",
      decided_by: { kind: "human", id: "operator" },
      decided_at: "2026-09-18T11:00:00Z",
      reason: "wrong topic",
    } as Approval;
    expect(approvalCard(decided, agents, NOW).decision).toEqual({
      by: "人員 operator",
      at: "2026-09-18T11:00:00Z",
      reason: "wrong topic",
    });
  });

  it("a CEO command says what it is and what each button does (D-201)", () => {
    // the CEO's request of 10/02, approved with the note 「請繼續運作、不要暫停」
    const pause = {
      ...pending,
      kind: "command",
      action: "command",
      task_id: null,
      run_id: null,
      summary: "Pause project 01a0d2c7-c9dd-750a-9a16-dc8cbd8b3f91: Last cycle spent NT$3.563520, produced 0 published articles",
      payload: {
        command: "PauseProject",
        role: "ceo",
        args: { project_id: "01a0d2c7-c9dd-750a-9a16-dc8cbd8b3f91", reason: "Last cycle spent NT$3.563520, produced 0 published articles" },
      },
    } as Approval;
    const card = approvalCard(pause, agents, NOW, { "01a0d2c7-c9dd-750a-9a16-dc8cbd8b3f91": "持股動態與科技產業" });
    expect(card.command).toMatchObject({
      title: "暫停專案「持股動態與科技產業」",
      body: "Last cycle spent NT$3.563520, produced 0 published articles",
      approve: "核准：暫停專案",
      reject: "駁回：繼續運作",
    });
    expect(card.command!.effect).toContain("不會有新文章");
    expect(card.canSendBack).toBe(false);
    // a project this page cannot name is shown by the start of its id
    expect(approvalCard(pause, agents, NOW).command!.title).toBe("暫停專案（01a0d2c7）");

    expect(commandChoice({ command: "UpdateStrategy", args: { summary: "雙語、有來源" } })).toMatchObject({
      title: "更新公司策略",
      body: "雙語、有來源",
      approve: "核准：採用新策略",
      reject: "駁回：維持原策略",
    });
    expect(commandChoice({ command: "KillProject", args: { project_id: "p1", reason: "r" } })!.effect).toContain("不能再恢復");
    // not a command, or one this page has no words for: the plain 核准 / 駁回
    expect(approvalCard(pending, agents, NOW).command).toBeNull();
    expect(commandChoice({ command: "SomethingNew", args: {} })).toBeNull();
  });

  it("an APPROVAL_* event makes every approvals list of the company stale", () => {
    const keys = eventToQueryKeys({
      event_type: "APPROVAL_APPROVED",
      company_id: pending.company_id,
      run_id: pending.run_id,
      task_id: pending.task_id,
    } as Parameters<typeof eventToQueryKeys>[0]);
    expect(keys).toContainEqual(["approvals", pending.company_id]);
  });
});

describe("inbox", () => {
  function setup(overrides: Partial<ApprovalInboxProps> = {}) {
    const props: ApprovalInboxProps = {
      state: "PENDING",
      onState: vi.fn(),
      cards: [approvalCard(pending, agents, NOW)],
      loadError: null,
      decide: vi.fn(async () => ({})),
      live: true,
      refresh: vi.fn(),
      ...overrides,
    };
    const view = render(<ApprovalInbox {...props} />);
    const card = () => screen.getByTestId(`approval-${pending.id}`);
    return { props, view, card };
  }

  it("an article can be sent back, but only with what to change (D-044)", async () => {
    const article = { ...pending, kind: "article", run_id: null, task_id: "t-approve" };
    const { props, card } = setup({ cards: [approvalCard(article, agents, NOW)] });
    const sendBack = within(card()).getByRole("button", { name: "退回修改" }) as HTMLButtonElement;
    expect(sendBack.disabled).toBe(true);
    expect(within(card()).getByRole("button", { name: "駁回（放棄這則）" })).toBeTruthy();

    fireEvent.change(within(card()).getByRole("textbox"), { target: { value: "標題不要用「狂加」" } });
    expect(sendBack.disabled).toBe(false);
    fireEvent.click(sendBack);
    await waitFor(() => expect(within(card()).getByRole("status").textContent).toBe("已退回修改，等待更新…"));
    expect(props.decide).toHaveBeenCalledWith(pending.id, "revise", "標題不要用「狂加」");
  });

  it("an article sent back twice cannot be sent back a third time (D-233)", () => {
    const article = { ...pending, kind: "article", run_id: null, task_id: "t-approve" };
    const last = approvalCard({ ...article, payload: { article_id: "a1", returns_left: 0 } }, agents, NOW);
    expect(last.returnsLeft).toBe(0);
    const { card } = setup({ cards: [last] });
    expect(within(card()).queryByRole("button", { name: "退回修改" })).toBeNull();
    expect(within(card()).getByRole("button", { name: "駁回（放棄這則）" })).toBeTruthy();
    expect(within(card()).getByText(/已經退回 2 次，不能再退回修改/)).toBeTruthy();
    // one asked before D-233 does not say: it can be sent back, as it could
    expect(approvalCard(article, agents, NOW).returnsLeft).toBeNull();
  });

  it("a paused agent run is approved or rejected, never sent back", () => {
    const { card } = setup();
    expect(within(card()).queryByRole("button", { name: "退回修改" })).toBeNull();
    expect(within(card()).getByRole("button", { name: "駁回" })).toBeTruthy();
  });

  it("approve: sent over REST, then the list changes when the event refreshes it", async () => {
    const { props, view, card } = setup();
    expect(within(card()).getByText(pending.summary)).toBeTruthy();
    expect(within(card()).getByRole("link", { name: "執行軌跡" }).getAttribute("href")).toBe(`/admin/trace/${pending.run_id}`);

    fireEvent.click(within(card()).getByRole("button", { name: "核准" }));
    await waitFor(() => expect(within(card()).getByRole("status").textContent).toBe("已送出核准，等待更新…"));
    expect(props.decide).toHaveBeenCalledWith(pending.id, "approve", null);
    expect(within(card()).queryByRole("button", { name: "核准" })).toBeNull();
    expect(props.refresh).not.toHaveBeenCalled(); // live: the APPROVAL_APPROVED event will do it

    view.rerender(<ApprovalInbox {...props} cards={[]} />);
    expect(screen.getByText("目前沒有等待審批的項目。")).toBeTruthy();
  });

  it("reject with a reason", async () => {
    const { props, card } = setup();
    fireEvent.change(within(card()).getByRole("textbox"), { target: { value: "  wrong topic " } });
    fireEvent.click(within(card()).getByRole("button", { name: "駁回" }));
    await waitFor(() => expect(props.decide).toHaveBeenCalledWith(pending.id, "reject", "wrong topic"));
    await waitFor(() => expect(within(card()).getByRole("status").textContent).toBe("已送出駁回，等待更新…"));
  });

  it("with the stream down, no event will come: refetch right away", async () => {
    const { props, card } = setup({ live: false });
    fireEvent.click(within(card()).getByRole("button", { name: "核准" }));
    await waitFor(() => expect(props.refresh).toHaveBeenCalledTimes(1));
  });

  it("already decided elsewhere (409): says so and reloads", async () => {
    const decide = vi.fn(async () => {
      throw new ApiError(409, "Conflict", `approval ${pending.id} is already APPROVED`, null);
    });
    const { props, card } = setup({ decide });
    fireEvent.click(within(card()).getByRole("button", { name: "核准" }));
    await waitFor(() => expect(within(card()).getByRole("alert").textContent).toContain("已經被處理"));
    expect(props.refresh).toHaveBeenCalled();
    expect(within(card()).getByRole("button", { name: "核准" })).toBeTruthy(); // not marked as sent
  });

  it("another failure keeps the card and shows the error", async () => {
    const decide = vi.fn(async () => {
      throw new Error("network down");
    });
    const { props, card } = setup({ decide });
    fireEvent.click(within(card()).getByRole("button", { name: "駁回" }));
    await waitFor(() => expect(within(card()).getByRole("alert").textContent).toBe("送出失敗：network down"));
    expect(props.refresh).not.toHaveBeenCalled();
  });

  it("a command's buttons name the outcome; it cannot be sent back (D-201)", async () => {
    const pause = {
      ...pending,
      kind: "command",
      action: "command",
      task_id: null,
      run_id: null,
      payload: { command: "PauseProject", args: { project_id: "p1", reason: null } },
    } as Approval;
    const { props, card } = setup({ cards: [approvalCard(pause, agents, NOW, { p1: "持股動態與科技產業" })] });
    expect(within(card()).getByRole("heading").textContent).toBe("暫停專案「持股動態與科技產業」");
    expect(within(card()).getByTestId("command-choice").textContent).toContain("直到有人在儀表板按「恢復專案」");
    expect(within(card()).queryByRole("button", { name: "核准" })).toBeNull();
    expect(within(card()).queryByRole("button", { name: "退回修改" })).toBeNull();
    fireEvent.change(within(card()).getByRole("textbox"), { target: { value: "請繼續運作、不要暫停" } });
    fireEvent.click(within(card()).getByRole("button", { name: "駁回：繼續運作" }));
    await waitFor(() => expect(props.decide).toHaveBeenCalledWith(pending.id, "reject", "請繼續運作、不要暫停"));
    expect(within(card()).queryByRole("button", { name: "核准：暫停專案" })).toBeNull(); // sent
  });

  it("state tabs; decided lists have no buttons", () => {
    const decided = { ...pending, state: "APPROVED", decided_by: { kind: "human", id: "operator" }, decided_at: pending.created_at } as Approval;
    const { props } = setup({ state: "APPROVED", cards: [approvalCard(decided, agents, NOW)] });
    expect(screen.queryByRole("button", { name: "核准" })).toBeNull();
    expect(screen.getByText(/人員 operator 於/)).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "已過期" }));
    expect(props.onState).toHaveBeenCalledWith("EXPIRED");
  });
});
