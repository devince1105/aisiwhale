"use client";

// 加入觀察 / 已觀察 on a stock's page (D-060): its own file, as the watchlist page shows whole
// stock pages and a stock page shows this button.
import { useState } from "react";

import { words, type Lang } from "./i18n";
import { setWatched, useWatchlist } from "./watchlistStore";

/** 加入觀察 / 已觀察 on a stock's page; signed out, a way to sign in and come back. */
export function WatchButton({ symbol, lang }: { symbol: string; lang: Lang }) {
  const w = words(lang).watch;
  const list = useWatchlist(lang);
  const [busy, setBusy] = useState(false);
  const base = "rounded-full border px-3 py-1 text-sm whitespace-nowrap";
  if (list.status === "loading" || list.status === "failed") return null;
  if (list.status === "signedOut") {
    const next = typeof window === "undefined" ? "" : `?next=${encodeURIComponent(window.location.pathname)}`;
    return (
      <a href={`/news/${lang}/login${next}`} className={`${base} border-line text-muted hover:border-accent hover:text-accent`}>
        {w.add}
      </a>
    );
  }
  const watched = list.items.some((item) => item.symbol === symbol);
  return (
    <button
      type="button"
      disabled={busy}
      aria-pressed={watched}
      data-testid="watch-button"
      onClick={async () => {
        setBusy(true);
        await setWatched(symbol, !watched).catch(() => false);
        setBusy(false);
      }}
      className={`${base} disabled:opacity-50 ${watched ? "border-accent text-accent" : "border-line text-muted hover:border-accent hover:text-accent"}`}
    >
      {watched ? w.added : w.add}
    </button>
  );
}

