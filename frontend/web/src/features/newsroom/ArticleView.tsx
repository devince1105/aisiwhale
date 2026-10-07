// One article (T-517, AC-7): a version's text in every language with each paragraph's claims
// marked; every claim with its quotes, each in place in its evidence; the fact-checks, the
// distribution and the readers; the timeline. The writer's, the editor's and marketing's activity
// links land here (?version=N, #fact-check, #distribution).
import type { EventEnvelope } from "@autora/event-schema";
import Link from "next/link";
import { Fragment, useState, type ReactNode } from "react";

import { isSection, SECTIONS, words, type Section as SiteSection } from "@/features/site/i18n";

import { Button } from "@/features/admin-ui/Button";
import { ConfirmDialog } from "@/features/admin-ui/Dialog";
import { AdminPage, PageHeader } from "@/features/admin-ui/PageHeader";
import { StatusLozenge } from "@/features/admin-ui/StatusLozenge";

import { ARTICLE_STATE, claimNumbers, formatTime, label, orderedClaims, problems, type ArticleDetail } from "./model";
import { ClaimList, Empty, EventList, Section } from "./parts";

const CHANNEL: Record<string, string> = { site: "網站", social_draft: "社群貼文（草稿，未發出）" };

/** A published article on the site: taking it down, putting it back (D-044), changing it (D-045). */
export interface OnSite {
  unpublish: (reason: string) => void;
  republish: () => void;
  revise: (reason: string) => void;
  /** VIP or free (D-159): the editor-in-chief's choice, which a person may change. */
  setAccess?: (access: "free" | "members") => void;
  /** Where it goes on the site (D-208); null: what its story's sources say. */
  setSection?: (section: SiteSection | null) => void;
  busy: boolean;
  error: string | null;
}

const REVISING = new Set(["DRAFT", "IN_REVIEW", "APPROVED"]);

function SiteControls({ article, onSite }: { article: ArticleDetail; onSite: OnSite }) {
  const [note, setNote] = useState("");
  const [askingDown, setAskingDown] = useState(false);
  const { state } = article;
  const published = Boolean(article.published_at);
  if (published && REVISING.has(state)) {
    return (
      <section aria-label="網站上架" data-testid="site-controls" className="mb-6 rounded-lg border border-line p-4 text-sm">
        <span className="text-muted">
          {article.listed
            ? "修改中：網站仍顯示目前發布的版本，新版本核准後才會換上。"
            : "修改中（已下架）：新版本核准發布後才會重新出現在網站上。"}
        </span>
      </section>
    );
  }
  if (state !== "PUBLISHED" && state !== "ARCHIVED") return null;
  const said = note.trim();
  return (
    <section aria-label="網站上架" data-testid="site-controls" className="mb-6 grid gap-2 rounded-lg border border-line p-4 text-sm">
      {state === "ARCHIVED" ? <span className="text-muted">已下架：網站上看不到這篇。</span> : null}
      <label className="grid gap-1">
        <span className="text-muted">說明（修改：要改什麼，寫手照這段改；下架：為什麼下架）</span>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={8000}
          rows={2}
          className="rounded-lg border border-line bg-canvas px-3 py-1.5"
        />
      </label>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" disabled={onSite.busy || !said} onClick={() => onSite.revise(said)}>
          修改文章
        </Button>
        {state === "PUBLISHED" ? (
          <Button variant="danger" disabled={onSite.busy || !said} onClick={() => setAskingDown(true)}>
            下架
          </Button>
        ) : (
          <Button disabled={onSite.busy} onClick={() => onSite.republish()}>
            重新上架
          </Button>
        )}
      </div>
      {askingDown ? (
        <ConfirmDialog
          title="下架這篇文章？"
          confirmLabel="確定下架"
          onConfirm={() => {
            setAskingDown(false);
            onSite.unpublish(said);
          }}
          onCancel={() => setAskingDown(false)}
        >
          網站上將看不到這篇，之後可以重新上架。說明：{said}
        </ConfirmDialog>
      ) : null}
      {onSite.error ? (
        <p role="alert" className="mt-2 text-danger">
          {onSite.error}
        </p>
      ) : null}
    </section>
  );
}

/** Free or VIP (D-159): the editor-in-chief set it at her final review; a person may change it. */
function AccessControl({ article, onSite }: { article: ArticleDetail; onSite: OnSite }) {
  const vip = article.access === "members";
  return (
    <section aria-label="閱讀權限" data-testid="access-control" className="mb-6 flex flex-wrap items-center gap-3 rounded-lg border border-line p-4 text-sm">
      <span className="text-muted">閱讀權限：</span>
      <div role="group" aria-label="閱讀權限" className="flex rounded-lg border border-line p-0.5">
        {(
          [
            ["free", "免費"],
            ["members", "VIP（會員看全文）"],
          ] as const
        ).map(([value, name]) => (
          <button
            key={value}
            type="button"
            aria-pressed={(value === "members") === vip}
            disabled={onSite.busy}
            onClick={() => onSite.setAccess!(value)}
            className={`rounded-md px-3 py-1 ${(value === "members") === vip ? "bg-accent text-canvas" : "text-muted"} disabled:opacity-50`}
          >
            {name}
          </button>
        ))}
      </div>
      <span className="text-muted">總編在終審時依 VIP 原則決定，可在這裡改。</span>
    </section>
  );
}

const SECTION_NAMES = words("zh-TW").sections;

/** Where it is on the site (D-047, D-208): what its story's sources say, unless a person chose. A
 * brief from the team chat has no sources, so on its own it is on the front page only. */
function SectionControl({ article, onSite }: { article: ArticleDetail; onSite: OnSite }) {
  const now = article.section && isSection(article.section) ? SECTION_NAMES[article.section] : null;
  return (
    <section aria-label="分類" data-testid="section-control" className="mb-6 flex flex-wrap items-center gap-3 rounded-lg border border-line p-4 text-sm">
      <label className="flex items-center gap-2">
        <span className="text-muted">分類：</span>
        <select
          aria-label="分類"
          value={article.section_given && article.section ? article.section : ""}
          disabled={onSite.busy}
          onChange={(e) => onSite.setSection!(isSection(e.target.value) ? e.target.value : null)}
          className="rounded-lg border border-line bg-canvas px-2 py-1"
        >
          <option value="">{!article.section_given && now ? `自動（${now}）` : "自動"}</option>
          {SECTIONS.map((section) => (
            <option key={section} value={section}>
              {SECTION_NAMES[section]}
            </option>
          ))}
        </select>
      </label>
      <span className="text-muted">
        {article.section_given
          ? "你指定的分類。"
          : now
            ? "自動分類（依新聞來源；沒有來源時依題材文字），可在這裡改。"
            : "新聞來源和題材文字都看不出分類，只出現在首頁「全部」；請選一個分類。"}
      </span>
    </section>
  );
}

export function ArticleView({
  article,
  lang,
  onLang,
  events,
  onSite,
  cover,
}: {
  article: ArticleDetail;
  lang: string;
  onLang: (lang: string) => void;
  events: readonly EventEnvelope[];
  onSite?: OnSite;
  /** The cover and what a person can do with it (D-142: ``CoverPanel``). */
  cover?: ReactNode;
}) {
  const [state, tone] = label(ARTICLE_STATE, article.state);
  const primary = article.primary_lang;
  const langs = Object.keys(article.languages).sort(
    (a, b) => Number(b === primary) - Number(a === primary) || a.localeCompare(b),
  );
  const shownLang = article.languages[lang] ? lang : langs[0];
  const text = shownLang ? article.languages[shownLang] : undefined;
  const numbers = claimNumbers(text?.blocks ?? []);
  const claims = orderedClaims(article.claims, numbers);
  const href = `/admin/newsroom/articles/${article.id}`;

  return (
    <AdminPage width="read">
      <PageHeader title={article.title}>
        <p className="mt-2 flex flex-wrap items-center gap-3 text-sm">
          <StatusLozenge tone={tone}>{state}</StatusLozenge>
          <Link href={`/admin/newsroom/stories/${article.story_id}`} className="text-accent underline">
            題材：{article.story_title}
          </Link>
          {article.revision_count ? <span className="text-muted">修訂 {article.revision_count} 次</span> : null}
          {Object.entries(article.public_urls).map(([l, url]) => (
            <a key={l} href={url} target="_blank" rel="noopener" className="text-accent underline">
              公開頁（{l}）
            </a>
          ))}
          {article.published_at ? <span className="text-muted">發布於 {formatTime(article.published_at)}</span> : null}
        </p>
      </PageHeader>

      {onSite?.setAccess ? <AccessControl article={article} onSite={onSite} /> : null}
      {onSite?.setSection ? <SectionControl article={article} onSite={onSite} /> : null}
      {onSite ? <SiteControls article={article} onSite={onSite} /> : null}
      {cover ? (
        <section aria-label="首圖" className="mb-6 rounded-lg border border-line p-4">
          {cover}
        </section>
      ) : null}

      <nav aria-label="版本" className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted">版本</span>
        {article.versions.map((v) => (
          <Link
            key={v.version}
            href={`${href}?version=${v.version}`}
            aria-current={v.version === article.shown ? "page" : undefined}
            className={`rounded border px-2 py-0.5 ${v.version === article.shown ? "border-accent text-accent" : "border-line"}`}
          >
            v{v.version}
            {v.published ? "・已發布" : v.current ? "・目前" : ""}
          </Link>
        ))}
        <span className="grow" />
        <span role="tablist" className="flex gap-1">
          {langs.map((l) => (
            <button
              key={l}
              role="tab"
              aria-selected={l === shownLang}
              onClick={() => onLang(l)}
              className={`rounded border px-2 py-0.5 ${l === shownLang ? "border-accent text-accent" : "border-line"}`}
            >
              {l}
            </button>
          ))}
        </span>
      </nav>
      {article.versions.find((v) => v.version === article.shown)?.change_summary ? (
        <p className="mt-2 text-sm text-muted">
          這一版的修改：{article.versions.find((v) => v.version === article.shown)?.change_summary}
        </p>
      ) : null}

      {text ? (
        <article lang={shownLang} className="mt-4 space-y-3 rounded border border-line bg-surface p-5 leading-7">
          <h2 className="text-xl font-semibold">{text.title}</h2>
          {text.summary ? <p className="text-muted">{text.summary}</p> : null}
          {text.blocks.map((block, index) => {
            const marks = block.claim_ids.map((id) => (
              <Fragment key={id}>
                <a href={`#claim-${id}`} className="ml-0.5 align-super text-xs text-accent">
                  [{numbers.get(id)}]
                </a>
              </Fragment>
            ));
            if (block.type === "heading") return <h3 key={index} className="pt-2 font-semibold">{block.text}</h3>;
            if (block.type === "quote")
              return (
                <blockquote key={index} className="border-l-4 border-line pl-3 italic">
                  {block.text}
                  {marks}
                </blockquote>
              );
            return (
              <p key={index}>
                {block.text}
                {marks}
              </p>
            );
          })}
        </article>
      ) : (
        <Empty>這個版本沒有內容。</Empty>
      )}

      <Section id="claims" title={`引用的主張（${claims.length}）`}>
        <ClaimList claims={claims} numbers={numbers} />
      </Section>

      <Section id="fact-check" title="事實查核">
        {article.fact_checks.length === 0 ? (
          <Empty>還沒有查核。</Empty>
        ) : (
          <ul className="space-y-3">
            {article.fact_checks.map((report) => (
              <li key={report.id} className="rounded border border-line bg-surface p-3 text-sm">
                <p className="flex flex-wrap items-center gap-2">
                  <StatusLozenge tone={report.passed ? "ok" : "danger"}>{report.passed ? "通過" : "未通過"}</StatusLozenge>
                  <span>v{report.version ?? "?"}</span>
                  <span className="text-muted">
                    {report.checked - report.failed}/{report.checked} 則主張通過・{formatTime(report.created_at)}
                  </span>
                </p>
                {report.results
                  .filter((r) => r.verdict === "fail" || "draft" in r)
                  .map((r, index) => (
                    <p key={index} className="mt-1 text-danger">
                      {typeof r.text === "string" ? `「${r.text}」：` : ""}
                      {problems(r)}
                    </p>
                  ))}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section id="distribution" title="發布紀錄">
        {article.distributions.length === 0 ? (
          <Empty>還沒有發布。</Empty>
        ) : (
          <ul className="space-y-3 text-sm">
            {article.distributions.map((d) => (
              <li key={d.id} className="rounded border border-line bg-surface p-3">
                <p className="font-medium">
                  {CHANNEL[d.channel] ?? d.channel}
                  <span className="ml-2 text-xs text-muted">{formatTime(d.created_at)}</span>
                </p>
                <ul className="mt-1 space-y-1">
                  {Object.entries(d.content).map(([l, value]) => {
                    const entry = (value ?? {}) as { text?: string; title?: string; url?: string };
                    return (
                      <li key={l}>
                        <span className="mr-2 text-muted">{l}</span>
                        {entry.text ?? entry.title}
                        {entry.url ? (
                          <a href={entry.url} target="_blank" rel="noopener" className="ml-2 text-accent underline">
                            {entry.url}
                          </a>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section id="analytics" title={`讀者（共 ${article.views.toLocaleString()} 次瀏覽）`}>
        {article.analytics.length === 0 ? (
          <Empty>還沒有讀者資料（每小時彙總一次）。</Empty>
        ) : (
          <table className="text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="pr-6">日期</th>
                <th className="pr-6">語言</th>
                <th className="pr-6 text-right">瀏覽</th>
                <th className="pr-6 text-right">讀者</th>
                <th className="text-right">讀完</th>
              </tr>
            </thead>
            <tbody>
              {article.analytics.map((d) => (
                <tr key={`${d.day}-${d.lang}`}>
                  <td className="pr-6">{d.day}</td>
                  <td className="pr-6">{d.lang}</td>
                  <td className="pr-6 text-right">{d.views}</td>
                  <td className="pr-6 text-right">{d.uniques}</td>
                  <td className="text-right">{d.read_complete}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section id="timeline" title="時間軸">
        <EventList events={events} />
      </Section>
    </AdminPage>
  );
}
