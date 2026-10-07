// @vitest-environment jsdom
// AD-07: a thing's history beside it, in words — and a row opened beside its list, on the address.
import { act, cleanup, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe as group, expect, it, vi } from "vitest";

let search = new URLSearchParams("company=c1");
const push = vi.fn((href: string) => (search = new URLSearchParams(href.split("?")[1] ?? "")));
const replace = vi.fn((href: string) => (search = new URLSearchParams(href.split("?")[1] ?? "")));
const back = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace, back }),
  usePathname: () => "/admin/newsroom/articles",
  useSearchParams: () => search,
}));

import type { ActivityEntry } from "@/api/queries";
import { usePeek } from "@/features/admin-ui/usePeek";
import { ArticlesView } from "@/features/newsroom/ArticlesView";

import { ActivityList, describe } from "./ActivityTimeline";

const AT = "2026-10-07T07:00:00Z";
const entry = (over: Partial<ActivityEntry>): ActivityEntry => ({
  at: AT,
  kind: "state",
  subject: "article",
  subject_id: "a1",
  actor: { kind: "human", id: "operator" },
  actor_label: "操作者權杖",
  from_state: null,
  to_state: null,
  reason: null,
  route: null,
  action: null,
  status: null,
  ...over,
});

beforeEach(() => {
  search = new URLSearchParams("company=c1");
  push.mockClear();
  replace.mockClear();
  back.mockClear();
});
afterEach(cleanup);

group("what an entry says", () => {
  it("a state change, an approval asked and decided, a person's change and a refused one", () => {
    expect(describe(entry({ from_state: "DRAFT", to_state: "IN_REVIEW" }), "article")).toBe("草稿 → 待核准");
    expect(describe(entry({ kind: "asked", subject: "approval", to_state: "PENDING" }), "article")).toBe("審批：提出審批");
    expect(describe(entry({ subject: "approval", from_state: "PENDING", to_state: "APPROVED" }), "article")).toBe("審批：待審批 → 已核准");
    expect(describe(entry({ kind: "action", route: "/api/articles/{article_id}/unpublish", status: 200 }), "article")).toBe("下架");
    expect(describe(entry({ kind: "action", route: "/api/articles/{article_id}/unpublish", status: 409 }), "article")).toBe("下架（被拒 409）");
    expect(describe(entry({ kind: "action", route: "/api/new/thing", action: "new_thing", status: 200 }), "article")).toBe("new_thing");
    expect(describe(entry({ subject: "story", from_state: "DISCOVERED", to_state: "SELECTED" }), "story")).toBe("新發現 → 已選定");
  });
});

group("the 活動 box", () => {
  it("shows everything, or only state changes, or only what people did", () => {
    const entries = [
      entry({ kind: "action", route: "/api/articles/{article_id}/access", status: 200, reason: null }),
      entry({ from_state: "DRAFT", to_state: "IN_REVIEW", actor_label: "水野亞美", reason: "改好了" }),
    ];
    let tab: "all" | "state" | "action" = "all";
    const { rerender } = render(<ActivityList entries={entries} error={null} tab={tab} onTab={(t) => (tab = t)} own="article" />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("改好了")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "人的操作" }));
    rerender(<ActivityList entries={entries} error={null} tab={tab} onTab={(t) => (tab = t)} own="article" />);
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual([expect.stringContaining("閱讀權限")]);
    rerender(<ActivityList entries={entries} error={null} tab="state" onTab={vi.fn()} own="article" />);
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual([expect.stringContaining("水野亞美草稿 → 待核准")]);
    rerender(<ActivityList entries={[]} error={null} tab="all" onTab={vi.fn()} own="article" />);
    expect(screen.getByText("沒有紀錄。")).toBeTruthy();
  });
});

group("a row beside its list", () => {
  it("a plain click on a title opens it on the address; back or close shuts it", () => {
    const { result, rerender } = renderHook(() => usePeek());
    render(
      <ArticlesView
        articles={[
          {
            id: "a1",
            story_id: "s1",
            title: "台股創新高",
            state: "PUBLISHED",
            slug: "x",
            version: 1,
            langs: ["zh-TW"],
            revision_count: 0,
            published_at: AT,
            listed: true,
            access: "free",
            revised_at: null,
            updated_at: AT,
            views: 3,
          },
        ]}
        onPeek={(id) => result.current.open(id)}
      />,
    );
    const link = screen.getByRole("link", { name: "台股創新高" });
    expect(link.getAttribute("href")).toBe("/admin/newsroom/articles/a1"); // the full page, for a new tab
    fireEvent.click(link, { metaKey: true });
    expect(push).not.toHaveBeenCalled();
    fireEvent.click(link);
    expect(push).toHaveBeenCalledWith("/admin/newsroom/articles?company=c1&peek=a1", { scroll: false });
    rerender();
    expect(result.current.peek).toBe("a1");
    act(() => result.current.close());
    expect(back).toHaveBeenCalled(); // opened here: closing is going back

    // came with the address (a link someone sent): closing takes it off, never leaves the page
    search = new URLSearchParams("company=c1&peek=a1");
    const fresh = renderHook(() => usePeek());
    act(() => fresh.result.current.close());
    expect(replace).toHaveBeenCalledWith("/admin/newsroom/articles?company=c1", { scroll: false });
  });
});
