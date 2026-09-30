// @vitest-environment jsdom
// D-109: 團隊群組 — the office's group chat, told from the company's own events.
import type { EventEnvelope } from "@autora/event-schema";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { realtimeStore, type AgentState } from "@/stores/realtime";

import { chatItem, chatItems, dayLabel, timeLabel } from "./chatModel";
import { TeamChat } from "./TeamChat";

// the app's client, asking whatever fetch the test puts in place
vi.mock("@/api/client", async (original) => {
  const client = await original<typeof import("@/api/client")>();
  return { ...client, api: client.createApiClient({ baseUrl: "http://api.test", fetch: (request) => globalThis.fetch(request) }) };
});
vi.mock("next/navigation", () => ({ usePathname: () => "/admin/office", useSearchParams: () => new URLSearchParams("company=c1") }));

afterEach(() => {
  cleanup();
  realtimeStore.getState().reset();
  vi.unstubAllGlobals();
});

const agent = (id: string, role: string, name: string): AgentState => ({
  id,
  role,
  display_name: name,
  avatar_key: "default",
  department_id: null,
  department_key: null,
  office_zone_key: null,
  business_unit_key: null,
  activity: null,
  liveProgress: null,
});
const AGENTS = Object.fromEntries(
  [agent("w1", "writer", "Wren"), agent("e1", "editor", "Eli"), agent("c1", "editor_in_chief", "Edda")].map((a) => [a.id, a]),
);

let seq = 0;
const event = (event_type: string, payload: Record<string, unknown>, over: Partial<EventEnvelope> = {}): EventEnvelope =>
  ({
    event_id: `e${++seq}`,
    event_type,
    seq,
    company_id: "c1",
    occurred_at: "2026-09-29T02:05:00Z",
    actor: { kind: "system", id: "service:newsroom" },
    agent_id: null,
    task_id: null,
    run_id: null,
    payload,
    ...over,
  }) as unknown as EventEnvelope;

describe("the group's messages (D-109)", () => {
  it("each from the agent who acted, in words; the system's as notices; the operator's own", () => {
    const items = chatItems(
      [
        event("ARTICLE_CREATED", { article_id: "a1", langs: ["zh-TW", "en"] }, { agent_id: "w1", actor: { kind: "agent", id: "w1" } }),
        event("ARTICLE_REVIEWED", { article_id: "a1", verdict: "revise", fact_check_passed: false }, { actor: { kind: "agent", id: "e1" } }),
        event("APPROVAL_REQUESTED", { summary: "核准發布：黃金需求", ref_id: "t9" }),
        event("ARTICLE_PUBLISHED", { url: "/news/zh-TW/articles/x", revision: false }),
        event("TEAM_MESSAGE_POSTED", { text: "輝達財報", kind: "brief", ref_type: "story", ref_id: "s1" }, { actor: { kind: "human", id: "operator" } }),
      ],
      AGENTS,
      new Map([["a1", "黃金需求轉向結構性支撐"]]),
    );
    expect(items.map((i) => (i.type === "message" ? `${i.speaker.kind === "me" ? "我" : i.speaker.name}：${i.text}` : `〔${i.text}〕`))).toEqual([
      "Wren：「黃金需求轉向結構性支撐」初稿寫好了（中文、英文），請編輯看一下。", // which story: several at once
      "Eli：「黃金需求轉向結構性支撐」要改：事實查核沒有過。",
      "Edda：核准發布：黃金需求，請您核准。", // no agent on it: the editor-in-chief asks
      "〔已發布到網站〕",
      "我：輝達財報",
    ]);
    const [draft, , asked, published, mine] = items;
    expect(draft.type === "message" && draft.link?.href).toBe("/admin/newsroom/articles/a1");
    expect(asked.type === "message" && asked.approvalRef).toBe("t9");
    expect(published.type === "notice" && published.link?.href).toBe("/news/zh-TW/articles/x");
    expect(mine.type === "message" && [mine.brief, mine.link?.href]).toEqual([true, "/admin/newsroom/stories/s1"]);
  });

  it("the editor-in-chief's final review reads as hers (D-110)", () => {
    const chief = { actor: { kind: "agent" as const, id: "c1" } };
    const said = (verdict: string) => {
      const item = chatItem(event("ARTICLE_REVIEWED", { article_id: "a1", verdict, by_role: "editor_in_chief" }, chief), AGENTS)!;
      return item.type === "message" ? `${item.speaker.kind === "agent" ? item.speaker.name : ""}：${item.text}` : "";
    };
    expect(said("accept")).toBe("Edda：這篇終審通過，請您最後核准。");
    expect(said("veto")).toBe("Edda：這篇不發了，我否決。");
    expect(said("revise")).toBe("Edda：這篇要再改，退回給寫手。");
  });

  it("keeps quiet about a failure that will be retried and the steps between; each event once", () => {
    const retry = event("AGENT_RUN_FAILED", { final: false, error_class: "Timeout" }, { agent_id: "w1" });
    const final = event("AGENT_RUN_FAILED", { final: true, error_class: "Timeout" }, { agent_id: "w1" });
    expect(chatItem(retry, AGENTS)).toBeNull();
    expect(chatItem(event("AGENT_THINKING", { phase: "plan" }), AGENTS)).toBeNull();
    const told = chatItem(final, AGENTS)!;
    expect(told.type === "message" && [told.text, told.tone]).toEqual(["我這邊出錯了：Timeout", "danger"]);
    expect(chatItems([final, final], AGENTS)).toHaveLength(1);
  });

  it("a newsroom that stopped is said: a project paused, a day without an article (D-131)", () => {
    const paused = chatItem(event("PROJECT_PAUSED", { name: "持股動態", reason: "每篇成本過高", trigger: "ceo" }, { actor: { kind: "agent", id: "a-ceo" } } as never), {})!;
    expect(paused.type === "notice" && [paused.text, paused.tone]).toEqual(["專案「持股動態」暫停（總經理提出）：每篇成本過高", "danger"]);
    const quiet = chatItem(event("NEWSROOM_QUIET", { hours: 30, causes: ["project_paused", "awaiting_approval"], waiting_approvals: 2 }), AGENTS)!;
    expect(quiet.type === "notice" && quiet.text).toBe("已經 30 小時沒有新文章。可能的原因：新聞專案暫停中、有文章等您核准（2 篇）。");
    expect(quiet.type === "notice" && quiet.link?.href).toBe("/admin/approvals");
  });

  it("days and times in Taipei", () => {
    const now = new Date("2026-09-29T03:00:00Z");
    expect(dayLabel("2026-09-29T01:00:00Z", now)).toBe("今天");
    expect(dayLabel("2026-09-28T16:30:00Z", now)).toBe("今天"); // 00:30 on the 29th, in Taipei
    expect(dayLabel("2026-09-28T15:30:00Z", now)).toBe("昨天"); // 23:30 on the 28th
    expect(dayLabel("2026-09-28T10:00:00Z", now)).toBe("昨天");
    expect(dayLabel("2026-09-26T10:00:00Z", now)).toBe("9月26日（六）");
    expect(timeLabel("2026-09-29T02:05:00Z")).toBe("10:05");
  });
});

describe("the group beside the office (D-109)", () => {
  // as the API sends them: whole envelopes, which the page checks against the schema
  const envelope = (n: number, event_type: string, payload: Record<string, unknown>, actor: Record<string, string>) => ({
    event_id: `0192f000-0000-7000-8000-00000000000${n}`,
    seq: n,
    company_id: "0192f000-0000-7000-8000-0000000000c1",
    occurred_at: "2026-09-29T02:05:00Z",
    aggregate_type: "task",
    aggregate_id: "0192f000-0000-7000-8000-0000000000a1",
    actor,
    schema_version: 1,
    event_type,
    payload,
  });
  const TASK = "0192f000-0000-7000-8000-0000000000f9";
  const feed = [
    envelope(1, "APPROVAL_REQUESTED", { kind: "article", ref_type: "task", ref_id: TASK, summary: "核准發布：黃金需求" }, { kind: "system", id: "service:newsroom.approve" }),
    envelope(2, "TEAM_MESSAGE_POSTED", { text: "早安", kind: "note" }, { kind: "human", id: "operator" }),
  ];
  const serve = () => {
    const calls: { url: string; method: string; body: unknown }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: Request | string, init?: RequestInit) => {
        const request = input instanceof Request ? input : new Request(input, init);
        const url = request.url;
        const body = request.method === "GET" ? null : await request.clone().json().catch(() => null);
        calls.push({ url, method: request.method, body });
        if (url.includes("/team/feed")) return Response.json({ items: feed, has_more: false });
        if (url.includes("/team/messages")) return Response.json({ seq: 99, story_id: null, workflow_run_id: null }, { status: 201 });
        if (url.includes("/decide")) return Response.json({ id: "ap1" });
        if (url.includes("/articles")) return Response.json([]);
        if (url.includes("/api/approvals")) return Response.json([{ id: "ap1", ref_id: TASK, state: "PENDING" }]);
        return Response.json({});
      }),
    );
    return calls;
  };
  const open = () => {
    realtimeStore.setState({
      company: { companyId: "c1", lastSeq: 9, agents: AGENTS, tasks: {}, recentEvents: [], cycle: null },
    });
    return render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <TeamChat companyId="c1" onClose={() => {}} />
      </QueryClientProvider>,
    );
  };

  it("shows the feed; an approval is given from the chat as from the inbox", async () => {
    const calls = serve();
    open();
    const asked = await screen.findByTestId("chat-approval");
    expect(screen.getByText("早安")).toBeTruthy();
    // newest first (D-111): the note (seq 2) above the approval asked for before it (seq 1)
    const order = screen.getByTestId("team-chat-messages").textContent!;
    expect(order.indexOf("早安")).toBeLessThan(order.indexOf("核准發布：黃金需求"));
    // and what you write goes in at the top, above the messages
    const chat = screen.getByTestId("team-chat");
    const composer = screen.getByTestId("team-chat-composer");
    expect([...chat.children].indexOf(composer)).toBeLessThan([...chat.children].indexOf(screen.getByTestId("team-chat-messages")));
    expect(screen.getByText(/Wren、Eli、Edda 和你/)).toBeTruthy();
    fireEvent.click(within(asked).getByRole("button", { name: "核准" }));
    await waitFor(() => expect(calls.some((c) => c.url.includes("/api/approvals/ap1/decide"))).toBe(true));
    expect(calls.find((c) => c.url.includes("/decide"))!.body).toEqual({ decision: "approve", reason: null });
  });

  it("退回修改 asks why first", async () => {
    const calls = serve();
    open();
    const asked = await screen.findByTestId("chat-approval");
    fireEvent.click(within(asked).getByRole("button", { name: "退回修改" }));
    const send = within(asked).getByRole("button", { name: "送出" }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    fireEvent.change(within(asked).getByRole("textbox", { name: "退回修改的理由" }), { target: { value: "標題太長" } });
    fireEvent.click(send);
    await waitFor(() => expect(calls.find((c) => c.url.includes("/decide"))?.body).toEqual({ decision: "revise", reason: "標題太長" }));
  });

  it("a brief goes to the newsroom; Enter sends, but not while an input method is composing", async () => {
    const calls = serve();
    open();
    await screen.findByText("早安");
    fireEvent.click(screen.getByRole("button", { name: "交辦題材" }));
    const box = screen.getByRole("textbox", { name: "交辦的題材" });
    fireEvent.change(box, { target: { value: "輝達財報重點" } });
    fireEvent.keyDown(box, { key: "Enter", isComposing: true });
    expect(calls.some((c) => c.url.includes("/team/messages"))).toBe(false);
    fireEvent.keyDown(box, { key: "Enter" });
    await waitFor(() =>
      expect(calls.find((c) => c.url.includes("/team/messages"))?.body).toEqual({ text: "輝達財報重點", kind: "brief" }),
    );
  });
});
