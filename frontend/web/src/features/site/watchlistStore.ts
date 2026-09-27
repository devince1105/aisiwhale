// A signed-in reader's watchlist (D-060), shared by every part of the page that shows it: the
// list beside a stock, the button on it, the watchlist page. One store, so adding a stock with
// the button shows it in the list at once. The API knows the reader by their cookie only.
"use client";

import { useEffect, useSyncExternalStore } from "react";

import { API_URL } from "@/config";

export interface WatchedStock {
  symbol: string;
  market: string;
  key: string;
  name: string;
  exchange?: string | null;
}

/** ``signedOut``: the API said 401 — the reader is not signed in, and the list is theirs to keep
 * only once they are. */
export type WatchlistState =
  | { status: "loading" }
  | { status: "signedOut" }
  | { status: "ready"; items: WatchedStock[] }
  | { status: "failed" };

const LOADING: WatchlistState = { status: "loading" };
let state: WatchlistState = LOADING;
let loadedFor: string | null = null;
const listeners = new Set<() => void>();

function set(next: WatchlistState) {
  state = next;
  listeners.forEach((listener) => listener());
}

async function call(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${API_URL}/api/me/watchlist${path}`, { ...init, credentials: "include" });
}

export async function loadWatchlist(lang: string): Promise<void> {
  loadedFor = lang;
  try {
    const response = await call(`?lang=${encodeURIComponent(lang)}`);
    if (response.status === 401) return set({ status: "signedOut" });
    if (!response.ok) return set({ status: "failed" });
    set({ status: "ready", items: (await response.json()) as WatchedStock[] });
  } catch {
    set({ status: "failed" });
  }
}

/** Put a stock on the list, or take it off; the list is read again after, in the page's language. */
export async function setWatched(symbol: string, watched: boolean): Promise<boolean> {
  const response = await call(`/${encodeURIComponent(symbol)}`, { method: watched ? "POST" : "DELETE" });
  if (response.ok) await loadWatchlist(loadedFor ?? "zh-TW");
  return response.ok;
}

/** Put the list in the reader's order (D-063): shown at once, then kept; if keeping fails, the
 * list is read again, so the page never shows an order the API does not have. */
export async function reorderWatchlist(keys: string[]): Promise<boolean> {
  if (state.status === "ready") {
    const byKey = new Map(state.items.map((item) => [item.key, item]));
    set({ status: "ready", items: keys.flatMap((key) => (byKey.has(key) ? [byKey.get(key)!] : [])) });
  }
  try {
    const response = await call("", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys }),
    });
    if (response.ok) return true;
  } catch {
    // read it again below
  }
  await loadWatchlist(loadedFor ?? "zh-TW");
  return false;
}

/** The watchlist, loaded once per page for the language it is in. */
export function useWatchlist(lang: string): WatchlistState {
  const current = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => state,
    () => LOADING,
  );
  useEffect(() => {
    if (loadedFor !== lang) void loadWatchlist(lang);
  }, [lang]);
  return current;
}

/** For tests: forget what was loaded. */
export function resetWatchlist(): void {
  state = LOADING;
  loadedFor = null;
  listeners.clear();
}
