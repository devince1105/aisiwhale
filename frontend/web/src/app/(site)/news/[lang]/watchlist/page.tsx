import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { isLang, words } from "@/features/site/i18n";
import { WatchlistPage } from "@/features/site/Watchlist";

type Params = Promise<{ lang: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { lang } = await params;
  if (!isLang(lang)) return {};
  return { title: `${words(lang).watch.title} · ${words(lang).site}`, robots: { index: false } };
}

/** A reader's own watchlist (D-060, D-064): to watch, and behind 編輯清單, to set. Filled in the
 * browser, from their cookie. */
export default async function Page({ params }: { params: Params }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  return (
    <section className="mx-auto max-w-6xl px-4 py-8">
      {/* the picked item and the settings are in the address (?s=, ?edit=1), read in the browser */}
      <Suspense fallback={<p className="text-muted">…</p>}>
        <WatchlistPage lang={lang} />
      </Suspense>
    </section>
  );
}
