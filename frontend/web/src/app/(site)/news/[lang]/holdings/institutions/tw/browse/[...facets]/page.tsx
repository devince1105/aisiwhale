// ?day=&group=&side= of the TWSE/TPEx flows ranking is this page, by a rewrite in the router
// (queryRoutes.ts), built the first time it is asked for and kept.
import { facetsOf } from "@/features/site/queryRoutes";

import { FlowsPage, flowsMetadata } from "../../flows";

export const revalidate = 300; // no longer than the layout's market strip
export const dynamicParams = true;
export function generateStaticParams() {
  return [];
}

type Params = Promise<{ lang: string; facets: string[] }>;

export async function generateMetadata({ params }: { params: Params }) {
  const { lang, facets } = await params;
  return flowsMetadata(lang, facetsOf(facets));
}

export default async function Page({ params }: { params: Params }) {
  const { lang, facets } = await params;
  return <FlowsPage lang={lang} query={facetsOf(facets)} />;
}
