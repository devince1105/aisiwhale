// /news/{lang}?section=ai&page=2 is this page, /news/{lang}/browse/section/ai/page/2, by a rewrite
// in the router (queryRoutes.ts): kept like the front page instead of rendered per request.
import { facetsOf } from "@/features/site/queryRoutes";

import { FrontPage, frontMetadata } from "../../front";

export const revalidate = 120;

// any tab, day or page, built the first time it is asked for, then kept
export const dynamicParams = true;
export function generateStaticParams() {
  return [];
}

type Params = Promise<{ lang: string; facets: string[] }>;

export async function generateMetadata({ params }: { params: Params }) {
  const { lang, facets } = await params;
  return frontMetadata(lang, facetsOf(facets));
}

export default async function Page({ params }: { params: Params }) {
  const { lang, facets } = await params;
  return <FrontPage lang={lang} query={facetsOf(facets)} />;
}
