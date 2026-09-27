// The stocks an article names (D-077), each straight to its chart on the watchlist page — on the
// article's page, and under it in the lists (D-078).
import Link from "next/link";

import type { PublicArticleSummary } from "./api";
import { words, type Lang } from "./i18n";
import { stockCode } from "./quote";

export function StocksNamed({
  stocks,
  lang,
  compact = false,
}: {
  stocks: PublicArticleSummary["stocks"];
  lang: Lang;
  /** In a list: smaller, and no label before them. */
  compact?: boolean;
}) {
  if (!stocks?.length) return null;
  const w = words(lang);
  // a story's stocks (tw:2330) or its figures — a coin, gold, oil, a currency (D-079)
  const label = stocks.some((s) => s.key.includes(":")) ? w.stocksNamed : w.figuresNamed;
  return (
    <nav
      aria-label={label}
      className={`flex flex-wrap items-center gap-2 print:hidden ${compact ? "mt-2 text-xs" : "mt-4 text-sm"}`}
      data-testid="stocks-named"
    >
      {compact ? null : <span className="text-muted">{label}</span>}
      {stocks.map((stock) => (
        <Link
          key={stock.key}
          href={`/news/${lang}/watchlist?${new URLSearchParams({ s: stock.key })}`}
          className={`rounded-full border border-line hover:border-accent hover:text-accent ${compact ? "px-2 py-px text-muted" : "px-3 py-0.5"}`}
        >
          {stock.name}
          <span className="ml-1 text-muted">{stockCode(stock.key) ?? stock.symbol}</span>
        </Link>
      ))}
    </nav>
  );
}
