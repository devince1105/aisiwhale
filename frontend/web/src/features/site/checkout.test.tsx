// @vitest-environment jsdom
// T-702: the paywall's button, from "become a member" to PAYUNi's payment page.
//
// The point of most of these is what the browser does *not* do: it never sees a secret, it never
// grants anything, and a site with no store yet says so instead of failing silently.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CheckoutError, fetchOffer, formatOffer, goToPaymentPage, startCheckout } from "./checkout";
import { MembersOnly } from "./MembersOnly";

const PAGE = {
  order_id: "0192cccc-cccc-7ccc-8ccc-cccccccccccc",
  mer_trade_no: "AU0192CCCCCCCC7CCC",
  amount: "360.000000",
  currency: "TWD",
  url: "https://sandbox-api.payuni.com.tw/api/upp",
  fields: { MerID: "SHOP123", Version: "1.0", EncryptInfo: "abcd1234", HashInfo: "F00D" },
};

const OFFER = { amount: "360.000000", currency: "TWD", interval: "year", available: true };

function respond(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
}

/** The paywall shows its button first; the plans are a click away (D-159). */
const openPlans = () => fireEvent.click(screen.getByRole("button", { name: "我要成為 VIP 會員看全文" }));

/** A plan's button once the API has said it is on sale: until then none can be pressed (P2-B). */
async function pressable(name: string): Promise<HTMLButtonElement> {
  const button = (await screen.findByRole("button", { name })) as HTMLButtonElement;
  await waitFor(() => expect(button.disabled).toBe(false));
  return button;
}

afterEach(() => {
  cleanup();
  document.body.innerHTML = ""; // the forms are appended to the body, not rendered by React
  vi.restoreAllMocks();
});

describe("what a year costs", () => {
  it("is what the API says, not what the page was written with", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockReturnValue(respond({ ...OFFER, amount: "480.000000" }));
    const offer = await fetchOffer("lumen");
    expect(String(fetchMock.mock.calls[0][0])).toContain("interval=year");
    expect(offer).not.toBeNull();
    expect(formatOffer(offer!, "zh-TW")).toBe("NT$480");
  });

  it("is nothing at all when the site has nothing for sale", async () => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(respond({ ...OFFER, amount: "0", available: false }));
    expect(await fetchOffer()).toBeNull();
  });

  it("is the catalogue's price, not for sale, while checkout is closed (P2, D-231)", async () => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(
      respond({ amount: "30.000000", currency: "TWD", interval: "month", available: false }),
    );
    const offer = await fetchOffer("lumen", "month");
    expect(offer).not.toBeNull();
    expect(offer!.available).toBe(false);
    expect(formatOffer(offer!, "zh-TW")).toBe("NT$30");
  });

  it("is nothing at all when the API cannot be reached, rather than an error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
    expect(await fetchOffer()).toBeNull();
  });

  it("says which dollar it is", () => {
    expect(formatOffer(OFFER, "zh-TW")).toBe("NT$360");
    expect(formatOffer(OFFER, "en")).toBe("NT$360");
    expect(formatOffer({ ...OFFER, currency: "USD", amount: "12" }, "en")).toBe("USD 12");
  });
});

describe("starting a checkout", () => {
  it("asks for an order and hands back the form", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockReturnValue(respond(PAGE, 201));
    const page = await startCheckout("zh-TW", "lumen");
    expect(page.url).toBe(PAGE.url);
    const [, init] = fetchMock.mock.calls[0];
    expect(init?.credentials).toBe("include");
    expect(JSON.parse(String(init?.body))).toEqual({ lang: "zh-TW", company: "lumen", interval: "year" });
  });

  it("asks for a month when a month is chosen (D-034)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockReturnValue(respond(PAGE, 201));
    await startCheckout("zh-TW", undefined, "month");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body)).interval).toBe("month");
  });

  it.each([
    [401, "signed-out"],
    [404, "unavailable"],
    [503, "unavailable"],
    [500, "failed"],
  ])("turns %i into %s", async (status, problem) => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(respond({}, status));
    await expect(startCheckout("zh-TW")).rejects.toMatchObject({ problem });
  });

  it("is a failure, not a crash, when the network is gone", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
    await expect(startCheckout("zh-TW")).rejects.toBeInstanceOf(CheckoutError);
  });
});

describe("going to the payment page", () => {
  it("posts the sealed fields as a form, because the reader has to land there", () => {
    const submit = vi.fn();
    vi.spyOn(HTMLFormElement.prototype, "submit").mockImplementation(submit);
    goToPaymentPage(PAGE);

    const form = document.querySelector("form");
    expect(form?.method).toBe("post");
    expect(form?.action).toBe(PAGE.url);
    const sent = Object.fromEntries(
      Array.from(form!.querySelectorAll("input")).map((i) => [i.name, i.value]),
    );
    expect(sent).toEqual(PAGE.fields);
    expect(submit).toHaveBeenCalledOnce();
  });
});

describe("the paywall", () => {
  beforeEach(() => {
    vi.spyOn(HTMLFormElement.prototype, "submit").mockImplementation(() => undefined);
  });

  const MONTH = { ...OFFER, amount: "30.000000", interval: "month" };

  /** The API: ``year`` for the yearly offer, ``month`` for the monthly one (unavailable if null). */
  function mockCalls(
    year: unknown,
    checkout: () => Promise<Response>,
    month: unknown = { ...MONTH, amount: "0", available: false }, // no price in the catalogue
  ) {
    return vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (!url.includes("/api/checkout/offer")) return checkout();
      return respond(url.includes("interval=month") ? month : year);
    });
  }

  it("shows the price the API charges", async () => {
    mockCalls({ ...OFFER, amount: "480.000000" }, () => respond(PAGE, 201));
    render(<MembersOnly lang="zh-TW" path="/news/zh-TW/articles/x" company="lumen" />);
    openPlans();
    await waitFor(() => expect(screen.getByTestId("members-only").textContent).toContain("NT$480"));
  });

  it("offers a month and a year side by side, and says what a year saves (D-034)", async () => {
    mockCalls({ ...OFFER, amount: "330.000000" }, () => respond(PAGE, 201), MONTH);
    render(<MembersOnly lang="zh-TW" path="/news/zh-TW/articles/x" company="lumen" />);
    openPlans();
    await waitFor(() => expect(screen.getByTestId("plan-month").textContent).toContain("NT$30"));
    expect(screen.getByTestId("plan-year").textContent).toContain("NT$330");
    expect(screen.getByTestId("plan-year").textContent).toContain("比月繳省 8%");
  });

  it("keeps a plan the API does not sell yet, faded, with 即將開放 (D-161)", async () => {
    mockCalls(OFFER, () => respond(PAGE, 201));
    render(<MembersOnly lang="zh-TW" path="/news/zh-TW/articles/x" company="lumen" />);
    openPlans();
    await waitFor(() => expect(screen.getByTestId("plan-month").getAttribute("data-reserved")).toBe("true"));
    const month = screen.getByTestId("plan-month");
    expect(month.className).toContain("opacity-50");
    expect((within(month).getByRole("button") as HTMLButtonElement).disabled).toBe(true);
    expect(month.textContent).toContain("即將開放");
    const year = screen.getByTestId("plan-year");
    expect(year.getAttribute("data-reserved")).toBeNull();
    expect(within(year).getByRole("button", { name: "選擇年繳" })).toBeTruthy();
  });

  it("orders the plan that was chosen", async () => {
    const fetchMock = mockCalls(OFFER, () => respond(PAGE, 201), MONTH);
    render(<MembersOnly lang="zh-TW" path="/news/zh-TW/articles/x" company="lumen" />);
    openPlans();
    fireEvent.click(await screen.findByRole("button", { name: "選擇月繳" }));
    await waitFor(() => expect(document.querySelector("form")).not.toBeNull());
    const order = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/api/checkout"));
    expect(JSON.parse(String(order![1]!.body)).interval).toBe("month");
  });

  it("says what paying agrees to, with the policies a click away", () => {
    mockCalls(OFFER, () => respond(PAGE, 201));
    render(<MembersOnly lang="zh-TW" path="/news/zh-TW/articles/x" />);
    openPlans();
    const notice = screen.getByTestId("members-only");
    expect(notice.textContent).toContain("不會自動扣款");
    expect(screen.getByRole("link", { name: "服務條款" }).getAttribute("href")).toBe("/news/zh-TW/terms");
    expect(screen.getByRole("link", { name: "退款政策" }).getAttribute("href")).toBe("/news/zh-TW/refund");
  });

  it("takes the reader to PAYUNi", async () => {
    mockCalls(OFFER, () => respond(PAGE, 201));
    render(<MembersOnly lang="zh-TW" path="/news/zh-TW/articles/x" company="lumen" />);
    openPlans();
    fireEvent.click(await pressable("選擇年繳"));
    await waitFor(() => expect(document.querySelector("form")?.action).toBe(PAGE.url));
  });

  it("says so when the site has no store yet, instead of a dead end", async () => {
    mockCalls(OFFER, () => respond({}, 503));
    render(<MembersOnly lang="zh-TW" path="/news/zh-TW/articles/x" />);
    openPlans();
    fireEvent.click(await pressable("選擇年繳"));
    expect((await screen.findByRole("status")).textContent).toContain("即將開放");
  });

  it("says try again when the payment page could not be opened", async () => {
    mockCalls(OFFER, () => respond({}, 500));
    render(<MembersOnly lang="zh-TW" path="/news/zh-TW/articles/x" />);
    openPlans();
    fireEvent.click(await pressable("選擇年繳"));
    expect((await screen.findByRole("status")).textContent).toContain("請稍後再試");
  });

  it("sends somebody who is not signed in to sign in first", async () => {
    mockCalls(OFFER, () => respond({}, 401));
    const assign = vi.fn();
    Object.defineProperty(window, "location", { value: { assign }, writable: true });
    render(<MembersOnly lang="zh-TW" path="/news/zh-TW/articles/x" />);
    openPlans();
    fireEvent.click(await pressable("選擇年繳"));
    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith(
        "/news/zh-TW/login?next=%2Fnews%2Fzh-TW%2Farticles%2Fx",
      ),
    );
  });

  it("never puts a secret in the page", async () => {
    mockCalls(OFFER, () => respond(PAGE, 201));
    render(<MembersOnly lang="en" path="/news/en/articles/x" company="lumen" />);
    fireEvent.click(screen.getByRole("button", { name: "Become a VIP member to read on" }));
    fireEvent.click(await pressable("Choose yearly"));
    await waitFor(() => expect(document.querySelector("form")).not.toBeNull());
    const sent = Array.from(document.querySelectorAll("form input")).map((i) => i.getAttribute("name"));
    expect(sent).toEqual(["MerID", "Version", "EncryptInfo", "HashInfo"]);
  });
});

describe("持股觀察 (D-159)", () => {
  it("asks a stranger to sign in, free, and comes back to the story", () => {
    render(<MembersOnly lang="zh-TW" path="/news/zh-TW/articles/x" lock="sign_in" />);
    const notice = screen.getByTestId("sign-in-to-read");
    expect(notice.textContent).toContain("登入即可免費閱讀全文");
    expect(screen.getByRole("link", { name: "登入看全文" }).getAttribute("href")).toBe(
      `/news/zh-TW/login?next=${encodeURIComponent("/news/zh-TW/articles/x")}`,
    );
    expect(screen.queryByTestId("members-only")).toBeNull();
  });
});

describe("before membership opens (D-161)", () => {
  it("shows what will be sold and at what price, and 即將開放 where the button would be", async () => {
    const fetchMock = vi.fn<(url: RequestInfo | URL) => Promise<Response>>(async () => new Response(JSON.stringify({ amount: "30.000000", currency: "TWD", interval: "month", available: false }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    render(<MembersOnly lang="zh-TW" path="/news/zh-TW/articles/x" company="lumen" />);
    openPlans();
    await waitFor(() => expect(screen.getByTestId("members-only").textContent).toContain("NT$30"));
    const buttons = screen.getAllByRole("button", { name: "即將開放" }) as HTMLButtonElement[];
    expect(buttons.length).toBeGreaterThan(0);
    expect(buttons.every((b) => b.disabled)).toBe(true);
    expect(screen.getByRole("status").textContent).toContain("即將開放");
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/checkout"))).toBe(false);
  });
});

describe("while checkout is closed (P2, D-231)", () => {
  it("shows NT$30 a month, NT$300 a year faded, both 即將開放, and never starts a checkout", async () => {
    // P2's API: the month priced and not on sale; the year with no price in the catalogue yet
    const fetchMock = vi.fn<(url: RequestInfo | URL) => Promise<Response>>(async (url) => {
      const month = String(url).includes("interval=month");
      return new Response(
        JSON.stringify({ amount: month ? "30.000000" : "0", currency: "TWD", interval: month ? "month" : "year", available: false }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    // the API decides what is for sale: the page has no switch of its own (P2-B)
    render(<MembersOnly lang="zh-TW" path="/news/zh-TW/articles/x" company="lumen" />);
    openPlans();
    await waitFor(() => expect(screen.getByTestId("plan-year").getAttribute("data-reserved")).toBe("true"));

    const month = screen.getByTestId("plan-month");
    expect(month.textContent).toContain("NT$30");
    expect(month.getAttribute("data-reserved")).toBeNull();
    expect(month.className).not.toContain("opacity-50");
    const monthButton = within(month).getByRole("button") as HTMLButtonElement;
    expect(monthButton.disabled).toBe(true);
    expect(monthButton.textContent).toBe("即將開放");

    const year = screen.getByTestId("plan-year");
    expect(year.textContent).toContain("NT$300");
    expect(year.className).toContain("opacity-50");
    const yearButton = within(year).getByRole("button") as HTMLButtonElement;
    expect(yearButton.disabled).toBe(true);
    expect(yearButton.textContent).toBe("即將開放");

    expect(screen.getByTestId("members-only").textContent).not.toContain("NT$149");
    fireEvent.click(monthButton);
    fireEvent.click(yearButton);
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/checkout"))).toBe(false);
  });
});

describe("聯絡我們 (D-165)", () => {
  it("asks what is needed first, then who is asking, and sends it to the API", async () => {
    const { ContactForm } = await import("./ContactForm");
    const fetchMock = vi.fn<(url: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(async () => new Response(null, { status: 202 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ContactForm lang="zh-TW" />);
    const legends = Array.from(document.querySelectorAll("legend")).map((l) => l.textContent);
    expect(legends).toEqual(["請幫助我們了解你的需求", "你的聯絡資訊"]);
    fireEvent.change(screen.getByLabelText("請說明你的問題或需求"), { target: { value: "想請問月繳可以開發票嗎？" } });
    fireEvent.click(screen.getByLabelText("合作與廣告"));
    fireEvent.change(screen.getByLabelText("姓名"), { target: { value: "王小明" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "reader@example.com" } });
    expect(screen.getByRole("link", { name: "隱私權政策" }).getAttribute("href")).toBe("/news/zh-TW/privacy");
    fireEvent.click(screen.getByRole("button", { name: "送出" }));
    expect(await screen.findByTestId("contact-sent")).toBeTruthy();
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/public\/contact$/);
    const sent = JSON.parse(String(init!.body));
    expect(sent).toMatchObject({ name: "王小明", topic: "partnership", website: "", lang: "zh-TW", turnstile_token: "" });
    expect(typeof sent.elapsed_ms).toBe("number"); // how long it was open, for the API to judge (D-166)
  });

  it("with a Turnstile site key, asks for the check before sending, and sends its token (D-166)", async () => {
    const { ContactForm } = await import("./ContactForm");
    const fetchMock = vi.fn<(url: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(async () => new Response(null, { status: 202 }));
    vi.stubGlobal("fetch", fetchMock);
    let rendered: Record<string, unknown> = {};
    vi.stubGlobal("turnstile", { render: (_el: HTMLElement, options: Record<string, unknown>) => ((rendered = options), "w1"), reset: vi.fn(), remove: vi.fn() });
    render(<ContactForm lang="zh-TW" siteKey="site-key" />);
    fireEvent.change(screen.getByLabelText("請說明你的問題或需求"), { target: { value: "想請問月繳可以開發票嗎？" } });
    fireEvent.change(screen.getByLabelText("姓名"), { target: { value: "王小明" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "reader@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "送出" }));
    expect((await screen.findByRole("alert")).textContent).toContain("真人驗證");
    expect(fetchMock).not.toHaveBeenCalled();
    await waitFor(() => expect(rendered.sitekey).toBe("site-key"));
    act(() => (rendered.callback as (t: string) => void)("token-1"));
    fireEvent.click(screen.getByRole("button", { name: "送出" }));
    expect(await screen.findByTestId("contact-sent")).toBeTruthy();
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]!.body)).turnstile_token).toBe("token-1");
    vi.unstubAllGlobals();
  });

  it("says try later when too many were sent", async () => {
    const { sendContact } = await import("./ContactForm");
    const busy = vi.fn(async () => new Response(null, { status: 429 })) as unknown as typeof fetch;
    const body = { name: "a", email: "a@b.c", phone: "", company: "", topic: "other" as const, message: "0123456789", lang: "zh-TW" as const, website: "", elapsed_ms: 5000, turnstile_token: "" };
    expect(await sendContact(body, busy)).toBe("busy");
    const down = vi.fn(async () => { throw new TypeError("fetch failed"); }) as unknown as typeof fetch;
    expect(await sendContact(body, down)).toBe("failed");
  });
});

describe("until the API has said what is for sale (P2-B)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("no plan can be pressed, and nothing is ordered", async () => {
    const fetchMock = vi.fn<(url: RequestInfo | URL) => Promise<Response>>(() => new Promise<Response>(() => undefined));
    vi.stubGlobal("fetch", fetchMock);
    render(<MembersOnly lang="zh-TW" path="/news/zh-TW/articles/x" company="lumen" />);
    openPlans();
    const buttons = within(screen.getByTestId("members-only")).getAllByRole("button") as HTMLButtonElement[];
    const plans = buttons.filter((b) => b.textContent?.startsWith("選擇"));
    expect(plans).toHaveLength(2);
    expect(plans.every((b) => b.disabled)).toBe(true);
    for (const plan of plans) fireEvent.click(plan);
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/checkout"))).toBe(false);
  });

  it("an API that cannot be reached reads as not yet", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new Error("offline"))));
    render(<MembersOnly lang="zh-TW" path="/news/zh-TW/articles/x" company="lumen" />);
    openPlans();
    expect((await screen.findByRole("status")).textContent).toContain("即將開放");
    const plans = screen.getAllByRole("button", { name: "即將開放" }) as HTMLButtonElement[];
    expect(plans.every((b) => b.disabled)).toBe(true);
  });
});
