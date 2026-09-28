"use client";

// 分析師評等與技術指標 on a stock's page (D-096). Two cards, facts only (D-035): the analysts'
// ratings as Finnhub counts them — a half ring in five parts, sized by how many, and no needle,
// for a needle would be the site's verdict — and the technical figures from the daily closes,
// with no "買入". Colours as the site's prices: buy ratings red, sell ratings green (D-048).
import { useEffect, useState } from "react";

import { API_URL } from "@/config";

import { fetchRatings, type PublicRatings } from "./api";
import { words, type Lang } from "./i18n";
import type { Technicals } from "./technicals";

const KINDS = ["strong_sell", "sell", "hold", "buy", "strong_buy"] as const;
type Kind = (typeof KINDS)[number];
const COLOUR: Record<Kind, [string, number]> = {
  strong_sell: ["fall", 1],
  sell: ["fall", 0.55],
  hold: ["neutral", 1],
  buy: ["rise", 0.55],
  strong_buy: ["rise", 1],
};

type Counts = PublicRatings["latest"];

/** The half ring's parts, left (strong sell) to right (strong buy): [kind, from, to] in degrees
 * along it, 0 at the left end, 180 at the right; a kind with none has no part. */
export function halfRing(counts: Counts, gap = 2): [Kind, number, number][] {
  const total = KINDS.reduce((sum, kind) => sum + counts[kind], 0);
  if (!total) return [];
  const shown = KINDS.filter((kind) => counts[kind] > 0);
  const room = 180 - gap * (shown.length - 1);
  let at = 0;
  return shown.map((kind) => {
    const span = (counts[kind] / total) * room;
    const part: [Kind, number, number] = [kind, at, at + span];
    at += span + gap;
    return part;
  });
}

function arc(from: number, to: number, r = 48, cx = 60, cy = 60): string {
  const point = (deg: number) => {
    const rad = Math.PI - (deg * Math.PI) / 180;
    return `${(cx + r * Math.cos(rad)).toFixed(2)} ${(cy - r * Math.sin(rad)).toFixed(2)}`;
  };
  return `M ${point(from)} A ${r} ${r} 0 0 1 ${point(to)}`;
}

const number = (value: number, lang: Lang) =>
  value.toLocaleString(lang, { maximumFractionDigits: value >= 1000 ? 1 : 2, minimumFractionDigits: value >= 1000 ? 0 : 2 });
const percent = (value: number) => `${(Math.abs(value) * 100).toFixed(1)}%`;

export function StockSignals({ symbol, lang, figures }: { symbol: string; lang: Lang; figures: Technicals | null }) {
  const w = words(lang).signals;
  const [ratings, setRatings] = useState<PublicRatings | null>(null);
  useEffect(() => {
    let live = true;
    void fetchRatings(symbol, { baseUrl: API_URL }).then((found) => live && setRatings(found));
    return () => {
      live = false;
    };
  }, [symbol]);
  if (!ratings && !figures) return null;
  return (
    <section className="mt-10" aria-labelledby="signals-title" data-testid="stock-signals">
      <h2 id="signals-title" className="text-xl font-bold">
        {w.title}
      </h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {ratings ? <Analysts ratings={ratings} lang={lang} /> : null}
        {figures ? <Figures figures={figures} lang={lang} /> : null}
      </div>
    </section>
  );
}

function Analysts({ ratings, lang }: { ratings: PublicRatings; lang: Lang }) {
  const w = words(lang).signals;
  const { latest, previous } = ratings;
  return (
    <div className="rounded-lg border border-line p-4" data-testid="analyst-ratings">
      <h3 className="flex items-baseline justify-between gap-2 font-semibold">
        {w.analysts}
        <span className="text-xs font-normal text-date">{w.month(latest.period)}</span>
      </h3>
      <div className="relative mx-auto mt-3 w-48">
        <svg viewBox="0 0 120 66" className="w-full" aria-hidden="true">
          {halfRing(latest).map(([kind, from, to]) => (
            <path
              key={kind}
              d={arc(from, to)}
              fill="none"
              strokeWidth="9"
              strokeLinecap="butt"
              style={{ stroke: `var(--color-${COLOUR[kind][0]})`, opacity: COLOUR[kind][1] }}
            />
          ))}
        </svg>
        <span className="absolute inset-x-0 bottom-0 flex flex-col items-center">
          <span className="text-2xl leading-none font-bold tabular-nums">{latest.total}</span>
          <span className="mt-0.5 text-xs text-muted">{w.analystsCount}</span>
        </span>
      </div>
      <dl className="mt-3 grid gap-1 text-sm">
        {[...KINDS].reverse().map((kind) => {
          const change = previous ? latest[kind] - previous[kind] : 0;
          return (
            <div key={kind} className="flex items-center justify-between gap-3">
              <dt className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ background: `var(--color-${COLOUR[kind][0]})`, opacity: COLOUR[kind][1] }}
                />
                {w.ratings[kind]}
              </dt>
              <dd className="tabular-nums">
                {latest[kind]}
                {change ? (
                  <span className="ml-2 text-xs text-muted" title={w.vsLast}>
                    {change > 0 ? `+${change}` : `−${-change}`}
                  </span>
                ) : null}
              </dd>
            </div>
          );
        })}
      </dl>
      {/* whose figures, and through which listing; what they are not is in the footer (D-097) */}
      <p className="mt-3 text-xs leading-relaxed text-muted">
        {ratings.via ? `${w.via(ratings.via)}${lang.startsWith("zh") ? "・" : ". "}` : ""}
        {lang.startsWith("zh") ? "資料來源：" : "Source: "}
        {ratings.source}
      </p>
    </div>
  );
}

function Figures({ figures, lang }: { figures: Technicals; lang: Lang }) {
  const w = words(lang).signals;
  return (
    <div className="rounded-lg border border-line p-4" data-testid="technicals">
      <h3 className="font-semibold">{w.technicals}</h3>
      <dl className="mt-3 grid gap-3 text-sm">
        {figures.averages.map(({ days, value, gap }) => (
          <div key={days} className="flex items-baseline justify-between gap-3">
            <dt className="text-muted">{w.ma(days)}</dt>
            <dd className="text-right tabular-nums">
              {number(value, lang)}
              <span className={`ml-2 text-xs ${gap >= 0 ? "text-rise" : "text-fall"}`}>
                {gap >= 0 ? w.above(percent(gap)) : w.below(percent(gap))}
              </span>
            </dd>
          </div>
        ))}
        {figures.rsi !== null ? (
          <div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-muted">{w.rsi}</dt>
              <dd className="tabular-nums">{figures.rsi.toFixed(1)}</dd>
            </div>
            <Scale at={figures.rsi / 100} marks={[0.3, 0.7]} />
            <p className="mt-1 text-xs text-muted">{w.rsiLines}</p>
          </div>
        ) : null}
        {figures.range ? (
          <div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-muted">{w.range}</dt>
              <dd className="tabular-nums">
                {number(figures.range.low, lang)} – {number(figures.range.high, lang)}
              </dd>
            </div>
            <Scale at={figures.range.at} />
            <p className="mt-1 text-xs text-muted">{w.rangeAt(Math.round(figures.range.at * 100))}</p>
          </div>
        ) : null}
      </dl>
    </div>
  );
}

/** A line from 0 to 1 with a dot where the figure is, and thin marks at ``marks``. */
function Scale({ at, marks = [] }: { at: number; marks?: number[] }) {
  const place = (x: number) => `${Math.min(Math.max(x, 0), 1) * 100}%`;
  return (
    <div className="relative mt-2 h-1.5 rounded-full bg-line" aria-hidden="true">
      {marks.map((m) => (
        <span key={m} className="absolute inset-y-0 w-px bg-muted/50" style={{ left: place(m) }} />
      ))}
      <span className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink" style={{ left: place(at) }} />
    </div>
  );
}
