"use client";

// 新聞情緒 on a stock's page (D-091): how the week's headlines about it read — a ring of positive,
// neutral and negative, how many there are against the usual (熱度), and the latest headlines,
// each with its tone and the model's reason, to be checked. A count of coverage, never a
// forecast: no arrows, no advice (the footer says so, for every page: D-097). Colours as the site's prices (D-048): red is
// good news, green is bad. Asked for after the page, like the chart's 15 minutes.
import { useEffect, useState } from "react";

import { API_URL } from "@/config";

import { fetchSentiment, type PublicSentiment } from "./api";
import { formatDate, words, type Lang } from "./i18n";

const TONE_TEXT = { positive: "text-rise", neutral: "text-muted", negative: "text-fall" } as const;
const TONE_DOT = { positive: "bg-rise", neutral: "bg-neutral", negative: "bg-fall" } as const;

/** The ring's arcs, as SVG dash lengths on a circle of circumference 100. */
export function arcs(s: Pick<PublicSentiment, "positive" | "neutral" | "negative">): [string, number, number][] {
  const total = s.positive + s.neutral + s.negative;
  if (!total) return [];
  let at = 0;
  return (["positive", "neutral", "negative"] as const).flatMap((tone) => {
    const share = (s[tone] / total) * 100;
    const arc: [string, number, number] = [tone, share, at];
    at += share;
    return share ? [arc] : [];
  });
}

export function NewsSentiment({ symbol, lang }: { symbol: string; lang: Lang }) {
  const w = words(lang).sentiment;
  const [sentiment, setSentiment] = useState<PublicSentiment | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    void fetchSentiment(symbol, lang, { baseUrl: API_URL }).then((found) => live && setSentiment(found));
    return () => {
      live = false;
    };
  }, [symbol, lang]);
  // off the strip, or nothing read yet: no section
  if (!sentiment || !sentiment.total) return null;
  const share = (n: number) => Math.round((n / sentiment.total) * 100);
  return (
    <section className="mt-10" aria-labelledby="sentiment-title" data-testid="news-sentiment">
      <h2 id="sentiment-title" className="text-xl font-bold">
        {w.title}
      </h2>
      <div className="mt-4 flex flex-wrap items-center gap-6">
        <div className="relative h-28 w-28 shrink-0">
          <svg viewBox="0 0 42 42" className="h-full w-full -rotate-90" aria-hidden="true">
            <circle cx="21" cy="21" r="15.915" fill="none" strokeWidth="5" className="stroke-line" />
            {arcs(sentiment).map(([tone, length, offset]) => (
              <circle
                key={tone}
                cx="21"
                cy="21"
                r="15.915"
                fill="none"
                strokeWidth="5"
                strokeDasharray={`${length} ${100 - length}`}
                strokeDashoffset={-offset}
                style={{ stroke: `var(--color-${tone === "positive" ? "rise" : tone === "negative" ? "fall" : "neutral"})` }}
              />
            ))}
          </svg>
          <span className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-xl font-bold tabular-nums">{share(sentiment.positive)}%</span>
            <span className="text-xs text-muted">{w.positive}</span>
          </span>
        </div>
        <dl className="grid min-w-40 gap-1 text-sm">
          {(["positive", "neutral", "negative"] as const).map((tone) => (
            <div key={tone} className="flex items-center justify-between gap-6">
              <dt className="flex items-center gap-2">
                <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${TONE_DOT[tone]}`} />
                {w[tone]}
              </dt>
              <dd className="tabular-nums">
                {sentiment[tone]}
                <span className="ml-2 text-xs text-muted">{share(sentiment[tone])}%</span>
              </dd>
            </div>
          ))}
          <div className="mt-1 flex items-center justify-between gap-6 border-t border-line pt-1 text-muted">
            <dt>{w.heat}</dt>
            <dd className="tabular-nums">{w.heatValue(sentiment.total, sentiment.heat ?? null)}</dd>
          </div>
        </dl>
      </div>
      {sentiment.headlines.length ? (
        <ul className="mt-4 divide-y divide-line">
          {sentiment.headlines.map((h) => (
            <li key={h.url} className="py-2.5 text-sm">
              <a href={h.url} target="_blank" rel="noopener nofollow" className="font-medium hover:text-accent">
                <span className={`mr-2 text-xs ${TONE_TEXT[h.sentiment]}`}>{w[h.sentiment]}</span>
                {h.title}
              </a>
              <p className="mt-0.5 text-xs text-muted">
                {h.source}・<time dateTime={h.published_at} className="text-date">{formatDate(lang, h.published_at)}</time>
                {h.reason ? `・${h.reason}` : ""}
              </p>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
