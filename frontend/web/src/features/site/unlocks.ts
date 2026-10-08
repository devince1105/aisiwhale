// A signed-in reader's COIN articles, from the browser (P4, D-249): what they unlocked, and
// unlocking one. The price, the balance and whether it was theirs already are the server's.
import type { Schemas } from "@/api/client";
import { API_URL } from "@/config";

export type UnlockResult = Schemas["UnlockResult"];

/** Unlocked now or before (``already``); too few coins, with what it takes and what they hold;
 * not signed in; or it could not be done. */
export type Unlocking =
  | { kind: "unlocked"; result: UnlockResult }
  | { kind: "short"; need: number; held: number }
  | { kind: "signed-out" }
  | { kind: "failed" };

export async function unlockArticle(articleId: string): Promise<Unlocking> {
  try {
    const response = await fetch(`${API_URL}/api/me/unlocks/${articleId}`, {
      method: "POST",
      credentials: "include",
    });
    if (response.status === 401) return { kind: "signed-out" };
    if (response.status === 402) {
      const body = (await response.json()) as { need: number; held: number };
      return { kind: "short", need: body.need, held: body.held };
    }
    if (!response.ok) return { kind: "failed" };
    return { kind: "unlocked", result: (await response.json()) as UnlockResult };
  } catch {
    return { kind: "failed" };
  }
}

let unlocked: Promise<Set<string>> | null = null;

/** The ids of the articles the reader unlocked, asked once per page however many badges ask;
 * empty for a reader not signed in, or when it could not be read. */
export function unlockedIds(): Promise<Set<string>> {
  unlocked ??= fetch(`${API_URL}/api/me/unlocks`, { credentials: "include" })
    .then(async (response) =>
      response.ok ? new Set(((await response.json()) as { article_id: string }[]).map((u) => u.article_id)) : new Set<string>(),
    )
    .catch(() => new Set<string>());
  return unlocked;
}

/** For tests: forget what was asked. */
export function forgetUnlocked(): void {
  unlocked = null;
}
