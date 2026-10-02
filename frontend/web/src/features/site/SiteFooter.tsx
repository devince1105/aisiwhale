// Every public page ends with who runs the site and where its policies are (D-034). A payment
// provider reviewing the site looks here first, and so does a reader deciding whether to pay.
import Link from "next/link";

import type { Operator } from "./operator";
import { words, type Lang } from "./i18n";

export function SiteFooter({
  lang,
  operator,
  marketSources = [],
}: {
  lang: Lang;
  operator: Operator;
  /** Whose figures the market strip shows, to credit them (D-048; CoinGecko asks it). */
  marketSources?: string[];
}) {
  const w = words(lang);
  // the plans are shown before they can be bought (D-161), and so is what a refund would be: a
  // payment provider's reviewer reads both before the store opens
  const links = [
    ["pricing", w.pricing],
    ["terms", w.terms],
    ["privacy", w.privacy],
    ["refund", w.refund],
  ] as const;
  return (
    <footer data-testid="site-footer" className="mt-12 border-t border-line bg-canvas print:hidden">
      <div className="mx-auto max-w-6xl px-4 py-8 text-sm text-muted">
        <p className="mb-3 flex items-baseline gap-3">
          <span className="font-display text-base font-bold text-ink">{w.site}</span>
          <span className="text-xs">{w.tagline}</span>
        </p>
        <nav className="flex flex-wrap gap-x-4 gap-y-1">
          {links.map(([page, label]) => (
            <Link key={page} href={`/news/${lang}/${page}`} className="underline">
              {label}
            </Link>
          ))}
        </nav>
        <p className="mt-3">
          {w.operator}
          {w.sep}
          {operator.brand}
          {operator.owner ? w.aside(operator.owner) : null}
        </p>
        <p>
          {w.contact}
          {w.sep}
          <a href={`mailto:${operator.email}`} className="underline">{operator.email}</a>
          {operator.phone ? (
            <>
              {" ・ "}
              {w.phone}
              {w.sep}
              {operator.phone}
            </>
          ) : null}
        </p>
        {marketSources.length ? (
          <p className="mt-3 text-xs">{w.marketsCredit(marketSources.map((s) => w.sourceNames[s] ?? s))}</p>
        ) : null}
      </div>
      {/* one statement for the whole site, not one per section (D-097): the footer's last row,
          the whole width, as a warning strip, no line above it (D-099, D-103) */}
      <div role="note" className="bg-alert text-alert-ink" data-testid="site-disclaimer">
        <p className="mx-auto flex max-w-6xl gap-2 px-4 pt-1.5 pb-2 text-xs leading-relaxed">
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" className="mt-px shrink-0">
            <path d="M8 1.8l6.6 11.7H1.4z" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
            <path d="M8 6.2v3.4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            <circle cx="8" cy="11.6" r="0.8" fill="currentColor" />
          </svg>
          <span>
            <strong className="font-semibold">{w.disclaimerTitle}</strong>
            {w.sep}
            {w.disclaimer}
          </span>
        </p>
      </div>
    </footer>
  );
}
