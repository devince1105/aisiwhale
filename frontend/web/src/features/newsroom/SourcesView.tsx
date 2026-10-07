"use client";

// The newsroom's sources (T-517): where stories come from — a table (AD-05) — and a form to add one.
import { useState, type FormEvent } from "react";

import type { NewSource } from "@/api/queries";

import { DataTable, type Column, type SortControl } from "@/features/admin-ui/DataTable";
import { StatusLozenge } from "@/features/admin-ui/StatusLozenge";

import { formatTime, type SourceView } from "./model";

const KINDS: Record<string, string> = {
  rss: "RSS / Atom",
  url_list: "網址清單",
  search_query: "搜尋",
  twse_announcements: "證交所重大訊息",
  gdelt: "GDELT",
};

const COLUMNS: readonly Column<SourceView>[] = [
  {
    key: "status",
    header: "狀態",
    className: "whitespace-nowrap",
    cell: (source) => (
      <StatusLozenge tone={source.status === "active" ? "ok" : "warn"}>{source.status === "active" ? "啟用" : "暫停"}</StatusLozenge>
    ),
  },
  { key: "name", header: "名稱", sort: "name", className: "font-medium", cell: (source) => source.name },
  { key: "kind", header: "種類", className: "whitespace-nowrap text-muted", cell: (source) => KINDS[source.kind] ?? source.kind },
  {
    key: "target",
    header: "網址或查詢",
    className: "max-w-xs truncate text-muted",
    cell: (source) => source.url ?? String(source.config.query ?? ""),
  },
  {
    key: "stats",
    header: "信任度・項目",
    className: "whitespace-nowrap text-xs text-muted",
    cell: (source) =>
      `信任度 ${Number(source.trust_level).toFixed(1)}・${source.items} 則項目・${
        source.last_polled_at ? `上次讀取 ${formatTime(source.last_polled_at)}` : "尚未讀取"
      }`,
  },
];

export function SourcesView({
  sources,
  sort,
  error = null,
}: {
  sources: readonly SourceView[] | undefined;
  sort?: SortControl;
  error?: string | null;
}) {
  return (
    <DataTable label="來源" rows={sources} columns={COLUMNS} rowKey={(source) => source.id} sort={sort} error={error} empty="還沒有來源。" />
  );
}

const TARGETS: Record<NewSource["kind"], string> = {
  rss: "Feed 網址",
  url_list: "網址（空白或換行分隔）",
  search_query: "搜尋字詞",
  twse_announcements: "股票代號（空白分隔，例：2330 2317）",
  gdelt: "GDELT 查詢（英文，例：Nvidia sourcelang:english）",
};

/** What each kind of source needs in its config (D-169: GDELT a query, TWSE the codes). */
export function sourceConfig(kind: NewSource["kind"], target: string): Record<string, unknown> {
  const words = target.split(/\s+/).filter(Boolean);
  if (kind === "url_list") return { urls: words };
  if (kind === "search_query" || kind === "gdelt") return { query: target.trim() };
  if (kind === "twse_announcements") return { codes: words };
  return {};
}

export function AddSourceForm({ onAdd }: { onAdd: (source: NewSource) => Promise<unknown> }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<NewSource["kind"]>("rss");
  const [target, setTarget] = useState("");
  const [trust, setTrust] = useState("0.5");
  const [language, setLanguage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onAdd({
        name,
        kind,
        url: kind === "rss" ? target.trim() : null,
        config: sourceConfig(kind, target),
        trust_level: trust,
        language: language || null,
        poll_interval_seconds: 3600,
      });
      setName("");
      setTarget("");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-3 rounded border border-line bg-surface p-4 text-sm sm:grid-cols-2">
      <label className="grid gap-1">
        名稱
        <input required value={name} onChange={(e) => setName(e.target.value)} className="rounded border border-line bg-canvas px-2 py-1" />
      </label>
      <label className="grid gap-1">
        種類
        <select value={kind} onChange={(e) => setKind(e.target.value as NewSource["kind"])} className="rounded border border-line bg-canvas px-2 py-1">
          {Object.entries(KINDS).map(([value, text]) => (
            <option key={value} value={value}>
              {text}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 sm:col-span-2">
        {TARGETS[kind]}
        <textarea required rows={kind === "url_list" ? 3 : 1} value={target} onChange={(e) => setTarget(e.target.value)} className="rounded border border-line bg-canvas px-2 py-1" />
      </label>
      <label className="grid gap-1">
        信任度（0–1）
        <input type="number" min="0" max="1" step="0.1" value={trust} onChange={(e) => setTrust(e.target.value)} className="rounded border border-line bg-canvas px-2 py-1" />
      </label>
      <label className="grid gap-1">
        語言（選填，例：zh-TW）
        <input value={language} onChange={(e) => setLanguage(e.target.value)} className="rounded border border-line bg-canvas px-2 py-1" />
      </label>
      <div className="flex items-center gap-3 sm:col-span-2">
        <button type="submit" disabled={busy} className="rounded bg-accent px-3 py-1 text-accent-ink disabled:opacity-50">
          {busy ? "新增中…" : "新增來源"}
        </button>
        {error ? <span className="text-danger">{error}</span> : null}
      </div>
    </form>
  );
}
