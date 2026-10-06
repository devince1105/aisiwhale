// What membership costs and what it gets you (D-034). The prices come from the API, through
// the same plan cards the paywall shows, so this page and the payment page never disagree. Before
// membership opens, the same page with 即將開放 for the buttons (D-161): what will be sold, and at
// what price, is there for a payment provider's reviewer and for readers. Whether it is open is
// the API's answer (``available``, P2-B), asked on every visit; no answer reads as not yet.
import { notFound } from "next/navigation";

import { SERVER_API_URL, SITE_COMPANY } from "@/config";
import { isLang, words } from "@/features/site/i18n";
import { fetchOffer } from "@/features/site/checkout";
import { PlanPicker } from "@/features/site/PlanPicker";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  return isLang(lang) ? { title: `${words(lang).pricing} · ${words(lang).site}` } : {};
}

export default async function Page({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const w = words(lang);
  const here = `/news/${lang}/pricing`;
  const offers = await Promise.all(
    (["month", "year"] as const).map((interval) => fetchOffer(SITE_COMPANY, interval, SERVER_API_URL)),
  );
  const open = offers.some((offer) => offer?.available === true);
  return (
    <article className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="text-2xl font-bold">{w.pricing}</h1>
      {open ? null : (
        <p data-testid="membership-closed" className="mt-2 rounded-lg border border-line bg-canvas p-3 leading-relaxed">
          {w.pricingClosed}
        </p>
      )}
      <p className="mt-2 leading-relaxed">{w.pricingIntro}</p>
      <ul className="mt-4 list-disc space-y-1 pl-6">
        {w.pricingIncludes.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <div className="mt-6">
        <PlanPicker
          lang={lang}
          loginHref={`/news/${lang}/login?next=${encodeURIComponent(here)}`}
          company={SITE_COMPANY}
        />
      </div>
      <p className="mt-4 text-sm text-muted">{w.pricingSignIn}</p>
      <p className="mt-1 text-sm text-muted">{w.pricingPayment}</p>
    </article>
  );
}
