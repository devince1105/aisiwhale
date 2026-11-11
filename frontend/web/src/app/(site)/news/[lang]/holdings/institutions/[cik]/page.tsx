import { InstitutionPage, institutionMetadata } from "./institution";

export const revalidate = 300; // no longer than the layout's market strip
export const dynamicParams = true;
export function generateStaticParams() {
  return [];
}

type Params = Promise<{ lang: string; cik: string }>;

export async function generateMetadata({ params }: { params: Params }) {
  const { lang, cik } = await params;
  return institutionMetadata(lang, cik, undefined);
}

export default async function Page({ params }: { params: Params }) {
  const { lang, cik } = await params;
  return <InstitutionPage lang={lang} cik={cik} period={undefined} />;
}
