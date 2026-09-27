"use client";

// A reader's watchlist on the site (D-060): the button on a stock's page, the list beside it
// (a column on a wide screen, a row to scroll on a phone), and the watchlist page. Prices are the
// market strip's own, fetched once; a stock off the strip shows its name alone.
import { useEffect, useState } from "react";

import { fetchMarkets, type PublicQuote } from "./api";
import { words, type Lang } from "./i18n";
import { ARROW, direction, formatChange, formatValue, label, stockCode, stockPage, TONE } from "./quote";
import { setWatched, useWatchlist, type WatchedStock } from "./watchlistStore";

function useQuotes(): PublicQuote[] {
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

const isStock = (key: string) => key.startsWith("tw:") || key.startsWith("us:");

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
  const code = stockCode(item.key);
  return (
    <a
      href={stockPage(item.key, lang) ?? "#"}
      aria-current={current ? "page" : undefined}
      className={`flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm hover:bg-canvas ${current ? "bg-canvas ring-1 ring-accent" : ""}`}
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
    </a>
  );
}

/** Beside a stock: the reader's list, the stock on show marked. Nothing when signed out or
 * empty — the page is the stock's, not a prompt. */
export function WatchlistSide({ lang, current }: { lang: Lang; current: string }) {
  const w = words(lang).watch;
  const list = useWatchlist(lang);
  const quotes = useQuotes();
  if (list.status !== "ready" || !list.items.length) return null;
  const byKey = new Map(quotes.map((q) => [q.key, q]));
  return (
    <nav aria-label={w.title} data-testid="watchlist-side">
      {/* a phone: a row to scroll above the stock */}
      <div className="mx-auto max-w-3xl px-4 pt-4 lg:hidden">
        <ul className="flex gap-2 overflow-x-auto pb-1">
          {list.items.map((item) => (
            <li key={item.key} className="shrink-0">
              <a
                href={stockPage(item.key, lang) ?? "#"}
                aria-current={item.key === current ? "page" : undefined}
                className={`block rounded-full border px-3 py-1 text-sm ${item.key === current ? "border-accent text-accent" : "border-line"}`}
              >
                {item.name}
              </a>
            </li>
          ))}
        </ul>
      </div>
      {/* a wide screen: a column to the left */}
      <div className="hidden lg:block">
        <p className="mb-2 px-3 text-xs tracking-wide text-muted">
          <a href={`/news/${lang}/watchlist`} className="hover:text-accent">
            {w.title}
          </a>
        </p>
        <ul className="grid gap-1">
          {list.items.map((item) => (
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
  const quotes = useQuotes();
  const byKey = new Map(quotes.map((q) => [q.key, q]));

  if (list.status === "loading") return <p className="text-muted">…</p>;
  if (list.status === "failed") return <p className="text-muted">{w.failed}</p>;
  if (list.status === "signedOut") {
    return (
      <div className="rounded-lg border border-line p-5" data-testid="watchlist-signed-out">
        <p>{w.signInToWatch}</p>
        <a
          href={`/news/${lang}/login?next=${encodeURIComponent(`/news/${lang}/watchlist`)}`}
          className="mt-3 inline-block rounded-full bg-accent px-4 py-1.5 text-sm font-semibold text-surface"
        >
          {words(lang).signIn}
        </a>
      </div>
    );
  }
  const watched = new Set(list.items.map((item) => item.key));
  const addable = quotes.filter((q) => isStock(q.key) && !watched.has(q.key));
  return (
    <div className="grid gap-8">
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
                    onClick={() => void setWatched(quote.key.slice(3), true)}
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
