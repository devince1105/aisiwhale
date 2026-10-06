import { notFound } from "next/navigation";

import { fetchArticlePage, fetchPortfolios } from "@/features/site/api";
import { PortfolioCards } from "@/features/site/Portfolios";
import { loadSidebar, taipeiToday } from "@/features/site/sidebarData";
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
  // the calendar opens on the day's month, else this one, its days already marked (D-084)
  // 持股觀察's first page opens with the followed filers' cards (HD-06); none to show leaves the
  // stories as they were, and a card that cannot be loaded does not take the page down with it
  const portfolios = section === "watch" && page === 1 && !day;
  const [{ articles, total }, sidebar, cards] = await Promise.all([
    fetchArticlePage(lang, {
      company,
      section: section ? sectionsOf(section) : undefined,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
      day: day ?? undefined,
    }),
    loadSidebar(lang, { section, month: (day ?? taipeiToday()).slice(0, 7) }),
    portfolios ? fetchPortfolios(lang, { company }).catch(() => []) : Promise.resolve([]),
  ]);
  return (
    <ArticleList
      articles={articles}
      lang={lang}
      section={section}
      page={page}
      pages={Math.ceil(total / PAGE_SIZE)}
      day={day}
      calendar={sidebar.calendar}
      popular={sidebar.popular}
      markets={sidebar.markets}
      events={sidebar.events}
      sentiment={sidebar.sentiment}
      top={cards.length ? <PortfolioCards cards={cards} lang={lang} /> : null}
    />
  );
}
