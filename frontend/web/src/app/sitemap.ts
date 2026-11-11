// sitemap.xml: the pages a search engine is to know about — both languages' front pages and tabs,
// the holdings pages, the policies, and the latest stories — built once an hour and kept, so a
// crawler reading it costs nothing more than a file.
import type { MetadataRoute } from "next";

import { SITE_URL } from "@/config";
import { fetchArticlePage, fetchPortfolios, type PublicArticleSummary } from "@/features/site/api";
import { LANGS, TOPICS, type Lang } from "@/features/site/i18n";
import { listHref } from "@/features/site/links";
import { portfolioHref } from "@/features/site/Portfolios";

export const revalidate = 3600;

/** The latest stories per language: as many as a crawler needs to find what is new. */
const STORIES = 500;
const BATCH = 50; // the API's largest page

const PAGES = ["holdings/institutions", "holdings/institutions/tw", "pricing", "office", "contact", "privacy", "terms", "refund"];

async function latest(lang: Lang): Promise<PublicArticleSummary[]> {
  const company = process.env.SITE_COMPANY || undefined;
  const stories: PublicArticleSummary[] = [];
  for (let offset = 0; offset < STORIES; offset += BATCH) {
    const page = await fetchArticlePage(lang, { company, limit: BATCH, offset }).catch(() => null);
    if (!page) break;
    stories.push(...page.articles);
    if (page.articles.length < BATCH || offset + BATCH >= page.total) break;
  }
  return stories;
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const at = (path: string) => `${SITE_URL}${path}`;
  const entries: MetadataRoute.Sitemap = [];
  for (const lang of LANGS) {
    entries.push({ url: at(`/news/${lang}`), changeFrequency: "hourly", priority: 1 });
    for (const topic of TOPICS) entries.push({ url: at(listHref(lang, topic)), changeFrequency: "hourly", priority: 0.8 });
    for (const page of PAGES) entries.push({ url: at(`/news/${lang}/${page}`), changeFrequency: "daily", priority: 0.5 });
    const cards = await fetchPortfolios(lang, { company: process.env.SITE_COMPANY || undefined }).catch(() => []);
    for (const card of cards) entries.push({ url: at(portfolioHref(lang, card.slug)), changeFrequency: "weekly", priority: 0.6 });
    for (const story of await latest(lang)) {
      entries.push({
        url: at(story.path),
        lastModified: story.revised_at ?? story.published_at,
        changeFrequency: "weekly",
        priority: 0.7,
      });
    }
  }
  return entries;
}
