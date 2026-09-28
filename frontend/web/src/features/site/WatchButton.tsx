"use client";

// 加入觀察 / 已觀察 on a stock's page (D-060): its own file, as the watchlist page shows whole
// stock pages and a stock page shows this button.
import { useState } from "react";

import { ICONS, IconButton } from "./IconButton";
import { words, type Lang } from "./i18n";
import { setWatched, useWatchlist } from "./watchlistStore";

/** 加入觀察 / 已觀察 on a stock's page; signed out, a way to sign in and come back. ``icon``: a
 * star, its words on hover (D-093, the watchlist page's title row). */
export function WatchButton({ symbol, lang, icon = false }: { symbol: string; lang: Lang; icon?: boolean }) {
  const w = words(lang).watch;
  const list = useWatchlist(lang);
  const [busy, setBusy] = useState(false);
  const base = "rounded-full border px-3 py-1 text-sm whitespace-nowrap";
  if (list.status === "loading" || list.status === "failed") return null;
  if (list.status === "signedOut") {
    const next = typeof window === "undefined" ? "" : `?next=${encodeURIComponent(window.location.pathname)}`;
    if (icon)
      return (
        <IconButton label={bare(w.add)} href={`/news/${lang}/login${next}`}>
          {ICONS.star(false)}
        </IconButton>
      );
    return (
      <a href={`/news/${lang}/login${next}`} className={`${base} border-line text-muted hover:border-accent hover:text-accent`}>
        {w.add}
      </a>
    );
  }
  const watched = list.items.some((item) => item.symbol === symbol);
  const toggle = async () => {
    setBusy(true);
    await setWatched(symbol, !watched).catch(() => false);
    setBusy(false);
  };
  if (icon)
    return (
      <IconButton label={bare(watched ? w.added : w.add)} active={watched} pressed={watched} disabled={busy} onClick={toggle} testId="watch-button">
        {ICONS.star(watched)}
      </IconButton>
    );
  return (
    <button
      type="button"
      disabled={busy}
      aria-pressed={watched}
      data-testid="watch-button"
      onClick={toggle}
      className={`${base} disabled:opacity-50 ${watched ? "border-accent text-accent" : "border-line text-muted hover:border-accent hover:text-accent"}`}
    >
      {watched ? w.added : w.add}
    </button>
  );
}


/** The words without their star: the icon is the star. */
function bare(text: string): string {
  return text.replace(/^[☆★]\s*/, "");
}
