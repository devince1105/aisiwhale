"use client";

// A reader's watchlist on the site (D-060, D-061): the button on a stock's page, the list beside
// it (a column on a wide screen, a row to scroll on a phone), and the watchlist page with a search
// for any listed Taiwan or US stock. Prices: the strip's own for its stocks, the last stored close
// for any other (a stock just added has none until its prices are fetched).
import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useEffect, useMemo, useState } from "react";

import { useRouter, useSearchParams } from "next/navigation";

import { API_URL } from "@/config";

import {
  fetchHistory,
  fetchMarkets,
  fetchQuotes,
  fetchStock,
  searchSecurities,
  type PublicHistory,
  type PublicQuote,
  type PublicSecurity,
  type PublicStock,
} from "./api";
import { formatDate, words, type Lang } from "./i18n";
import { StockView } from "./StockView";
import { ARROW, direction, formatChange, formatValue, label, stockCode, stockPage, TONE } from "./quote";
import { reorderWatchlist, setWatched, useWatchlist, type WatchedStock } from "./watchlistStore";

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

function Row({
  item,
  quote,
  lang,
  current,
  plain = false,
}: {
  item: WatchedStock;
  quote?: PublicQuote;
  lang: Lang;
  current?: boolean;
  /** Not a link: inside a button that picks it. */
  plain?: boolean;
}) {
  const way = quote ? direction(quote) : "flat";
  const change = quote ? formatChange(quote) : null;
  const code = stockCode(item.key, item.exchange);
  const page = plain ? null : stockPage(item.key, lang); // an index, a rate, oil or a coin has none
  const Tag = page ? "a" : "div";
  return (
    <Tag
      href={page ?? undefined}
      aria-current={current ? "page" : undefined}
      className={`flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm ${page || plain ? "hover:bg-canvas" : ""} ${current ? "bg-canvas ring-1 ring-accent" : ""}`}
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
        <p className="mb-2 flex items-baseline justify-between px-3 text-xs tracking-wide text-muted">
          <a href={`/news/${lang}/watchlist`} className="hover:text-accent">
            {sample ? w.sample : w.title}
          </a>
          {/* the list is set on its own page, not here (D-064) */}
          {sample ? null : (
            <a href={`/news/${lang}/watchlist?edit=1`} className="text-accent hover:underline" data-testid="watchlist-edit-link">
              {w.editLink}
            </a>
          )}
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

/** The watchlist's settings (D-064: behind 編輯清單 on its page): search to add, drag to order,
 * take off, and the strip's figures to add back. */
function WatchlistEditor({ lang }: { lang: Lang }) {
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
        <SortableList items={list.items} byKey={byKey} lang={lang} />
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

/** The list on the watchlist page, in the reader's order, dragged by its handle (D-063): with a
 * mouse, a finger (after a short hold, so the page still scrolls) or the keyboard (space, the
 * arrows, space). */
function SortableList({
  items,
  byKey,
  lang,
}: {
  items: WatchedStock[];
  byKey: Map<string, PublicQuote>;
  lang: Lang;
}) {
  const w = words(lang).watch;
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const keys = items.map((item) => item.key);
  const nameOf = (id: string | number) => items.find((item) => item.key === String(id))?.name ?? String(id);
  const placeOf = (id: string | number) => keys.indexOf(String(id)) + 1;
  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const moved = arrayMove(keys, keys.indexOf(String(active.id)), keys.indexOf(String(over.id)));
    void reorderWatchlist(moved);
  };
  return (
    <div>
      <p className="mb-2 text-xs text-muted">{w.reorderHint}</p>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={onDragEnd}
        accessibility={{
          screenReaderInstructions: { draggable: w.dnd.instructions },
          announcements: {
            onDragStart: ({ active }) => w.dnd.start(nameOf(active.id)),
            onDragOver: ({ active, over }) => (over ? w.dnd.over(nameOf(active.id), placeOf(over.id)) : undefined),
            onDragEnd: ({ active, over }) => (over ? w.dnd.end(nameOf(active.id), placeOf(over.id)) : undefined),
            onDragCancel: ({ active }) => w.dnd.cancel(nameOf(active.id)),
          },
        }}
      >
        <SortableContext items={keys} strategy={verticalListSortingStrategy}>
          <ul className="divide-y divide-line rounded-lg border border-line" data-testid="watchlist">
            {items.map((item) => (
              <SortableRow key={item.key} item={item} quote={byKey.get(item.key)} lang={lang} />
            ))}
          </ul>
        </SortableContext>
      </DndContext>
    </div>
  );
}

function SortableRow({ item, quote, lang }: { item: WatchedStock; quote?: PublicQuote; lang: Lang }) {
  const w = words(lang).watch;
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.key });
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`flex items-center gap-1 bg-surface pr-3 ${isDragging ? "relative z-10 shadow-lg" : ""}`}
    >
      <button
        type="button"
        ref={setActivatorNodeRef}
        {...attributes}
        {...listeners}
        aria-label={w.drag(item.name)}
        className="cursor-grab touch-none self-stretch px-2 text-muted hover:text-ink active:cursor-grabbing"
      >
        ⋮⋮
      </button>
      <div className="min-w-0 flex-1">
        <Row item={item} quote={quote} lang={lang} />
      </div>
        <button
          type="button"
          onClick={() => void setWatched(item.symbol, false)}
          className="text-xs text-muted hover:text-accent"
        >
          {w.remove}
        </button>
    </li>
  );
}

/** The watchlist page (D-064): the list to watch — each figure, and the one picked with its
 * chart beside it, as a trading screen has it — and, behind 編輯清單, its settings. ``?s=`` is
 * the one picked, ``?edit=1`` opens the settings. */
export function WatchlistPage({ lang }: { lang: Lang }) {
  const w = words(lang).watch;
  const router = useRouter();
  const params = useSearchParams();
  const editing = params.get("edit") === "1";
  const list = useWatchlist(lang);
  const strip = useStrip();
  const sample = list.status === "signedOut";
  const items = list.status === "ready" ? list.items : sample ? stripItems(strip, words(lang).quoteNames) : [];
  const listed = useQuotes(list.status === "ready" ? list.items.map((item) => item.key) : []);
  const byKey = sample ? new Map(strip.map((q) => [q.key, q])) : listed;
  const picked = items.find((item) => item.key === params.get("s")) ?? items[0] ?? null;
  const go = (query: Record<string, string>) => router.replace(`/news/${lang}/watchlist?${new URLSearchParams(query)}`, { scroll: false });

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">{w.title}</h1>
        <button
          type="button"
          onClick={() => go(editing ? (picked ? { s: picked.key } : {}) : { edit: "1" })}
          aria-pressed={editing}
          className={`rounded-full border px-4 py-1.5 text-sm ${editing ? "border-accent bg-accent text-accent-ink" : "border-line hover:border-accent hover:text-accent"}`}
          data-testid="watchlist-edit"
        >
          {editing ? w.done : w.edit}
        </button>
      </div>
      {editing ? (
        <div className="max-w-3xl">
          <WatchlistEditor lang={lang} />
        </div>
      ) : list.status === "loading" ? (
        <p className="text-muted">…</p>
      ) : list.status === "failed" ? (
        <p className="text-muted">{w.failed}</p>
      ) : !items.length ? (
        <p className="text-muted">{w.emptyBoard}</p>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[16rem_minmax(0,1fr)]" data-testid="watch-board">
          <nav aria-label={w.title}>
            {sample ? <p className="mb-2 px-3 text-xs text-muted">{w.sample}</p> : null}
            {/* a phone: a row to scroll; a wide screen: a column */}
            <ul className="flex gap-2 overflow-x-auto pb-1 lg:grid lg:gap-1 lg:overflow-visible">
              {items.map((item) => (
                <li key={item.key} className="shrink-0 lg:shrink">
                  <button
                    type="button"
                    onClick={() => go({ s: item.key })}
                    aria-current={item.key === picked?.key ? "true" : undefined}
                    className="block w-full text-left"
                  >
                    <span className="lg:hidden">
                      <span className={`block rounded-full border px-3 py-1 text-sm ${item.key === picked?.key ? "border-accent text-accent" : "border-line"}`}>
                        {item.name}
                      </span>
                    </span>
                    <span className="hidden lg:block">
                      <Row item={item} quote={byKey.get(item.key)} lang={lang} current={item.key === picked?.key} plain />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </nav>
          {picked ? <WatchPane key={picked.key} item={picked} quote={byKey.get(picked.key)} lang={lang} /> : null}
        </div>
      )}
    </div>
  );
}

/** The one picked (D-064): a stock as its whole page — figure, chart, holders, coverage — and an
 * index, a rate, oil or a coin as its figure, which is all it has. */
function WatchPane({ item, quote, lang }: { item: WatchedStock; quote?: PublicQuote; lang: Lang }) {
  const w = words(lang);
  const page = stockPage(item.key, lang);
  const [detail, setDetail] = useState<{ stock: PublicStock | null; history: PublicHistory | null } | null>(null);
  useEffect(() => {
    if (!page) return;
    let live = true;
    const symbol = symbolOf(item.key);
    void Promise.all([
      fetchStock(symbol, lang, { baseUrl: API_URL }).catch(() => null),
      fetchHistory(symbol, { baseUrl: API_URL }).catch(() => null),
    ]).then(([stock, history]) => live && setDetail({ stock, history }));
    return () => {
      live = false;
    };
  }, [item.key, lang, page]);

  if (page) {
    return (
      <div className="min-w-0 [&>article]:max-w-none [&>article]:px-0 [&>article]:pt-0" data-testid="watch-pane">
        {detail === null ? (
          <p className="flex h-80 items-center justify-center text-sm text-muted">…</p>
        ) : detail.stock ? (
          <StockView stock={detail.stock} lang={lang} history={detail.history} />
        ) : (
          <p className="rounded-lg border border-line p-4 text-sm text-muted">{w.stock.noQuote}</p>
        )}
      </div>
    );
  }
  const way = quote ? direction(quote) : "flat";
  const change = quote ? formatChange(quote) : null;
  return (
    <section aria-labelledby="watch-pane" className="min-w-0" data-testid="watch-pane">
      <h2 id="watch-pane" className="text-2xl font-bold">
        {item.name}
      </h2>
      {quote ? (
        <div className="mt-2 flex flex-wrap items-end gap-x-3">
          <span className={`text-3xl leading-none font-semibold tabular-nums ${TONE[way]}`}>{formatValue(quote, lang)}</span>
          {change ? (
            <span className={`text-base leading-none tabular-nums ${TONE[way]}`}>
              {way === "rise" ? "+" : way === "fall" ? "−" : ""}
              {change} {ARROW[way]}
            </span>
          ) : null}
          <span className="text-xs text-muted">
            {w.basis[quote.basis]} {formatDate(lang, quote.as_of)}・{w.sourceNames[quote.source] ?? quote.source}
          </span>
        </div>
      ) : null}
      <p className="mt-5 rounded-lg border border-line p-4 text-sm text-muted">{w.watch.noChart}</p>
    </section>
  );
}
