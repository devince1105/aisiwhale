// 機構排行 searched (?q=, by a rewrite in the router: queryRoutes.ts): rendered on request, since
// what is typed cannot be known ahead. The API's answer is still kept (the Data Cache), so the same
// search asked twice is asked of the API once; the answers are not for search engines to list.
import { RankingPage, rankingMetadata, type Query } from "../ranking";

// said, not left to be worked out: kept, it would answer every search with the first one
export const dynamic = "force-dynamic";

type Params = Promise<{ lang: string }>;
type Search = Promise<Query>;

export async function generateMetadata({ params, searchParams }: { params: Params; searchParams: Search }) {
  return rankingMetadata((await params).lang, await searchParams);
}

export default async function Page({ params, searchParams }: { params: Params; searchParams: Search }) {
  return <RankingPage lang={(await params).lang} query={await searchParams} />;
}
