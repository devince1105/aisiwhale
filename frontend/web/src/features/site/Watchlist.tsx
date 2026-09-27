"use client";

// A reader's watchlist on the site (D-060, D-061): the button on a stock's page, the list beside
// it (a column on a wide screen, a row to scroll on a phone), and the watchlist page with a search
// for any listed Taiwan or US stock. Prices: the strip's own for its stocks, the last stored close
// for any other (a stock just added has none until its prices are fetched).
import { useEffect, useMemo, useState } from "react";

import { fetchMarkets, fetchQuotes, searchSecurities, type PublicQuote, type PublicSecurity } from "./api";
import { words, type Lang } from "./i18n";
import { ARROW, direction, formatChange, formatValue, label, stockCode, stockPage, TONE } from "./quote";
import { setWatched, useWatchlist, type WatchedStock } from "./watchlistStore";

/** The strip's quotes: the popular stocks the watchlist page offers. */
function useStrip(): PublicQuote[] {
  const [quotes, setQuotes] = useState<PublicQuote[]>([]);
  useEffect(() => {
    let live = true;
    void fetchMarkets().then((answer) => live && setQuotes(answer));
    return () => {
      live = false;
    };
  }, []);
  return quotes;
}

/** Quotes for the stocks on the list, whichever they are. */
function useQuotes(keys: string[]): Map<string, PublicQuote> {
  const [quotes, setQuotes] = useState<PublicQuote[]>([]);
  const joined = keys.join(",");
  useEffect(() => {
    let live = true;
    void fetchQuotes(joined ? joined.split(",") : []).then((answer) => live && setQuotes(answer));
    return () => {
      live = false;
    };
  }, [joined]);
  return useMemo(() => new Map(quotes.map((q) => [q.key, q])), [quotes]);
}

/** The symbol the watchlist API takes for a strip key: ``tw:2330`` → 2330, ``btc`` → BTC. */
export const symbolOf = (key: string) => (key.includes(":") ? key.split(":")[1] : key.toUpperCase());

/** The strip's entries as watchlist items: what a signed-out reader is shown as a sample, and
 * what a new watchlist starts as (D-062). */
export function stripItems(quotes: PublicQuote[], names: Record<string, string>): WatchedStock[] {
  return quotes.map((q) => ({
    key: q.key,
    symbol: symbolOf(q.key),
    market: q.key.includes(":") ? q.key.split(":")[0] : "market",
    name: label(q.key, names)[0],
  }));
}

/** 加入觀察 / 已觀察 on a stock's page; signed out, a way to sign in and come back. */
export function WatchButton({ symbol, lang }: { symbol: string; lang: Lang }) {
  const w = words(lang).watch;
  const list = useWatchlist(lang);
  const [busy, setBusy] = useState(false);
  const base = "rounded-full border px-3 py-1 text-sm whitespace-nowrap";
  if (list.status === "loading" || list.status === "failed") return null;
  if (list.status === "signedOut") {
    const next = typeof window === "undefined" ? "" : `?next=${encodeURIComponent(window.location.pathname)}`;
    return (
      <a href={`/news/${lang}/login${next}`} className={`${base} border-line text-muted hover:border-accent hover:text-accent`}>
        {w.add}
      </a>
    );
  }
  const watched = list.items.some((item) => item.symbol === symbol);
  return (
    <button
      type="button"
      disabled={busy}
      aria-pressed={watched}
      data-testid="watch-button"
      onClick={async () => {
        setBusy(true);
        await setWatched(symbol, !watched).catch(() => false);
        setBusy(false);
      }}
      className={`${base} disabled:opacity-50 ${watched ? "border-accent text-accent" : "border-line text-muted hover:border-accent hover:text-accent"}`}
    >
      {watched ? w.added : w.add}
    </button>
  );
}

function Row({ item, quote, lang, current }: { item: WatchedStock; quote?: PublicQuote; lang: Lang; current?: boolean }) {
  const way = quote ? direction(quote) : "flat";
  const change = quote ? formatChange(quote) : null;
  const code = stockCode(item.key, item.exchange);
  const page = stockPage(item.key, lang); // an index, a rate, oil or a coin has none
  const Tag = page ? "a" : "div";
  return (
    <Tag
      href={page ?? undefined}
      aria-current={current ? "page" : undefined}
      className={`flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm ${page ? "hover:bg-canvas" : ""} ${current ? "bg-canvas ring-1 ring-accent" : ""}`}
    >
      <span className="min-w-0">
        <span className="block truncate font-medium">{item.name}</span>
        <span className="block text-xs text-muted">{code}</span>
      </span>
      {quote ? (
        <span className={`text-right tabular-nums ${TONE[way]}`}>
          <span className="block">{formatValue(quote, lang)}</span>
          {change ? (
            <span className="block text-xs">
              {way === "rise" ? "+" : way === "fall" ? "−" : ""}
              {change} {ARROW[way]}
            </span>
          ) : null}
        </span>
      ) : null}
    </Tag>
  );
}

/** Beside a stock: the reader's list, the stock on show marked. Nothing when signed out or
 * empty — the page is the stock's, not a prompt. */
export function WatchlistSide({ lang, current }: { lang: Lang; current: string }) {
  const w = words(lang).watch;
  const list = useWatchlist(lang);
  const strip = useStrip();
  const sample = list.status === "signedOut";
  // signed out: the strip itself, as a sample of what a list can be (D-062)
  const items =
    list.status === "ready" ? list.items : sample ? stripItems(strip, words(lang).quoteNames) : [];
  const listed = useQuotes(list.status === "ready" ? list.items.map((item) => item.key) : []);
  const byKey = sample ? new Map(strip.map((q) => [q.key, q])) : listed;
  if (!items.length) return null;
  return (
    <nav aria-label={w.title} data-testid="watchlist-side">
      {/* a phone: a row to scroll above the stock */}
      <div className="mx-auto max-w-3xl px-4 pt-4 lg:hidden">
        <ul className="flex gap-2 overflow-x-auto pb-1">
          {items.map((item) => (
            <li key={item.key} className="shrink-0">
              {stockPage(item.key, lang) ? (
                <a
                  href={stockPage(item.key, lang)!}
                  aria-current={item.key === current ? "page" : undefined}
                  className={`block rounded-full border px-3 py-1 text-sm ${item.key === current ? "border-accent text-accent" : "border-line"}`}
                >
                  {item.name}
                </a>
              ) : (
                <span className="block rounded-full border border-line px-3 py-1 text-sm text-muted">{item.name}</span>
              )}
            </li>
          ))}
        </ul>
      </div>
      {/* a wide screen: a column to the left */}
      <div className="hidden lg:block">
        <p className="mb-2 px-3 text-xs tracking-wide text-muted">
          <a href={`/news/${lang}/watchlist`} className="hover:text-accent">
            {sample ? w.sample : w.title}
          </a>
        </p>
        <ul className="grid gap-1">
          {items.map((item) => (
            <li key={item.key}>
              <Row item={item} quote={byKey.get(item.key)} lang={lang} current={item.key === current} />
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}

/** The watchlist page: the list with a way to take stocks off, and the stocks that can go on. */
export function WatchlistPage({ lang }: { lang: Lang }) {
  const w = words(lang).watch;
  const names = words(lang).quoteNames;
  const list = useWatchlist(lang);
  const quotes = useStrip();
  const byKey = useQuotes(list.status === "ready" ? list.items.map((item) => item.key) : []);

  if (list.status === "loading") return <p className="text-muted">…</p>;
  if (list.status === "failed") return <p className="text-muted">{w.failed}</p>;
  if (list.status === "signedOut") {
    // not signed in: what a list starts as — the market strip — as a sample (D-062)
    const sample = stripItems(quotes, names);
    return (
      <div className="grid gap-8">
        <Search lang={lang} watched={null} />
        <div className="rounded-lg border border-line p-5" data-testid="watchlist-signed-out">
          <p>{w.signInToWatch}</p>
          <a
            href={`/news/${lang}/login?next=${encodeURIComponent(`/news/${lang}/watchlist`)}`}
            className="mt-3 inline-block rounded-full bg-accent px-4 py-1.5 text-sm font-semibold text-surface"
          >
            {words(lang).signIn}
          </a>
        </div>
        {sample.length ? (
          <section aria-labelledby="sample">
            <h2 id="sample" className="mb-2 text-sm text-muted">
              {w.sample}
            </h2>
            <ul className="divide-y divide-line rounded-lg border border-line" data-testid="watchlist-sample">
              {sample.map((item) => (
                <li key={item.key}>
                  <Row item={item} quote={quotes.find((q) => q.key === item.key)} lang={lang} />
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    );
  }
  const watched = new Set(list.items.map((item) => item.key));
  const addable = quotes.filter((q) => !watched.has(q.key));
  return (
    <div className="grid gap-8">
      <Search lang={lang} watched={watched} />
      {list.items.length ? (
        <ul className="divide-y divide-line rounded-lg border border-line" data-testid="watchlist">
          {list.items.map((item) => (
            <li key={item.key} className="flex items-center gap-2 pr-3">
              <div className="min-w-0 flex-1">
                <Row item={item} quote={byKey.get(item.key)} lang={lang} />
              </div>
              <button
                type="button"
                onClick={() => void setWatched(item.symbol, false)}
                className="text-xs text-muted hover:text-accent"
              >
                {w.remove}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted">{w.empty}</p>
      )}
      {addable.length ? (
        <section aria-labelledby="addable">
          <h2 id="addable" className="text-lg font-bold">
            {w.more}
          </h2>
          <ul className="mt-3 flex flex-wrap gap-2" data-testid="addable">
            {addable.map((quote) => {
              const [name, code] = label(quote.key, names);
              return (
                <li key={quote.key}>
                  <button
                    type="button"
                    onClick={() => void setWatched(symbolOf(quote.key), true)}
                    className="rounded-full border border-line px-3 py-1 text-sm hover:border-accent hover:text-accent"
                  >
                    ＋ {name}
                    {code ? <span className="ml-1 text-xs text-muted">{code}</span> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
      <p className="text-xs text-muted">{w.note}</p>
    </div>
  );
}

/** Any listed stock, by code, ticker or name: its page, or onto the list. */
function Search({ lang, watched }: { lang: Lang; watched: Set<string> | null }) {
  const w = words(lang).watch;
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<PublicSecurity[] | null>(null);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setFound(null);
      return;
    }
    let live = true;
    const wait = setTimeout(() => {
      void searchSecurities(q).then((answer) => live && setFound(answer));
    }, 250); // a word, not every letter
    return () => {
      live = false;
      clearTimeout(wait);
    };
  }, [query]);

  return (
    <div>
      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={w.search}
        aria-label={w.searchLabel}
        className="w-full rounded-lg border border-line bg-surface px-3 py-2"
      />
      {found ? (
        found.length ? (
          <ul className="mt-2 divide-y divide-line rounded-lg border border-line" data-testid="search-results">
            {found.map((security) => {
              const key = `${security.market}:${security.symbol}`;
              return (
                <li key={key} className="flex items-center gap-3 px-3 py-2 text-sm">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{security.name}</span>
                    <span className="block text-xs text-muted">
                      {stockCode(key, security.exchange)}・{security.exchange}・{w.kinds[security.kind] ?? security.kind}
                    </span>
                  </span>
                  <a href={stockPage(key, lang) ?? "#"} className="text-xs text-accent underline">
                    {w.view}
                  </a>
                  {watched === null ? (
                    <a
                      href={`/news/${lang}/login?next=${encodeURIComponent(`/news/${lang}/watchlist`)}`}
                      className="rounded-full border border-line px-2 py-0.5 text-xs hover:border-accent hover:text-accent"
                    >
                      {w.addShort}
                    </a>
                  ) : watched.has(key) ? (
                    <span className="text-xs text-muted">{w.added}</span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => void setWatched(security.symbol, true)}
                      className="rounded-full border border-line px-2 py-0.5 text-xs hover:border-accent hover:text-accent"
                    >
                      {w.addShort}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-muted">{w.noResults}</p>
        )
      ) : null}
    </div>
  );
}
