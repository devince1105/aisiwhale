// Taiwan's three institutional investors ranked (HD-12): the same for every reader. What the bare
// address (page.tsx) and its days, groups and sides (browse/[...facets], by a rewrite:
// queryRoutes.ts) both show. Nothing here reads the request.
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { fetchTwFlows } from "@/features/site/api";
import { isLang, words } from "@/features/site/i18n";
import { Breadcrumb, rankingHref } from "@/features/site/Institutions";
import {
  type FlowGroup,
  type FlowParams,
  type FlowSide,
  MarketSwitch,
  TwRankingView,
  twRankingHref,
} from "@/features/site/TwFlows";

export type Query = Record<string, string | string[] | undefined>;

const GROUPS: readonly FlowGroup[] = ["foreign", "trust", "dealer", "total"];

export function asked(query: Query): FlowParams {
  const one = (value: string | string[] | undefined) =>
    typeof value === "string" ? value : undefined;
  const day = one(query.day);
  const group = one(query.group);
  return {
    day: day && /^\d{4}-\d{2}-\d{2}$/.test(day) ? day : undefined,
    group: GROUPS.includes(group as FlowGroup)
      ? (group as FlowGroup)
      : undefined,
    side: one(query.side) === "sell" ? ("sell" as FlowSide) : undefined,
  };
}

export function flowsMetadata(lang: string, query: Query): Metadata {
  if (!isLang(lang)) return {};
  const w = words(lang);
  return {
    title: `${w.twFlows.rankingHeading} · ${w.site}`,
    description: w.twFlows.note,
    alternates: { canonical: twRankingHref(lang, asked(query)) },
  };
}

export async function FlowsPage({ lang, query: asking }: { lang: string; query: Query }) {
  if (!isLang(lang)) notFound();
  const query = asked(asking);
  const ranking = await fetchTwFlows(query);
  const w = words(lang);
  return (
    <article className="mx-auto max-w-[56rem] px-4 pt-4 pb-12">
      <Breadcrumb
        lang={lang}
        here={[
          { label: w.ranking.title, href: rankingHref(lang) },
          { label: w.twFlows.market.tw },
        ]}
      />
      <div className="mt-4">
        <MarketSwitch lang={lang} market="tw" />
      </div>
      <TwRankingView ranking={ranking} lang={lang} params={query} />
    </article>
  );
}
