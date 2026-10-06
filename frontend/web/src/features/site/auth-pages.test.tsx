// @vitest-environment jsdom
// The site's sign-in pages (D-230): a password or Google, answers that do not say whether an
// address has an account, and nothing that proves who somebody is kept in browser storage.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ForgotForm, LoginForm, RegisterForm, ResetForm } from "./AuthPages";

const calls: { url: string; init: RequestInit }[] = [];
const replace = vi.fn();

/** Answer each path with a status (and body); /api/auth/me says nobody unless told otherwise. */
function api(answers: Record<string, [number, unknown?]>) {
  vi.stubGlobal("fetch", async (url: string, init: RequestInit = {}) => {
    calls.push({ url, init });
    const path = new URL(url).pathname;
    const [status, body] = answers[path] ?? (path === "/api/auth/me" ? [200, null] : [404]);
    return new Response(body === undefined ? null : JSON.stringify(body), { status });
  });
}

const posted = (path: string) =>
  calls.filter((call) => call.url.endsWith(path)).map((call) => JSON.parse(String(call.init.body)));

beforeEach(() => {
  calls.length = 0;
  replace.mockReset();
  window.localStorage.clear();
  vi.stubGlobal("location", { ...window.location, replace });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("signing in", () => {
  it("signs in with the password, keeps nothing in storage, and goes on", async () => {
    api({ "/api/auth/login": [200, { reader_id: "r1", email: "a@example.com" }] });
    render(<LoginForm lang="zh-TW" next="/news/zh-TW/watchlist" />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: " a@example.com " } });
    fireEvent.change(screen.getByLabelText("密碼"), { target: { value: "correct horse" } });
    fireEvent.click(screen.getByRole("button", { name: "登入" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/news/zh-TW/watchlist"));
    expect(posted("/api/auth/login")).toEqual([{ email: "a@example.com", password: "correct horse" }]);
    expect(calls.every((call) => call.init.credentials === "include")).toBe(true);
    expect(window.localStorage.length).toBe(0);
  });

  it("says only that the email or the password is wrong", async () => {
    api({ "/api/auth/login": [401] });
    render(<LoginForm lang="zh-TW" />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@example.com" } });
    fireEvent.change(screen.getByLabelText("密碼"), { target: { value: "nope nope" } });
    fireEvent.click(screen.getByRole("button", { name: "登入" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Email 或密碼不正確。");
    expect(replace).not.toHaveBeenCalled();
  });

  it("offers Google through the API, and says why a Google sign-in came back", () => {
    api({});
    render(<LoginForm lang="en" next="/news/en/stocks/NVDA" error="google_needs_verified_email" />);
    const href = screen.getByTestId("google-sign-in").getAttribute("href")!;
    expect(href).toMatch(/\/api\/auth\/google\/start\?/);
    expect(new URL(href).searchParams.get("next")).toBe("/news/en/stocks/NVDA");
    expect(screen.getByRole("alert").textContent).toContain("Forgot your password");
  });
});

describe("creating an account", () => {
  it("tells everyone to check the inbox, whether or not the address was new", async () => {
    api({ "/api/auth/register": [202], "/api/auth/login": [401] });
    render(<RegisterForm lang="zh-TW" />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "taken@example.com" } });
    fireEvent.change(screen.getByLabelText("密碼"), { target: { value: "a long password" } });
    fireEvent.click(screen.getByRole("button", { name: "建立帳號" }));
    expect((await screen.findByRole("status")).textContent).toContain("請到信箱查看");
    expect(posted("/api/auth/register")).toEqual([
      { email: "taken@example.com", password: "a long password", lang: "zh-TW" },
    ]);
    expect(window.localStorage.length).toBe(0);
  });
});

describe("forgetting and resetting", () => {
  it("answers the same for any address", async () => {
    api({ "/api/auth/password/forgot": [202] });
    render(<ForgotForm lang="zh-TW" />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "who@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "寄出重設信" }));
    expect((await screen.findByRole("status")).textContent).toContain("如果這個 email 有帳號");
  });

  it("sends the token and the new password, and says when the link no longer works", async () => {
    api({ "/api/auth/password/reset": [400] });
    render(<ResetForm lang="zh-TW" token="the-token" />);
    fireEvent.change(screen.getByLabelText("新密碼"), { target: { value: "a new password" } });
    fireEvent.click(screen.getByRole("button", { name: "設定新密碼" }));
    expect((await screen.findByRole("alert")).textContent).toContain("已經失效");
    expect(posted("/api/auth/password/reset")).toEqual([{ token: "the-token", password: "a new password" }]);
  });
});
