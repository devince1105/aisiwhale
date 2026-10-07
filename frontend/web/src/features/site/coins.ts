// A signed-in reader's Whale Coins, from the browser (P3-C): ``GET /api/me/coins``, read only.
// The balance, the month's terms and whether it was given are the server's answers; nothing here
// works out a tier, a cap or a month.
import type { Schemas } from "@/api/client";
import { API_URL } from "@/config";

export type CoinWallet = Schemas["CoinWallet"];
export type CoinMovement = Schemas["CoinMovement"];

/** The reader's wallet, ``"signed-out"`` without a session, or null when it could not be read. */
export async function fetchCoins(
  options: { company?: string; cursor?: string | null; limit?: number } = {},
): Promise<CoinWallet | "signed-out" | null> {
  const query = new URLSearchParams();
  if (options.company) query.set("company", options.company);
  if (options.cursor) query.set("cursor", options.cursor);
  if (options.limit) query.set("limit", String(options.limit));
  try {
    const response = await fetch(`${API_URL}/api/me/coins${query.size ? `?${query}` : ""}`, {
      credentials: "include",
    });
    if (response.status === 401) return "signed-out";
    if (!response.ok) return null;
    return (await response.json()) as CoinWallet;
  } catch {
    return null;
  }
}

/** What the month says, in one of three words: off, given, or still to come. */
export function monthState(wallet: CoinWallet): "coming" | "given" | "next-visit" {
  if (!wallet.monthly.grants_on) return "coming";
  return wallet.monthly.granted ? "given" : "next-visit";
}
