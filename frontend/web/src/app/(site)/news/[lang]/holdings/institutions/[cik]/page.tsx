import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { cache } from "react";

import { fetchInstitution } from "@/features/site/api";
import { isLang, words } from "@/features/site/i18n";
import { InstitutionView, institutionHref } from "@/features/site/Institutions";
import { quarterOf } from "@/features/site/Portfolios";

// Rendered per request, not cached: how much of the page there is depends on who is asking
// (D-159), and one opened for the first time is queued (HD-11).
export const dynamic = "force-dynamic";

type Params = Promise<{ lang: string; cik: string }>;
type Search = Promise<{ [key: string]: string | string[] | undefined }>;

const load = cache((cik: string, lang: string, period: string | undefined, cookie: string) =>
  fetchInstitution(cik, lang, { period, cookie }),
);

async function readerCookie(): Promise<string> {
  const jar = await cookies();
  const session = jar.get("autora_reader");
  return session ? `autora_reader=${session.value}` : "";
}

async function periodOf(searchParams: Search): Promise<string | undefined> {
  const period = (await searchParams).period;
  return typeof period === "string" && /^\d{4}-\d{2}-\d{2}$/.test(period) ? period : undefined;
}

export async function generateMetadata({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Search;
}): Promise<Metadata> {
  const { lang, cik } = await params;
  if (!isLang(lang) || !/^\d{1,10}$/.test(cik)) return {};
  const page = await load(cik, lang, await periodOf(searchParams), await readerCookie());
  if (!page) return {};
  const w = words(lang);
  return {
    title: `${page.name} · ${w.ranking.title} · ${w.site}`,
    description: w.institution.quarter(quarterOf(lang, page.period)),
  };
}

export default async function Page({ params, searchParams }: { params: Params; searchParams: Search }) {
  const { lang, cik } = await params;
  if (!isLang(lang) || !/^\d{1,10}$/.test(cik)) notFound();
  const period = await periodOf(searchParams);
  const page = await load(cik, lang, period, await readerCookie());
  if (!page) notFound();
  const loginHref = `/news/${lang}/login?next=${encodeURIComponent(institutionHref(lang, page.cik, period))}`;
  return <InstitutionView page={page} lang={lang} loginHref={loginHref} />;
}
