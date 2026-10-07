// Every public page ends with where the site's policies are and how to reach it (D-034, D-165).
// Who runs it — the operator's name, address and phone — is in the terms of service, where the
// law asks for it and a payment provider's reviewer reads it; the footer has 聯絡我們 instead.
// Beside them, as blogs have it, a "Buy me a coffee" button (D-250): a plain link in the service's
// yellow to the operator's page, a new tab, none of its scripts.
import Link from "next/link";

import { words, type Lang } from "./i18n";

export const COFFEE_URL = "https://buymeacoffee.com/vince115";

export function SiteFooter({
  lang,
  marketSources = [],
}: {
  lang: Lang;
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
    ["contact", w.contactLink],
  ] as const;
  return (
    <footer data-testid="site-footer" className="mt-12 border-t border-line bg-canvas print:hidden">
      <div className="mx-auto max-w-6xl px-4 py-8 text-sm text-muted sm:flex sm:items-start sm:justify-between sm:gap-8">
        <div className="min-w-0">
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
          {marketSources.length ? (
            <p className="mt-3 text-xs">{w.marketsCredit(marketSources.map((s) => w.sourceNames[s] ?? s))}</p>
          ) : null}
        </div>
        <div data-testid="site-coffee" className="mt-6 sm:mt-0 sm:max-w-72 sm:shrink-0 sm:text-right">
          <p className="text-xs leading-relaxed">
            {w.coffee.lead.map((line) => (
              <span key={line} className="block">
                {line}
              </span>
            ))}
          </p>
          <a
            href={COFFEE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 inline-flex items-center gap-2 rounded-full bg-[#ffdd00] px-4 py-2 text-sm font-semibold text-[#0d0c22] shadow-sm transition-colors hover:bg-[#ffe54d] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" className="shrink-0">
              <path d="M4 9.5h12V14a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5z" fill="currentColor" />
              <path d="M16 11h1.3a2.6 2.6 0 0 1 0 5.2H15.6" fill="none" stroke="currentColor" strokeWidth="1.8" />
              <path
                d="M8 3.5c-.9.9.9 1.7 0 2.6M12 3.5c-.9.9.9 1.7 0 2.6"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
            {w.coffee.button}
            <span className="sr-only">{w.coffee.newTab}</span>
          </a>
        </div>
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
