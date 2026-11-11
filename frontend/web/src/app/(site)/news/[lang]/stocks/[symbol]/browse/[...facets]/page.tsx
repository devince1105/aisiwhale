// /news/{lang}/stocks/{symbol}?page=2 is this page, by a rewrite in the router (queryRoutes.ts).
import { facetsOf } from "@/features/site/queryRoutes";

import { pageOf, StockPage, stockMetadata } from "../../stock";

export const revalidate = 300;
export const dynamicParams = true;
export function generateStaticParams() {
  return [];
}

type Params = Promise<{ lang: string; symbol: string; facets: string[] }>;

export async function generateMetadata({ params }: { params: Params }) {
  const { lang, symbol, facets } = await params;
  return stockMetadata(lang, symbol, pageOf(facetsOf(facets)));
}

export default async function Page({ params }: { params: Params }) {
  const { lang, symbol, facets } = await params;
  return <StockPage lang={lang} symbol={symbol} page={pageOf(facetsOf(facets))} />;
}
