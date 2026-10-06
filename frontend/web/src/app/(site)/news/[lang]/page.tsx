import { notFound } from "next/navigation";

import { fetchArticlePage, fetchPortfolios } from "@/features/site/api";
import { isView, KINDS, PortfolioCards, WatchTabs, type View } from "@/features/site/Portfolios";
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
  // 持股觀察's tab (HD-06): asked for, or the stories on a later page or a day, else the big names
  const view: View | null =
    section === "watch" ? (isView(query.view) ? query.view : page > 1 || day ? "news" : "people") : null;
  return { section, page, day, view };
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
  const { section, page, day, view } = await where(searchParams);
  const company = process.env.SITE_COMPANY || undefined;
  const w = words(lang);
  // the calendar opens on the day's month, else this one, its days already marked (D-084)
  // 持股觀察 opens on its cards (HD-06); a card that cannot be loaded does not take the page down
  const portfolios = view === "people" || view === "groups";
  const [{ articles, total }, sidebar, cards] = await Promise.all([
    // a tab of cards shows no stories: none asked for
    portfolios
      ? Promise.resolve({ articles: [], total: 0 })
      : fetchArticlePage(lang, {
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
      // its tabs above the cards or the stories; its sections' stories are its news tab too
      top={view || section === "holdings" || section === "figures" ? <WatchTabs lang={lang} view={view ?? "news"} /> : null}
      only={
        view === "people" || view === "groups" ? (
          <PortfolioCards
            cards={cards.filter((card) => KINDS[view].includes(card.kind))}
            lang={lang}
            heading={view === "groups" ? w.portfolio.groupsHeading : undefined}
          />
        ) : null
      }
    />
  );
}
