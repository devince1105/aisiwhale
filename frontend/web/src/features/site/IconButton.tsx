// An icon for a button (D-093), its word a label that shows on hover or keyboard focus — and is
// the button's name to a screen reader. A link when it goes somewhere, a button when it acts.
import type { ReactNode } from "react";

type Props = {
  label: string;
  children: ReactNode;
  /** Lit: on, pressed or open. */
  active?: boolean;
  href?: string;
  onClick?: () => void;
  disabled?: boolean;
  pressed?: boolean;
  expanded?: boolean;
  controls?: string;
  testId?: string;
  /** Borderless and smaller: an action on a row. */
  quiet?: boolean;
};

const BOX = "group relative inline-flex shrink-0 items-center justify-center rounded-full disabled:opacity-50";

export function IconButton({ label, children, active, href, onClick, disabled, pressed, expanded, controls, testId, quiet }: Props) {
  const tone = quiet
    ? "h-7 w-7 text-muted hover:bg-canvas hover:text-danger"
    : `h-8 w-8 border ${active ? "border-accent text-accent" : "border-line text-muted hover:border-accent hover:text-accent"}`;
  const tip = (
    <span
      aria-hidden="true"
      className="pointer-events-none absolute top-full left-1/2 z-40 mt-1.5 -translate-x-1/2 rounded bg-ink px-2 py-1 text-xs whitespace-nowrap text-surface opacity-0 transition-opacity delay-150 group-hover:opacity-100 group-focus-visible:opacity-100"
    >
      {label}
    </span>
  );
  if (href)
    return (
      <a href={href} aria-label={label} className={`${BOX} ${tone}`} data-testid={testId}>
        {children}
        {tip}
      </a>
    );
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      aria-pressed={pressed}
      aria-expanded={expanded}
      aria-controls={controls}
      className={`${BOX} ${tone}`}
      data-testid={testId}
    >
      {children}
      {tip}
    </button>
  );
}

/** The icons, 16px, drawn in the text's colour. */
export const ICONS = {
  star: (filled: boolean) => (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path
        d="M8 1.8l1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.6l-3.8 2 .7-4.3-3.1-3 4.3-.6z"
        fill={filled ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
    </svg>
  ),
  pencil: (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path d="M10.8 2.7l2.5 2.5-7.8 7.8-3 .5.5-3z M9.3 4.2l2.5 2.5" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  ),
  trash: (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path
        d="M2.5 4.5h11 M6.2 4.5V3a.8.8 0 01.8-.8h2a.8.8 0 01.8.8v1.5 M3.8 4.5l.7 8.6a1 1 0 001 .9h5a1 1 0 001-.9l.7-8.6 M6.6 7v4.5 M9.4 7v4.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  check: (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path d="M3 8.5l3.2 3.2L13 5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  /** A page with a column on its right: the list beside the one picked. */
  sideList: (open: boolean) => (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <rect x="1.8" y="2.8" width="12.4" height="10.4" rx="1.6" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <path d="M10 2.8v10.4" stroke="currentColor" strokeWidth="1.3" />
      {open ? <rect x="10" y="2.8" width="4.2" height="10.4" rx="1" fill="currentColor" opacity="0.35" /> : null}
    </svg>
  ),
};
