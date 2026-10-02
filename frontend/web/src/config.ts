// Where the API lives. NEXT_PUBLIC_API_URL is baked in at build time (docker-compose sets it).
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

/** ws:// or wss:// for the same host as an http(s) API URL. */
export function toWebSocketUrl(apiUrl: string): string {
  return apiUrl.replace(/^http/, "ws");
}

/** Where the server (Next.js rendering the public site) reaches the API. In Docker the browser's
 * URL (NEXT_PUBLIC_API_URL) is not reachable from inside the web container: API_INTERNAL_URL is. */
export const SERVER_API_URL = (process.env.API_INTERNAL_URL ?? API_URL).replace(/\/+$/, "");

/** Which company's site this is (D-025). The server reads SITE_COMPANY for the article list;
 * the browser needs its own copy to ask whether the reader is a member of *this* company. */
export const SITE_COMPANY = process.env.NEXT_PUBLIC_SITE_COMPANY || undefined;

/** Cloudflare Turnstile's site key for the 聯絡我們 form (D-166): public by design, baked in at
 * build time. Unset, the form shows no check (the API then does not ask for one either). */
export const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || undefined;
