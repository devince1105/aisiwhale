// What the sidebar shows (D-085–D-088), asked of the API together on the server: a month's days
// for the calendar, the strip's figures, 熱門文章 and 財經行事曆. Each fails alone into nothing.
import { fetchCalendar, fetchEvents, fetchMarkets, fetchPopular } from "./api";
import { sectionsOf, type Filter, type Lang } from "./i18n";

/** Today in Taipei, "YYYY-MM-DD": the site's day. */
export function taipeiToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Taipei" }).format(new Date());
}

export async function loadSidebar(lang: Lang, { section = null, month }: { section?: Filter | null; month?: string } = {}) {
  const company = process.env.SITE_COMPANY || undefined;
  const shown = month ?? taipeiToday().slice(0, 7);
  const [days, markets, popular, events] = await Promise.all([
    fetchCalendar(lang, shown, { company, section: section ? sectionsOf(section) : undefined }),
    fetchMarkets(),
    fetchPopular(lang, { company }),
    fetchEvents(lang),
  ]);
  return { calendar: { month: shown, days }, markets, popular, events };
}
