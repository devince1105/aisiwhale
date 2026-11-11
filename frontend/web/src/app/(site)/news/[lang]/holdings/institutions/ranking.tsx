// 機構排行 (HD-11): the same for every reader. What the bare address (page.tsx), its sorts and
// pages (browse/[...facets], by a rewrite: queryRoutes.ts) and its search (search/, rendered per
// request: what is typed cannot be known ahead) all show. Nothing here reads the request.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { fetchRanking } from "@/features/site/api";
import { isLang, words } from "@/features/site/i18n";
import { RANK_PAGE, rankingHref, RankingView, type RankingParams, type RankSort } from "@/features/site/Institutions";

export type Query = Record<string, string | string[] | undefined>;

const SORTS: readonly RankSort[] = ["value", "change", "filed"];

function one(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" ? value : undefined;
}

export function asked(query: Query): RankingParams {
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

export function rankingMetadata(lang: string, query: Query): Metadata {
  if (!isLang(lang)) return {};
  const w = words(lang);
  const params = asked(query);
  return {
    title: `${w.ranking.title} · ${w.site}`,
    description: w.ranking.note,
    // a search's answers are not a page of their own to list
    alternates: { canonical: rankingHref(lang, { ...params, q: undefined }) },
    ...(params.q ? { robots: { index: false, follow: true } } : {}),
  };
}

export async function RankingPage({ lang, query }: { lang: string; query: Query }) {
  if (!isLang(lang)) notFound();
  const params = asked(query);
  const ranking = await fetchRanking(lang, {
    period: params.period,
    q: params.q,
    sort: params.sort,
    order: params.order,
    limit: RANK_PAGE,
    offset: ((params.page ?? 1) - 1) * RANK_PAGE,
  });
  return <RankingView ranking={ranking} lang={lang} params={params} />;
}
