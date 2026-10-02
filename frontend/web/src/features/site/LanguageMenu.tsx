"use client";

// The site's language, in the masthead's controls (D-163), as a newspaper puts its editions: its
// flag alone, "[flag] ⌄", opens the others, each named in full (D-164). The button says which
// language it is in words too, for a screen reader. The flags are drawn, not emoji:
// Windows shows a flag emoji as two letters. The other language keeps the reader where they are —
// the same tab, day, page or stock, and on an article the same article (D-168): its versions share
// one slug, and the company publishes in both languages. One that is not in the other language
// after all sends the reader on to that language's front page (the article page does that).
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useCallback, useId, useRef, useState } from "react";

import { useDismiss } from "./dismiss";
import { LANG_LABELS, LANGS, words, type Lang } from "./i18n";

/** Taiwan's sun: twelve rays round a ring, as a star polygon, about (cx, cy) in a 30×20 flag. */
function sunRays(cx: number, cy: number, outer: number, inner: number): string {
  return Array.from({ length: 24 }, (_, i) => {
    const r = i % 2 === 0 ? outer : inner;
    const a = (Math.PI / 12) * i - Math.PI / 2;
    return `${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`;
  }).join(" ");
}

const SUN = sunRays(7.5, 5, 3.75, 2.15);

/** The edition's flag: Taiwan for Chinese, the United States for English (the site's readers in
 * English come for its US stocks). Small enough that the US flag keeps only stripes and canton. */
export function Flag({ lang, className = "" }: { lang: Lang; className?: string }) {
  const frame = `inline-block h-3.5 w-[21px] shrink-0 overflow-hidden rounded-[2px] ring-1 ring-line ${className}`;
  if (lang === "zh-TW") {
    return (
      <svg viewBox="0 0 30 20" aria-hidden="true" className={frame} data-flag="tw">
        <rect width="30" height="20" fill="#fe0000" />
        <rect width="15" height="10" fill="#000095" />
        <polygon points={SUN} fill="#fff" />
        <circle cx="7.5" cy="5" r="2.1" fill="#000095" />
        <circle cx="7.5" cy="5" r="1.8" fill="#fff" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 30 20" aria-hidden="true" className={frame} data-flag="us">
      <rect width="30" height="20" fill="#fff" />
      {Array.from({ length: 7 }, (_, i) => (
        <rect key={i} y={(i * 20 * 2) / 13} width="30" height={20 / 13} fill="#b22234" />
      ))}
      <rect width="12" height={(20 * 7) / 13} fill="#3c3b6e" />
    </svg>
  );
}

/** The same page in ``other``: its path and query, with the language swapped. */
export function inOtherLanguage(pathname: string, search: string, lang: Lang, other: Lang): string {
  const prefix = `/news/${lang}`;
  if (!pathname.startsWith(prefix)) return `/news/${other}`;
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
        aria-label={`${w.languageLabel}${lang === "en" ? ": " : "："}${LANG_LABELS[lang]}`}
        className="inline-flex h-9 items-center gap-1 rounded-md px-2 text-sm text-muted hover:bg-canvas hover:text-ink"
      >
        <Flag lang={lang} />
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
                  <span className="flex items-center gap-2">
                    <Flag lang={other} />
                    {LANG_LABELS[other]}
                  </span>
                  <span aria-hidden="true" className="text-accent">
                    ✓
                  </span>
                </span>
              ) : (
                <Link
                  href={inOtherLanguage(pathname, search, lang, other)}
                  hrefLang={other}
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-2 px-3 py-1.5 text-muted hover:bg-canvas hover:text-ink"
                >
                  <Flag lang={other} />
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
