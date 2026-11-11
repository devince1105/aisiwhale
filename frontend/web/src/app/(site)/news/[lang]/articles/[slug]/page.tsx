import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { cache } from "react";

import { fetchArticle } from "@/features/site/api";
import { ArticleReader } from "@/features/site/ArticleReader";
import { coverSrc } from "@/features/site/Cover";
import { isLang, LANGS, words } from "@/features/site/i18n";
import { Sidebar } from "@/features/site/Sidebar";
import { loadSidebar } from "@/features/site/sidebarData";

// Built the first time it is asked for, then kept for everybody (ISR): the page is the article as
// a reader nobody knows reads it, and no cookie is read here, so nothing a member may read is ever
// in what is kept. A member, or a reader who unlocked it, gets the rest from the browser
// (ArticleReader, D-025, D-249). Five minutes: its sidebar's figures are kept that long.
export const revalidate = 300;
export const dynamicParams = true;
export function generateStaticParams() {
  return [];
}

type Params = Promise<{ lang: string; slug: string }>;

// generateMetadata and the page ask for the same article: one request.
const load = cache((lang: string, slug: string) => fetchArticle(lang, slug));

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { lang, slug } = await params;
  if (!isLang(lang)) return {};
  const article = await load(lang, slug);
  if (!article) return {};
  return {
    title: `${article.title} · ${words(lang).site}`,
    description: article.summary ?? undefined,
    alternates: { canonical: article.path, languages: article.langs },
    // what Facebook, LINE and X show when the article is shared: its cover, 1200x630 (D-142)
    openGraph: {
      type: "article",
      title: article.title,
      description: article.summary ?? undefined,
      publishedTime: article.published_at,
      images: article.cover
        ? [{ url: coverSrc(article.cover.url), width: article.cover.width, height: article.cover.height, alt: article.cover.alt }]
        : undefined,
    },
    twitter: article.cover ? { card: "summary_large_image", images: [coverSrc(article.cover.url)] } : undefined,
  };
}

export default async function Page({ params }: { params: Params }) {
  const { lang, slug } = await params;
  if (!isLang(lang)) notFound();
  const article = await load(lang, slug);
  if (!article) {
    // switched here from the other language, but this one was not published in it (D-168): on to
    // this language's front page rather than a page that says nothing is here
    const elsewhere = await Promise.all(
      LANGS.filter((other) => other !== lang).map((other) => load(other, slug)),
    );
    if (elsewhere.some(Boolean)) redirect(`/news/${lang}`);
    notFound();
  }
  // the front page's sidebar beside the article on a wide screen (D-088); its calendar opens on
  // the article's month
  const month = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Taipei" }).format(new Date(article.published_at)).slice(0, 7);
  const sidebar = await loadSidebar(lang, { month });
  return (
    // the same box as the front page's (D-146): the article starts where the list does
    <div className="mx-auto max-w-6xl px-4 lg:grid lg:grid-cols-[minmax(0,1fr)_17rem] lg:gap-x-10">
      <div className="min-w-0">
        <ArticleReader key={`${lang}/${slug}`} article={article} lang={lang} slug={slug} />
      </div>
      <Sidebar lang={lang} {...sidebar} />
    </div>
  );
}
