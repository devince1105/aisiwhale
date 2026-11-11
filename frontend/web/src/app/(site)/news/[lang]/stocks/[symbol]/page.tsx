import { StockPage, stockMetadata } from "./stock";

// its figure changes every few minutes, its holders a few times a year: kept five minutes (it was
// a minute, but the page was rendered per request anyway), built the first time a symbol is asked
export const revalidate = 300;
export const dynamicParams = true;
export function generateStaticParams() {
  return [];
}

type Params = Promise<{ lang: string; symbol: string }>;

export async function generateMetadata({ params }: { params: Params }) {
  const { lang, symbol } = await params;
  return stockMetadata(lang, symbol, 1);
}

export default async function Page({ params }: { params: Params }) {
  const { lang, symbol } = await params;
  return <StockPage lang={lang} symbol={symbol} page={1} />;
}
