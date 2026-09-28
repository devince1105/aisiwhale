"use client";

// The front page's calendar (D-084): a reader pages back through the stories by date. A month at a
// time; a day with stories is a link (its own address, server-rendered, to share) and carries a dot,
// a day without is muted and not a link; today is ringed, the day shown is filled. It follows the
// tab it is on (a day's 台股 stories) and keeps to Taipei's days, as the site does. Closed until
// asked for, like the watchlist beside a stock: the list is the page.
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import { API_URL, SITE_COMPANY } from "@/config";

import { fetchCalendar, type PublicDay } from "./api";
import { listHref } from "./links";
import { sectionsOf, words, type Filter, type Lang } from "./i18n";

/** Today in Taipei, "YYYY-MM-DD": the site's day. */
function taipeiToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Taipei" }).format(new Date());
}

function shift(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const at = new Date(Date.UTC(y, m - 1 + by, 1));
  return `${at.getUTCFullYear()}-${String(at.getUTCMonth() + 1).padStart(2, "0")}`;
}

/** The month's days laid out a week a row, Sunday first; blanks before the 1st. */
export function monthGrid(month: string): (string | null)[] {
  const [y, m] = month.split("-").map(Number);
  const first = new Date(Date.UTC(y, m - 1, 1)).getUTCDay();
  const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return [
    ...Array<null>(first).fill(null),
    ...Array.from({ length: days }, (_, i) => `${month}-${String(i + 1).padStart(2, "0")}`),
  ];
}

export function ArticleCalendar({
  lang,
  section,
  selected,
  initialMonth,
  initialDays,
  inline = false,
}: {
  lang: Lang;
  section: Filter | null;
  /** The day shown (``?date=``), if one is. */
  selected: string | null;
  /** "YYYY-MM": the selected day's month, else this month. */
  initialMonth: string;
  /** Its days with stories, as the server found them. */
  initialDays: PublicDay[];
  /** In the front page's sidebar (D-085): always open, no button, framed by its block. */
  inline?: boolean;
}) {
  const w = words(lang).calendar;
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(initialMonth);
  const [days, setDays] = useState<Map<string, number>>(() => new Map(initialDays.map((d) => [d.day, d.count])));
  const [today, setToday] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const panel = useId();

  useEffect(() => setToday(taipeiToday()), []);

  // another month: its days, asked of the API (the first one came with the page)
  useEffect(() => {
    if (month === initialMonth) {
      setDays(new Map(initialDays.map((d) => [d.day, d.count])));
      return;
    }
    let live = true;
    void fetchCalendar(lang, month, {
      baseUrl: API_URL,
      company: SITE_COMPANY,
      section: section ? sectionsOf(section) : undefined,
    }).then((found) => live && setDays(new Map(found.map((d) => [d.day, d.count]))));
    return () => {
      live = false;
    };
  }, [month, lang, section, initialMonth, initialDays]);

  // closed by a click elsewhere, or Escape (a dropdown's; the sidebar's stays)
  useEffect(() => {
    if (!open || inline) return;
    const away = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [open, inline]);

  const [y, m] = month.split("-").map(Number);
  const thisMonth = (today ?? initialMonth).slice(0, 7);
  const atLatest = month >= thisMonth; // no stories from the future

  return (
    <div ref={box} className="relative" data-testid={inline ? "article-calendar-inline" : "article-calendar"}>
      {inline ? null : (
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={panel}
        className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${
          open || selected ? "border-accent text-accent" : "border-line text-muted hover:border-accent hover:text-accent"
        }`}
        data-testid="calendar-toggle"
      >
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
          <rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="currentColor" strokeWidth="1.4" />
          <path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
        {selected ? w.on(selected) : w.open}
      </button>
      )}

      {open || inline ? (
        <div
          id={panel}
          role={inline ? "group" : "dialog"}
          aria-label={w.label}
          className={
            inline
              ? "w-full"
              : "mt-2 w-full rounded-lg border border-line bg-surface p-3 shadow-lg sm:absolute sm:right-0 sm:z-20 sm:w-72"
          }
        >
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setMonth(shift(month, -1))}
              aria-label={w.prev}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-line text-muted hover:border-accent hover:text-accent"
            >
              ‹
            </button>
            <p className="text-sm font-semibold tabular-nums" aria-live="polite">
              {w.month(y, m)}
            </p>
            <button
              type="button"
              onClick={() => setMonth(shift(month, 1))}
              disabled={atLatest}
              aria-label={w.next}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-line text-muted hover:border-accent hover:text-accent disabled:opacity-30 disabled:hover:border-line disabled:hover:text-muted"
            >
              ›
            </button>
          </div>

          <div className="mt-3 grid grid-cols-7 gap-1 text-center text-xs" role="grid">
            {w.weekdays.map((day) => (
              <span key={day} className="py-1 text-muted" role="columnheader">
                {day}
              </span>
            ))}
            {monthGrid(month).map((day, i) => {
              if (day === null) return <span key={`blank-${i}`} />;
              const count = days.get(day) ?? 0;
              const number = Number(day.slice(8));
              const isSelected = day === selected;
              const isToday = day === today;
              const ring = isToday && !isSelected ? "ring-1 ring-accent/60" : "";
              if (!count) {
                return (
                  <span key={day} className={`rounded-md py-1.5 text-muted/50 tabular-nums ${ring}`} role="gridcell">
                    {number}
                  </span>
                );
              }
              return (
                <Link
                  key={day}
                  href={listHref(lang, section, 1, day)}
                  onClick={() => setOpen(false)}
                  aria-current={isSelected ? "date" : undefined}
                  aria-label={w.dayLabel(day, count)}
                  className={`relative rounded-md py-1.5 font-medium tabular-nums ${ring} ${
                    isSelected ? "bg-accent text-accent-ink" : "hover:bg-canvas hover:text-accent"
                  }`}
                  role="gridcell"
                >
                  {number}
                  <span
                    aria-hidden="true"
                    className={`absolute bottom-0.5 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full ${isSelected ? "bg-accent-ink" : "bg-accent"}`}
                  />
                </Link>
              );
            })}
          </div>

          <div className="mt-3 flex items-center justify-between border-t border-line pt-2 text-xs">
            <span className="text-muted">{w.hint}</span>
            {selected ? (
              <Link href={listHref(lang, section)} onClick={() => setOpen(false)} className="text-accent hover:underline">
                {w.clear}
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
