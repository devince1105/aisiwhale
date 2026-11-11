// 機構排行 with nothing asked: built and kept (ISR). It was meant to be kept five minutes before,
// but reading the query made it rendered on every request; its sorts and pages are browse/ now.
import { RankingPage, rankingMetadata } from "./ranking";

// 13F filings come in a few times a day at most; five minutes, as long as the market strip above
export const revalidate = 300; // no longer than the layout's market strip

type Params = Promise<{ lang: string }>;

export async function generateMetadata({ params }: { params: Params }) {
  return rankingMetadata((await params).lang, {});
}

export default async function Page({ params }: { params: Params }) {
  return <RankingPage lang={(await params).lang} query={{}} />;
}
