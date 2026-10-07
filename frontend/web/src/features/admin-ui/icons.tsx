// The back office's icons: 20-px line drawings in the text colour, so they follow the theme.
const PATHS = {
  dashboard: "M3 3h6v8H3zM11 3h6v5h-6zM11 10h6v7h-6zM3 13h6v4H3z",
  office: "M3 17V7l7-4 7 4v10M7 17v-5h6v5",
  inbox: "M3 11l2-7h10l2 7v6H3zM3 11h4l1 2h4l1-2h4",
  cycle: "M16 10a6 6 0 1 1-2-4.5M16 3v3h-3",
  timeline: "M5 4v12M5 6h10M5 10h7M5 14h9",
  story: "M4 4h12v12H4zM7 8h6M7 11h4",
  article: "M5 3h7l3 3v11H5zM12 3v3h3M8 10h4M8 13h4",
  source: "M4 16a12 12 0 0 1 12-12M4 11a7 7 0 0 1 7-7M5 15h.01",
  agents: "M7 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM2 17c0-3 2-5 5-5s5 2 5 5M13 9a3 3 0 1 0 0-6M15 12c2 .5 3 2.5 3 5",
  member: "M10 3l2.2 4.5 4.8.7-3.5 3.4.8 4.9L10 14.2l-4.3 2.3.8-4.9L3 8.2l4.8-.7z",
  coin: "M10 3a7 7 0 1 0 0 14a7 7 0 1 0 0-14zM12 7.5H9a1.5 1.5 0 0 0 0 3h2a1.5 1.5 0 0 1 0 3H8M10 6v1.5M10 13.5V15",
  audit: "M6 3h8l2 2v12H4V5zM7 8h6M7 11h6M7 14h3",
  menu: "M3 5h14M3 10h14M3 15h14",
  collapse: "M12 5l-5 5 5 5",
  expand: "M8 5l5 5-5 5",
  close: "M5 5l10 10M15 5L5 15",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, className = "size-5" }: { name: IconName; className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={`shrink-0 ${className}`}>
      <path d={PATHS[name]} />
    </svg>
  );
}
