import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { cache } from "react";

import { fetchHistory, fetchStock } from "@/features/site/api";
import { isLang, words } from "@/features/site/i18n";
import { StockView } from "@/features/site/StockView";
import { WatchlistSide } from "@/features/site/Watchlist";

// its figure changes every few minutes, its holders a few times a year: a minute is fresh enough
export const revalidate = 60;

type Params = Promise<{ lang: string; symbol: string }>;

const load = cache((symbol: string, lang: string) =>
  fetchStock(symbol, lang, { company: process.env.SITE_COMPANY || undefined }),
);

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { lang, symbol } = await params;
  if (!isLang(lang)) return {};
  const stock = await load(symbol, lang);
  if (!stock) return {};
  return { title: `${stock.name} ${stock.symbol} · ${words(lang).site}` };
}

export default async function Page({ params }: { params: Params }) {
  const { lang, symbol } = await params;
  if (!isLang(lang)) notFound();
  const [stock, history] = await Promise.all([
    load(symbol, lang),
    // a chart that cannot be loaded leaves the page without one, not without a page
    fetchHistory(symbol).catch(() => null),
  ]);
  if (!stock) notFound();
  // the reader's watchlist beside the stock (D-060): a column on a wide screen, a row on a phone
  return (
    <div className="mx-auto max-w-6xl lg:flex lg:gap-6 lg:px-4">
      <aside className="lg:w-56 lg:shrink-0 lg:pt-6">
        <WatchlistSide lang={lang} current={`${stock.market}:${stock.symbol}`} />
      </aside>
      <div className="min-w-0 flex-1">
        <StockView stock={stock} lang={lang} history={history} />
      </div>
    </div>
  );
}
