import { notFound } from "next/navigation";

import { fetchArticlePage } from "@/features/site/api";
import { ArticleList, PAGE_SIZE } from "@/features/site/ArticleList";
import { filterName, isFilter, isLang, sectionsOf, words } from "@/features/site/i18n";

export const revalidate = 30;

type Params = Promise<{ lang: string }>;
type Search = Promise<{ [key: string]: string | string[] | undefined }>;

async function where(searchParams: Search) {
  const query = await searchParams;
  const section = isFilter(query.section) ? query.section : null;
  const page = Math.min(Math.max(Number.parseInt(String(query.page ?? "1"), 10) || 1, 1), 500);
  return { section, page };
}

export async function generateMetadata({ params, searchParams }: { params: Params; searchParams: Search }) {
  const { lang } = await params;
  if (!isLang(lang)) return {};
  const { section } = await where(searchParams);
  const w = words(lang);
  return { title: section ? `${filterName(lang, section)} · ${w.site}` : w.site };
}

export default async function Page({ params, searchParams }: { params: Params; searchParams: Search }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const { section, page } = await where(searchParams);
  const { articles, total } = await fetchArticlePage(lang, {
    company: process.env.SITE_COMPANY || undefined,
    section: section ? sectionsOf(section) : undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });
  return (
    <ArticleList
      articles={articles}
      lang={lang}
      section={section}
      page={page}
      pages={Math.ceil(total / PAGE_SIZE)}
    />
  );
}
