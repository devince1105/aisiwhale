// @vitest-environment jsdom
// D-047: the public site's sections, pages, next article along, reading tools and light/dark.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchArticlePage, fetchArticles, fetchFigure, type PublicArticle, type PublicArticleSummary } from "./api";
import { ArticleList, listHref } from "./ArticleList";
import { ArticleView } from "./ArticleView";
import { StocksNamed } from "./StocksNamed";
import { slots } from "./Pagination";
import { currentSection, SectionNav } from "./SectionNav";
import { SiteName } from "./SiteName";
import { pickVoice } from "./ReadingTools";
import { isFilter, isSection, sectionsOf, topicOf } from "./i18n";
import { applyTheme, currentTheme, THEME_KEY, THEME_SCRIPT } from "./theme";
import { ThemeToggle } from "./ThemeToggle";

const nav = vi.hoisted(() => ({ pathname: "/news/zh-TW", search: "" }));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useSearchParams: () => new URLSearchParams(nav.search),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function summary(n: number, over: Partial<PublicArticleSummary> = {}): PublicArticleSummary {
  return {
    article_id: `a${n}`,
    lang: "zh-TW",
    slug: `s${n}`,
    stocks: [],
    path: `/news/zh-TW/articles/s${n}`,
    title: `第 ${n} 篇`,
    summary: `摘要 ${n}`,
    published_at: "2026-09-19T04:00:00Z",
    access: "free",
    section: "holdings",
    ...over,
  };
}

const ARTICLE: PublicArticle = {
  ...summary(1),
  company: "艾矽鯨",
  company_id: "c",
  company_slug: "autora-finance",
  locked: false,
  blocks: [{ type: "paragraph", text: "段永平第二季出清台積電。" }],
  sources: [],
  stocks: [],
  langs: { "zh-TW": "/news/zh-TW/articles/s1" },
  newer: { title: "較新的那篇", path: "/news/zh-TW/articles/s0" },
  older: null,
};

describe("the front page", () => {
  it("leads with the newest story, then lists the rest", () => {
    render(<ArticleList articles={[summary(1), summary(2), summary(3)]} lang="zh-TW" />);
    const headlines = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headlines).toEqual(["第 1 篇", "第 2 篇", "第 3 篇"]);
    expect(screen.getByRole("heading", { level: 2, name: "第 1 篇" }).closest("article")).toBeTruthy();
    expect(screen.getAllByText("大戶持股")).toHaveLength(3); // each story's label
  });

  it("has a tab per section under the masthead, the current one marked", () => {
    nav.pathname = "/news/zh-TW";
    nav.search = "section=ai";
    render(<SectionNav lang="zh-TW" />);
    const tabs = within(screen.getByRole("navigation", { name: "報導分類" })).getAllByRole("link");
    expect(tabs.map((t) => [t.textContent, t.getAttribute("href")])).toEqual([
      ["全部", "/news/zh-TW"],
      ["AI 科技", "/news/zh-TW?section=ai"],
      ["台股", "/news/zh-TW?section=tw"],
      ["美股", "/news/zh-TW?section=us"],
      ["加密貨幣", "/news/zh-TW?section=crypto"],
      ["黃金", "/news/zh-TW?section=gold"],
      ["期貨", "/news/zh-TW?section=commodities"],
      ["外匯", "/news/zh-TW?section=fx"],
      ["機構觀點", "/news/zh-TW?section=institutions"],
      ["持股觀察", "/news/zh-TW?section=watch"],
      ["觀察清單", "/news/zh-TW/watchlist"],
    ]);
    expect(tabs.filter((t) => t.getAttribute("aria-current") === "page").map((t) => t.textContent)).toEqual(["AI 科技"]);
  });

  it("marks no section away from the front page, and all on it without one", () => {
    expect(currentSection("zh-TW", "/news/zh-TW/articles/x", "ai")).toBeNull();
    expect(currentSection("zh-TW", "/news/zh-TW", null)).toBe("all");
    expect(currentSection("en", "/news/en", "nft")).toBe("all");
    // a section inside 持股觀察 lights the tab it is under
    expect(currentSection("zh-TW", "/news/zh-TW", "figures")).toBe("watch");
    expect(currentSection("zh-TW", "/news/zh-TW", "watch")).toBe("watch");
  });

  it("numbers the pages, each a link in the same section, with the ends dimmed", () => {
    const { rerender } = render(<ArticleList articles={[summary(1)]} lang="zh-TW" section="tw" pages={20} />);
    const nav = within(screen.getByRole("navigation", { name: "分頁" }));
    expect(nav.getByRole("link", { name: "下一頁" }).getAttribute("href")).toBe("/news/zh-TW?section=tw&page=2");
    expect(nav.getByRole("link", { name: "最後一頁" }).getAttribute("href")).toBe("/news/zh-TW?section=tw&page=20");
    expect(nav.queryByRole("link", { name: "上一頁" })).toBeNull(); // nowhere to go: not a link
    expect(nav.getByLabelText("上一頁").getAttribute("aria-disabled")).toBe("true");
    expect(nav.getByText("第 1／20 頁")).toBeTruthy();

    rerender(<ArticleList articles={[summary(51)]} lang="zh-TW" section="tw" page={6} pages={20} />);
    const again = within(screen.getByRole("navigation", { name: "分頁" }));
    expect(again.getByRole("link", { name: "上一頁" }).getAttribute("href")).toBe("/news/zh-TW?section=tw&page=5");
    expect(again.getByRole("link", { name: "第一頁" }).getAttribute("href")).toBe("/news/zh-TW?section=tw");
    expect(document.querySelector("[aria-current=page]")?.textContent).toBe("6");
    expect(
      again.getAllByRole("link").map((a) => a.textContent).filter((t) => /^\d+$/.test(t ?? "")),
    ).toEqual(["1", "4", "5", "7", "8", "20"]);
    // a wide screen's "…" before 4 and 20; a phone's, one neighbour each side, before 5 and 20
    expect(slots(6, 20).filter((x) => x.narrow).map((x) => [x.page, x.gap.narrow])).toEqual([
      [1, false],
      [5, true],
      [6, false],
      [7, false],
      [20, true],
    ]);
    expect(slots(3, 5).every((x) => x.wide && !x.gap.wide)).toBe(true); // few pages: all of them
    expect(document.querySelector("article")).toBeNull(); // only the first page leads with one
    cleanup();
    render(<ArticleList articles={[summary(1)]} lang="en" pages={1} />);
    expect(screen.queryByRole("navigation", { name: "Pages" })).toBeNull(); // one page: nothing to page through
  });

  it("under a story, the stocks it names, each to its chart on the watchlist page (D-078)", () => {
    render(
      <ArticleList
        articles={[summary(1, { stocks: [{ key: "us:NVDA", symbol: "NVDA", name: "輝達" }] }), summary(2)]}
        lang="zh-TW"
      />,
    );
    const named = screen.getAllByTestId("stocks-named");
    expect(named).toHaveLength(1); // the story that names none has no row
    expect(within(named[0]).getByRole("link").getAttribute("href")).toBe("/news/zh-TW/watchlist?s=us%3ANVDA");
    expect(named[0].textContent).toBe("輝達NVDA"); // in a list: no label before them
  });

  it("a crypto, gold, futures or FX story's figures are 相關行情 (D-079)", () => {
    render(<StocksNamed stocks={[{ key: "btc", symbol: "BTC", name: "比特幣" }, { key: "jpytwd", symbol: "JPYTWD", name: "日圓" }]} lang="zh-TW" />);
    const named = within(screen.getByRole("navigation", { name: "相關行情" }));
    expect(named.getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      ["比特幣BTC", "/news/zh-TW/watchlist?s=btc"],
      ["日圓JPY/TWD", "/news/zh-TW/watchlist?s=jpytwd"],
    ]);
  });

  it("marks members-only stories, and knows its sections", () => {
    render(<ArticleList articles={[summary(1, { access: "members", section: null })]} lang="en" />);
    expect(screen.getByText("Member")).toBeTruthy();
    expect(listHref("en", null, 3)).toBe("/news/en?page=3");
    expect(isSection("ai") && !isSection("nft") && !isSection(undefined)).toBe(true);
  });

  it("asks the API for a section and a page", async () => {
    const listed = vi.fn<typeof fetch>(() =>
      Promise.resolve(new Response("[]", { headers: { "Content-Type": "application/json" } })),
    );
    await fetchArticles("zh-TW", { baseUrl: "http://api", fetch: listed, section: "us", limit: 11, offset: 10 });
    expect((listed.mock.calls[0]![0] as Request).url).toBe(
      "http://api/api/public/articles?lang=zh-TW&section=us&limit=11&offset=10",
    );
    // how many in all comes in a header (D-065); an API that does not say: what the page reaches
    const counted = vi.fn<typeof fetch>(() =>
      Promise.resolve(
        new Response("[]", { headers: { "Content-Type": "application/json", "X-Total-Count": "57" } }),
      ),
    );
    expect((await fetchArticlePage("zh-TW", { baseUrl: "http://api", fetch: counted })).total).toBe(57);
    expect((await fetchArticlePage("zh-TW", { baseUrl: "http://api", fetch: listed, offset: 10 })).total).toBe(10);
  });
});

describe("the article page", () => {
  it("says where it is, and leads on to the next article along", () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(null, { status: 204 }))));
    render(<ArticleView article={ARTICLE} lang="zh-TW" />);
    const crumbs = within(screen.getByRole("navigation", { name: "breadcrumb" })).getAllByRole("link");
    expect(crumbs.map((a) => a.getAttribute("href"))).toEqual(["/news/zh-TW", "/news/zh-TW?section=watch", "/news/zh-TW?section=holdings"]);
    const newer = screen.getByRole("link", { name: /較新一篇/ });
    expect(newer.getAttribute("href")).toBe("/news/zh-TW/articles/s0");
    expect(newer.textContent).toContain("較新的那篇");
    expect(screen.queryByText(/較舊一篇/)).toBeNull();
    expect(screen.getByRole("button", { name: /列印/ })).toBeTruthy();
  });

  it("reads itself aloud, a paragraph at a time, where the browser can", () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(null, { status: 204 }))));
    const spoken: { text: string; lang: string }[] = [];
    const synth = { speak: vi.fn((u) => spoken.push({ text: u.text, lang: u.lang })), cancel: vi.fn(), getVoices: () => [] };
    vi.stubGlobal("speechSynthesis", synth);
    vi.stubGlobal(
      "SpeechSynthesisUtterance",
      class {
        lang = "";
        constructor(public text: string) {}
      },
    );
    render(<ArticleView article={ARTICLE} lang="zh-TW" />);
    fireEvent.click(screen.getByRole("button", { name: /朗讀/ }));
    expect(spoken.map((s) => s.text)).toEqual(["第 1 篇", "摘要 1", "段永平第二季出清台積電。"]);
    expect(spoken.every((s) => s.lang === "zh-TW")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /停止朗讀/ }));
    expect(synth.cancel).toHaveBeenCalled();
  });
});

describe("light and dark", () => {
  it("follows the system until the reader picks, and keeps the pick", () => {
    const root = document.createElement("div");
    expect(currentTheme(root, true)).toBe("dark");
    const saved = new Map<string, string>();
    applyTheme(root, "light", { setItem: (k, v) => void saved.set(k, v) });
    expect(root.getAttribute("data-theme")).toBe("light");
    expect(currentTheme(root, true)).toBe("light");
    expect(saved.get(THEME_KEY)).toBe("light");
    applyTheme(root, "dark", { setItem: () => { throw new Error("blocked"); } }); // still changes
    expect(root.getAttribute("data-theme")).toBe("dark");
  });

  it("the page-load script puts the saved pick on <html> for the site, and survives no storage", () => {
    const html = document.createElement("html");
    const run = (storage: unknown) => new Function("localStorage", "document", THEME_SCRIPT)(storage, { documentElement: html });
    run({ getItem: () => "sepia" });
    expect(html.hasAttribute("data-site-theme")).toBe(false);
    run({ getItem: () => "dark" });
    expect(html.getAttribute("data-site-theme")).toBe("dark");
    expect(() => run(undefined)).not.toThrow();
  });

  it("the button switches the site and says what it will do", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    const site = document.createElement("div");
    site.setAttribute("data-site", "");
    document.body.appendChild(site);
    render(<ThemeToggle lang="zh-TW" />, { container: site });
    fireEvent.click(screen.getByRole("button", { name: "切換為深色模式" }));
    expect(site.getAttribute("data-theme")).toBe("dark");
    expect(screen.getByRole("button", { name: "切換為淺色模式" })).toBeTruthy();
    site.remove();
  });
});

describe("a site reached without the page-load script", () => {
  it("the button puts the saved pick back", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    window.localStorage.setItem(THEME_KEY, "dark");
    const site = document.createElement("div");
    site.setAttribute("data-site", "");
    document.body.appendChild(site);
    render(<ThemeToggle lang="en" />, { container: site });
    expect(site.getAttribute("data-theme")).toBe("dark");
    expect(screen.getByRole("button", { name: "Switch to light mode" })).toBeTruthy();
    window.localStorage.removeItem(THEME_KEY);
    site.remove();
  });
});

describe("the voice that reads aloud", () => {
  const v = (name: string, lang: string) => ({ name, lang });
  const MAC = [
    v("Eddy (Chinese (Taiwan))", "zh-TW"),
    v("Flo (Chinese (Taiwan))", "zh-TW"),
    v("Tingting", "zh-CN"),
    v("Meijia", "zh-TW"),
    v("Samantha", "en-US"),
    v("Albert", "en-US"),
  ];

  it("is a real Taiwanese voice, not a novelty one that happens to come first", () => {
    expect(pickVoice(MAC, "zh-TW")?.name).toBe("Meijia");
    expect(pickVoice(MAC, "en")?.name).toBe("Samantha");
  });

  it("prefers a neural voice when the system has one", () => {
    const edge = [v("Microsoft Zhiwei - Chinese (Taiwan)", "zh-TW"), v("Microsoft HsiaoChen Online (Natural) - Chinese (Taiwan)", "zh-TW")];
    expect(pickVoice(edge, "zh-TW")?.name).toContain("HsiaoChen Online");
    expect(pickVoice([...MAC, v("Meijia (Enhanced)", "zh-TW")], "zh-TW")?.name).toBe("Meijia (Enhanced)");
    expect(pickVoice([v("Google 國語（臺灣）", "zh-TW"), ...MAC], "zh-TW")?.name).toBe("Google 國語（臺灣）");
  });

  it("never a Mainland or Hong Kong voice for Taiwanese text, and nothing when there is none", () => {
    expect(pickVoice([v("Tingting", "zh-CN"), v("Sinji", "zh-HK")], "zh-TW")).toBeNull();
    expect(pickVoice([v("Eddy (Chinese (Taiwan))", "zh_TW")], "zh-TW")?.name).toBe("Eddy (Chinese (Taiwan))"); // better than nothing
  });
});

describe("the site's name on the masthead", () => {
  it("draws 艾 as a rose heart and still reads 艾矽鯨; in English, the name in the same serif", () => {
    const { container } = render(<SiteName lang="zh-TW" />);
    expect(container.textContent).toBe("艾矽鯨");
    const heart = container.querySelector("svg")!;
    expect(heart.getAttribute("aria-hidden")).toBe("true");
    expect(heart.getAttribute("class")).toContain("text-rose-600");
    cleanup();
    const en = render(<SiteName lang="en" />);
    expect(en.container.textContent).toBe("AiSiWhale");
    expect(en.container.querySelector("svg")).toBeNull();
    expect(en.container.querySelector(".font-brand")?.textContent).toBe("AiSiWhale");
  });
});

describe("持股觀察: two sections under one tab, told apart by tags (D-050)", () => {
  it("has a tag for each inside it, the current one marked; other tabs have none", () => {
    render(<ArticleList articles={[summary(1)]} lang="zh-TW" section="figures" />);
    const tags = within(screen.getByRole("navigation", { name: "持股觀察的分類" })).getAllByRole("link");
    expect(tags.map((t) => [t.textContent, t.getAttribute("href"), t.getAttribute("aria-current")])).toEqual([
      ["全部", "/news/zh-TW?section=watch", null],
      ["大戶持股", "/news/zh-TW?section=holdings", null],
      ["名人持股", "/news/zh-TW?section=figures", "page"],
    ]);
    cleanup();
    render(<ArticleList articles={[summary(1)]} lang="zh-TW" section="ai" />);
    expect(screen.queryByRole("navigation", { name: "持股觀察的分類" })).toBeNull();
  });

  it("黃金, 期貨 and 外匯 are tabs of their own, with no tags inside (D-067)", () => {
    render(<ArticleList articles={[summary(1)]} lang="zh-TW" section="gold" />);
    expect(screen.queryByRole("navigation", { name: /的分類$/ })).toBeNull();
    expect(sectionsOf("commodities")).toEqual(["commodities"]);
    expect(topicOf("fx")).toBe("fx");
  });

  it("asks for both sections at once, and knows which tab a section is under", () => {
    expect(sectionsOf("watch")).toEqual(["holdings", "figures"]);
    expect(sectionsOf("figures")).toEqual(["figures"]);
    expect(topicOf("holdings")).toBe("watch");
    expect(isFilter("watch") && isFilter("ai") && !isFilter("nft")).toBe(true);
  });

  it("an article inside it has the tab and its section in the breadcrumb", () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(null, { status: 204 }))));
    render(<ArticleView article={ARTICLE} lang="zh-TW" />);
    const crumbs = within(screen.getByRole("navigation", { name: "breadcrumb" })).getAllByRole("link");
    expect(crumbs.map((a) => a.textContent)).toEqual(["艾矽鯨", "持股觀察", "大戶持股"]);
  });
});

describe("外匯: the bank's rates a click away (D-072)", () => {
  it("links to Bank of Taiwan's posted rates on its first page, and nowhere else", () => {
    render(<ArticleList articles={[summary(1)]} lang="zh-TW" section="fx" />);
    expect(screen.getByTestId("bank-rates").getAttribute("href")).toBe("https://rate.bot.com.tw/xrt?Lang=zh-TW");
    expect(screen.getByText("臺灣銀行牌告匯率 ↗")).toBeTruthy();
    cleanup();
    render(<ArticleList articles={[summary(11)]} lang="zh-TW" section="fx" page={2} pages={2} />);
    expect(screen.queryByTestId("bank-rates")).toBeNull();
    cleanup();
    render(<ArticleList articles={[summary(1)]} lang="zh-TW" section="gold" />);
    expect(screen.queryByTestId("bank-rates")).toBeNull();
  });

  it("a watchlist figure's chart is asked of the API, and a failure is no chart", async () => {
    const answered = vi.fn<typeof fetch>(() =>
      Promise.resolve(new Response(JSON.stringify({ key: "jpytwd", bars: [] }), { headers: { "Content-Type": "application/json" } })),
    );
    expect((await fetchFigure("jpytwd", { baseUrl: "http://api", fetch: answered }))?.key).toBe("jpytwd");
    expect((answered.mock.calls[0]![0] as Request).url).toBe("http://api/api/public/figures/jpytwd");
    const down = vi.fn<typeof fetch>(() => Promise.reject(new Error("down")));
    expect(await fetchFigure("jpytwd", { baseUrl: "http://api", fetch: down })).toBeNull();
  });
});
