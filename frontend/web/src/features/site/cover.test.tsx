// @vitest-environment jsdom
// D-142: an article's cover on the site (with its credit) and where a person decides.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createApiClient } from "@/api/client";
import * as queries from "@/api/queries";
import { API_URL } from "@/config";
import { CoverPanel, type CoverView } from "@/features/newsroom/CoverPanel";

import { CoverFigure, coverSrc } from "./Cover";

// the panel's 重找 is checked against a stand-in; the request itself against the real one
vi.mock("@/api/queries", async (actual) => ({
  ...(await actual<typeof import("@/api/queries")>()),
  searchCover: vi.fn(async () => ({})),
}));

afterEach(cleanup);

const COVER: CoverView = {
  state: "active",
  url: "https://img.example.test/covers/s1/pixabay-42.webp",
  width: 1200,
  height: 630,
  bytes: 154_000,
  alt: { "zh-TW": "一片矽晶圓", en: "A silicon wafer" },
  credit: "someone",
  library: "Pixabay",
  page_url: "https://pixabay.com/photos/wafer-42/",
  query: "semiconductor wafer",
  others: 5,
};

function withClient(node: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>);
}

describe("the cover on the site", () => {
  it("loads a bucket's address as it is, and an API path from the API", () => {
    expect(coverSrc(COVER.url)).toBe(COVER.url);
    expect(coverSrc("/api/public/covers/s1/x.webp")).toBe(`${API_URL}/api/public/covers/s1/x.webp`);
  });

  it("shows the photo at 1200x630 with what it shows, and credits its photographer", () => {
    render(<CoverFigure cover={{ ...COVER, alt: "一片矽晶圓" }} lang="zh-TW" />);
    const img = screen.getByRole("img", { name: "一片矽晶圓" });
    expect([img.getAttribute("width"), img.getAttribute("height")]).toEqual(["1200", "630"]);
    const credit = screen.getByRole("link", { name: "someone／Pixabay" });
    expect(credit.getAttribute("href")).toBe(COVER.page_url);
    expect(screen.getByTestId("article-cover").textContent).toContain("圖片：");
  });
});

describe("the cover where a person decides", () => {
  it("shows it with 換一張 and 拿掉", () => {
    withClient(<CoverPanel articleId="a1" cover={COVER} />);
    expect(screen.getByRole("img", { name: "一片矽晶圓" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "換一張" }).hasAttribute("disabled")).toBe(false);
    expect(screen.getByRole("button", { name: "拿掉" })).toBeTruthy();
    expect(screen.getByText(/154 KB/)).toBeTruthy();
  });

  it("cannot swap when the search found nothing else", () => {
    withClient(<CoverPanel articleId="a1" cover={{ ...COVER, others: 0 }} />);
    expect(screen.getByRole("button", { name: "換一張" }).hasAttribute("disabled")).toBe(true);
  });

  it("says when it was taken off, and offers to put one back", () => {
    withClient(<CoverPanel articleId="a1" cover={{ ...COVER, state: "removed" }} />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText(/首圖已拿掉/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "放回一張" })).toBeTruthy();
  });

  it("says when there is none, and a person can still look for one (D-233)", () => {
    withClient(<CoverPanel articleId="a1" cover={null} />);
    expect(screen.getByText(/沒有找到合適的圖片/)).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "用自己的話找首圖" })).toBeTruthy();
  });

  it("重找 looks again with the person's own words (D-233)", async () => {
    withClient(<CoverPanel articleId="a1" cover={COVER} />);
    const again = screen.getByRole("button", { name: "重找" }) as HTMLButtonElement;
    expect(again.disabled).toBe(true);
    fireEvent.change(screen.getByRole("textbox", { name: "用自己的話找首圖" }), { target: { value: " 晶圓廠 " } });
    expect(again.disabled).toBe(false);
    fireEvent.click(again);
    await waitFor(() => expect(queries.searchCover).toHaveBeenCalledWith("a1", "晶圓廠"));
  });

  it("the request goes where the API expects it", async () => {
    const seen: string[] = [];
    const api = createApiClient({
      baseUrl: "http://api",
      fetch: (async (r: Request) => {
        seen.push(`${r.method} ${r.url} ${JSON.stringify(await r.json())}`);
        return Response.json(COVER);
      }) as typeof fetch,
    });
    const { searchCover } = await vi.importActual<typeof import("@/api/queries")>("@/api/queries");
    await searchCover("a1", "wafer", api);
    expect(seen).toEqual(['POST http://api/api/articles/a1/cover/search {"query":"wafer"}']);
  });
});

describe("a generated cover (D-145)", () => {
  it("says it is an AI-generated illustration, with no library link", () => {
    const generated = { ...COVER, alt: "儀表板", credit: "AI 生成示意圖", library: "", page_url: "" };
    render(<CoverFigure cover={generated} lang="zh-TW" />);
    expect(screen.getByTestId("article-cover").textContent).toContain("圖片：AI 生成示意圖");
    expect(screen.queryByRole("link")).toBeNull();
    cleanup();
    render(<CoverFigure cover={generated} lang="en" />);
    expect(screen.getByTestId("article-cover").textContent).toContain("AI-generated illustration");
  });
});
