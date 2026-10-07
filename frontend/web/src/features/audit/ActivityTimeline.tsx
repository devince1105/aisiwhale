"use client";

// 活動 (AD-07): one thing's history beside it, Jira's way — everything, or only its state changes,
// or only what people did — newest first, each with who and when. From GET /api/admin/activity:
// its state changes, its back-office changes (AD-06) and, for an article, its approvals.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { activityQuery, type ActivityEntry } from "@/api/queries";
import { StatusLozenge } from "@/features/admin-ui/StatusLozenge";
import { STATES as APPROVAL_STATES } from "@/features/approvals/model";
import { ARTICLE_STATE, formatTime, STORY_STATE } from "@/features/newsroom/model";
import { personName } from "@/people";

import { ACTION_LABEL } from "./labels";

const SUBJECT: Record<string, string> = { article: "文章", story: "題材", approval: "審批" };

function stateName(subject: string, state: string | null | undefined): string {
  if (!state) return "—";
  if (subject === "article") return ARTICLE_STATE[state]?.[0] ?? state;
  if (subject === "story") return STORY_STATE[state]?.[0] ?? state;
  if (subject === "approval") return APPROVAL_STATES.find((s) => s.id === state)?.label ?? state;
  return state;
}

/** What an entry says happened, in words. */
export function describe(entry: ActivityEntry, own: string): string {
  const whose = entry.subject === own ? "" : `${SUBJECT[entry.subject] ?? entry.subject}：`;
  if (entry.kind === "asked") return `${whose}提出審批`;
  if (entry.kind === "action") {
    const name = (entry.route && ACTION_LABEL[entry.route]) ?? entry.action ?? "操作";
    return entry.status && entry.status >= 400 ? `${name}（被拒 ${entry.status}）` : name;
  }
  return `${whose}${stateName(entry.subject, entry.from_state)} → ${stateName(entry.subject, entry.to_state)}`;
}

const TABS = [
  ["all", "全部"],
  ["state", "狀態變化"],
  ["action", "人的操作"],
] as const;

export function ActivityTimeline({ targetType, targetId }: { targetType: "article" | "story" | "approval"; targetId: string }) {
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("all");
  const activity = useQuery(activityQuery(targetType, targetId));
  return <ActivityList entries={activity.data} error={activity.error?.message ?? null} tab={tab} onTab={setTab} own={targetType} />;
}

export function ActivityList({
  entries,
  error,
  tab,
  onTab,
  own,
}: {
  entries: readonly ActivityEntry[] | undefined;
  error: string | null;
  tab: (typeof TABS)[number][0];
  onTab: (tab: (typeof TABS)[number][0]) => void;
  own: string;
}) {
  const shown = (entries ?? []).filter((e) =>
    tab === "all" ? true : tab === "state" ? e.kind === "state" || e.kind === "asked" : e.kind === "action",
  );
  return (
    <section aria-label="活動" className="rounded-lg border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <h2 className="text-sm font-semibold">活動</h2>
        <div role="tablist" aria-label="活動種類" className="flex gap-1 text-xs">
          {TABS.map(([key, name]) => (
            <button
              key={key}
              role="tab"
              type="button"
              aria-selected={tab === key}
              onClick={() => onTab(key)}
              className={`rounded px-2 py-0.5 ${tab === key ? "bg-accent/10 font-medium text-accent" : "text-muted hover:text-ink"}`}
            >
              {name}
            </button>
          ))}
        </div>
      </div>
      {error ? (
        <p role="alert" className="px-3 py-3 text-sm text-danger">
          {error}
        </p>
      ) : !entries ? (
        <p className="px-3 py-3 text-sm text-muted">載入中…</p>
      ) : shown.length === 0 ? (
        <p className="px-3 py-3 text-sm text-muted">沒有紀錄。</p>
      ) : (
        <ol className="max-h-[32rem] divide-y divide-line overflow-y-auto">
          {shown.map((entry, index) => (
            <li key={`${entry.at}-${index}`} className="px-3 py-2 text-sm">
              <p className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-medium">{entry.actor.kind === "agent" ? personName(entry.actor_label) : entry.actor_label}</span>
                <span>{describe(entry, own)}</span>
                {entry.kind === "action" && entry.status && entry.status >= 400 ? <StatusLozenge tone="warn">被拒</StatusLozenge> : null}
              </p>
              {entry.reason ? <p className="mt-0.5 line-clamp-3 text-xs break-words text-muted">{entry.reason}</p> : null}
              <time dateTime={entry.at} className="text-xs text-muted tabular-nums">
                {formatTime(entry.at)}
              </time>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
