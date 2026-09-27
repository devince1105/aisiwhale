// Spot gold's price and chart (D-070), on the watchlist page when gold is picked (D-071): spot gold in US dollars an ounce, its change on
// the day before, what it is in New Taiwan dollars a gram at the day's reference rate — not Bank
// of Taiwan's gold passbook price, which it says and links to — and the stock pages' chart of
// about five years of days, weeks and months (no volume: gold has none).
import type { PublicGold } from "./api";
import { formatDate, words, type Lang } from "./i18n";
import { ARROW, TONE } from "./quote";
import { StockChart } from "./StockChart";

export function GoldBoard({ gold, lang, bare = false }: { gold: PublicGold; lang: Lang; bare?: boolean }) {
  const w = words(lang).gold;
  const locale = lang === "en" ? "en-US" : "zh-TW";
  const money = (value: number, digits = 2) =>
    value.toLocaleString(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const way = gold.change === null || gold.change === undefined || gold.change === 0 ? "flat" : gold.change > 0 ? "rise" : "fall";
  return (
    // bare: the watchlist's pane, where a stock is its page — no frame, a title its size
    <section
      aria-labelledby="gold-board"
      className={bare ? "min-w-0" : "mt-6 rounded-lg border border-line p-4 sm:p-5"}
      data-testid="gold-board"
    >
      <h2 id="gold-board" className={bare ? "text-2xl font-bold" : "font-bold"}>
        {w.title}
        <span className="ml-2 text-xs font-normal text-muted">{w.unit}</span>
      </h2>
      <div className="mt-3 flex flex-wrap items-end gap-x-3 gap-y-1">
        <span className={`text-4xl leading-none font-semibold tabular-nums ${TONE[way]}`}>{money(gold.usd_per_oz)}</span>
        {gold.change !== null && gold.change !== undefined && gold.change_pct !== null && gold.change_pct !== undefined ? (
          <span className={`text-lg leading-none tabular-nums ${TONE[way]}`}>
            {way === "rise" ? "+" : way === "fall" ? "−" : ""}
            {money(Math.abs(gold.change))} ({money(Math.abs(gold.change_pct))}%) {ARROW[way]}
          </span>
        ) : null}
        <span className="flex flex-col text-xs leading-snug text-muted">
          {gold.twd_per_gram ? (
            <span data-testid="gold-twd">
              {w.perGram}{" "}
              <span className="font-medium text-ink tabular-nums">{money(gold.twd_per_gram, 0)}</span>
            </span>
          ) : null}
          <span>{w.asOf(formatDate(lang, gold.as_of))}</span>
        </span>
      </div>
      <div className="mt-4">
        <StockChart bars={gold.bars} lang={lang} market="gold" symbol="XAUUSD" source={gold.source} volume={false} />
      </div>
      <p className="mt-1 text-xs leading-relaxed text-muted">
        {w.note}{" "}
        <a href={w.bankUrl} target="_blank" rel="noopener" className="text-accent hover:underline">
          {w.bank} ↗
        </a>
      </p>
    </section>
  );
}
