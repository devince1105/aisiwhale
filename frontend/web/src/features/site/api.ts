// The public site's reads (T-515): no operator token, published articles only. Typed by the API's
// OpenAPI document like the admin client; used by server components, so it takes the server-side
// API URL.
import createClient from "openapi-fetch";

import { ApiError, type Schemas } from "@/api/client";
import type { paths } from "@/api/schema.gen";
import { SERVER_API_URL } from "@/config";

import type { Section } from "./i18n";

export type PublicArticle = Schemas["PublicArticle"];
export type PublicArticleSummary = Schemas["PublicArticleSummary"];
export type PublicQuote = Schemas["PublicQuote"];
export type PublicStock = Schemas["PublicStock"];
export type PublicHistory = Schemas["PublicHistory"];
export type PublicIntraday = Schemas["PublicIntraday"];
export type PublicSecurity = Schemas["PublicSecurity"];
export type PublicHolder = Schemas["PublicHolder"];
export type PublicTrade = Schemas["PublicTrade"];

export interface SiteClientOptions {
  baseUrl?: string;
  fetch?: typeof fetch;
  /** The reader's cookie, forwarded when the server renders a page for them (D-025). Without
   * it the API cannot tell a member from anybody else, and a locked article stays locked. */
  cookie?: string;
}

function client(options: SiteClientOptions) {
  return createClient<paths>({
    baseUrl: options.baseUrl ?? SERVER_API_URL,
    fetch: options.fetch,
    headers: options.cookie ? { cookie: options.cookie } : undefined,
  });
}

/** A published article in ``lang``, or null when there is none (not published, or not in it). */
export async function fetchArticle(
  lang: string,
  slug: string,
  options: SiteClientOptions = {},
): Promise<PublicArticle | null> {
  const { data, error, response } = await client(options).GET("/api/public/articles/{lang}/{slug}", {
    params: { path: { lang, slug } },
  });
  if (response.status === 404) return null;
  if (error !== undefined || !data) throw ApiError.from(response, error);
  return data;
}

export interface ListOptions extends SiteClientOptions {
  company?: string;
  /** Only these sections (D-047); several for a tab of several (D-050). */
  section?: Section | Section[];
  limit?: number;
  offset?: number;
}

/** Newest first. A page that comes back shorter than ``limit`` is the last. */
export async function fetchArticles(lang: string, options: ListOptions = {}): Promise<PublicArticleSummary[]> {
  return (await fetchArticlePage(lang, options)).articles;
}

/** A page of the list, and how many articles there are in all (D-065): the list's page numbers. */
export async function fetchArticlePage(
  lang: string,
  options: ListOptions = {},
): Promise<{ articles: PublicArticleSummary[]; total: number }> {
  const { company, section, limit, offset } = options;
  const { data, error, response } = await client(options).GET("/api/public/articles", {
    params: {
      query: { lang, company, section: section === undefined ? undefined : [section].flat(), limit, offset },
    },
  });
  if (error !== undefined || !data) throw ApiError.from(response, error);
  const counted = Number.parseInt(response.headers.get("X-Total-Count") ?? "", 10);
  // an API that does not count: at least what this page reaches
  const total = Number.isFinite(counted) ? counted : (offset ?? 0) + data.length;
  return { articles: data, total };
}

/** The market strip's figures (D-048). Never throws: the strip is left out instead of the page. */
export async function fetchMarkets(options: SiteClientOptions = {}): Promise<PublicQuote[]> {
  try {
    const { data } = await client(options).GET("/api/public/markets");
    return data ?? [];
  } catch {
    return [];
  }
}

/** A stock's page (D-049), or null when the site has no page for that symbol. */
export async function fetchStock(
  symbol: string,
  lang: string,
  options: SiteClientOptions & { company?: string } = {},
): Promise<PublicStock | null> {
  const { data, error, response } = await client(options).GET("/api/public/stocks/{symbol}", {
    params: { path: { symbol }, query: { lang, company: options.company } },
  });
  if (response.status === 404) return null;
  if (error !== undefined || !data) throw ApiError.from(response, error);
  return data;
}

/** A stock's daily bars for its chart (D-059); null for a symbol with no page. */
export async function fetchHistory(
  symbol: string,
  options: SiteClientOptions = {},
): Promise<PublicHistory | null> {
  const { data, error, response } = await client(options).GET("/api/public/stocks/{symbol}/history", {
    params: { path: { symbol } },
  });
  if (response.status === 404) return null;
  if (error !== undefined || !data) throw ApiError.from(response, error);
  return data;
}

/** A US stock's last five trading days in 15-minute bars (D-059); empty for a Taiwan stock. */
export async function fetchIntraday(symbol: string, options: SiteClientOptions = {}): Promise<PublicIntraday> {
  const { data, error, response } = await client(options).GET("/api/public/stocks/{symbol}/intraday", {
    params: { path: { symbol } },
  });
  if (error !== undefined || !data) throw ApiError.from(response, error);
  return data;
}

/** Any listed Taiwan or US stock (D-061), by code, ticker or name. */
export async function searchSecurities(q: string, options: SiteClientOptions = {}): Promise<PublicSecurity[]> {
  const { data } = await client(options).GET("/api/public/securities", { params: { query: { q, limit: 12 } } });
  return data ?? [];
}

/** Quotes for these keys (tw:2330, us:PLTR): the strip's own, else the last stored close. */
export async function fetchQuotes(keys: string[], options: SiteClientOptions = {}): Promise<PublicQuote[]> {
  if (!keys.length) return [];
  try {
    const { data } = await client(options).GET("/api/public/quotes", { params: { query: { keys: keys.join(",") } } });
    return data ?? [];
  } catch {
    return [];
  }
}
