// The reader's own version of a page, asked from the browser (D-025, D-159).
//
// The server builds a page once for everybody — as for a reader nobody knows — and keeps it
// (ISR): no cookie is read there, so nothing one reader may see is ever kept for another. Where
// the page holds back something (a members-only story's rest, the whole of a 13F table), the
// browser asks the API again with the reader's cookie (it is the API's, on .aisiwhale.com) and
// shows what comes back. Signed out, the answer is the same as the page's, and nothing changes.
"use client";

import { createContext, useCallback, useEffect, useState } from "react";

import { API_URL } from "@/config";

/** Ask the page's reads again: what a COIN unlock calls once the article is the reader's. */
export const ReaderRefresh = createContext<(() => void) | null>(null);

/** ``initial`` until the browser has asked ``path`` (an API path with its query) with the
 * reader's cookie, then the answer. Asked on mount when ``ask``, and again on ``refresh()``;
 * an answer that does not come back leaves the page as it was. */
export function useReaderVersion<T>(
  initial: T,
  path: string,
  ask: boolean,
  send: typeof fetch = fetch,
): [T, () => void] {
  const [data, setData] = useState(initial);
  const [asked, setAsked] = useState(0);

  useEffect(() => {
    if (!ask && asked === 0) return;
    let live = true;
    send(`${API_URL}${path}`, { credentials: "include", cache: "no-store" })
      .then((response) => (response.ok ? (response.json() as Promise<T>) : null))
      .then((answer) => {
        if (live && answer) setData(answer);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [path, ask, asked, send]);

  return [data, useCallback(() => setAsked((n) => n + 1), [])];
}
