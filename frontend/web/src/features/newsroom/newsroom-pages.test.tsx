// @vitest-environment jsdom
// T-517: the newsroom's admin pages — stories, a story, articles, an article (versions, languages,
// claims with quotes in place, fact-check, distribution, readers), sources, and their data.
import type { EventEnvelope } from "@autora/event-schema";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createApiClient } from "@/api/client";
import { eventToQueryKeys } from "@/api/invalidation";
import { articleQuery, queryKeys, storiesQuery, workflowEventsQuery } from "@/api/queries";

import { ArticlesView } from "./ArticlesView";
import { ArticleProperties, ArticleView } from "./ArticleView";
import { claimNumbers, orderedClaims, problems, type ArticleDetail, type ClaimView, type StoryDetail } from "./model";
import { AddSourceForm, SourcesView, sourceConfig } from "./SourcesView";
import { StoriesView } from "./StoriesView";
import { StoryView } from "./StoryView";

vi.mock("next/navigation", () => ({ usePathname: () => "/admin/newsroom/articles/a1", useSearchParams: () => new URLSearchParams() }));
afterEach(cleanup);

const C = "0192c000-0000-7000-8000-000000000001";
const STORY = "0192c000-0000-7000-8000-000000000002";
const ARTICLE = "0192c000-0000-7000-8000-000000000003";
const PANELS = "0192c000-0000-7000-8000-00000000000a";
const COST = "0192c000-0000-7000-8000-00000000000b";
const AT = "2026-09-21T02:00:00Z";

const claim = (id: string, text: string, status = "VERIFIED"): ClaimView => ({
  id,
  text,
  claim_type: "number",
  status,
  quotes: [
    {
      evidence_id: "0192c000-0000-7000-8000-0000000000e1",
      evidence_title: "Lumen City switches on its first microgrid",
      url: "https://news.fixtures.autora.test/pilot",
      support_type: "supports",
      quote: "links 1,200 rooftop solar panels",
      before: "The pilot in Harbor District ",
      after: " and a 4 MWh battery.",
    },
  ],
});

const ARTICLE_DETAIL: ArticleDetail = {
  id: ARTICLE,
  story_id: STORY,
  title: "流明市首座社區微電網啟用",
  state: "PUBLISHED",
  slug: "microgrid-a1b2c3",
  version: 2,
  langs: ["en", "zh-TW"],
  revision_count: 1,
  published_at: AT,
  listed: true,
  access: "free",
  updated_at: AT,
  views: 7,
  story_title: "Lumen City microgrid",
  company_id: C,
  primary_lang: "zh-TW",
  published_langs: ["zh-TW", "en"],
  public_urls: { "zh-TW": "/news/zh-TW/articles/microgrid-a1b2c3", en: "/news/en/articles/microgrid-a1b2c3" },
  versions: [
    { version: 1, draft_group_id: "g1", langs: ["zh-TW", "en"], created_at: AT, change_summary: null, current: false, published: false },
    { version: 2, draft_group_id: "g2", langs: ["zh-TW", "en"], created_at: AT, change_summary: "補上導言", current: true, published: true },
  ],
  shown: 2,
  languages: {
    en: {
      version_id: "v2en",
      title: "Lumen City switches on its first microgrid",
      summary: null,
      blocks: [{ type: "paragraph", text: "The city spent NT$420 million.", claim_ids: [COST] }],
    },
    "zh-TW": {
      version_id: "v2zh",
      title: "流明市首座社區微電網啟用",
      summary: "重點數字",
      blocks: [
        { type: "heading", text: "重點", claim_ids: [] },
        { type: "paragraph", text: "市府花了 4.2 億元。", claim_ids: [COST] },
        { type: "paragraph", text: "串連 1,200 組太陽能板。", claim_ids: [PANELS, COST] },
      ],
    },
  },
  claims: [claim(PANELS, "The microgrid links 1,200 rooftop panels."), claim(COST, "The city spent NT$420 million.")],
  fact_checks: [
    { id: "f2", version: 2, passed: true, created_at: AT, checked: 2, failed: 0, results: [] },
    {
      id: "f1",
      version: 1,
      passed: false,
      created_at: AT,
      checked: 2,
      failed: 1,
      results: [{ claim_id: PANELS, text: "1,300 panels", verdict: "fail", problems: ["number 1,300 not in any quote"] }],
    },
  ],
  distributions: [
    { id: "d1", channel: "site", status: "published", external_ref: "/news/zh-TW/articles/x", created_at: AT, content: { "zh-TW": { url: "/news/zh-TW/articles/x", title: "流明市" } } },
    { id: "d2", channel: "social_draft", status: "draft", external_ref: null, created_at: AT, content: { en: { text: "New: the microgrid.", url: "/news/en/articles/x" } } },
  ],
  analytics: [{ day: "2026-09-21", lang: "en", views: 5, uniques: 5, read_complete: 2 }],
  workflow_run_ids: ["run1"],
  section: null,
  section_given: false,
  in_production: false,
  cover_asked: false,
};

const event = (event_type: string, payload: object): EventEnvelope =>
  ({
    event_id: `e-${event_type}`,
    event_type,
    schema_version: 1,
    seq: 1,
    company_id: C,
    occurred_at: AT,
    payload,
    correlation_id: "run1",
  }) as unknown as EventEnvelope;

describe("the model", () => {
  it("numbers claims by first citation and orders them so", () => {
    const numbers = claimNumbers(ARTICLE_DETAIL.languages["zh-TW"]!.blocks);
    expect([...numbers]).toEqual([
      [COST, 1],
      [PANELS, 2],
    ]);
    expect(orderedClaims(ARTICLE_DETAIL.claims, numbers).map((c) => c.id)).toEqual([COST, PANELS]);
  });

  it("puts a fact-check result's problems on one line", () => {
    expect(problems({ problems: ["a", "b"] })).toBe("a；b");
    expect(problems({ draft: "the languages cite different claims" })).toBe("the languages cite different claims");
  });
});

describe("taking an article off the site (D-044)", () => {
  const onSite = () => ({ unpublish: vi.fn(), republish: vi.fn(), revise: vi.fn(), busy: false, error: null });

  it("free or VIP: the chief's choice, which a person may change (D-159)", () => {
    const controls = { ...onSite(), setAccess: vi.fn() };
    const { rerender } = render(<ArticleView article={{ ...ARTICLE_DETAIL, state: "PUBLISHED" }} lang="zh-TW" onLang={vi.fn()} events={[]} onSite={controls} />);
    const box = within(screen.getByTestId("access-control"));
    expect(box.getByRole("button", { name: "免費" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(box.getByRole("button", { name: "VIP（會員看全文）" }));
    expect(controls.setAccess).toHaveBeenCalledWith("members");
    rerender(<ArticleView article={{ ...ARTICLE_DETAIL, state: "PUBLISHED", access: "members" }} lang="zh-TW" onLang={vi.fn()} events={[]} onSite={controls} />);
    expect(within(screen.getByTestId("access-control")).getByRole("button", { name: "VIP（會員看全文）" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("COIN at a price only a person sets: 5 unless changed, 1 to 100 (D-249)", () => {
    const controls = { ...onSite(), setAccess: vi.fn() };
    const view = (patch: Partial<ArticleDetail>) => (
      <ArticleView article={{ ...ARTICLE_DETAIL, state: "PUBLISHED", ...patch }} lang="zh-TW" onLang={vi.fn()} events={[]} onSite={controls} />
    );
    const { rerender } = render(view({}));
    let box = within(screen.getByTestId("access-control"));
    expect(box.queryByLabelText("鯨幣價格（1～100）")).toBeNull();
    fireEvent.click(box.getByRole("button", { name: "鯨幣解鎖" }));
    expect(controls.setAccess).not.toHaveBeenCalled(); // a price first
    const price = box.getByLabelText("鯨幣價格（1～100）") as HTMLInputElement;
    expect(price.value).toBe("5");
    const set = box.getByRole("button", { name: "設為鯨幣解鎖" }) as HTMLButtonElement;
    for (const bad of ["0", "101", "2.5", ""]) {
      fireEvent.change(price, { target: { value: bad } });
      expect(set.disabled).toBe(true);
    }
    fireEvent.change(price, { target: { value: "12" } });
    fireEvent.click(set);
    expect(controls.setAccess).toHaveBeenCalledWith("coin", 12);

    rerender(view({ access: "coin", coin_price: 12 }));
    box = within(screen.getByTestId("access-control"));
    expect(box.getByRole("button", { name: "鯨幣解鎖" }).getAttribute("aria-pressed")).toBe("true");
    expect((box.getByRole("button", { name: "更新價格" }) as HTMLButtonElement).disabled).toBe(true); // unchanged
    expect(screen.getByTestId("access-control").textContent).toContain("總編不會改動");
    fireEvent.click(box.getByRole("button", { name: "免費" }));
    expect(controls.setAccess).toHaveBeenLastCalledWith("free");
  });

  it("the properties say COIN and its price", () => {
    render(<ArticleProperties article={{ ...ARTICLE_DETAIL, access: "coin", coin_price: 7 }} />);
    expect(screen.getByText("鯨幣 7 幣")).toBeTruthy();
  });

  it("a section a person chooses; a brief with no sources is on the front page only (D-208)", () => {
    const controls = { ...onSite(), setSection: vi.fn() };
    const view = (patch: Partial<ArticleDetail>) => (
      <ArticleView article={{ ...ARTICLE_DETAIL, state: "PUBLISHED", ...patch }} lang="zh-TW" onLang={vi.fn()} events={[]} onSite={controls} />
    );
    const { rerender } = render(view({ section: null, section_given: false }));
    const box = () => within(screen.getByTestId("section-control"));
    expect(box().getByText(/只出現在首頁「全部」/)).toBeTruthy();
    expect(box().getByRole("option", { name: "自動" })).toBeTruthy();
    fireEvent.change(box().getByRole("combobox", { name: "分類" }), { target: { value: "tw" } });
    expect(controls.setSection).toHaveBeenCalledWith("tw");

    rerender(view({ section: "tw", section_given: true }));
    expect((box().getByRole("combobox", { name: "分類" }) as HTMLSelectElement).value).toBe("tw");
    fireEvent.change(box().getByRole("combobox", { name: "分類" }), { target: { value: "" } });
    expect(controls.setSection).toHaveBeenLastCalledWith(null); // back to what the sources say

    rerender(view({ section: "ai", section_given: false }));
    expect(box().getByRole("option", { name: "自動（AI 科技）" })).toBeTruthy();
  });

  it("a published article comes down only with a reason, and after asking (AD-01)", () => {
    const controls = onSite();
    render(<ArticleView article={{ ...ARTICLE_DETAIL, state: "PUBLISHED" }} lang="zh-TW" onLang={vi.fn()} events={[]} onSite={controls} />);
    const down = within(screen.getByTestId("site-controls")).getByRole("button", { name: "下架" }) as HTMLButtonElement;
    expect(down.disabled).toBe(true);
    fireEvent.change(within(screen.getByTestId("site-controls")).getByRole("textbox"), { target: { value: "用字要改" } });
    fireEvent.click(down);
    expect(controls.unpublish).not.toHaveBeenCalled();
    const ask = screen.getByRole("dialog", { name: "下架這篇文章？" });
    expect(ask.textContent).toContain("說明：用字要改");
    fireEvent.click(within(ask).getByRole("button", { name: "取消" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(down);
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "確定下架" }));
    expect(controls.unpublish).toHaveBeenCalledWith("用字要改");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("one that was taken down says so and can go back up", () => {
    const controls = onSite();
    render(<ArticleView article={{ ...ARTICLE_DETAIL, state: "ARCHIVED" }} lang="zh-TW" onLang={vi.fn()} events={[]} onSite={controls} />);
    expect(screen.getByTestId("site-controls").textContent).toContain("網站上看不到這篇");
    fireEvent.click(screen.getByRole("button", { name: "重新上架" }));
    expect(controls.republish).toHaveBeenCalled();
  });

  it("a published article is changed with what to change (D-045)", () => {
    const controls = onSite();
    render(<ArticleView article={{ ...ARTICLE_DETAIL, state: "PUBLISHED" }} lang="zh-TW" onLang={vi.fn()} events={[]} onSite={controls} />);
    const change = screen.getByRole("button", { name: "修改文章" }) as HTMLButtonElement;
    expect(change.disabled).toBe(true);
    fireEvent.change(within(screen.getByTestId("site-controls")).getByRole("textbox"), { target: { value: "把「狂加」改成「大幅加碼」" } });
    fireEvent.click(change);
    expect(controls.revise).toHaveBeenCalledWith("把「狂加」改成「大幅加碼」");
    expect(controls.unpublish).not.toHaveBeenCalled();
  });

  it("while it is changed, says the site still shows the published version", () => {
    render(<ArticleView article={{ ...ARTICLE_DETAIL, state: "IN_REVIEW" }} lang="zh-TW" onLang={vi.fn()} events={[]} onSite={onSite()} />);
    expect(screen.getByTestId("site-controls").textContent).toContain("網站仍顯示目前發布的版本");
    expect(screen.queryByRole("button", { name: "修改文章" })).toBeNull();
    render(<ArticleView article={{ ...ARTICLE_DETAIL, state: "DRAFT", listed: false }} lang="zh-TW" onLang={vi.fn()} events={[]} onSite={onSite()} />);
    expect(screen.getAllByTestId("site-controls")[1].textContent).toContain("已下架");
  });

  it("a draft that was never published has nothing to take down", () => {
    render(<ArticleView article={{ ...ARTICLE_DETAIL, state: "DRAFT", published_at: null }} lang="zh-TW" onLang={vi.fn()} events={[]} onSite={onSite()} />);
    expect(screen.queryByTestId("site-controls")).toBeNull();
  });
});

describe("an article", () => {
  function show(lang = "zh-TW", onLang = vi.fn()) {
    render(<ArticleView article={ARTICLE_DETAIL} lang={lang} onLang={onLang} events={[event("ARTICLE_PUBLISHED", { langs: ["zh-TW", "en"], url: "/news/zh-TW/articles/x" })]} />);
    return onLang;
  }

  it("shows the version's text with each paragraph's claims marked", () => {
    show();
    const text = screen.getByRole("article");
    expect(text.getAttribute("lang")).toBe("zh-TW");
    expect(within(text).getByRole("heading", { name: "流明市首座社區微電網啟用" })).toBeTruthy();
    const paragraph = within(text).getByText(/串連 1,200 組太陽能板/);
    const marks = within(paragraph).getAllByRole("link");
    expect(marks.map((a) => a.textContent)).toEqual(["[2]", "[1]"]);
    expect(marks[0]!.getAttribute("href")).toBe(`#claim-${PANELS}`);
    expect(screen.getByText("這一版的修改：補上導言")).toBeTruthy();
  });

  it("switches language and version", () => {
    const onLang = show();
    fireEvent.click(screen.getByRole("tab", { name: "en" }));
    expect(onLang).toHaveBeenCalledWith("en");
    cleanup();
    show("en");
    expect(within(screen.getByRole("article")).getByText(/NT\$420 million/)).toBeTruthy();
    const versions = within(screen.getByRole("navigation", { name: "版本" }));
    expect(versions.getByRole("link", { name: /v1/ }).getAttribute("href")).toBe(`/admin/newsroom/articles/${ARTICLE}?version=1`);
    expect(versions.getByRole("link", { name: /v2・已發布/ }).getAttribute("aria-current")).toBe("page");
  });

  it("lists every cited claim with its quote in place", () => {
    show();
    const item = document.getElementById(`claim-${PANELS}`)!;
    expect(within(item).getByText("[2]")).toBeTruthy();
    expect(within(item).getByText("查核通過")).toBeTruthy();
    const mark = item.querySelector("mark")!;
    expect(mark.textContent).toBe("links 1,200 rooftop solar panels");
    expect(mark.parentElement!.textContent).toBe("…The pilot in Harbor District links 1,200 rooftop solar panels and a 4 MWh battery.…");
  });

  it("shows the fact-checks, the distribution, the readers, the public pages and the timeline", () => {
    show();
    const checks = within(document.getElementById("fact-check")!);
    expect(checks.getByText("通過")).toBeTruthy();
    expect(checks.getByText("「1,300 panels」：number 1,300 not in any quote")).toBeTruthy();
    const distribution = within(document.getElementById("distribution")!);
    expect(distribution.getByText("社群貼文（草稿，未發出）")).toBeTruthy();
    expect(distribution.getByText("New: the microgrid.")).toBeTruthy();
    expect(screen.getByText("讀者（共 7 次瀏覽）")).toBeTruthy();
    // the public pages are in the properties box beside the article (AD-07)
    expect(within(screen.getByRole("region", { name: "屬性" })).getByRole("link", { name: "en" }).getAttribute("href")).toBe("/news/en/articles/microgrid-a1b2c3");
    expect(within(document.getElementById("timeline")!).getByText("文章發布")).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "屬性" })).getByRole("link", { name: "Lumen City microgrid" }).getAttribute("href")).toBe(`/admin/newsroom/stories/${STORY}`);
  });
});

const STORY_DETAIL: StoryDetail = {
  id: STORY,
  company_id: C,
  title: "Lumen City microgrid",
  state: "DISCOVERED",
  score: "0.72",
  items: 3,
  sources: 2,
  evidence: 1,
  claims: 1,
  first_seen_at: AT,
  article: null,
  summary: "A pilot.",
  angle: null,
  seed: {},
  leads: [{ title: "A lead", url: "https://news.fixtures.autora.test/a", source: "Lumen City News", published_at: AT }],
  evidence_list: [
    {
      id: "e1",
      title: "Pilot page",
      url: "https://news.fixtures.autora.test/pilot",
      site: "news.fixtures.autora.test",
      retrieved_at: AT,
      chars: 1234,
      truncated: false,
      trust_level: "0.70",
      run_id: null,
    },
  ],
  claim_list: [claim(PANELS, "The microgrid links 1,200 rooftop panels.", "UNVERIFIED")],
  workflow_run_ids: [],
};

describe("a story", () => {
  it("shows its leads, evidence and claims, and can be started", () => {
    const onStart = vi.fn();
    render(<StoryView story={STORY_DETAIL} events={[]} onStart={onStart} starting={false} startError={null} />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Lumen City microgrid");
    expect(screen.getByText("新發現")).toBeTruthy();
    expect(screen.getByRole("link", { name: "A lead" })).toBeTruthy();
    expect(within(document.getElementById("evidence")!).getByText(/1,234 字・信任度 0.7/)).toBeTruthy();
    expect(within(document.getElementById("claims")!).getByText("未查核")).toBeTruthy();
    expect(screen.getByText("還沒有開始製作。")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "開始製作" }));
    expect(onStart).toHaveBeenCalledOnce();
    // the sections are in the shell's sidebar now (AD-02); the way back keeps the company
    expect(screen.getByRole("link", { name: "← 所有題材" }).getAttribute("href")).toBe(`/admin/newsroom/stories?company=${C}`);
  });

  it("cannot be started twice, and says why a start failed", () => {
    render(
      <StoryView
        story={{ ...STORY_DETAIL, state: "IN_PRODUCTION", workflow_run_ids: ["run1"] }}
        events={[event("TASK_READY", { required_role: "researcher" })]}
        onStart={vi.fn()}
        starting={false}
        startError="the company has no active project"
      />,
    );
    expect(screen.queryByRole("button", { name: "開始製作" })).toBeNull();
    expect(screen.getByText("the company has no active project")).toBeTruthy();
    expect(screen.queryByText("還沒有開始製作。")).toBeNull();
  });
});

describe("the lists", () => {
  it("stories: link to each story and its article (the state filter is the table's, AD-05)", () => {
    render(
      <StoriesView stories={[{ ...STORY_DETAIL, state: "PUBLISHED", article: { id: ARTICLE, state: "PUBLISHED", slug: "s", title: "t" } }]} />,
    );
    const row = screen.getByRole("link", { name: "Lumen City microgrid" }).closest("tr")!;
    expect(screen.getByRole("link", { name: "Lumen City microgrid" }).getAttribute("href")).toBe(`/admin/newsroom/stories/${STORY}`);
    expect(within(row).getByRole("link", { name: "文章" }).getAttribute("href")).toBe(`/admin/newsroom/articles/${ARTICLE}`);
    expect(within(row).getByText("72")).toBeTruthy();
    expect(within(row).getByText("3 則來源項目・1 則主張")).toBeTruthy();
  });

  it("articles: state, version, languages, readers", () => {
    render(<ArticlesView articles={[ARTICLE_DETAIL]} />);
    const row = screen.getByRole("link", { name: "流明市首座社區微電網啟用" }).closest("tr")!;
    expect(within(row).getByText("已發布")).toBeTruthy();
    expect(within(row).getByText("（修訂 1 次）")).toBeTruthy();
    expect(within(row).getByText("en / zh-TW")).toBeTruthy();
    expect(within(row).getByText("7")).toBeTruthy();
    cleanup();
    render(<ArticlesView articles={[]} />);
    expect(screen.getByText(/還沒有文章/)).toBeTruthy();
  });
});

describe("sources", () => {
  it("lists them", () => {
    render(
      <SourcesView
        sources={[
          { id: "s1", name: "Lumen City News", kind: "rss", url: "https://x.test/feed", config: {}, trust_level: "0.70", language: "en", status: "active", poll_interval_seconds: 3600, last_polled_at: null, next_poll_at: AT, items: 4 },
        ]}
      />,
    );
    expect(screen.getByText("Lumen City News")).toBeTruthy();
    expect(screen.getByText(/信任度 0.7・4 則項目・尚未讀取/)).toBeTruthy();
  });

  it("adds one of each kind", async () => {
    const onAdd = vi.fn(() => Promise.resolve());
    render(<AddSourceForm onAdd={onAdd} />);
    fireEvent.change(screen.getByLabelText("名稱"), { target: { value: "Watchlist" } });
    fireEvent.change(screen.getByLabelText("種類"), { target: { value: "url_list" } });
    fireEvent.change(screen.getByLabelText(/網址（空白或換行分隔）/), { target: { value: "https://a.test/1\nhttps://a.test/2" } });
    fireEvent.submit(screen.getByRole("button", { name: "新增來源" }).closest("form")!);
    await vi.waitFor(() => expect(onAdd).toHaveBeenCalledOnce());
    expect(onAdd.mock.calls[0]).toEqual([
      expect.objectContaining({ name: "Watchlist", kind: "url_list", url: null, config: { urls: ["https://a.test/1", "https://a.test/2"] } }),
    ]);
  });

  it("the exchange's announcements by stock code, GDELT by a query (D-169)", () => {
    expect(sourceConfig("twse_announcements", " 2330  2317\n")).toEqual({ codes: ["2330", "2317"] });
    expect(sourceConfig("gdelt", " Nvidia sourcelang:english ")).toEqual({ query: "Nvidia sourcelang:english" });
    expect(sourceConfig("rss", "https://x.test/feed")).toEqual({});
  });

  it("shows why a source was refused", async () => {
    render(<AddSourceForm onAdd={() => Promise.reject(new Error("422 an rss source needs an http(s) feed url"))} />);
    fireEvent.change(screen.getByLabelText("名稱"), { target: { value: "x" } });
    fireEvent.change(screen.getByLabelText("Feed 網址"), { target: { value: "not a url" } });
    fireEvent.submit(screen.getByRole("button", { name: "新增來源" }).closest("form")!);
    expect(await screen.findByText("422 an rss source needs an http(s) feed url")).toBeTruthy();
  });
});

describe("the data", () => {
  function client() {
    const requests: Request[] = [];
    const api = createApiClient({
      baseUrl: "http://api",
      getToken: () => "t",
      fetch: (async (r: Request) => {
        requests.push(r);
        return new Response(JSON.stringify({ items: [], next_after: 0, has_more: false }), { headers: { "Content-Type": "application/json" } });
      }) as unknown as typeof fetch,
    });
    return { api, requests };
  }

  it("asks for the version, the state and the workflow's events", async () => {
    const { api, requests } = client();
    await articleQuery(ARTICLE, 2, api).queryFn!({} as never);
    await storiesQuery(C, "PUBLISHED", {}, api).queryFn!({} as never);
    await storiesQuery(C, null, { q: "台股", cursor: "next", sort: "title" }, api).queryFn!({} as never);
    await workflowEventsQuery(C, "run1", api).queryFn!({} as never);
    expect(requests.map((r) => r.url)).toEqual([
      `http://api/api/articles/${ARTICLE}?version=2`,
      `http://api/api/companies/${C}/stories?state=PUBLISHED&limit=50`,
      `http://api/api/companies/${C}/stories?limit=50&cursor=next&q=${encodeURIComponent("台股")}&sort=title`,
      `http://api/api/events?company_id=${C}&correlation_id=run1&limit=500`,
    ]);
  });

  it("newsroom events refresh the newsroom pages; a workflow's events its timeline", () => {
    expect(eventToQueryKeys({ ...event("ARTICLE_PUBLISHED", {}), run_id: null, task_id: null })).toEqual([["newsroom"]]);
    expect(eventToQueryKeys({ ...event("WORKFLOW_RUN_EXTENDED", {}), run_id: null, task_id: null })).toEqual([
      queryKeys.workflowEvents(C, "run1"),
    ]);
  });
});
