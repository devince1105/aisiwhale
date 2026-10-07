// @vitest-environment jsdom
// D-034: the pages a payment provider reviews before it lets the site take money — who runs it,
// what is sold on what terms, and what happens after paying.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "@/app/(site)/news/[lang]/membership/return/route";

import { LANGS } from "./i18n";
import { LEGAL_PAGES, legalDoc } from "./legal";
import { LegalView } from "./LegalView";
import { operator } from "./operator";
import { PaymentDone } from "./PaymentDone";
import { yearlySaving } from "./PlanPicker";
import { SiteFooter } from "./SiteFooter";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const PERSON = operator({
  SITE_OPERATOR: "Nanguado",
  SITE_OPERATOR_OWNER: "王小明",
  SITE_CONTACT_EMAIL: "service@nanguado.com",
  SITE_CONTACT_PHONE: "02-1234-5678",
});

describe("who runs the site", () => {
  it("defaults to the brand and its address, and leaves a person's details to the environment", () => {
    expect(operator({})).toEqual({ brand: "Nanguado", owner: null, email: "service@aisiwhale.com", phone: null });
    expect(operator({ SITE_OPERATOR_OWNER: "  ", SITE_CONTACT_PHONE: "" }).owner).toBeNull();
  });

  it("is on every page's footer: the plans and policies (D-161) and 聯絡我們, no operator's details (D-165)", () => {
    render(<SiteFooter lang="zh-TW" />);
    const footer = screen.getByTestId("site-footer");
    expect(footer.textContent).not.toContain("經營者");
    expect(footer.textContent).not.toContain("@");
    const hrefs = Array.from(footer.querySelectorAll("nav a")).map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual([
      "/news/zh-TW/pricing",
      "/news/zh-TW/terms",
      "/news/zh-TW/privacy",
      "/news/zh-TW/refund",
      "/news/zh-TW/contact",
    ]);
  });

  it("says once, for every page, what the site's figures are and are not (D-097)", () => {
    render(<SiteFooter lang="zh-TW" />);
    const said = screen.getByTestId("site-disclaimer").textContent!;
    expect(said.startsWith("免責聲明：")).toBe(true);
    for (const part of ["AI 新聞室", "公開申報", "Finnhub", "AI 判讀", "不構成投資建議"]) expect(said).toContain(part);
    // the footer's last row, a warning strip across it (D-099)
    const strip = screen.getByTestId("site-disclaimer");
    expect(screen.getByTestId("site-footer").lastElementChild).toBe(strip);
    expect(strip.className).toContain("bg-alert");
    expect(strip.getAttribute("role")).toBe("note");
  });

  it("in English too, the footer says Contact us; the operator's details stay with the policies (D-165)", () => {
    render(<SiteFooter lang="en" />);
    const footer = screen.getByTestId("site-footer");
    expect(footer.textContent).not.toContain("Operated by");
    expect(screen.getByRole("link", { name: "Contact us" }).getAttribute("href")).toBe("/news/en/contact");
    // what the policies name when nothing is configured: the site's own inbox, no phone
    expect(operator({})).toEqual({ brand: "Nanguado", owner: null, email: "service@aisiwhale.com", phone: null });
  });
});

describe("the policies", () => {
  it.each(LEGAL_PAGES.flatMap((page) => LANGS.map((lang) => [page, lang] as const)))(
    "%s in %s names the operator's address and renders",
    (page, lang) => {
      const doc = legalDoc(page, lang, PERSON);
      expect(doc.sections.length).toBeGreaterThan(2);
      render(<LegalView doc={doc} lang={lang} />);
      expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(doc.title);
      expect(document.body.textContent).toContain("service@nanguado.com");
    },
  );

  it("name no price, so a new price cannot make them wrong", () => {
    for (const page of LEGAL_PAGES) {
      for (const lang of LANGS) {
        expect(JSON.stringify(legalDoc(page, lang, PERSON))).not.toMatch(/NT\$|\d+ ?元/);
      }
    }
  });

  it("promise what the code does: one payment, nothing renewed, 7 days to change your mind", () => {
    const text = JSON.stringify(legalDoc("terms", "zh-TW", PERSON)) + JSON.stringify(legalDoc("refund", "zh-TW", PERSON));
    expect(text).toContain("不會自動續約或自動扣款");
    expect(text).toContain("7 天內");
  });

  it("say what Whale Coins are and are not, in both languages, dated the day they were added (P3-C-3)", () => {
    const zh = legalDoc("terms", "zh-TW", PERSON);
    const en = legalDoc("terms", "en", PERSON);
    const coinsZh = zh.sections.find((s) => s.heading === "五、鯨幣");
    const coinsEn = en.sections.find((s) => s.heading === "5. Whale Coins");
    expect(coinsZh && coinsEn).toBeTruthy();
    const said = JSON.stringify(coinsZh);
    for (const part of ["不能以金錢購買", "不是法定貨幣", "沒有現金價值", "不得販售、轉讓", "不得提領", "上限", "不會因此被收回", "調整"]) {
      expect(said).toContain(part);
    }
    const saidEn = JSON.stringify(coinsEn);
    for (const part of ["cannot be bought", "not legal tender", "no cash value", "may not be sold, transferred", "withdrawn", "limits", "does not take back", "may change"]) {
      expect(saidEn).toContain(part);
    }
    expect(said).not.toContain("需法律確認"); // the lawyer's questions are for the code, not the page
    expect(zh.sections.map((s) => s.heading).slice(4)).toEqual(["五、鯨幣", "六、內容的使用", "七、服務變更與中斷", "八、責任限制", "九、準據法與管轄"]);
    expect(en.sections.map((s) => s.heading).slice(4)).toEqual(["5. Whale Coins", "6. Use of the content", "7. Changes and interruptions", "8. Liability", "9. Law"]);
    expect([zh.updated, en.updated]).toEqual(["2026-10-07", "2026-10-07"]);
    expect(legalDoc("privacy", "zh-TW", PERSON).updated).toBe("2026-10-06"); // not changed, not redated
  });
});

describe("a year against twelve months", () => {
  it("is a whole percent, and nothing when it saves nothing", () => {
    expect(yearlySaving(30, 330)).toBe(8);
    expect(yearlySaving(30, 360)).toBeNull();
    expect(yearlySaving(0, 330)).toBeNull();
  });
});

describe("coming back from PAYUNi", () => {
  it("answers PAYUNi's form POST with the done page, in the reader's language", async () => {
    const response = await POST(new Request("http://site/news/en/membership/return", { method: "POST" }), {
      params: Promise.resolve({ lang: "en" }),
    });
    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe("/news/en/membership/done");
  });

  it("does not follow a language it does not know", async () => {
    const response = await POST(new Request("http://site/x", { method: "POST" }), {
      params: Promise.resolve({ lang: "evil.example" }),
    });
    expect(response.headers.get("Location")).toBe("/news/zh-TW/membership/done");
  });

  function me(body: unknown, status = 200) {
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  }

  it("says paid once the API says they are a member, even if it takes a few asks", async () => {
    const until = "2026-10-24T08:00:00Z";
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(me({ reader_id: "r", email: "a@b.c", member_until: null, tier: "free", capabilities: [] }))
      .mockResolvedValue(me({ reader_id: "r", email: "a@b.c", member_until: until, tier: "vip", capabilities: ["read_vip_articles"] }));
    render(<PaymentDone lang="zh-TW" email="service@nanguado.com" every={1} />);
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("付款完成"));
    expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("says not yet, and where to write, when the notification never comes", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(me({ reader_id: "r", email: "a@b.c", member_until: null, tier: "free", capabilities: [] })),
    );
    render(<PaymentDone lang="zh-TW" email="service@nanguado.com" every={1} />);
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("還沒收到付款確認"));
    expect(screen.getByRole("status").textContent).toContain("service@nanguado.com");
  });

  it("asks a signed-out reader to sign in rather than wait", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.resolve(me({}, 401)));
    render(<PaymentDone lang="en" email="service@nanguado.com" every={1} />);
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Sign in"));
  });
});
