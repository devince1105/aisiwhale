// 聯絡我們 (D-165): the footer's way to reach the site, in place of an address on every page.
import { notFound } from "next/navigation";

import { ContactForm } from "@/features/site/ContactForm";
import { isLang, words } from "@/features/site/i18n";

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  return isLang(lang) ? { title: `${words(lang).contactForm.title} · ${words(lang).site}` } : {};
}

export default async function Page({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const w = words(lang).contactForm;
  return (
    <section className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="text-2xl font-bold">{w.title}</h1>
      <p className="mt-2 leading-relaxed text-muted">{w.intro}</p>
      <div className="mt-6">
        <ContactForm lang={lang} />
      </div>
    </section>
  );
}
