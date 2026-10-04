// How a market figure is written (D-048, D-049): shared by the strip, which runs in the browser,
// and the stock pages, which are rendered on the server — so it lives in neither.
import type { PublicQuote } from "./api";
import type { Lang } from "./i18n";

const DECIMALS: Record<string, number> = { btc: 0, txf1: 0 }; // 台指期 trades in whole points

/** A stock's code as readers look it up: ``tw:2330`` is ``2330.TW``, ``us:NVDA`` is ``NVDA``. */
export function stockCode(key: string, exchange?: string | null): string | null {
  // a TPEx (over-the-counter) stock is 6488.TWO, as Taiwan's quote services write it
  if (key.startsWith("tw:")) return `${key.slice(3)}.${exchange === "TPEx" ? "TWO" : "TW"}`;
  if (key.startsWith("us:")) return key.slice(3);
  // a currency against the New Taiwan dollar, and spot gold (D-071, D-072)
  if (isCurrency(key)) return `${key.slice(0, 3).toUpperCase()}/TWD`;
  if (key === "xau") return "XAU/USD";
  return null;
}

/** ``jpytwd``: a currency against the New Taiwan dollar (D-072). */
export function isCurrency(key: string): boolean {
  return /^[a-z]{3}twd$/.test(key);
}

/** A stock's page on the site (D-049): ``us:NVDA`` → ``/news/en/stocks/NVDA``; none for the rest. */
export function stockPage(key: string, lang: Lang): string | null {
  const [market, symbol] = key.split(":");
  return (market === "tw" || market === "us") && symbol ? `/news/${lang}/stocks/${encodeURIComponent(symbol)}` : null;
}

/** Its name in the reader's language, and its code when that is not the name already. */
export function label(
  key: string,
  names: Record<string, string>,
  exchange?: string | null,
): [name: string, code: string | null] {
  const code = stockCode(key, exchange);
  const name = names[key] ?? code ?? key;
  return [name, code === name ? null : code];
}

const MONEY: Record<string, string> = { TWD: "NT$", USD: "US$" };

/** A market value, short: ``NT$64.2兆``, ``US$5.4T``. */
export function formatCap(value: number, currency: string | null | undefined, lang: Lang): string {
  const short = new Intl.NumberFormat(lang, { notation: "compact", maximumFractionDigits: 1 }).format(value);
  return `${MONEY[currency ?? ""] ?? ""}${short}`;
}

/** A price of the stock's, with its decimals (``formatValue``'s rule). */
export function formatPrice(quote: PublicQuote, price: number, lang: Lang): string {
  return formatValue({ ...quote, value: price }, lang);
}

export function formatValue(quote: PublicQuote, lang: Lang): string {
  // a Taiwan stock is quoted to its tick: whole dollars above 1,000, else two places
  // a currency in NT$ as a bank posts it: three places, four below one (0.2017 for the yen)
  const digits =
    DECIMALS[quote.key] ??
    (isCurrency(quote.key) ? (quote.value < 1 ? 4 : 3) : quote.key.startsWith("tw:") && quote.value >= 1000 ? 0 : 2);
  const value = new Intl.NumberFormat(lang, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(
    quote.value,
  );
  return quote.key === "us10y" ? `${value}%` : value;
}

/** The change as shown: a percentage, or for the yield its points (a change in a percentage). */
export function formatChange(quote: PublicQuote): string | null {
  const shown = quote.change_pct ?? quote.change;
  if (shown === null || shown === undefined) return null;
  const size = Math.abs(shown).toFixed(2);
  return quote.change_pct !== null && quote.change_pct !== undefined ? `${size}%` : size;
}

export function direction(quote: PublicQuote): "rise" | "fall" | "flat" {
  const shown = quote.change_pct ?? quote.change ?? 0;
  return shown > 0 ? "rise" : shown < 0 ? "fall" : "flat";
}

export const ARROW = { rise: "↑", fall: "↓", flat: "" } as const;
export const TONE = { rise: "text-rise", fall: "text-fall", flat: "text-muted" } as const;

export const GROUPS = ["tw", "us", "index", "commodity", "fx", "crypto"] as const;
export type Group = (typeof GROUPS)[number];

/** Funds that follow a commodity: with the futures, not the stocks (D-080, D-081). */
const COMMODITY_FUNDS = new Set(["us:USO", "us:CORN", "us:SOYB", "us:WEAT"]);
const COMMODITIES = new Set(["wti", "xau", "maize", "soybeans", "wheat"]);

/** Which drawer of the watchlist an item sits in (D-094). */
export function groupOf(key: string): Group {
  if (COMMODITY_FUNDS.has(key) || COMMODITIES.has(key)) return "commodity";
  // 台指期 (D-179) with the Taiwan stocks, where a reader of the Taiwan market looks (D-190)
  if (key.startsWith("tw:") || key === "txf1") return "tw";
  if (key.startsWith("us:")) return "us";
  if (isCurrency(key)) return "fx";
  if (key === "btc" || key === "eth") return "crypto";
  return "index"; // TAIEX, the Nasdaq, the 10-year yield
}
