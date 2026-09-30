// @vitest-environment jsdom
// D-142: an article's cover on the site (with its credit) and where a person decides.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { API_URL } from "@/config";
import { CoverPanel, type CoverView } from "@/features/newsroom/CoverPanel";

import { CoverFigure, coverSrc } from "./Cover";

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

  it("says when there is none", () => {
    withClient(<CoverPanel articleId="a1" cover={null} />);
    expect(screen.getByText(/沒有找到合適的圖片/)).toBeTruthy();
  });
});
