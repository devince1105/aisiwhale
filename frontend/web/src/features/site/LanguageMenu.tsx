"use client";

// The site's language, at the right end of the sections bar (D-087), as a newspaper puts its
// editions: "繁體中文 ⌄" opens the others. The other language keeps the reader where they are —
// the same tab, day, page or stock — except on an article, which may not be published in it:
// that goes to the other language's front page (the article's own page links its translations).
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useCallback, useId, useRef, useState } from "react";

import { useDismiss } from "./dismiss";
import { LANG_LABELS, LANGS, words, type Lang } from "./i18n";

/** The same page in ``other``: its path and query, with the language swapped. */
export function inOtherLanguage(pathname: string, search: string, lang: Lang, other: Lang): string {
  const prefix = `/news/${lang}`;
  if (!pathname.startsWith(prefix) || pathname.startsWith(`${prefix}/articles/`)) return `/news/${other}`;
  return `/news/${other}${pathname.slice(prefix.length)}${search ? `?${search}` : ""}`;
}

export function LanguageMenu({ lang }: { lang: Lang }) {
  const w = words(lang);
  const pathname = usePathname() ?? `/news/${lang}`;
  const search = useSearchParams()?.toString() ?? "";
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const menu = useId();
  useDismiss(box, open, useCallback(() => setOpen(false), []));

  return (
    <div ref={box} className="relative shrink-0 print:hidden" data-testid="language-menu">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={menu}
        aria-label={w.languageLabel}
        className="inline-flex items-center gap-1 px-3 py-2.5 text-sm text-muted hover:text-ink"
      >
        {LANG_LABELS[lang]}
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" className={open ? "rotate-180" : ""}>
          <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open ? (
        <ul
          id={menu}
          className="absolute right-0 z-40 mt-1 min-w-36 rounded-lg border border-line bg-surface py-1 text-sm shadow-lg"
        >
          {LANGS.map((other) => (
            <li key={other}>
              {other === lang ? (
                <span aria-current="true" className="flex items-center justify-between gap-3 px-3 py-1.5 font-semibold">
                  {LANG_LABELS[other]}
                  <span aria-hidden="true" className="text-accent">
                    ✓
                  </span>
                </span>
              ) : (
                <Link
                  href={inOtherLanguage(pathname, search, lang, other)}
                  hrefLang={other}
                  onClick={() => setOpen(false)}
                  className="block px-3 py-1.5 text-muted hover:bg-canvas hover:text-ink"
                >
                  {LANG_LABELS[other]}
                </Link>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
