import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { cache } from "react";

import { fetchPortfolio } from "@/features/site/api";
import { isLang, words } from "@/features/site/i18n";
import { PortfolioView, portfolioHref } from "@/features/site/Portfolios";

// Rendered per request, not cached: how much of the table is in the page depends on who is
// asking (D-159, HD-06), and a cached page would answer for the wrong reader.
export const dynamic = "force-dynamic";

type Params = Promise<{ lang: string; slug: string }>;

const load = cache((slug: string, lang: string, cookie: string) =>
  fetchPortfolio(slug, lang, { company: process.env.SITE_COMPANY || undefined, cookie }),
);

async function readerCookie(): Promise<string> {
  const jar = await cookies();
  const session = jar.get("autora_reader");
  return session ? `autora_reader=${session.value}` : "";
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { lang, slug } = await params;
  if (!isLang(lang)) return {};
  const portfolio = await load(slug, lang, await readerCookie());
  if (!portfolio) return {};
  const w = words(lang);
  return {
    title: `${portfolio.kind === "official" ? w.portfolio.officialTitle(portfolio.name) : w.portfolio.title(portfolio.name, portfolio.kind)} · ${w.site}`,
    description: portfolio.period ? w.portfolio.lag(portfolio.period) : w.portfolio.officialNote,
  };
}

export default async function Page({ params }: { params: Params }) {
  const { lang, slug } = await params;
  if (!isLang(lang)) notFound();
  const portfolio = await load(slug, lang, await readerCookie());
  if (!portfolio) notFound();
  const loginHref = `/news/${lang}/login?next=${encodeURIComponent(portfolioHref(lang, slug))}`;
  return <PortfolioView portfolio={portfolio} lang={lang} loginHref={loginHref} />;
}
