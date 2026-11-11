// The front page with nothing asked (D-015). Built and kept, not rendered per request: its tabs,
// days and pages are the same page under browse/ (queryRoutes.ts), kept the same way.
import { FrontPage, frontMetadata } from "./front";

// a story just published is on the list within two minutes (KEPT.list)
export const revalidate = 120;

type Params = Promise<{ lang: string }>;

export async function generateMetadata({ params }: { params: Params }) {
  return frontMetadata((await params).lang, {});
}

export default async function Page({ params }: { params: Params }) {
  return <FrontPage lang={(await params).lang} query={{}} />;
}
