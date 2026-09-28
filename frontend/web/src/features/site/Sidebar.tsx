// The site's sidebar on a wide screen (D-085–D-089): 市場概況, the calendar, 財經行事曆 and 熱門文章,
// beside the front page's stories and beside an article. Hidden on a phone, where the front page
// keeps its calendar button and an article is the page.
import Link from "next/link";

import type { PublicArticleSummary, PublicDay, PublicEvent, PublicQuote } from "./api";
import { ArticleCalendar } from "./ArticleCalendar";
import { formatDate, words, type Filter, type Lang, type Section } from "./i18n";
import { direction, formatChange, formatValue, TONE } from "./quote";

export function Sidebar({
  lang,
  section = null,
  day = null,
  calendar,
  markets = [],
  popular = [],
  events = [],
}: {
  lang: Lang;
  section?: Filter | null;
  day?: string | null;
  calendar: { month: string; days: PublicDay[] };
  markets?: PublicQuote[];
  popular?: PublicArticleSummary[];
  events?: PublicEvent[];
}) {
  const w = words(lang);
  return (
    <aside aria-label={w.sidebar} className="hidden lg:block" data-testid="front-sidebar">
      {/* not sticky: four blocks are taller than a screen, and a pinned column hides its end */}
      <div className="grid gap-10 pt-6">
        {markets.length ? (
          <SidebarBlock label={w.marketOverview} title={w.marketOverview}>
            <MarketOverview quotes={markets} lang={lang} />
          </SidebarBlock>
        ) : null}
        {/* the calendar needs no title: its month is one */}
        <SidebarBlock label={w.calendar.label}>
          <ArticleCalendar
            lang={lang}
            section={section}
            selected={day}
            initialMonth={calendar.month}
            initialDays={calendar.days}
            inline
          />
        </SidebarBlock>
        {events.length ? (
          <SidebarBlock label={w.events.title} title={w.events.title}>
            <Events events={events} lang={lang} />
          </SidebarBlock>
        ) : null}
        {popular.length ? (
          <SidebarBlock label={w.popular} title={w.popular}>
            <Popular articles={popular} lang={lang} />
          </SidebarBlock>
        ) : null}
      </div>
    </aside>
  );
}

/** 財經行事曆 (D-088): the coming weeks by day — the US data due and the earnings, a stock's a
 * link to its chart on the watchlist page. */
function Events({ events, lang }: { events: PublicEvent[]; lang: Lang }) {
  const w = words(lang).events;
  const days = [...new Set(events.map((e) => e.day))];
  return (
    <ol className="grid gap-3 text-sm" data-testid="events">
      {days.map((day) => (
        <li key={day}>
          {/* a dark teal (teal-800): the days apart from what falls on them, quietly (D-089) */}
          <p className="text-xs font-semibold text-date tabular-nums">{w.day(day)}</p>
          <ul className="mt-1 grid gap-1">
            {events
              .filter((e) => e.day === day)
              .map((event) => (
                <li key={`${event.kind}-${event.key}`} className="flex items-baseline justify-between gap-2">
                  {event.kind === "earnings" ? (
                    <Link href={`/news/${lang}/watchlist?${new URLSearchParams({ s: event.key })}`} className="min-w-0 hover:text-accent">
                      {event.name}
                    </Link>
                  ) : (
                    <span className="min-w-0">{event.name}</span>
                  )}
                  {event.detail ? <span className="shrink-0 text-xs text-muted">{event.detail}</span> : null}
                </li>
              ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}

/** A block of the sidebar (D-085): what it holds, under a plain title when it
 * needs one (D-086: no rule above, no line beside). */
function SidebarBlock({ label, title, children }: { label: string; title?: string; children: React.ReactNode }) {
  return (
    <section aria-label={label}>
      {title ? <h2 className="pb-3 text-sm font-bold text-ink">{title}</h2> : null}
      {children}
    </section>
  );
}

/** 市場概況's figures (D-087), in this order: the two markets, the yield, gold and oil, the dollar,
 * the coin — each a link to its chart on the watchlist page. */
const OVERVIEW = ["taiex", "nasdaq", "us10y", "xau", "wti", "usdtwd", "btc"];

function MarketOverview({ quotes, lang }: { quotes: PublicQuote[]; lang: Lang }) {
  const w = words(lang);
  const byKey = new Map(quotes.map((q) => [q.key, q]));
  const shown = OVERVIEW.flatMap((key) => (byKey.has(key) ? [byKey.get(key)!] : []));
  return (
    <ul className="divide-y divide-line text-sm" data-testid="market-overview">
      {shown.map((quote) => {
        const way = direction(quote);
        const change = formatChange(quote);
        return (
          <li key={quote.key}>
            <Link
              href={`/news/${lang}/watchlist?${new URLSearchParams({ s: quote.key })}`}
              className="flex items-baseline justify-between gap-3 py-2 hover:text-accent"
            >
              <span className="min-w-0 truncate">{w.quoteNames[quote.key] ?? quote.key}</span>
              <span className={`shrink-0 text-right tabular-nums ${TONE[way]}`}>
                {formatValue(quote, lang)}
                {change ? (
                  <span className="ml-2 text-xs">
                    {way === "rise" ? "+" : way === "fall" ? "−" : ""}
                    {change}
                  </span>
                ) : null}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/** 熱門文章 (D-086): the week's most read, numbered as a newspaper's "most read" is. */
function Popular({ articles, lang }: { articles: PublicArticleSummary[]; lang: Lang }) {
  const w = words(lang);
  return (
    <ol className="grid gap-4" data-testid="popular">
      {articles.map((article, i) => (
        <li key={article.article_id} className="flex gap-3">
          <span className="w-5 shrink-0 font-display text-xl leading-none font-bold text-accent tabular-nums">{i + 1}</span>
          <span className="min-w-0">
            <Link href={article.path} className="line-clamp-3 text-sm leading-snug font-semibold hover:text-accent">
              {article.title}
            </Link>
            <span className="mt-1 block text-xs text-muted">
              {article.section ? `${w.sections[article.section as Section]}・` : ""}
              <time dateTime={article.published_at} className="text-date">
                {formatDate(lang, article.published_at)}
              </time>
            </span>
          </span>
        </li>
      ))}
    </ol>
  );
}
