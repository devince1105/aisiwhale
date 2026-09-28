// The site's front page (D-047): the newest story large, then the rest as a list of headlines —
// a news reader scans headlines, and these stories have no pictures to put in cards. Below them,
// the page numbers (D-065). The tabs are in the header (SectionNav); a tab of several sections
// (持股觀察, D-050) has its tags here, and every story says its section as a tag.
import Link from "next/link";

import type { PublicArticleSummary, PublicDay, PublicEvent, PublicQuote } from "./api";
import { ArticleCalendar } from "./ArticleCalendar";
import {
  filterName,
  formatDate,
  revisedOn,
  isSection,
  tagsOf,
  topicOf,
  words,
  type Filter,
  type Lang,
  type Section,
} from "./i18n";
import { Pagination } from "./Pagination";
import { Sidebar } from "./Sidebar";
import { StocksNamed } from "./StocksNamed";

export const PAGE_SIZE = 10;

import { listHref } from "./links";

export { listHref };

function Meta({ article, lang }: { article: PublicArticleSummary; lang: Lang }) {
  const w = words(lang);
  const section = article.section as Section | null | undefined;
  return (
    <p className="flex flex-wrap items-center gap-x-2 text-xs text-muted">
      {section ? (
        <span className="rounded-full border border-accent/40 px-2 py-px font-semibold text-accent">
          {w.sections[section]}
        </span>
      ) : null}
      <time dateTime={article.published_at}>{formatDate(lang, article.published_at)}</time>
      {revisedOn(lang, article.published_at, article.revised_at) ? (
        <span>
          ・{w.revised} {revisedOn(lang, article.published_at, article.revised_at)}
        </span>
      ) : null}
      {article.access === "members" ? (
        <span className="rounded-full border border-line px-1.5 py-px text-[0.7rem]">{w.member}</span>
      ) : null}
    </p>
  );
}

function Lead({ article, lang }: { article: PublicArticleSummary; lang: Lang }) {
  return (
    <article className="border-b border-line py-8">
      <Meta article={article} lang={lang} />
      <h2 className="mt-3 font-display text-3xl leading-snug font-bold sm:text-4xl sm:leading-tight">
        <Link href={article.path} className="hover:text-accent">
          {article.title}
        </Link>
      </h2>
      {article.summary ? <p className="mt-4 text-lg leading-relaxed text-muted">{article.summary}</p> : null}
      <StocksNamed stocks={article.stocks} lang={lang} compact />
    </article>
  );
}

function Row({ article, lang }: { article: PublicArticleSummary; lang: Lang }) {
  return (
    <li className="py-6">
      <Meta article={article} lang={lang} />
      <h2 className="mt-2 font-display text-xl leading-snug font-semibold">
        <Link href={article.path} className="hover:text-accent">
          {article.title}
        </Link>
      </h2>
      {article.summary ? <p className="mt-2 line-clamp-2 leading-relaxed text-muted">{article.summary}</p> : null}
      <StocksNamed stocks={article.stocks} lang={lang} compact />
    </li>
  );
}

/** A tab of several sections' tags: all of it, or one of them. */
function Tags({ lang, filter, day = null }: { lang: Lang; filter: Filter; day?: string | null }) {
  const w = words(lang);
  const topic = isSection(filter) ? topicOf(filter) : filter;
  const tags = tagsOf(topic);
  if (!tags.length) return null;
  const chips: [Filter, string][] = [[topic, w.all], ...tags.map((t): [Filter, string] => [t, w.sections[t]])];
  return (
    <nav aria-label={w.tagsLabel(w.topics[topic] ?? topic)} className="flex flex-wrap gap-2 pt-4 print:hidden">
      {chips.map(([id, label]) => (
        <Link
          key={id}
          href={listHref(lang, id, 1, day)}
          aria-current={id === filter ? "page" : undefined}
          className={`rounded-full border px-3 py-1 text-xs ${
            id === filter ? "border-ink bg-ink font-semibold text-surface" : "border-line text-muted hover:text-ink"
          }`}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}

function BankRates({ lang }: { lang: Lang }) {
  const w = words(lang).fx;
  return (
    <a
      href={w.bankUrl}
      target="_blank"
      rel="noopener"
      className="mt-6 flex items-center justify-between gap-3 rounded-lg border border-line p-4 hover:border-accent"
      data-testid="bank-rates"
    >
      <span>
        <span className="block font-semibold">{w.bank} ↗</span>
        <span className="block text-xs text-muted">{w.bankNote}</span>
      </span>
    </a>
  );
}

export function ArticleList({
  articles,
  lang,
  section = null,
  page = 1,
  pages = 1,
  day = null,
  calendar,
  popular = [],
  markets = [],
  events = [],
}: {
  articles: PublicArticleSummary[];
  lang: Lang;
  /** The tab or the section shown (``?section=``). */
  section?: Filter | null;
  page?: number;
  /** How many pages the list has in all. */
  pages?: number;
  /** The day shown (``?date=``, D-084), if one is. */
  day?: string | null;
  /** The calendar's first month and its days with stories; no calendar without it. */
  calendar?: { month: string; days: PublicDay[] };
  /** 熱門文章, the week's most read (D-086), for the sidebar. */
  popular?: PublicArticleSummary[];
  /** The market strip's figures, for 市場概況 (D-087). */
  markets?: PublicQuote[];
  /** 財經行事曆, the coming weeks' releases and earnings (D-088). */
  events?: PublicEvent[];

}) {
  const w = words(lang);
  // only the first page leads with a story: an older page is a plain continuation of the list
  const lead = page === 1 ? articles[0] : undefined;
  const rest = lead ? articles.slice(1) : articles;
  return (
    // a newspaper's front page on a wide screen (D-085): the stories in the main column, a
    // sidebar of blocks beside them — the calendar first, more to come; one column on a phone
    <section className="mx-auto max-w-6xl px-4 pt-2 pb-10 lg:grid lg:grid-cols-[minmax(0,1fr)_17rem] lg:gap-x-10">
      <div className="min-w-0">
        <h1 className="sr-only">
          {section ? filterName(lang, section) : w.latest}
          {day ? `・${w.calendar.on(day)}` : ""}
          {page > 1 ? `・${w.page(page)}` : ""}
        </h1>
        {/* the tab's tags; on a narrow screen the calendar's button beside them (D-084) */}
        <div className="flex flex-wrap items-start justify-between gap-x-4">
          <div className="min-w-0 flex-1">{section ? <Tags lang={lang} filter={section} day={day} /> : null}</div>
          {calendar ? (
            <div className="w-full pt-4 sm:w-auto lg:hidden">
              <ArticleCalendar lang={lang} section={section} selected={day} initialMonth={calendar.month} initialDays={calendar.days} />
            </div>
          ) : null}
        </div>
        {/* 外匯: the bank's own rates are a click away (D-072); a currency's chart is on the watchlist */}
        {section === "fx" && page === 1 ? <BankRates lang={lang} /> : null}
        {articles.length === 0 ? (
          <p className="py-16 text-center text-muted">{day ? w.calendar.emptyDay : w.empty}</p>
        ) : (
          <>
            {lead ? <Lead article={lead} lang={lang} /> : null}
            <ul className="divide-y divide-line">
              {rest.map((article) => (
                <Row key={article.article_id} article={article} lang={lang} />
              ))}
            </ul>
          </>
        )}
        <Pagination lang={lang} page={page} total={pages} to={(n) => listHref(lang, section, n, day)} />
      </div>
      {calendar ? (
        <Sidebar
          lang={lang}
          section={section}
          day={day}
          calendar={calendar}
          markets={markets}
          popular={popular}
          events={events}
        />
      ) : null}
    </section>
  );
}

