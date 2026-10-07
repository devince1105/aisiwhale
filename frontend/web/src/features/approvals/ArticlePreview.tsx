// The article an approval is about, readable where the decision is made (D-046).
//
// An approver used to see a title and a JSON blob, and had to go and find the article. Now the
// card opens the version that was submitted — title, summary, every paragraph, in each language
// — with its fact-check and what the writer said they changed; and for a revision of a
// published article, the paragraphs that differ from the one on the site.
"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { articleQuery } from "@/api/queries";
import { withCompany } from "@/features/company/CompanyScope";
import { CoverPanel } from "@/features/newsroom/CoverPanel";
import { ARTICLE_STATE, type ArticleDetail } from "@/features/newsroom/model";

import { changed, diffParagraphs, type DiffLine } from "./diff";
import { STATES, type ApprovalState } from "./model";

const LANG_NAME: Record<string, string> = { "zh-TW": "中文", en: "English" };
const BLOCK_PREFIX: Record<string, string> = { heading: "## ", quote: "〉" };

/** The version's text as lines a person reads and a diff compares: title, summary, paragraphs. */
export function lines(article: ArticleDetail, lang: string): string[] {
  const text = article.languages[lang];
  if (!text) return [];
  return [
    `標題：${text.title}`,
    ...(text.summary ? [`摘要：${text.summary}`] : []),
    ...text.blocks.map((b) => `${BLOCK_PREFIX[b.type] ?? ""}${b.text}`),
  ];
}

/** The version's text to paste elsewhere (D-141): title, summary, then the paragraphs, a blank
 * line between each; headings and quotes marked as in Markdown. */
export function copyText(article: ArticleDetail, lang: string): string {
  const text = article.languages[lang];
  if (!text) return "";
  const mark: Record<string, string> = { heading: "## ", quote: "> " };
  const blocks = text.blocks.map((b) => `${mark[b.type] ?? ""}${b.text}`);
  return [text.title, ...(text.summary ? [text.summary] : []), ...blocks].join("\n\n");
}

/** Why it was turned down, in words (D-233): the editor's limit is the engine's sentence. */
function rejectedBecause(reason: string): string {
  const limit = /^still not ready after (\d+) revisions$/.exec(reason);
  if (limit) return `編輯與總編要求修改超過 ${limit[1]} 次，題材已放棄`;
  return reason.length > 80 ? `${reason.slice(0, 80)}…` : reason;
}

/**
 * What became of the article after this decision (D-141): the card's title is what was asked
 * (申請發布), its tab what was decided, and this line where the article stands now — a version
 * sent back is often published later as its revision, or dropped, and then it says why (D-233).
 */
export function outcomeText(decision: ApprovalState, latest: ArticleDetail, draftGroupId: string | null): string {
  const decided = STATES.find((s) => s.id === decision)?.label ?? decision;
  const versions = latest.versions ?? [];
  const mine = versions.find((v) => v.draft_group_id === draftGroupId)?.version ?? null;
  const newest = versions.reduce((n, v) => Math.max(n, v.version), 0);
  // a draft after a decision is the writer at work on the revision — unless nothing is at work
  // on it any more (D-233)
  const label =
    latest.state === "DRAFT"
      ? latest.in_production === false
        ? "停在草稿（流程已結束，沒有人在改）"
        : "寫手修改中"
      : (ARTICLE_STATE[latest.state]?.[0] ?? latest.state);
  let now = label;
  if (latest.state === "REJECTED" && latest.state_reason) {
    now = `${label}（${rejectedBecause(latest.state_reason)}）`;
  } else if (latest.state === "PUBLISHED") {
    const onSite = versions.find((v) => v.published)?.version ?? null;
    if (onSite !== null && mine !== null) {
      now =
        onSite === mine
          ? "已發布（就是這一版）"
          : onSite > mine
            ? `已發布（第 ${onSite} 版，這一版之後修改的）`
            : `已發布（網站上仍是較早的第 ${onSite} 版）`;
    }
  } else if ((latest.state === "IN_REVIEW" || latest.state === "DRAFT") && mine !== null && newest > mine) {
    now = `${label}（修改後的第 ${newest} 版）`;
  }
  return `結果：${decided}・這篇目前：${now}`;
}

function Outcome({ articleId, draftGroupId, decision }: { articleId: string; draftGroupId: string | null; decision: ApprovalState }) {
  const latest = useQuery(articleQuery(articleId));
  if (!latest.data) return null;
  return (
    <p className="mt-1 text-sm text-muted" data-testid="article-outcome">
      {outcomeText(decision, latest.data, draftGroupId)}
    </p>
  );
}

const COPY_LABEL = { idle: "複製文章", done: "已複製", failed: "複製失敗" } as const;

function CopyIcon({ done }: { done: boolean }) {
  const line = { fill: "none", stroke: "currentColor", strokeLinecap: "round", strokeLinejoin: "round" } as const;
  return (
    <svg viewBox="0 0 20 20" className="size-4" aria-hidden>
      {done ? (
        <path d="M4 10.5l4 4 8-9" strokeWidth="2" {...line} />
      ) : (
        <>
          <rect x="7" y="7" width="10" height="10" rx="2" strokeWidth="1.6" {...line} />
          <path d="M13 4.5V4a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h.5" strokeWidth="1.6" {...line} />
        </>
      )}
    </svg>
  );
}

const DIFF_STYLE: Record<DiffLine["op"], string> = {
  same: "",
  removed: "bg-danger/10 text-danger line-through decoration-danger/60",
  added: "bg-ok/10 text-ok",
};
const DIFF_MARK: Record<DiffLine["op"], string> = { same: "", removed: "－ ", added: "＋ " };

export function ArticlePreviewView({
  draft,
  published,
  lang,
  onLang,
}: {
  /** The article as submitted: ``shown`` is the version being decided. */
  draft: ArticleDetail;
  /** The version on the site, when it is another one: a revision is read against it. */
  published: ArticleDetail | null;
  lang: string;
  onLang: (lang: string) => void;
}) {
  const [compare, setCompare] = useState(published !== null);
  const langs = Object.keys(draft.languages).sort(
    (a, b) => Number(b === draft.primary_lang) - Number(a === draft.primary_lang) || a.localeCompare(b),
  );
  const shownLang = draft.languages[lang] ? lang : langs[0];
  const version = draft.versions.find((v) => v.version === draft.shown);
  const check = draft.fact_checks.filter((f) => f.version === draft.shown).at(-1);
  const now = shownLang ? lines(draft, shownLang) : [];
  const diff = published && shownLang ? diffParagraphs(lines(published, shownLang), now) : null;

  return (
    <div data-testid="article-preview" className="mt-3 grid gap-3 rounded-lg border border-line bg-canvas p-4 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        {langs.map((l) => (
          <button
            key={l}
            type="button"
            aria-pressed={l === shownLang}
            onClick={() => onLang(l)}
            className={l === shownLang ? "font-semibold underline" : "text-accent"}
          >
            {LANG_NAME[l] ?? l}
          </button>
        ))}
        {diff ? (
          <label className="ml-auto flex items-center gap-1 text-muted">
            <input type="checkbox" checked={compare} onChange={(e) => setCompare(e.target.checked)} />
            對照目前發布的版本
          </label>
        ) : null}
      </div>

      <p className="text-muted">
        第 {draft.shown} 版
        {check ? (
          <span className={check.passed ? "text-ok" : "text-danger"}>
            ・事實查核{check.passed ? "通過" : "未通過"}（檢查 {check.checked} 項{check.failed ? `，${check.failed} 項未過` : ""}）
          </span>
        ) : (
          "・沒有事實查核紀錄"
        )}
        {version?.change_summary ? `・寫手說明：${version.change_summary}` : null}
      </p>

      {compare && diff ? (
        <div data-testid="article-diff" className="grid gap-2">
          {changed(diff) ? null : <p className="text-muted">這個語言的內容和目前發布的版本相同。</p>}
          {diff.map((line, i) => (
            <p key={i} data-op={line.op} className={`rounded px-1 leading-relaxed whitespace-pre-wrap ${DIFF_STYLE[line.op]}`}>
              {DIFF_MARK[line.op]}
              {line.text}
            </p>
          ))}
        </div>
      ) : (
        <div data-testid="article-text" className="grid gap-2">
          {now.map((line, i) => (
            <p key={i} className={`leading-relaxed whitespace-pre-wrap ${i === 0 ? "font-semibold" : ""}`}>
              {line}
            </p>
          ))}
        </div>
      )}

      <Link
        href={withCompany(`/admin/newsroom/articles/${draft.id}?version=${draft.shown}`, draft.company_id)}
        className="text-accent underline"
      >
        開啟完整文章頁（論點、引用出處、查核細節）
      </Link>
    </div>
  );
}

/** The submitted version and, for a revision, the published one — fetched only when opened. */
export function ArticlePreview({
  articleId,
  draftGroupId,
  decision,
}: {
  articleId: string;
  draftGroupId: string | null;
  /** Decided: say where the article stands now. */
  decision?: ApprovalState;
}) {
  const [open, setOpen] = useState(false);
  const [lang, setLang] = useState("zh-TW");
  const [copy, setCopy] = useState<keyof typeof COPY_LABEL>("idle");
  const queryClient = useQueryClient();
  const head = useQuery(articleQuery(articleId));
  /** The submitted version, in the language being read — fetched if the card is still closed. */
  const onCopy = async () => {
    try {
      const head = await queryClient.fetchQuery(articleQuery(articleId));
      const version = head.versions.find((v) => v.draft_group_id === draftGroupId)?.version ?? head.shown;
      const article = await queryClient.fetchQuery(articleQuery(articleId, version));
      const shown = article.languages[lang] ? lang : (Object.keys(article.languages)[0] ?? lang);
      await navigator.clipboard.writeText(copyText(article, shown));
      setCopy("done");
    } catch {
      setCopy("failed");
    }
  };
  const latest = useQuery({ ...articleQuery(articleId), enabled: open });
  const versions = latest.data?.versions ?? [];
  const submitted = versions.find((v) => v.draft_group_id === draftGroupId)?.version ?? latest.data?.shown ?? null;
  const onSite = versions.find((v) => v.published && v.version !== submitted)?.version ?? null;
  const draft = useQuery({ ...articleQuery(articleId, submitted), enabled: open && submitted !== null });
  const published = useQuery({ ...articleQuery(articleId, onSite), enabled: open && onSite !== null });
  const error = latest.error ?? draft.error ?? published.error;
  const ready = draft.data && (onSite === null || published.data);

  return (
    <div className="mt-2">
      {decision && decision !== "PENDING" ? (
        <Outcome articleId={articleId} draftGroupId={draftGroupId} decision={decision} />
      ) : null}
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => setOpen(!open)} className="text-sm text-accent underline">
          {open ? "收合全文" : "展開全文"}
        </button>
        <button
          type="button"
          onClick={onCopy}
          // the mark stays until the pointer or focus moves on: no timer on the screen (AC-S6)
          onMouseLeave={() => setCopy("idle")}
          onBlur={() => setCopy("idle")}
          aria-label={COPY_LABEL[copy]}
          title={COPY_LABEL[copy]}
          className={`rounded p-1 hover:bg-canvas ${copy === "failed" ? "text-danger" : copy === "done" ? "text-ok" : "text-muted hover:text-ink"}`}
        >
          <CopyIcon done={copy === "done"} />
        </button>
      </div>
      {head.data ? (
        <div className="mt-2">
          <CoverPanel articleId={articleId} cover={head.data.cover} />
        </div>
      ) : null}
      {open && error ? (
        <p role="alert" className="mt-2 text-sm text-danger">
          {error.message}
        </p>
      ) : null}
      {open && !error && !ready ? <p className="mt-2 text-sm text-muted">載入文章中…</p> : null}
      {open && ready && draft.data ? (
        <ArticlePreviewView
          draft={draft.data}
          published={onSite !== null ? (published.data ?? null) : null}
          lang={lang}
          onLang={setLang}
        />
      ) : null}
    </div>
  );
}
