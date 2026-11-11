import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { cache } from "react";

import { fetchPortfolio } from "@/features/site/api";
import { PortfolioReader } from "@/features/site/HoldingsReader";
import { isLang, words } from "@/features/site/i18n";
import { portfolioHref } from "@/features/site/Portfolios";

// Built the first time it is asked for, then kept for everybody (ISR): the table as a reader not
// signed in sees it, and no cookie is read here, so the whole table — a signed-in reader's
// (D-159, HD-06) — is never in what is kept. The browser asks for it (PortfolioReader).
export const revalidate = 300; // no longer than the layout's market strip
export const dynamicParams = true;
export function generateStaticParams() {
  return [];
}

type Params = Promise<{ lang: string; slug: string }>;

const load = cache((slug: string, lang: string) =>
  fetchPortfolio(slug, lang, { company: process.env.SITE_COMPANY || undefined }),
);

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { lang, slug } = await params;
  if (!isLang(lang)) return {};
  const portfolio = await load(slug, lang);
  if (!portfolio) return {};
  const w = words(lang);
  return {
    title: `${portfolio.kind === "official" ? w.portfolio.officialTitle(portfolio.name) : w.portfolio.title(portfolio.name, portfolio.kind)} · ${w.site}`,
    description: portfolio.period ? w.portfolio.lag(portfolio.period) : w.portfolio.officialNote,
    alternates: { canonical: portfolioHref(lang, slug) },
  };
}

export default async function Page({ params }: { params: Params }) {
  const { lang, slug } = await params;
  if (!isLang(lang)) notFound();
  const portfolio = await load(slug, lang);
  if (!portfolio) notFound();
  const loginHref = `/news/${lang}/login?next=${encodeURIComponent(portfolioHref(lang, slug))}`;
  return <PortfolioReader key={`${lang}/${slug}`} portfolio={portfolio} lang={lang} slug={slug} loginHref={loginHref} />;
}
