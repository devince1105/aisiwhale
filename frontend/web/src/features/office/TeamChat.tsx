"use client";

// 團隊群組 (D-109): the office's group chat, beside the office. The company's agents report in it
// — a story taken up, a draft, an editor's verdict, an approval to give — and the operator writes
// back: a note, or 交辦題材, a story for the newsroom to write, started at once. Approvals are
// given here as in the inbox. Every message is an event the company recorded (chatModel.ts).
import { parseEvent, type EventEnvelope } from "@autora/event-schema";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { approvalsQuery, articlesQuery, decideApproval, itemsOf, fetchTeamFeed, postTeamMessage, queryKeys, teamFeedQuery } from "@/api/queries";
import { Face } from "@/features/agent-panel/Face";
import { commandChoice, type Approval } from "@/features/approvals/model";
import { isSection, SECTIONS, words as siteWords, type Section } from "@/features/site/i18n";
import { withCompany } from "@/features/company/CompanyScope";
import { useNow } from "@/hooks/useNow";
import { useRealtime } from "@/stores/realtime";

import { CHAT_TYPES, ROLE_NAME, chatItems, dayLabel, timeLabel, type ChatItem, type Speaker } from "./chatModel";
import { personName } from "@/people";

const TONE_TEXT: Record<string, string> = { ok: "text-ok", warn: "text-warn", danger: "text-danger" };

function parsed(items: unknown[]): EventEnvelope[] {
  return items.flatMap((raw) => {
    const result = parseEvent(raw);
    return result.ok ? [result.event] : [];
  });
}

/** The group: its first page, older pages asked for, and what arrives on the stream. */
function useTeamFeed(companyId: string) {
  const first = useQuery(teamFeedQuery(companyId));
  const [older, setOlder] = useState<{ events: EventEnvelope[]; more: boolean } | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const live = useRealtime((s) => (s.company?.companyId === companyId ? s.company.recentEvents : null));
  const agents = useRealtime((s) => (s.company?.companyId === companyId ? s.company.agents : null));
  const firstEvents = useMemo(() => parsed(first.data?.items ?? []), [first.data]);
  const events = useMemo(
    () => [...(older?.events ?? []), ...firstEvents, ...(live ?? []).filter((e) => CHAT_TYPES.has(e.event_type))],
    [older, firstEvents, live],
  );
  // the articles' titles, to say which story a draft or a verdict is about
  // the latest page's (AD-04): a chat is about what is being written now
  const articles = useInfiniteQuery(articlesQuery(companyId));
  const titles = useMemo(() => new Map((itemsOf(articles.data) ?? []).map((a) => [a.id, a.title])), [articles.data]);
  const items = useMemo(() => chatItems(events, agents ?? {}, titles), [events, agents, titles]);
  const more = older ? older.more : (first.data?.has_more ?? false);
  const loadOlder = async () => {
    const oldest = items[0]?.seq;
    if (!oldest || loadingOlder) return;
    setLoadingOlder(true);
    try {
      const page = await fetchTeamFeed(companyId, oldest);
      setOlder((now) => ({ events: [...parsed(page.items), ...(now?.events ?? [])], more: page.has_more }));
    } finally {
      setLoadingOlder(false);
    }
  };
  return { items, agents: agents ?? {}, loading: first.isPending, failed: first.isError, more, loadOlder, loadingOlder };
}

export function TeamChat({ companyId, onClose }: { companyId: string; onClose: () => void }) {
  const { items, agents, loading, failed, more, loadOlder, loadingOlder } = useTeamFeed(companyId);
  const pending = useInfiniteQuery(approvalsQuery(companyId));
  const pendingByRef = useMemo(() => new Map((itemsOf(pending.data) ?? []).map((a) => [a.ref_id, a])), [pending.data]);
  const members = Object.values(agents).filter((a) => ROLE_NAME[a.role]);
  const now = useNow();
  const list = useRef<HTMLDivElement>(null);
  // newest first (D-111): the latest message at the top, older ones below it
  const shown = useMemo(() => [...items].reverse(), [items]);
  const newest = shown[0]?.seq ?? 0;
  const atTop = useRef(true);
  const height = useRef(0);

  // a new message arrives at the top: in view if the reader is there; if they have scrolled down
  // to read, what they are reading stays where it is
  useLayoutEffect(() => {
    const box = list.current;
    if (!box) return;
    const grown = box.scrollHeight - height.current;
    if (atTop.current) box.scrollTop = 0;
    else if (grown > 0 && height.current) box.scrollTop += grown;
    height.current = box.scrollHeight;
  }, [newest, loading]);

  return (
    <aside
      aria-label="團隊群組"
      className="flex h-full w-full flex-col border-l border-line bg-surface lg:w-[22rem]"
      data-testid="team-chat"
    >
      <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <h2 className="font-semibold">團隊群組</h2>
          <p className="truncate text-xs text-muted">
            {members.length ? `${members.map((a) => personName(a.display_name)).join("、")} 和你` : "還沒有成員"}
          </p>
        </div>
        <button type="button" onClick={onClose} aria-label="收起群組" className="rounded-md p-1.5 text-muted hover:bg-canvas hover:text-ink">
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
            <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      </header>

      {/* what you write goes to the top, where the newest is */}
      <Composer companyId={companyId} onSent={() => (atTop.current = true)} />

      <div
        ref={list}
        onScroll={(e) => {
          atTop.current = e.currentTarget.scrollTop < 40;
          height.current = e.currentTarget.scrollHeight;
        }}
        className="min-h-0 flex-1 space-y-3 overflow-y-auto bg-canvas px-3 py-4"
        data-testid="team-chat-messages"
      >
        {loading ? <p className="text-center text-sm text-muted">…</p> : null}
        {failed ? <p className="text-center text-sm text-muted">群組訊息暫時讀不到。</p> : null}
        {!loading && !failed && !items.length ? <p className="text-center text-sm text-muted">還沒有訊息。</p> : null}
        {shown.map((item, i) => {
          const day = dayLabel(item.at, now);
          const newDay = i === 0 || dayLabel(shown[i - 1].at, now) !== day;
          // a run of one speaker's messages shows their name and face once, on the newest
          const sameSpeaker =
            !newDay &&
            item.type === "message" &&
            shown[i - 1]?.type === "message" &&
            sameVoice((shown[i - 1] as Extract<ChatItem, { type: "message" }>).speaker, item.speaker);
          return (
            <div key={item.key}>
              {newDay ? (
                <p className="mb-3 text-center">
                  <span className="rounded-full bg-surface px-2.5 py-0.5 text-[11px] text-muted">{day}</span>
                </p>
              ) : null}
              {item.type === "notice" ? (
                <Notice item={item} />
              ) : (
                <Bubble item={item} companyId={companyId} compact={sameSpeaker} approval={item.approvalRef ? pendingByRef.get(item.approvalRef) : undefined} />
              )}
            </div>
          );
        })}
        {more ? (
          <p className="text-center">
            <button type="button" onClick={() => void loadOlder()} disabled={loadingOlder} className="text-xs text-accent hover:underline disabled:opacity-50">
              {loadingOlder ? "載入中…" : "載入較早的訊息"}
            </button>
          </p>
        ) : null}
      </div>
    </aside>
  );
}

function sameVoice(a: Speaker, b: Speaker): boolean {
  return a.kind === b.kind && (a.kind === "me" || (b.kind === "agent" && a.name === b.name));
}

function Avatar({ speaker }: { speaker: Extract<Speaker, { kind: "agent" }> }) {
  return <Face name={speaker.name} role={speaker.role} avatarKey={speaker.avatarKey} size={32} />;
}

function Notice({ item }: { item: Extract<ChatItem, { type: "notice" }> }) {
  return (
    <p className="text-center text-[11px] text-muted" data-testid="chat-notice">
      <span className={`rounded-full bg-surface px-2.5 py-0.5 ${TONE_TEXT[item.tone] ?? ""}`}>
        {item.text}
        {item.link ? (
          <>
            {" ・ "}
            <Link href={item.link.href} className="underline">
              {item.link.label}
            </Link>
          </>
        ) : null}
        <span className="ml-1.5 text-muted">{timeLabel(item.at)}</span>
      </span>
    </p>
  );
}

function Bubble({
  item,
  companyId,
  compact,
  approval,
}: {
  item: Extract<ChatItem, { type: "message" }>;
  companyId: string;
  compact: boolean;
  approval?: Pick<Approval, "id" | "payload">;
}) {
  const mine = item.speaker.kind === "me";
  const time = <span className="shrink-0 self-end text-[10px] text-muted">{timeLabel(item.at)}</span>;
  const body = (
    <div
      className={`max-w-[15rem] rounded-2xl px-3 py-2 text-sm leading-relaxed break-words whitespace-pre-wrap ${
        mine ? "rounded-tr-sm bg-accent text-accent-ink" : "rounded-tl-sm bg-surface text-ink"
      }`}
    >
      {item.brief ? <span className={`mb-1 block text-[11px] font-semibold ${mine ? "opacity-80" : "text-accent"}`}>交辦題材</span> : null}
      <span className={!mine && item.tone === "danger" ? "text-danger" : undefined}>{item.text}</span>
      {item.link ? (
        <Link href={withCompany(item.link.href, companyId)} className={`mt-1 block text-xs underline ${mine ? "" : "text-accent"}`}>
          {item.link.label}
        </Link>
      ) : null}
      {item.approvalRef ? <ApprovalActions approval={approval} companyId={companyId} /> : null}
    </div>
  );
  if (mine)
    return (
      <div className="flex justify-end gap-1.5" data-testid="chat-mine">
        {time}
        {body}
      </div>
    );
  const speaker = item.speaker as Extract<Speaker, { kind: "agent" }>;
  return (
    <div className="flex gap-2" data-testid="chat-message">
      {compact ? <span className="w-8 shrink-0" /> : <Avatar speaker={speaker} />}
      <div className="min-w-0">
        {compact ? null : (
          <p className="mb-0.5 text-xs text-muted">
            {speaker.name}
            <span className="ml-1 text-[10px]">{ROLE_NAME[speaker.role] ?? speaker.role}</span>
          </p>
        )}
        <div className="flex gap-1.5">
          {body}
          {time}
        </div>
      </div>
    </div>
  );
}

/** 核准 / 退回修改 / 駁回, as in the inbox; once decided, what became of it. An executive's command
 * cannot be sent back, and its buttons say what they do (D-201). */
function ApprovalActions({ approval, companyId }: { approval?: Pick<Approval, "id" | "payload">; companyId: string }) {
  const client = useQueryClient();
  const [asking, setAsking] = useState<"revise" | "reject" | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!approval) return <span className="mt-1.5 block text-[11px] text-muted">已處理</span>;
  const choice = commandChoice(approval.payload ?? {});
  const decide = async (decision: "approve" | "revise" | "reject") => {
    setBusy(true);
    setError(null);
    try {
      await decideApproval(approval.id, decision, decision === "approve" ? null : reason.trim() || null);
      setAsking(null);
      await client.invalidateQueries({ queryKey: queryKeys.approvals(companyId) });
    } catch {
      setError("沒有送出，請再試一次。");
    } finally {
      setBusy(false);
    }
  };
  const button = "rounded-full border px-2.5 py-0.5 text-xs disabled:opacity-50";
  return (
    <div className="mt-2 grid gap-1.5" data-testid="chat-approval">
      {asking ? (
        <div className="grid gap-1.5">
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={asking === "revise" ? "要改哪裡？" : choice ? "為什麼不同意？" : "為什麼不發？"}
            aria-label={asking === "revise" ? "退回修改的理由" : "駁回的理由"}
            className="rounded-md border border-line bg-canvas px-2 py-1 text-xs"
          />
          <div className="flex gap-1.5">
            <button type="button" disabled={busy || !reason.trim()} onClick={() => void decide(asking)} className={`${button} border-accent text-accent`}>
              送出
            </button>
            <button type="button" disabled={busy} onClick={() => setAsking(null)} className={`${button} border-line text-muted`}>
              取消
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          <button type="button" disabled={busy} onClick={() => void decide("approve")} className={`${button} border-ok bg-ok text-white`}>
            {choice?.approve ?? "核准"}
          </button>
          {/* a third send-back would leave the article a draft nobody writes (D-233) */}
          {choice || approval.payload?.returns_left === 0 ? null : (
            <button type="button" disabled={busy} onClick={() => setAsking("revise")} className={`${button} border-line text-ink`}>
              退回修改
            </button>
          )}
          <button type="button" disabled={busy} onClick={() => setAsking("reject")} className={`${button} border-line text-danger`}>
            {choice?.reject ?? "駁回"}
          </button>
          <Link href={withCompany("/admin/approvals", companyId)} className="self-center text-[11px] text-muted underline">
            看全文
          </Link>
        </div>
      )}
      {error ? <span className="text-[11px] text-danger">{error}</span> : null}
    </div>
  );
}

/** A note, or 交辦題材: a story for the newsroom to write, started at once. Enter sends (not
 * while an input method is still composing); Shift+Enter is a new line. */
const SECTION_NAMES = siteWords("zh-TW").sections;

function Composer({ companyId, onSent }: { companyId: string; onSent: () => void }) {
  const client = useQueryClient();
  const [text, setText] = useState("");
  const [brief, setBrief] = useState(false);
  const [section, setSection] = useState<Section | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const send = async () => {
    const words = text.trim();
    if (!words || busy) return;
    setBusy(true);
    setError(null);
    try {
      await postTeamMessage(companyId, words, brief ? "brief" : "note", section);
      setText("");
      setBrief(false);
      setSection(null);
      onSent();
      await client.invalidateQueries({ queryKey: queryKeys.team(companyId) });
    } catch (e) {
      setError(e instanceof Error && e.message ? `沒有送出：${e.message}` : "沒有送出，請再試一次。");
    } finally {
      setBusy(false);
    }
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void send();
    }
  };
  return (
    <div className="border-b border-line p-3" data-testid="team-chat-composer">
      <div className="mb-2 flex items-center gap-2">
        <button
          type="button"
          aria-pressed={brief}
          onClick={() => setBrief(!brief)}
          className={`rounded-full border px-2.5 py-0.5 text-xs ${brief ? "border-accent bg-accent text-accent-ink" : "border-line text-muted hover:border-accent hover:text-accent"}`}
        >
          交辦題材
        </button>
        <span className="text-[11px] text-muted">{brief ? "送出後新聞室會立刻開始製作這個題材" : "一般留言"}</span>
        {brief ? (
          // D-208: a story from a sentence has no sources to say where on the site it belongs; left
          // to itself, its words do (D-212)
          <select
            aria-label="題材的分類"
            value={section ?? ""}
            onChange={(e) => setSection(isSection(e.target.value) ? e.target.value : null)}
            className="ml-auto rounded-md border border-line bg-canvas px-1.5 py-0.5 text-[11px]"
          >
            <option value="">分類：自動判斷</option>
            {SECTIONS.map((s) => (
              <option key={s} value={s}>
                {SECTION_NAMES[s]}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      <div className="flex items-end gap-2">
        <textarea
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setError(null);
          }}
          onKeyDown={onKey}
          rows={1}
          maxLength={1000}
          placeholder={brief ? "例如：輝達財報重點" : "輸入訊息"}
          aria-label={brief ? "交辦的題材" : "訊息"}
          className="max-h-32 min-h-9 flex-1 resize-none rounded-2xl border border-line bg-canvas px-3 py-2 text-sm"
        />
        <button
          type="button"
          onClick={() => void send()}
          disabled={busy || !text.trim()}
          aria-label="送出"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-accent-ink disabled:opacity-40"
        >
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
            <path d="M2.5 8h9M8 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
      {error ? <p className="mt-1.5 text-xs text-danger">{error}</p> : null}
    </div>
  );
}
