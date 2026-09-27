// The front page's page numbers (D-065), after the blog's: ‹ 1 … 4 5 [6] 7 8 … 20 ›, the page
// shown filled in, and « » to the first and last. Every number is a link — each page has its own
// address, rendered on the server, to share or to be read by a search engine. A phone shows one
// neighbour each side instead of two, and no « », so the row fits; "第 6／20 頁" beneath says where
// the reader is. An end with nowhere to go shows its arrow, dimmed, and not as a link.
import Link from "next/link";

import { words, type Lang } from "./i18n";

const WIDE = 2;
const NARROW = 1;

type Slot = { page: number; wide: boolean; narrow: boolean; gap: { wide: boolean; narrow: boolean } };

/** The numbers to show around ``page``, and where a "…" goes, on a wide screen and a narrow one. */
export function slots(page: number, total: number): Slot[] {
  const shown = (n: number, delta: number) => n === 1 || n === total || Math.abs(n - page) <= delta;
  const out: Slot[] = [];
  let lastWide = 0;
  let lastNarrow = 0;
  for (let n = 1; n <= total; n++) {
    const wide = shown(n, WIDE);
    const narrow = shown(n, NARROW);
    if (!wide && !narrow) continue;
    out.push({
      page: n,
      wide,
      narrow,
      gap: { wide: wide && lastWide > 0 && n - lastWide > 1, narrow: narrow && lastNarrow > 0 && n - lastNarrow > 1 },
    });
    if (wide) lastWide = n;
    if (narrow) lastNarrow = n;
  }
  return out;
}

function shownOn(wide: boolean, narrow: boolean): string {
  if (wide && narrow) return "inline-flex";
  return wide ? "hidden sm:inline-flex" : "inline-flex sm:hidden";
}

const BOX = "h-8 min-w-8 items-center justify-center rounded-md border px-2 text-sm tabular-nums";
const IDLE = "border-line text-muted hover:border-accent hover:text-accent";

function Arrow({ href, label, rel, className = "inline-flex", children }: {
  href: string | null;
  label: string;
  rel?: string;
  className?: string;
  children: React.ReactNode;
}) {
  if (href === null) {
    return (
      <span aria-disabled="true" aria-label={label} className={`${className} ${BOX} border-line text-muted opacity-30`}>
        {children}
      </span>
    );
  }
  return (
    <Link href={href} rel={rel} aria-label={label} className={`${className} ${BOX} ${IDLE}`}>
      {children}
    </Link>
  );
}

function Chevron({ double = false, back = false }: { double?: boolean; back?: boolean }) {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" className={back ? "rotate-180" : ""}>
      <path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      {double ? (
        <path d="M2 3.5 6.5 8 2 12.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      ) : null}
    </svg>
  );
}

export function Pagination({
  lang,
  page,
  total,
  to,
}: {
  lang: Lang;
  page: number;
  /** How many pages there are in all. */
  total: number;
  /** A page's address. */
  to: (page: number) => string;
}) {
  if (total <= 1) return null;
  const w = words(lang).pagination;
  const first = page > 1;
  const last = page < total;
  return (
    <nav aria-label={w.label} className="mt-8 border-t border-line pt-6 print:hidden" data-testid="pagination">
      <div className="flex items-center justify-center gap-1">
        <Arrow href={first ? to(1) : null} label={w.first} className="hidden sm:inline-flex">
          <Chevron double back />
        </Arrow>
        <Arrow href={first ? to(page - 1) : null} label={w.previous} rel="prev">
          <Chevron back />
        </Arrow>
        {slots(page, total).map((slot) => (
          <span key={slot.page} className="contents">
            {slot.gap.wide || slot.gap.narrow ? (
              <span aria-hidden="true" className={`${shownOn(slot.gap.wide, slot.gap.narrow)} h-8 min-w-6 items-end justify-center pb-1 text-sm text-muted`}>
                …
              </span>
            ) : null}
            {slot.page === page ? (
              <span aria-current="page" className={`${shownOn(slot.wide, slot.narrow)} ${BOX} border-accent bg-accent font-semibold text-accent-ink`}>
                {slot.page}
              </span>
            ) : (
              <Link href={to(slot.page)} aria-label={w.page(slot.page)} className={`${shownOn(slot.wide, slot.narrow)} ${BOX} ${IDLE}`}>
                {slot.page}
              </Link>
            )}
          </span>
        ))}
        <Arrow href={last ? to(page + 1) : null} label={w.next} rel="next">
          <Chevron />
        </Arrow>
        <Arrow href={last ? to(total) : null} label={w.last} className="hidden sm:inline-flex">
          <Chevron double />
        </Arrow>
      </div>
      <p className="mt-3 text-center text-xs text-muted tabular-nums">{w.counter(page, total)}</p>
    </nav>
  );
}
