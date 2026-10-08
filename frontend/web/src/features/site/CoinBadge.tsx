// A COIN article's badge on a list (P4, D-249): what it costs — or, for a reader who already
// unlocked it, 已解鎖. The price comes with the list (cached for everybody); whether this reader
// unlocked it is asked from the browser, once per page.
"use client";

import { useEffect, useState } from "react";

import { words, type Lang } from "./i18n";
import { unlockedIds } from "./unlocks";

export function CoinBadge({ articleId, price, lang }: { articleId: string; price: number; lang: Lang }) {
  const w = words(lang).unlock;
  const [mine, setMine] = useState(false);
  useEffect(() => {
    let live = true;
    void unlockedIds().then((ids) => {
      if (live) setMine(ids.has(articleId));
    });
    return () => {
      live = false;
    };
  }, [articleId]);
  return (
    <span data-testid="coin-badge" className="rounded-full border border-line px-1.5 py-px text-[0.7rem]">
      {mine ? w.unlocked : w.badge(price)}
    </span>
  );
}
