// The AI newsroom at work (D-155): a demo of the office the stories come from. Made-up people
// playing a script, labelled as a demo; the real office stays in the back office.
import { notFound } from "next/navigation";

import { OfficeSlot } from "@/features/demo-office/KeptOffice";
import { isLang, words } from "@/features/site/i18n";

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  return isLang(lang) ? { title: `${words(lang).office.title} · ${words(lang).site}`, description: words(lang).office.intro } : {};
}

export default async function Page({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const w = words(lang).office;
  return (
    <section className="mx-auto max-w-6xl px-4 py-8">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">{w.title}</h1>
        <span data-testid="demo-badge" className="rounded-full border border-accent px-2.5 py-0.5 text-xs font-semibold text-accent">
          {w.badge}
        </span>
      </div>
      <p className="mt-3 max-w-3xl leading-relaxed text-muted">{w.intro}</p>
      <div className="mt-6">
        {/* on a capable computer, the office kept between pages moves in here (D-176) */}
        <OfficeSlot lang={lang} />
      </div>
    </section>
  );
}
