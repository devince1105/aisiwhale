// A stock's page (D-049): today's figure, which of the investors we follow hold it and what they
// did with it this quarter (their 13F filings, as the newsroom reads them), and our stories that
// name it. Server-rendered; nothing on it is advice, and it says so.
import Link from "next/link";

import type { PublicHistory, PublicHolder, PublicStock, PublicTrade } from "./api";
import { formatDate, words, type Lang } from "./i18n";
import { StockChart } from "./StockChart";
import { WatchButton } from "./WatchButton";
import { NewsSentiment } from "./NewsSentiment";
import { Pagination } from "./Pagination";
import { ARROW, direction, formatCap, formatChange, formatValue, stockCode, TONE } from "./quote";

// the day's figures, after the watch cards the site's owner uses: the high in the rising colour,
// the low in the falling one

function usd(lang: Lang, value: number): string {
  return `US$${new Intl.NumberFormat(lang, { notation: "compact", maximumFractionDigits: 1 }).format(value)}`;
}

function count(lang: Lang, value: number): string {
  return new Intl.NumberFormat(lang).format(value);
}

const CHANGE_TONE: Record<string, string> = {
  new: "text-rise border-rise/40",
  increased: "text-rise border-rise/40",
  decreased: "text-fall border-fall/40",
  sold_out: "text-fall border-fall/40",
  unchanged: "text-muted border-line",
};

function Holder({ holder, lang }: { holder: PublicHolder; lang: Lang }) {
  const w = words(lang).stock;
  // an option is a bet, not a holding: its badge is not coloured as buying or selling the stock,
  // it says which way the bet goes, and its count is of the shares underneath
  const option = holder.put_call ? (w.options[holder.put_call] ?? holder.put_call) : null;
  const tone = option ? CHANGE_TONE.unchanged : (CHANGE_TONE[holder.change] ?? CHANGE_TONE.unchanged);
  return (
    <li className="grid gap-2 py-4 sm:grid-cols-[1fr_auto] sm:items-center" data-testid="holder">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2">
          <span className="font-semibold">{holder.investor}</span>
          <span className={`rounded-full border px-2 py-px text-xs ${tone}`}>
            {w.changes[holder.change] ?? holder.change}
            {option ? `・${option}` : null}
          </span>
          <span className="truncate text-xs text-muted">{holder.title_of_class}</span>
        </p>
        <p className="mt-1 text-xs text-muted">{holder.filer}</p>
      </div>
      <dl className="grid grid-cols-3 gap-3 text-sm tabular-nums sm:w-96 sm:text-right">
        <div>
          <dt className="text-xs text-muted">{option ? w.underlying : w.shares}</dt>
          <dd>{count(lang, holder.shares)}</dd>
          {holder.change !== "unchanged" && holder.previous_shares ? (
            <dd className="text-xs text-muted">{w.was(count(lang, holder.previous_shares))}</dd>
          ) : null}
        </div>
        <div>
          <dt className="text-xs text-muted">{w.value}</dt>
          <dd>{holder.value_usd ? usd(lang, holder.value_usd) : "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{w.weight}</dt>
          <dd>{holder.portfolio_pct !== null && holder.portfolio_pct !== undefined ? `${holder.portfolio_pct}%` : "—"}</dd>
          <dd className="text-xs">
            <a href={holder.filing_url} rel="noopener nofollow" className="text-accent hover:underline">
              {w.filing} ↗
            </a>
          </dd>
        </div>
      </dl>
    </li>
  );
}

function amountRange(lang: Lang, trade: PublicTrade): string {
  const s = words(lang).stock;
  const money = (n: number) => `US$${new Intl.NumberFormat(lang).format(n)}`;
  if (trade.amount_min === null || trade.amount_min === undefined) return trade.amount_text || "—";
  if (trade.amount_max === null || trade.amount_max === undefined) return s.over(money(trade.amount_min - 1));
  return `${money(trade.amount_min)} – ${money(trade.amount_max)}`;
}

const TRADE_TONE: Record<string, string> = {
  purchase: "text-rise border-rise/40",
  sale: "text-fall border-fall/40",
  "partial sale": "text-fall border-fall/40",
};

function Trade({ trade, lang }: { trade: PublicTrade; lang: Lang }) {
  const s = words(lang).stock;
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-3 text-sm" data-testid="trade">
      {/* whose it is: a member's spouse's trade is the spouse's, and says so */}
      <span className="font-semibold">
        {trade.person}
        {trade.owner ? <span className="font-normal text-muted">（{s.owners[trade.owner] ?? trade.owner}）</span> : null}
      </span>
      <span className={`rounded-full border px-2 py-px text-xs ${TRADE_TONE[trade.kind] ?? "border-line text-muted"}`}>
        {s.kinds[trade.kind] ?? trade.kind}
      </span>
      {/* an option is a bet on the stock, not the stock */}
      {trade.option ? <span className="rounded-full border border-line px-2 py-px text-xs text-muted">{s.option}</span> : null}
      <span className="tabular-nums">{amountRange(lang, trade)}</span>
      <span className="text-xs text-muted tabular-nums">
        {trade.traded_on ? formatDate(lang, trade.traded_on) : "—"}
        {trade.late ? `・${s.late}` : ""}
      </span>
      <a href={trade.report_url} rel="noopener nofollow" className="ml-auto text-xs text-accent hover:underline">
        {s.report} ↗
      </a>
      {trade.note ? <p className="w-full text-xs text-muted">{trade.note}</p> : null}
    </li>
  );
}

/** How many of our stories a stock page lists at a time (the API's own ten). */
export const COVERAGE_PAGE = 10;

export function StockView({
  stock,
  lang,
  history = null,
  watch = true,
  coverage,
}: {
  stock: PublicStock;
  lang: Lang;
  history?: PublicHistory | null;
  /** Its own 加入觀察 button; the watchlist page puts it in its own title row instead (D-064). */
  watch?: boolean;
  /** Which page of our stories that name it this is, and a page's address (D-066); the stock's
   * own page by default. */
  coverage?: { page: number; to: (page: number) => string };
}) {
  const w = words(lang);
  const s = w.stock;
  const quote = stock.quote;
  const way = quote ? direction(quote) : "flat";
  const change = quote ? formatChange(quote) : null;
  const code = stockCode(`${stock.market}:${stock.symbol}`, stock.exchange);
  const period = stock.holders[0]?.period;
  const before = stock.holders[0]?.previous_period ?? null;
  return (
    <article className="mx-auto max-w-3xl px-4 pt-6 pb-10">
      <header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="flex flex-wrap items-baseline gap-x-3 text-3xl font-bold">
            {stock.name}
            {code && code !== stock.name ? <span className="text-lg font-medium text-muted">{code}</span> : null}
          </h1>
          {watch ? <WatchButton symbol={stock.symbol} lang={lang} /> : null}
        </div>
        {quote ? (
          <div className="mt-3 flex flex-wrap items-end gap-x-3">
            <span className={`text-4xl leading-none font-semibold tabular-nums ${TONE[way]}`}>{formatValue(quote, lang)}</span>
            {change ? (
              <span className={`text-lg leading-none tabular-nums ${TONE[way]}`}>
                {way === "rise" ? "+" : way === "fall" ? "−" : ""}
                {change} {ARROW[way]}
              </span>
            ) : null}
            {/* the market value above where the price comes from: one block beside the price */}
            <span className="flex flex-col text-xs leading-snug text-muted">
              {quote.market_cap ? (
                <span data-testid="market-cap">
                  {s.marketCap}{" "}
                  <span className="font-medium text-ink tabular-nums">{formatCap(quote.market_cap, quote.currency, lang)}</span>
                </span>
              ) : null}
              <span>
                {w.basis[quote.basis]} {formatDate(lang, quote.as_of)}・{w.sourceNames[quote.source] ?? quote.source}
              </span>
            </span>
          </div>
        ) : (
          <p className="mt-3 text-muted">{s.noQuote}</p>
        )}
      </header>

      {history ? (
        <section className="mt-5" aria-labelledby="chart">
          <h2 id="chart" className="sr-only">
            {w.chart.title}
          </h2>
          <StockChart
            bars={history.bars}
            lang={lang}
            market={stock.market}
            symbol={stock.symbol}
            source={history.source ?? null}
            preparing={history.preparing ?? false}
          />
        </section>
      ) : null}

      {/* US filings say nothing about a stock with no US listing: 13F holders and officials'
          trades only for a US stock or a Taiwan one's ADR (2330 → TSM) */}
      {stock.us_listing ? (
        <>
        {/* 13F holders only where the CUSIPs are known: the strip's stocks (D-061) */}
        {stock.tracks_13f ? (
        <section className="mt-8" aria-labelledby="holders">
          <h2 id="holders" className="text-xl font-bold">
            {s.holders}
          </h2>
          {stock.holders.length ? (
            <>
              <p className="mt-2 text-xs leading-relaxed text-muted">
                {stock.market === "tw" ? `${s.holdersUs} ` : ""}
                {period ? s.holdersNote(formatDate(lang, period), before ? formatDate(lang, before) : null) : null}
              </p>
              <ul className="mt-2 divide-y divide-line">
                {stock.holders.map((holder, i) => (
                  <Holder key={`${holder.investor}-${holder.title_of_class}-${holder.put_call}-${i}`} holder={holder} lang={lang} />
                ))}
              </ul>
            </>
          ) : (
            <p className="mt-3 text-muted">{stock.market === "tw" ? s.twNo13f : s.holdersNone}</p>
          )}
        </section>
        ) : null}

        <section className="mt-10" aria-labelledby="trades">
          <h2 id="trades" className="text-xl font-bold">
            {s.trades}
          </h2>
          {/* D-052: pointed to where these are already published, not compiled here — any trades
              a person has checked from our own transcriptions (D-051, now off) still show */}
          {stock.trades.length ? (
            <>
              <p className="mt-2 text-xs leading-relaxed text-muted">{s.tradesNote}</p>
              <ul className="mt-2 divide-y divide-line">
                {stock.trades.map((trade, i) => (
                  <Trade key={`${trade.report_url}-${i}`} trade={trade} lang={lang} />
                ))}
              </ul>
            </>
          ) : null}
          <p className="mt-3 text-sm text-muted">{s.tradesElsewhere}</p>
          <ul className="mt-2 flex flex-wrap gap-2 text-sm" data-testid="trackers">
            {s.trackers.map(([label, href]) => (
              <li key={href}>
                <a
                  href={href}
                  target="_blank"
                  rel="noopener nofollow"
                  className="inline-block rounded-full border border-line px-3 py-1 hover:border-accent hover:text-accent"
                >
                  {label} ↗
                </a>
              </li>
            ))}
          </ul>
        </section>
        </>
      ) : null}

      {/* how the week's news about it reads (D-091): the strip's stocks, above our own stories */}
      <NewsSentiment symbol={stock.symbol} lang={lang} />

      <section id="coverage" className="mt-10 scroll-mt-24" aria-labelledby="coverage-title">
        <h2 id="coverage-title" className="text-xl font-bold">
          {s.coverage}
        </h2>
        {stock.articles.length ? (
          <>
            <ul className="mt-2 divide-y divide-line">
              {stock.articles.map((article) => (
                <li key={article.article_id} className="py-4">
                  <Link href={article.path} className="font-semibold hover:text-accent">
                    {article.title}
                  </Link>
                  <p className="mt-1 text-xs text-muted">
                    <time dateTime={article.published_at} className="text-date">{formatDate(lang, article.published_at)}</time>
                  </p>
                </li>
              ))}
            </ul>
            <Pagination
              lang={lang}
              page={coverage?.page ?? 1}
              total={Math.ceil((stock.articles_total ?? 0) / COVERAGE_PAGE)}
              to={coverage?.to ?? ((n) => `/news/${lang}/stocks/${stock.symbol}${n > 1 ? `?page=${n}` : ""}#coverage`)}
            />
          </>
        ) : (coverage?.page ?? 1) > 1 ? (
          <p className="mt-3 text-muted">{s.coveragePast}</p>
        ) : (
          <p className="mt-3 text-muted">{s.coverageNone}</p>
        )}
      </section>

      <p className="mt-10 rounded-lg bg-canvas p-4 text-xs leading-relaxed text-muted">{stock.tracks_13f ? s.notice : s.noticeNo13f}</p>
      <p className="mt-6 text-sm">
        <Link href={`/news/${lang}`} className="text-accent hover:underline">
          {s.back}
        </Link>
      </p>
    </article>
  );
}
