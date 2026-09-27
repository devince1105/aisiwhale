import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { isLang, words } from "@/features/site/i18n";
import { WatchlistPage } from "@/features/site/Watchlist";

type Params = Promise<{ lang: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { lang } = await params;
  if (!isLang(lang)) return {};
  return { title: `${words(lang).watch.title} · ${words(lang).site}`, robots: { index: false } };
}

/** A reader's own watchlist (D-060): filled in the browser, from their cookie. */
export default async function Page({ params }: { params: Params }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  return (
    <section className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">{words(lang).watch.title}</h1>
      <WatchlistPage lang={lang} />
    </section>
  );
}
