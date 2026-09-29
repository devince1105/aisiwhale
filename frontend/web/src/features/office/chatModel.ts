// 團隊群組 (D-109): the office's group chat, told from the company's own events. Pure functions:
// which events are messages, who says each (the agent that acted, or the role whose work it is),
// and how it reads. Nothing is invented — a message is an event the company recorded.
import type { EventEnvelope } from "@autora/event-schema";

import type { Tone } from "@/events/describe";
import type { AgentState } from "@/realtime/reducer";
import { personName } from "@/people";

/** Mirrors the backend's CHAT_TYPES (autora/company/team_chat.py): what the group hears about. */
export const CHAT_TYPES = new Set([
  "TEAM_MESSAGE_POSTED",
  "STORY_SELECTED",
  "STORY_DROPPED",
  "ARTICLE_CREATED",
  "ARTICLE_REVIEWED",
  "APPROVAL_REQUESTED",
  "APPROVAL_APPROVED",
  "APPROVAL_REJECTED",
  "APPROVAL_RETURNED",
  "APPROVAL_EXPIRED",
  "ARTICLE_PUBLISHED",
  "ARTICLE_REJECTED",
  "WORKFLOW_RUN_COMPLETED",
  "WORKFLOW_RUN_FAILED",
  "AGENT_RUN_FAILED",
  "TASK_BLOCKED",
  "BUDGET_EXHAUSTED",
  "SOURCE_PAUSED",
  "POLICY_DENIED",
  "AGENT_CREATED",
  "AGENT_RETIRED",
]);

export const ROLE_NAME: Record<string, string> = {
  ceo: "執行長",
  editor_in_chief: "總編輯",
  news_intelligence: "財經情報",
  editor: "編輯",
  writer: "寫手",
  analyst: "分析師",
  researcher: "研究員",
  marketing: "行銷",
  finance: "財務長",
  business: "商業開發",
};

/** Whose work an event is, when no agent is on it: the approval is the editor-in-chief's to ask. */
const VOICE: Record<string, string> = { APPROVAL_REQUESTED: "editor_in_chief" };

export type Speaker = { kind: "agent"; id: string | null; name: string; role: string } | { kind: "me" };

export interface ChatLink {
  href: string;
  label: string;
}

export type ChatItem =
  | {
      type: "message";
      key: string;
      seq: number;
      at: string;
      speaker: Speaker;
      text: string;
      tone: Tone;
      /** A brief: a story handed to the newsroom. */
      brief?: boolean;
      link?: ChatLink;
      /** An approval asked for: its task, to find it among the pending ones. */
      approvalRef?: string;
    }
  | { type: "notice"; key: string; seq: number; at: string; text: string; tone: Tone; link?: ChatLink };

type Payload = Record<string, unknown>;
const s = (value: unknown) => (typeof value === "string" && value ? value : null);
const clip = (text: string, most = 120) => (text.length > most ? `${text.slice(0, most - 1)}…` : text);
const seconds = (ms: unknown) => (typeof ms === "number" ? `${Math.max(1, Math.round(ms / 1000))} 秒` : null);
const LANG_NAME: Record<string, string> = { "zh-TW": "中文", en: "英文" };
const langs = (p: Payload) =>
  Array.isArray(p.langs) ? p.langs.map((l) => LANG_NAME[String(l)] ?? String(l)).join("、") : null;

function speakerOf(event: EventEnvelope, agents: Record<string, AgentState>): Speaker | null {
  if (event.actor.kind === "human") return { kind: "me" };
  const id = event.agent_id ?? (event.actor.kind === "agent" ? event.actor.id : null);
  const agent = id ? agents[id] : undefined;
  if (agent) return { kind: "agent", id: agent.id, name: personName(agent.display_name), role: agent.role };
  const role = VOICE[event.event_type];
  const byRole = role ? Object.values(agents).find((a) => a.role === role) : undefined;
  if (byRole) return { kind: "agent", id: byRole.id, name: personName(byRole.display_name), role: byRole.role };
  if (role) return { kind: "agent", id: null, name: ROLE_NAME[role] ?? role, role };
  return null; // the system: a notice, not a message
}

/** One event as the group reads it; null for one it keeps quiet about. */
export function chatItem(
  event: EventEnvelope,
  agents: Record<string, AgentState>,
  titles: ReadonlyMap<string, string> = new Map(),
): ChatItem | null {
  if (event.seq === null || !CHAT_TYPES.has(event.event_type)) return null;
  const p = event.payload as Payload;
  const base = { key: event.event_id, seq: event.seq, at: event.occurred_at };
  const speaker = speakerOf(event, agents);
  const say = (text: string, tone: Tone = "neutral", extra: Partial<Extract<ChatItem, { type: "message" }>> = {}): ChatItem =>
    speaker
      ? { type: "message", ...base, speaker, text, tone, ...extra }
      : { type: "notice", ...base, text, tone, link: extra.link };
  const notice = (text: string, tone: Tone = "neutral", link?: ChatLink): ChatItem => ({ type: "notice", ...base, text, tone, link });
  const article = s(p.article_id);
  const draft = article ? { href: `/admin/newsroom/articles/${article}`, label: "看稿子" } : undefined;
  // which story: several are in the works at once
  const title = article ? titles.get(article) : undefined;
  const which = title ? `「${clip(title, 40)}」` : "這篇";

  switch (event.event_type) {
    case "TEAM_MESSAGE_POSTED":
      return say(s(p.text) ?? "", "neutral", {
        brief: p.kind === "brief",
        link: p.ref_type === "story" && s(p.ref_id) ? { href: `/admin/newsroom/stories/${p.ref_id}`, label: "看題材" } : undefined,
      });
    case "STORY_SELECTED":
      return speaker?.kind === "agent"
        ? say(`我選了這個題材：「${s(p.title)}」`, "ok")
        : notice(`開始製作「${clip(s(p.title) ?? "", 60)}」`, "ok");
    case "STORY_DROPPED": {
      const why = s(p.reason);
      return speaker?.kind === "agent"
        ? say(`這個題材先放掉：「${s(p.title)}」${why ? `（${clip(why, 80)}）` : ""}`, "warn")
        : notice(`放棄題材「${clip(s(p.title) ?? "", 60)}」`, "warn");
    }
    case "ARTICLE_CREATED":
      return say(`${title ? which : ""}初稿寫好了${langs(p) ? `（${langs(p)}）` : ""}，請編輯看一下。`, "work", { link: draft });
    case "ARTICLE_REVIEWED":
      // the editor-in-chief's final review (D-110)
      if (p.by_role === "editor_in_chief")
        return s(p.verdict) === "accept"
          ? say(`${title ? which : "這篇"}終審通過，請您最後核准。`, "ok", { link: draft })
          : s(p.verdict) === "veto"
            ? say(`${which}不發了，我否決。`, "danger", { link: draft })
            : say(`${which}要再改，退回給寫手。`, "warn", { link: draft });
      return s(p.verdict) === "accept"
        ? say(`${title ? which : ""}看過了，沒有問題，送交核准。`, "ok", { link: draft })
        : say(p.fact_check_passed === false ? `${which}要改：事實查核沒有過。` : `${which}要改，已經退回給寫手。`, "warn", { link: draft });
    case "APPROVAL_REQUESTED":
      return say(`${clip(s(p.summary) ?? "有一件事", 160)}，請您核准。`, "warn", { approvalRef: s(p.ref_id) ?? undefined });
    case "APPROVAL_APPROVED":
      return notice(event.actor.kind === "human" ? "你核准了" : "已自動核准", "ok");
    case "APPROVAL_REJECTED":
      return notice(`${event.actor.kind === "human" ? "你退回了" : "已退回"}${s(p.reason) ? `：${clip(s(p.reason)!, 60)}` : ""}`, "danger");
    case "APPROVAL_RETURNED":
      return notice(`${event.actor.kind === "human" ? "你退回修改" : "已退回修改"}${s(p.reason) ? `：${clip(s(p.reason)!, 60)}` : ""}`, "warn");
    case "APPROVAL_EXPIRED":
      return notice("審批逾期了", "warn");
    case "ARTICLE_PUBLISHED":
      return notice(`${p.revision === true ? "修改版已發布" : "已發布"}${title ? which : "到網站"}`, "ok", s(p.url) ? { href: s(p.url)!, label: "看文章" } : undefined);
    case "ARTICLE_REJECTED":
      return notice(`文章駁回${s(p.reason) ? `：${clip(s(p.reason)!, 60)}` : ""}`, "danger");
    case "WORKFLOW_RUN_COMPLETED":
      return notice(`這一輪完成${seconds(p.duration_ms) ? `・${seconds(p.duration_ms)}` : ""}`, "ok");
    case "WORKFLOW_RUN_FAILED":
      return notice(`這一輪沒有完成${s(p.reason) ? `：${clip(s(p.reason)!, 60)}` : ""}`, "danger");
    case "AGENT_RUN_FAILED":
      if (!p.final) return null; // it will be tried again: nothing to tell yet
      return say(`我這邊出錯了${s(p.error_class) ? `：${s(p.error_class)}` : ""}${s(p.message) ? `（${clip(s(p.message)!, 80)}）` : ""}`, "danger");
    case "TASK_BLOCKED":
      return notice("任務卡住了：預算不足", "warn");
    case "BUDGET_EXHAUSTED":
      return notice(`預算用盡${s(p.scope) ? `：${s(p.scope)}` : ""}`, "danger");
    case "SOURCE_PAUSED":
      return notice(`新聞來源暫停${s(p.reason) ? `：${clip(s(p.reason)!, 60)}` : ""}`, "warn");
    case "POLICY_DENIED":
      return say(`這件事公司政策不允許${s(p.action) ? `：${s(p.action)}` : ""}${s(p.detail) ? `（${clip(s(p.detail)!, 60)}）` : ""}`, "danger");
    case "AGENT_CREATED":
      return notice(`${personName(s(p.display_name)) || "新同事"}${s(p.role) ? `（${ROLE_NAME[s(p.role)!] ?? s(p.role)}）` : ""}加入群組`);
    case "AGENT_RETIRED":
      return notice(`${personName(s(p.display_name)) || "一位同事"}離開群組`);
    default:
      return null;
  }
}

/** The group, oldest first: each event once (the page and the stream may both carry it). */
export function chatItems(
  events: readonly EventEnvelope[],
  agents: Record<string, AgentState>,
  titles: ReadonlyMap<string, string> = new Map(),
): ChatItem[] {
  const seen = new Set<string>();
  return [...events]
    .filter((e) => e.seq !== null)
    .sort((a, b) => a.seq! - b.seq!)
    .filter((e) => (seen.has(e.event_id) ? false : (seen.add(e.event_id), true)))
    .map((e) => chatItem(e, agents, titles))
    .filter((item): item is ChatItem => item !== null);
}

/** A day's heading, in Taipei: 今天, 昨天, or 9月27日（六）. */
export function dayLabel(at: string, now: Date): string {
  const taipei = (d: Date) => new Date(d.getTime() + 8 * 3600_000).toISOString().slice(0, 10);
  const day = taipei(new Date(at));
  if (day === taipei(now)) return "今天";
  if (day === taipei(new Date(now.getTime() - 86_400_000))) return "昨天";
  const d = new Date(`${day}T00:00:00Z`);
  return `${d.getUTCMonth() + 1}月${d.getUTCDate()}日（${"日一二三四五六"[d.getUTCDay()]}）`;
}

/** 14:05, in Taipei. */
export function timeLabel(at: string): string {
  return new Date(new Date(at).getTime() + 8 * 3600_000).toISOString().slice(11, 16);
}
