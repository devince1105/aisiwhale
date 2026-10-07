import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { CoinsPage } from "@/features/site/CoinsPage";
import { isLang, words } from "@/features/site/i18n";

type Params = Promise<{ lang: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { lang } = await params;
  if (!isLang(lang)) return {};
  return { title: `${words(lang).coins.title} · ${words(lang).site}`, robots: { index: false } };
}

/** A reader's Whale Coins (P3-C): filled in the browser, from their cookie. */
export default async function Page({ params }: { params: Params }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  return (
    <section className="px-4 py-8">
      <CoinsPage lang={lang} />
    </section>
  );
}
