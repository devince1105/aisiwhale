// The 外匯 tab's reference rates (D-069): New Taiwan dollars for one unit of each currency Bank of
// Taiwan posts, in its order and with its names — a market mid rate, once a day. Not the bank's
// own buying and selling rates (those are behind a bot check, in no open dataset): it says so, and
// links to them. The provider's terms ask for its link on the page that shows its rates.
import type { PublicFxBoard } from "./api";
import { formatDate, words, type Lang } from "./i18n";

function rate(lang: Lang, value: number): string {
  return value.toLocaleString(lang === "en" ? "en-US" : "zh-TW", { minimumSignificantDigits: 4, maximumSignificantDigits: 4 });
}

export function FxBoard({ board, lang }: { board: PublicFxBoard; lang: Lang }) {
  const w = words(lang).fx;
  return (
    <section aria-labelledby="fx-board" className="mt-6 rounded-lg border border-line p-4 sm:p-5" data-testid="fx-board">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 id="fx-board" className="font-bold">
          {w.title}
          <span className="ml-2 text-xs font-normal text-muted">{w.unit}</span>
        </h2>
        <p className="text-xs text-muted">
          <time dateTime={board.as_of}>{w.asOf(formatDate(lang, board.as_of))}</time>
        </p>
      </div>
      {/* two columns of rows on a wide screen, one on a phone */}
      <dl className="mt-3 grid grid-cols-1 gap-x-8 text-sm sm:grid-cols-2">
        {board.rates.map((r) => (
          <div key={r.code} className="flex items-baseline justify-between border-b border-line py-1.5">
            <dt>
              {r.name}
              <span className="ml-1.5 text-xs text-muted">{r.code}</span>
            </dt>
            <dd className="tabular-nums">{rate(lang, r.twd)}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-xs leading-relaxed text-muted">
        {w.note}{" "}
        <a href={board.bank_url} target="_blank" rel="noopener" className="text-accent hover:underline">
          {w.bank} ↗
        </a>
      </p>
      <p className="mt-1 text-xs text-muted">
        {w.source}
        <a href={board.source_url} target="_blank" rel="noopener" className="hover:underline">
          Rates By Exchange Rate API
        </a>
      </p>
    </section>
  );
}
