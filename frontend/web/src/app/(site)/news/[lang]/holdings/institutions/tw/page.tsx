// The TWSE/TPEx flows ranking with nothing asked: built and kept (ISR). It was meant to be kept
// five minutes before, but reading the query made it rendered on every request.
import { FlowsPage, flowsMetadata } from "./flows";

// the exchanges publish a trading day's figures once, in the afternoon; five minutes, as the strip
export const revalidate = 300; // no longer than the layout's market strip

type Params = Promise<{ lang: string }>;

export async function generateMetadata({ params }: { params: Params }) {
  return flowsMetadata((await params).lang, {});
}

export default async function Page({ params }: { params: Params }) {
  return <FlowsPage lang={(await params).lang} query={{}} />;
}
