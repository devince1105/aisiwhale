// Signing in to the back office (D-055, D-230): the readers' own sign-in — a password, or Google —
// through the back office's door, which lets in an address on ADMIN_EMAILS that is proven to be
// theirs. The session is the API's httpOnly cookie; every call sends it with
// `credentials: "include"`. Nothing that proves who somebody is is ever kept in browser storage.
import { API_URL } from "@/config";

export interface AdminMe {
  via: "email" | "token";
  email: string | null;
}

async function call(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
}

export type AdminLoginResult = "ok" | "wrong" | "forbidden" | "limited" | "failed";

/** Sign in with an address and a password. */
export async function loginAdmin(email: string, password: string): Promise<AdminLoginResult> {
  const response = await call("/api/admin/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (response.ok) return "ok";
  if (response.status === 401) return "wrong";
  if (response.status === 403) return "forbidden";
  if (response.status === 429) return "limited";
  return "failed";
}

/** Where the "continue with Google" button goes: the API, which sends the browser on to Google. */
export function adminGoogleUrl(next: string | null): string {
  const query = next && /^\/admin(\/|$)/.test(next) ? `?next=${encodeURIComponent(next)}` : "";
  return `${API_URL}/api/admin/auth/google/start${query}`;
}

/** Who is calling the back office; null when nobody may. */
export async function fetchAdminMe(): Promise<AdminMe | null> {
  const response = await call("/api/admin/auth/me");
  if (response.status === 401) return null;
  if (!response.ok) throw new Error(`me failed (${response.status})`);
  return (await response.json()) as AdminMe;
}

export async function signOutAdmin(): Promise<void> {
  await call("/api/admin/auth/logout", { method: "POST" });
}

/** Where a signed-out visit to ``path`` goes: the login page, and back afterwards. */
export function loginHref(path: string | null): string {
  return path && path.startsWith("/admin") && !path.startsWith("/admin/login")
    ? `/admin/login?next=${encodeURIComponent(path)}`
    : "/admin/login";
}

/** Where a sign-in goes on to: a back-office page, never another address. */
export function afterLogin(next: string | null | undefined): string {
  return next && /^\/admin(\/|$)/.test(next) && !next.startsWith("/admin/login") ? next : "/admin/dashboard";
}
