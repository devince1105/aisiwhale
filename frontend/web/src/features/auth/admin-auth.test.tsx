// @vitest-environment jsdom
// The back office's door (D-055, D-230): a signed-out visit goes to /admin/login and comes back,
// a signed-in admin sees the page and who they are, and the login form signs in with a password
// or Google — keeping nothing in browser storage.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/admin/dashboard",
  useSearchParams: () => search,
}));

import { adminGoogleUrl, afterLogin, loginHref } from "./adminAuth";
import { AdminLogin } from "./AdminLogin";
import { TokenGate } from "./TokenGate";

const calls: { url: string; init: RequestInit }[] = [];
function answer(status: number, body: unknown = null) {
  vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
    // the shell's own requests (its company list, its approvals count): nothing there
    const target: unknown = url;
    if (!(target instanceof Request ? target.url : String(target)).includes("/api/admin/")) return new Response("[]", { status: 200 });
    calls.push({ url, init });
    return new Response(body === null ? null : JSON.stringify(body), { status });
  });
}

function wrap(children: ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>);
}

beforeEach(() => {
  calls.length = 0;
  replace.mockReset();
  search = new URLSearchParams();
  window.localStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the back office's door", () => {
  it("sends a signed-out visit to the login page, and back afterwards", async () => {
    answer(401);
    wrap(<TokenGate><p>inside</p></TokenGate>);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/login?next=%2Fadmin%2Fdashboard"));
    expect(screen.queryByText("inside")).toBeNull();
    expect(calls[0].init.credentials).toBe("include");
  });

  it("shows the page and who is signed in", async () => {
    answer(200, { via: "email", email: "admin@aisiwhale.test" });
    wrap(<TokenGate><p>inside</p></TokenGate>);
    expect(await screen.findByText("inside")).toBeTruthy();
    expect(screen.getByTestId("admin-who").textContent).toBe("admin@aisiwhale.test");
    expect(screen.getByRole("button", { name: "登出" })).toBeTruthy();
  });

  it("goes back only to a page of the back office", () => {
    expect(afterLogin("/admin/approvals?company=c1")).toBe("/admin/approvals?company=c1");
    expect(afterLogin("https://evil.example/admin")).toBe("/admin/dashboard");
    expect(afterLogin("/news/zh-TW")).toBe("/admin/dashboard");
    expect(afterLogin("/admin/login")).toBe("/admin/dashboard");
    expect(loginHref("/admin/login")).toBe("/admin/login");
  });
});

describe("the login page", () => {
  it("signs in with the password and goes on to the page that was asked for", async () => {
    answer(200, { via: "email", email: "admin@aisiwhale.test" });
    search = new URLSearchParams("next=/admin/approvals");
    wrap(<AdminLogin />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: " admin@aisiwhale.test " } });
    fireEvent.change(screen.getByLabelText("密碼"), { target: { value: "correct horse battery" } });
    fireEvent.click(screen.getByRole("button", { name: "登入" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/approvals"));
    expect(calls[0].url).toMatch(/\/api\/admin\/auth\/login$/);
    expect(calls[0].init.credentials).toBe("include");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      email: "admin@aisiwhale.test",
      password: "correct horse battery",
    });
    expect(window.localStorage.length).toBe(0); // nothing that proves who they are is kept here
  });

  it("says why when the account may not come in", async () => {
    answer(403);
    wrap(<AdminLogin />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "someone@example.com" } });
    fireEvent.change(screen.getByLabelText("密碼"), { target: { value: "whatever pw" } });
    fireEvent.click(screen.getByRole("button", { name: "登入" }));
    expect((await screen.findByRole("alert")).textContent).toContain("不能進入後台");
    expect(replace).not.toHaveBeenCalled();
  });

  it("offers Google through the API, and shows why a Google sign-in came back", () => {
    search = new URLSearchParams("error=not_admin");
    wrap(<AdminLogin />);
    expect(screen.getByTestId("admin-google").getAttribute("href")).toMatch(/\/api\/admin\/auth\/google\/start$/);
    expect(screen.getByRole("alert").textContent).toContain("管理員名單");
    expect(adminGoogleUrl("/admin/approvals")).toMatch(/google\/start\?next=%2Fadmin%2Fapprovals$/);
    expect(adminGoogleUrl("https://evil.example")).toMatch(/google\/start$/);
  });

  it("no longer takes an operator token", () => {
    wrap(<AdminLogin />);
    expect(screen.queryByLabelText("操作者權杖")).toBeNull();
  });
});
