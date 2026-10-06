// Signing in from the browser (D-230): an address and a password, or Google. The session is a
// cookie the API sets (httpOnly); every call here sends it with `credentials: "include"`, and
// nothing that proves who somebody is — no password, no token — is ever kept in browser storage.
import { API_URL } from "@/config";

export interface Me {
  reader_id: string;
  email: string;
  email_verified: boolean;
  member_until: string | null;
  /** Who they are to the site, decided by the server (P2): never worked out here. */
  tier: "public" | "free" | "vip";
  /** What the server says they may do: ``read_vip_articles``, ``watchlist``, ``admin``… */
  capabilities: string[];
}

/** How a call that the API may refuse came out. */
export type Outcome = "ok" | "wrong" | "invalid" | "expired" | "limited" | "failed";

async function call(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
}

function outcome(response: Response): Outcome {
  if (response.ok) return "ok";
  if (response.status === 401) return "wrong";
  if (response.status === 422) return "invalid";
  if (response.status === 400) return "expired";
  if (response.status === 429) return "limited";
  return "failed";
}

async function post(path: string, body: unknown): Promise<Outcome> {
  try {
    return outcome(await call(path, { method: "POST", body: JSON.stringify(body) }));
  } catch {
    return "failed";
  }
}

/** Make an account. Answers the same for an address that already has one: check the inbox. */
export function register(email: string, password: string, lang: string): Promise<Outcome> {
  return post("/api/auth/register", { email, password, lang });
}

export function login(email: string, password: string): Promise<Outcome> {
  return post("/api/auth/login", { email, password });
}

/** Ask for a link to set a new password. Answers the same whether or not the address has one. */
export function forgotPassword(email: string, lang: string): Promise<Outcome> {
  return post("/api/auth/password/forgot", { email, lang });
}

export function resetPassword(token: string, password: string): Promise<Outcome> {
  return post("/api/auth/password/reset", { token, password });
}

export function verifyEmail(token: string): Promise<Outcome> {
  return post("/api/auth/email/verify", { token });
}

export function resendVerification(lang: string): Promise<Outcome> {
  return post("/api/auth/email/resend", { lang });
}

/** Where "continue with Google" goes: the API, which sends the browser on to Google. */
export function googleStartUrl(lang: string, next?: string): string {
  const query = new URLSearchParams({ lang });
  if (next?.startsWith("/")) query.set("next", next);
  return `${API_URL}/api/auth/google/start?${query.toString()}`;
}

export async function fetchMe(company?: string): Promise<Me | null> {
  const query = company ? `?company=${encodeURIComponent(company)}` : "";
  const response = await call(`/api/auth/me${query}`);
  if (!response.ok) return null;
  return (await response.json()) as Me | null;
}

export async function signOut(): Promise<void> {
  await call("/api/auth/logout", { method: "POST" });
}

/** VIP, as the server decided it (P2): a running membership, bought or given by an admin. */
export function isMember(me: Me | null): boolean {
  return me?.tier === "vip";
}
