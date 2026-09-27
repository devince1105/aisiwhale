import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { cache } from "react";

import { fetchHistory, fetchStock } from "@/features/site/api";
import { isLang, words } from "@/features/site/i18n";
import { COVERAGE_PAGE, StockView } from "@/features/site/StockView";
import { WatchlistSide } from "@/features/site/Watchlist";

// its figure changes every few minutes, its holders a few times a year: a minute is fresh enough
export const revalidate = 60;

type Params = Promise<{ lang: string; symbol: string }>;
type Search = Promise<{ [key: string]: string | string[] | undefined }>;

const load = cache((symbol: string, lang: string, page = 1) =>
  fetchStock(symbol, lang, {
    company: process.env.SITE_COMPANY || undefined,
    articlesOffset: (page - 1) * COVERAGE_PAGE,
  }),
);

/** Which page of the stories that name it (D-066): ``?page=``, 1 to 500. */
async function pageOf(searchParams: Search): Promise<number> {
  const query = await searchParams;
  return Math.min(Math.max(Number.parseInt(String(query.page ?? "1"), 10) || 1, 1), 500);
}

export async function generateMetadata({ params, searchParams }: { params: Params; searchParams: Search }): Promise<Metadata> {
  const { lang, symbol } = await params;
  if (!isLang(lang)) return {};
  const stock = await load(symbol, lang, await pageOf(searchParams));
  if (!stock) return {};
  return { title: `${stock.name} ${stock.symbol} · ${words(lang).site}` };
}

export default async function Page({ params, searchParams }: { params: Params; searchParams: Search }) {
  const { lang, symbol } = await params;
  if (!isLang(lang)) notFound();
  const page = await pageOf(searchParams);
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
        <StockView stock={stock} lang={lang} history={history} coverage={{ page, to: (n) => `/news/${lang}/stocks/${stock.symbol}${n > 1 ? `?page=${n}` : ""}#coverage` }} />
      </div>
    </div>
  );
}
