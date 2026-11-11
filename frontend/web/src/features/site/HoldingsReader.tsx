// A person's or an institution's holdings as this reader may see them (D-159, HD-06, HD-11): the
// page as kept for everybody, then, if it holds back the rest of the table, the browser asks for
// the reader's own copy (readerVersion.tsx).
"use client";

import { useEffect, useRef } from "react";

import { SITE_COMPANY } from "@/config";

import type { PublicInstitution, PublicPortfolio } from "./api";
import type { Lang } from "./i18n";
import { InstitutionView } from "./Institutions";
import { PortfolioView } from "./Portfolios";
import { useReaderVersion } from "./readerVersion";

export function PortfolioReader({
  portfolio,
  lang,
  slug,
  loginHref,
}: {
  portfolio: PublicPortfolio;
  lang: Lang;
  slug: string;
  loginHref: string;
}) {
  const query = new URLSearchParams({ lang, ...(SITE_COMPANY ? { company: SITE_COMPANY } : {}) });
  const [shown] = useReaderVersion(
    portfolio,
    `/api/public/holdings/people/${encodeURIComponent(slug)}?${query}`,
    portfolio.locked,
  );
  return <PortfolioView portfolio={shown} lang={lang} loginHref={loginHref} />;
}

/** How often, and how many times, a page whose 13F is still being read is asked again. */
const QUEUED_EVERY_MS = 15_000;
const QUEUED_TRIES = 12;

export function InstitutionReader({
  page,
  lang,
  period,
  loginHref,
}: {
  page: PublicInstitution;
  lang: Lang;
  period?: string;
  loginHref: string;
}) {
  const query = new URLSearchParams({ lang, ...(period ? { period } : {}) });
  // locked for a reader not signed in; queued when the kept page was built before its 13F was
  // read (HD-11), which a reload used to ask again for and now the browser does
  const [shown, refresh] = useReaderVersion(
    page,
    `/api/public/institutions/${encodeURIComponent(page.cik)}?${query}`,
    page.locked || page.status === "queued",
  );
  const tries = useRef(0);
  useEffect(() => {
    if (shown.status !== "queued" || tries.current >= QUEUED_TRIES) return;
    const timer = setTimeout(() => {
      tries.current += 1;
      refresh();
    }, QUEUED_EVERY_MS);
    return () => clearTimeout(timer);
  }, [shown, refresh]);
  return <InstitutionView page={shown} lang={lang} loginHref={loginHref} />;
}
