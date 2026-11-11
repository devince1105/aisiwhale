// Query strings into paths, so a page that is asked for with ``?page=2`` can still be cached.
//
// A page that reads ``searchParams`` is rendered on every request: Next.js cannot know which
// queries there will be. The public site's lists (the front page's tabs, days and pages; a stock's
// stories; the 13F ranking's sorts and pages; the TWSE flows; an institution's quarters) keep the
// addresses readers and search engines already have, and next.config.ts rewrites each of them, in
// the router and before any function runs, to a path under ``…/browse/…`` that is cached like any
// other page (ISR). The reader's address bar still shows the query.
//
// A value the pattern does not accept is left out, as the pages already did with it. A query no
// family knows (utm_source, fbclid…) reaches the page without the query, which the cached page
// ignores. The search box of the ranking (``?q=``) is the one exception: what is typed is not
// knowable ahead, so it goes to a page rendered on request.
//
// No imports: next.config.ts loads this file.

export interface QueryParam {
  key: string;
  /** What the value may be; the whole value must match. */
  pattern: string;
}

export interface QueryFamily {
  /** The public address, as next.config's ``source``. */
  source: string;
  /** Where the cached page is; ``/{key}/{value}`` pairs follow it. */
  browse: string;
  params: QueryParam[];
  /** A query key that, when present, keeps this family's rewrites from applying. */
  unless?: string;
}

const LANG = ":lang(zh-TW|en)";
const DAY = "\\d{4}-\\d{2}-\\d{2}";
const PAGE = "[1-9]\\d{0,2}";

export const QUERY_FAMILIES: readonly QueryFamily[] = [
  {
    source: `/news/${LANG}`,
    browse: "/news/:lang/browse",
    params: [
      { key: "section", pattern: "[a-z][a-z-]{0,39}" },
      { key: "date", pattern: DAY },
      { key: "page", pattern: PAGE },
      { key: "view", pattern: "[a-z]{1,20}" },
    ],
  },
  {
    source: `/news/${LANG}/stocks/:symbol`,
    browse: "/news/:lang/stocks/:symbol/browse",
    params: [{ key: "page", pattern: PAGE }],
  },
  {
    source: `/news/${LANG}/holdings/institutions`,
    browse: "/news/:lang/holdings/institutions/browse",
    params: [
      { key: "period", pattern: DAY },
      { key: "sort", pattern: "value|change|filed" },
      { key: "order", pattern: "asc|desc" },
      { key: "page", pattern: PAGE },
    ],
    unless: "q",
  },
  {
    source: `/news/${LANG}/holdings/institutions/tw`,
    browse: "/news/:lang/holdings/institutions/tw/browse",
    params: [
      { key: "day", pattern: DAY },
      { key: "group", pattern: "foreign|trust|dealer|total" },
      { key: "side", pattern: "buy|sell" },
    ],
  },
  {
    source: `/news/${LANG}/holdings/institutions/:cik(\\d{1,10})`,
    browse: "/news/:lang/holdings/institutions/:cik/browse",
    params: [{ key: "period", pattern: DAY }],
  },
];

interface Condition {
  type: "query";
  key: string;
  value?: string;
}

export interface QueryRewrite {
  source: string;
  destination: string;
  has: Condition[];
  missing?: Condition[];
}

/** Every non-empty subset of ``items``, the largest first, each in ``items``' order. */
function subsets<T>(items: readonly T[]): T[][] {
  const all: T[][] = [];
  for (let mask = 1; mask < 1 << items.length; mask++) {
    all.push(items.filter((_, i) => mask & (1 << i)));
  }
  return all.sort((a, b) => b.length - a.length);
}

/** The rewrites, in the order they are to be tried: within a family, the most keys first, so a
 * request with ``section`` and ``page`` is not taken by the rule for ``section`` alone. */
export function queryRewrites(families: readonly QueryFamily[] = QUERY_FAMILIES): QueryRewrite[] {
  const rules: QueryRewrite[] = [];
  for (const family of families) {
    const missing = family.unless ? [{ type: "query" as const, key: family.unless }] : undefined;
    for (const set of subsets(family.params)) {
      rules.push({
        source: family.source,
        destination: `${family.browse}/${set.map((p) => `${p.key}/:${p.key}`).join("/")}`,
        has: set.map((p) => ({ type: "query", key: p.key, value: `(?<${p.key}>${p.pattern})` })),
        ...(missing ? { missing } : {}),
      });
    }
  }
  // the ranking's search box: rendered on request, its query as it came
  rules.push({
    source: `/news/${LANG}/holdings/institutions`,
    destination: "/news/:lang/holdings/institutions/search",
    has: [{ type: "query", key: "q" }],
  });
  return rules;
}

/** ``["page", "2", "section", "ai"]`` → ``{ page: "2", section: "ai" }``: what a browse page was
 * asked, in the shape the pages read a query in (Next.js has already decoded the segments). Keys
 * only once; anything odd is dropped. */
export function facetsOf(segments: readonly string[] | undefined): Record<string, string> {
  const query: Record<string, string> = {};
  const parts = segments ?? [];
  for (let i = 0; i + 1 < parts.length; i += 2) {
    const key = parts[i];
    if (/^[a-z]{1,10}$/.test(key) && !(key in query)) query[key] = parts[i + 1];
  }
  return query;
}
