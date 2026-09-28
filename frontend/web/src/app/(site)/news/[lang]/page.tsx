import { notFound } from "next/navigation";

import { fetchArticlePage, fetchCalendar, fetchMarkets, fetchPopular } from "@/features/site/api";
import { ArticleList, PAGE_SIZE } from "@/features/site/ArticleList";
import { filterName, isFilter, isLang, sectionsOf, words } from "@/features/site/i18n";

export const revalidate = 30;

type Params = Promise<{ lang: string }>;
type Search = Promise<{ [key: string]: string | string[] | undefined }>;

async function where(searchParams: Search) {
  const query = await searchParams;
  const section = isFilter(query.section) ? query.section : null;
  const page = Math.min(Math.max(Number.parseInt(String(query.page ?? "1"), 10) || 1, 1), 500);
  // a day to show (D-084): "YYYY-MM-DD", a real one, not after today
  const asked = typeof query.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(query.date) ? query.date : null;
  const day = asked && !Number.isNaN(Date.parse(`${asked}T00:00:00Z`)) && asked <= taipeiToday() ? asked : null;
  return { section, page, day };
}

/** Today in Taipei, "YYYY-MM-DD": the site's day. */
function taipeiToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Taipei" }).format(new Date());
}

export async function generateMetadata({ params, searchParams }: { params: Params; searchParams: Search }) {
  const { lang } = await params;
  if (!isLang(lang)) return {};
  const { section, day } = await where(searchParams);
  const w = words(lang);
  const name = [section ? filterName(lang, section) : null, day ? w.calendar.on(day) : null].filter(Boolean);
  return { title: name.length ? `${name.join(" ")} · ${w.site}` : w.site };
}

export default async function Page({ params, searchParams }: { params: Params; searchParams: Search }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const { section, page, day } = await where(searchParams);
  const company = process.env.SITE_COMPANY || undefined;
  const sections = section ? sectionsOf(section) : undefined;
  // the calendar opens on the day's month, else this one, its days already marked (D-084)
  const month = (day ?? taipeiToday()).slice(0, 7);
  const [{ articles, total }, days, popular, markets] = await Promise.all([
    fetchArticlePage(lang, { company, section: sections, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE, day: day ?? undefined }),
    fetchCalendar(lang, month, { company, section: sections }),
    // 熱門文章 for the sidebar: the whole site's, whatever the tab (D-086)
    fetchPopular(lang, { company }),
    // 市場概況: the strip's own figures (the layout asks for the same, cached) (D-087)
    fetchMarkets(),
  ]);
  return (
    <ArticleList
      articles={articles}
      lang={lang}
      section={section}
      page={page}
      pages={Math.ceil(total / PAGE_SIZE)}
      day={day}
      calendar={{ month, days }}
      popular={popular}
      markets={markets}
    />
  );
}
