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
} from "@/features/site/TwFlows";

// Taiwan's three institutional investors ranked (HD-12): the same for every reader
export const revalidate = 300;

type Params = Promise<{ lang: string }>;
type Search = Promise<{ [key: string]: string | string[] | undefined }>;

const GROUPS: readonly FlowGroup[] = ["foreign", "trust", "dealer", "total"];

async function asked(searchParams: Search): Promise<FlowParams> {
  const query = await searchParams;
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

export async function generateMetadata({
  params,
}: {
  params: Params;
}): Promise<Metadata> {
  const { lang } = await params;
  if (!isLang(lang)) return {};
  const w = words(lang);
  return {
    title: `${w.twFlows.rankingHeading} · ${w.site}`,
    description: w.twFlows.note,
  };
}

export default async function Page({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Search;
}) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const query = await asked(searchParams);
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
