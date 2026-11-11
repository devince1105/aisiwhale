// 機構排行 sorted, a later page, another quarter: ?sort=change&page=2 is this page, by a rewrite in
// the router (queryRoutes.ts), built the first time it is asked for and kept.
import { facetsOf } from "@/features/site/queryRoutes";

import { RankingPage, rankingMetadata } from "../../ranking";

export const revalidate = 300; // no longer than the layout's market strip
export const dynamicParams = true;
export function generateStaticParams() {
  return [];
}

type Params = Promise<{ lang: string; facets: string[] }>;

export async function generateMetadata({ params }: { params: Params }) {
  const { lang, facets } = await params;
  return rankingMetadata(lang, facetsOf(facets));
}

export default async function Page({ params }: { params: Params }) {
  const { lang, facets } = await params;
  return <RankingPage lang={lang} query={facetsOf(facets)} />;
}
