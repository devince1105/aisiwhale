// robots.txt: what crawlers are asked to leave alone, so they spend their visits (and the site's
// server time) on the stories. Asking is all it does — a crawler that ignores it is the
// firewall's (logs/perf/2026-11-11-vercel-function-usage.md).
import type { MetadataRoute } from "next";

import { SITE_URL } from "@/config";

/** Crawlers that index for SEO tools, not for readers, and are known to crawl hard. */
export const HEAVY_CRAWLERS = ["AhrefsBot", "SemrushBot", "MJ12bot", "DotBot", "PetalBot", "BLEXBot", "DataForSeoBot", "Bytespider"];

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/news/",
        disallow: [
          "/admin/",
          // a reader's own pages and the ways in: nothing for an index
          "/news/*/login",
          "/news/*/register",
          "/news/*/forgot-password",
          "/news/*/reset-password",
          "/news/*/verify-email",
          "/news/*/watchlist",
          "/news/*/coins",
          "/news/*/membership/",
          // the ranking's search box: every word typed is another page
          "/news/*/holdings/institutions?*q=",
          "/news/*/holdings/institutions/search",
          // where the query strings are rewritten to (any depth): the addresses with the query are
          // the pages to list
          "/news/*/browse/",
        ],
      },
      { userAgent: HEAVY_CRAWLERS, disallow: "/" },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
