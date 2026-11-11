// /news/{lang}/holdings/institutions/{cik}?period= is this page, by a rewrite in the router
// (queryRoutes.ts), built the first time it is asked for and kept.
import { facetsOf } from "@/features/site/queryRoutes";

import { InstitutionPage, institutionMetadata, periodOf } from "../../institution";

export const revalidate = 300; // no longer than the layout's market strip
export const dynamicParams = true;
export function generateStaticParams() {
  return [];
}

type Params = Promise<{ lang: string; cik: string; facets: string[] }>;

export async function generateMetadata({ params }: { params: Params }) {
  const { lang, cik, facets } = await params;
  return institutionMetadata(lang, cik, periodOf(facetsOf(facets)));
}

export default async function Page({ params }: { params: Params }) {
  const { lang, cik, facets } = await params;
  return <InstitutionPage lang={lang} cik={cik} period={periodOf(facetsOf(facets))} />;
}
