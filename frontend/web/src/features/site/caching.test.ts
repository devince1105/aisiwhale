// The site's Function budget (2026-11-11): the public lists' query strings are rewritten to cached
// pages, and a public read is kept on the server only when nobody's cookie went with it.
import { describe, expect, it, vi } from "vitest";

import { fetchArticle, KEPT, keptFetch } from "./api";
import { facetsOf, QUERY_FAMILIES, queryRewrites } from "./queryRoutes";

/** What Next.js does with a ``has`` value: the whole query value against it. */
function matches(pattern: string, value: string): Record<string, string> | null {
  const found = new RegExp(`^${pattern}$`).exec(value);
  return found ? { ...found.groups } : null;
}

/** The first rewrite that takes ``/news/zh-TW…`` with ``query``, and where it sends it. */
function rewrite(source: string, query: Record<string, string>): string | null {
  for (const rule of queryRewrites()) {
    if (rule.source !== source) continue;
    if (rule.missing?.some((m) => m.key in query)) continue;
    const captured: Record<string, string> = { lang: "zh-TW" };
    const ok = rule.has.every((h) => {
      if (!(h.key in query)) return false;
      if (h.value === undefined) return true;
      const groups = matches(h.value, query[h.key]);
      if (groups) Object.assign(captured, groups);
      return groups !== null;
    });
    if (ok) return rule.destination.replace(/:([a-z]+)/g, (_, key: string) => captured[key] ?? `:${key}`);
  }
  return null;
}

const FRONT = QUERY_FAMILIES[0].source;
const RANKING = QUERY_FAMILIES[2].source;

describe("query strings to cached pages", () => {
  it("sends every combination of the front page's query to a browse path, the most keys first", () => {
    expect(rewrite(FRONT, { section: "ai", page: "2" })).toBe("/news/zh-TW/browse/section/ai/page/2");
    expect(rewrite(FRONT, { page: "3" })).toBe("/news/zh-TW/browse/page/3");
    expect(rewrite(FRONT, { section: "watch", view: "groups" })).toBe("/news/zh-TW/browse/section/watch/view/groups");
    expect(rewrite(FRONT, { section: "ai", date: "2026-11-10", page: "2", view: "news" })).toBe(
      "/news/zh-TW/browse/section/ai/date/2026-11-10/page/2/view/news",
    );
  });

  it("leaves out a value the page would not take, keeping the rest", () => {
    expect(rewrite(FRONT, { section: "ai", page: "abc" })).toBe("/news/zh-TW/browse/section/ai");
    expect(rewrite(FRONT, { page: "0" })).toBeNull(); // page 1: the bare page
  });

  it("does not rewrite a query no page reads (it reaches the bare, cached page)", () => {
    expect(rewrite(FRONT, { utm_source: "line" })).toBeNull();
  });

  it("sends the ranking's search to the page rendered per request, its sorts to the cached one", () => {
    expect(rewrite(RANKING, { sort: "change", page: "2" })).toBe("/news/zh-TW/holdings/institutions/browse/sort/change/page/2");
    expect(rewrite(RANKING, { q: "blackrock", sort: "change" })).toBe("/news/zh-TW/holdings/institutions/search");
  });

  it("reads a browse path back as the query it was", () => {
    expect(facetsOf(["section", "ai", "page", "2"])).toEqual({ section: "ai", page: "2" });
    expect(facetsOf(["page", "2", "page", "9", "odd"])).toEqual({ page: "2" });
    expect(facetsOf(["Bad Key", "x"])).toEqual({});
  });

  it("stays a small, ordered list (every rule is checked by the router)", () => {
    expect(queryRewrites().length).toBeLessThan(50);
  });
});

describe("what the server keeps", () => {
  it("keeps a read nobody signed in made, for the time asked, under one tag", async () => {
    const send = vi.fn(async () => new Response("{}"));
    await keptFetch(KEPT.short, { fetch: send }, true)("http://api/x");
    expect(send).toHaveBeenCalledWith("http://api/x", expect.objectContaining({ cache: "force-cache", next: { revalidate: 300, tags: ["public-api"] } }));
  });

  it("never keeps a read that carried a reader's cookie", async () => {
    const send = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => new Response(String(input) + String(init)));
    await keptFetch(KEPT.medium, { fetch: send, cookie: "autora_reader=abc" }, true)("http://api/x");
    const init = send.mock.calls[0][1] as RequestInit & { next?: unknown };
    expect(init.cache).toBe("no-store");
    expect(init.next).toBeUndefined();
  });

  it("leaves the browser's reads to the browser", async () => {
    const send = vi.fn(async () => new Response("{}"));
    await keptFetch(KEPT.short, { fetch: send }, false)("http://api/x");
    expect(send).toHaveBeenCalledWith("http://api/x", undefined);
  });

  it("asks for an article with no cookie unless one is given", async () => {
    const send = vi.fn(async (input: RequestInfo | URL) => {
      void input;
      return new Response(JSON.stringify({ title: "t" }), { headers: { "Content-Type": "application/json" } });
    });
    await fetchArticle("zh-TW", "s", { baseUrl: "http://api", fetch: send as typeof fetch });
    const request = send.mock.calls[0][0] as unknown as Request;
    expect(request.headers.get("cookie")).toBeNull();
  });
});

describe("robots.txt by host", () => {
  it("lets the site's own host be crawled and asks every other not to be", async () => {
    const { isSiteHost } = await import("@/app/robots");
    expect(isSiteHost("aisiwhale.com", "https://aisiwhale.com")).toBe(true);
    expect(isSiteHost("www.aisiwhale.com", "https://aisiwhale.com")).toBe(true);
    expect(isSiteHost("aisiwhale-web.example.workers.dev", "https://aisiwhale.com")).toBe(false);
    expect(isSiteHost(null, "https://aisiwhale.com")).toBe(false);
  });
});
