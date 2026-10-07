import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { fetchRanking } from "@/features/site/api";
import { isLang, words } from "@/features/site/i18n";
import { RANK_PAGE, RankingView, type RankingParams, type RankSort } from "@/features/site/Institutions";

// 機構排行 (HD-11): the same for every reader, so the API's answer is kept a few minutes
export const revalidate = 300;

type Params = Promise<{ lang: string }>;
type Search = Promise<{ [key: string]: string | string[] | undefined }>;

const SORTS: readonly RankSort[] = ["value", "change", "filed"];

function one(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" ? value : undefined;
}

async function asked(searchParams: Search): Promise<RankingParams> {
  const query = await searchParams;
  const sort = one(query.sort);
  const period = one(query.period);
  const q = one(query.q)?.trim().slice(0, 100);
  return {
    period: period && /^\d{4}-\d{2}-\d{2}$/.test(period) ? period : undefined,
    q: q || undefined,
    sort: SORTS.includes(sort as RankSort) ? (sort as RankSort) : undefined,
    order: one(query.order) === "asc" ? "asc" : undefined,
    page: Math.min(Math.max(Number.parseInt(one(query.page) ?? "1", 10) || 1, 1), 400),
  };
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { lang } = await params;
  if (!isLang(lang)) return {};
  const w = words(lang);
  return { title: `${w.ranking.title} · ${w.site}`, description: w.ranking.note };
}

export default async function Page({ params, searchParams }: { params: Params; searchParams: Search }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const query = await asked(searchParams);
  const ranking = await fetchRanking(lang, {
    period: query.period,
    q: query.q,
    sort: query.sort,
    order: query.order,
    limit: RANK_PAGE,
    offset: ((query.page ?? 1) - 1) * RANK_PAGE,
  });
  return <RankingView ranking={ranking} lang={lang} params={query} />;
}
