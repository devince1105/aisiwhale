"use client";

// The watchlist in drawers (D-094): 台股, 美股, 指數・利率, 黃金・期貨, 外匯, 加密貨幣 — folded or
// not with a click, and remembered in this browser. The reader's own order within each drawer; a
// drawer with nothing in it is not shown. How many are in each only where the list is set (D-095).
import { useEffect, useState, type ReactNode } from "react";

import { words, type Lang } from "./i18n";
import { GROUPS, groupOf, type Group } from "./quote";
import type { WatchedStock } from "./watchlistStore";

const FOLDED = "autora:watchlist-folded";

function useFolded(): [Set<Group>, (group: Group) => void] {
  const [folded, setFolded] = useState<Set<Group>>(new Set());
  useEffect(() => {
    try {
      const kept = JSON.parse(localStorage.getItem(FOLDED) ?? "[]") as Group[];
      if (kept.length) setFolded(new Set(kept));
    } catch {
      // nothing kept, or storage closed: all open
    }
  }, []);
  const toggle = (group: Group) =>
    setFolded((now) => {
      const next = new Set(now);
      if (!next.delete(group)) next.add(group);
      try {
        localStorage.setItem(FOLDED, JSON.stringify([...next]));
      } catch {
        // not remembered: it still folds now
      }
      return next;
    });
  return [folded, toggle];
}

export function GroupedList({
  items,
  lang,
  row,
  body,
  counted = false,
  testId = "watchlist-groups",
}: {
  items: WatchedStock[];
  lang: Lang;
  /** Each item, in a list of its drawer's; or the drawer's whole ``body``. */
  row?: (item: WatchedStock) => ReactNode;
  body?: (inside: WatchedStock[]) => ReactNode;
  /** 台股 6: on the settings, not the list to watch. */
  counted?: boolean;
  testId?: string;
}) {
  const names = words(lang).watch.groups;
  const [folded, toggle] = useFolded();
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-1" data-testid={testId}>
      {GROUPS.map((group) => {
        const inside = items.filter((item) => groupOf(item.key) === group);
        if (!inside.length) return null;
        const open = !folded.has(group);
        return (
          <section key={group} className="min-w-0" data-group={group}>
            <button
              type="button"
              onClick={() => toggle(group)}
              aria-expanded={open}
              className="flex w-full items-center gap-1.5 px-2 py-1.5 text-xs tracking-wide text-muted hover:text-ink"
            >
              <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" className={open ? "rotate-90" : ""}>
                <path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {names[group]}
              {counted ? <span className="tabular-nums">{inside.length}</span> : null}
            </button>
            {!open ? null : body ? (
              body(inside)
            ) : (
              <ul className="grid grid-cols-[minmax(0,1fr)] gap-0.5">
                {inside.map((item) => (
                  <li key={item.key} className="min-w-0">
                    {row?.(item)}
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
