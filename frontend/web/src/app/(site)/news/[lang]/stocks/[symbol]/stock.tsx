// A stock's page (D-049) and a later page of the stories that name it (D-066): what the bare
// address (page.tsx) and ?page= (browse/[...facets], by a rewrite: queryRoutes.ts) both show.
// Nothing here reads the request, so both are built and kept (ISR).
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { cache } from "react";

import { fetchHistory, fetchStock } from "@/features/site/api";
import { isLang, words } from "@/features/site/i18n";
import { COVERAGE_PAGE, StockView } from "@/features/site/StockView";
import { WatchlistSide } from "@/features/site/Watchlist";

const load = cache((symbol: string, lang: string, page = 1) =>
  fetchStock(symbol, lang, {
    company: process.env.SITE_COMPANY || undefined,
    articlesOffset: (page - 1) * COVERAGE_PAGE,
  }),
);

/** Which page of the stories that name it (D-066): ``?page=``, 1 to 500. */
export function pageOf(query: Record<string, string | undefined>): number {
  return Math.min(Math.max(Number.parseInt(String(query.page ?? "1"), 10) || 1, 1), 500);
}

function href(lang: string, symbol: string, page: number): string {
  return `/news/${lang}/stocks/${symbol}${page > 1 ? `?page=${page}` : ""}`;
}

export async function stockMetadata(lang: string, symbol: string, page: number): Promise<Metadata> {
  if (!isLang(lang)) return {};
  const stock = await load(symbol, lang, page);
  if (!stock) return {};
  return {
    title: `${stock.name} ${stock.symbol} · ${words(lang).site}`,
    alternates: { canonical: href(lang, stock.symbol, page) },
  };
}

export async function StockPage({ lang, symbol, page }: { lang: string; symbol: string; page: number }) {
  if (!isLang(lang)) notFound();
  const [stock, history] = await Promise.all([
    load(symbol, lang, page),
    // a chart that cannot be loaded leaves the page without one, not without a page
    fetchHistory(symbol).catch(() => null),
  ]);
  if (!stock) notFound();
  // the reader's watchlist beside the stock (D-060), hidden until asked for (D-066): a column on
  // a wide screen, a row on a phone
  return (
    <div className="mx-auto max-w-6xl lg:flex lg:flex-wrap lg:gap-x-6 lg:px-4">
      <WatchlistSide lang={lang} current={`${stock.market}:${stock.symbol}`} />
      <div className="min-w-0 flex-1">
        <StockView stock={stock} lang={lang} history={history} coverage={{ page, to: (n) => `${href(lang, stock.symbol, n)}#coverage` }} />
      </div>
    </div>
  );
}
