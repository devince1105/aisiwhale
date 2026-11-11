// An institution's page (HD-11), as the bare address (page.tsx) and another quarter (?period=,
// browse/[...facets], by a rewrite: queryRoutes.ts) both show it. Built and kept for everybody
// (ISR): no cookie is read here, so the rest of the page — a signed-in reader's (D-159) — is never
// in what is kept; the browser asks for it, and asks again while a first-opened filer is queued
// (InstitutionReader).
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { cache } from "react";

import { fetchInstitution } from "@/features/site/api";
import { InstitutionReader } from "@/features/site/HoldingsReader";
import { isLang, words } from "@/features/site/i18n";
import { institutionHref } from "@/features/site/Institutions";
import { quarterOf } from "@/features/site/Portfolios";

const load = cache((cik: string, lang: string, period: string | undefined) => fetchInstitution(cik, lang, { period }));

export function periodOf(query: Record<string, string | undefined>): string | undefined {
  const period = query.period;
  return typeof period === "string" && /^\d{4}-\d{2}-\d{2}$/.test(period) ? period : undefined;
}

export async function institutionMetadata(lang: string, cik: string, period: string | undefined): Promise<Metadata> {
  if (!isLang(lang) || !/^\d{1,10}$/.test(cik)) return {};
  const page = await load(cik, lang, period);
  if (!page) return {};
  const w = words(lang);
  return {
    title: `${page.name} · ${w.ranking.title} · ${w.site}`,
    description: w.institution.quarter(quarterOf(lang, page.period)),
    alternates: { canonical: institutionHref(lang, page.cik, period) },
  };
}

export async function InstitutionPage({ lang, cik, period }: { lang: string; cik: string; period: string | undefined }) {
  if (!isLang(lang) || !/^\d{1,10}$/.test(cik)) notFound();
  const page = await load(cik, lang, period);
  if (!page) notFound();
  const loginHref = `/news/${lang}/login?next=${encodeURIComponent(institutionHref(lang, page.cik, period))}`;
  return <InstitutionReader key={`${lang}/${cik}/${period ?? ""}`} page={page} lang={lang} period={period} loginHref={loginHref} />;
}
