// 技術指標 (D-096): figures from a stock's daily bars — where the close sits against its moving
// averages, the 14-day RSI, and where it sits in its 52-week range. Figures only: what they
// "mean" for buying or selling is not the site's to say (D-035).
import type { PublicHistory } from "./api";

type Bar = PublicHistory["bars"][number];

export type Technicals = {
  close: number;
  averages: { days: number; value: number; gap: number }[];
  /** Wilder's, 0–100; null with fewer than 15 closes. */
  rsi: number | null;
  range: { low: number; high: number; at: number } | null;
};

export const AVERAGE_DAYS = [20, 60, 200] as const;
const YEAR = 252; // trading days

/** Wilder's RSI over ``period`` days, smoothed through every close given. */
export function rsi(closes: number[], period = 14): number | null {
  if (closes.length <= period) return null;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const move = closes[i] - closes[i - 1];
    gain += Math.max(move, 0);
    loss += Math.max(-move, 0);
  }
  gain /= period;
  loss /= period;
  for (let i = period + 1; i < closes.length; i++) {
    const move = closes[i] - closes[i - 1];
    gain = (gain * (period - 1) + Math.max(move, 0)) / period;
    loss = (loss * (period - 1) + Math.max(-move, 0)) / period;
  }
  if (loss === 0) return gain === 0 ? 50 : 100;
  return 100 - 100 / (1 + gain / loss);
}

/** None without two closes; an average only when there are its days. */
export function technicals(bars: Bar[]): Technicals | null {
  if (bars.length < 2) return null;
  const closes = bars.map((b) => b.c);
  const close = closes[closes.length - 1];
  const averages = AVERAGE_DAYS.filter((days) => closes.length >= days).map((days) => {
    const value = closes.slice(-days).reduce((a, b) => a + b, 0) / days;
    return { days, value, gap: close / value - 1 };
  });
  const year = bars.slice(-YEAR);
  const low = Math.min(...year.map((b) => b.l));
  const high = Math.max(...year.map((b) => b.h));
  return {
    close,
    averages,
    // enough to settle Wilder's smoothing, not five years of it
    rsi: rsi(closes.slice(-YEAR)),
    range: bars.length >= YEAR && high > low ? { low, high, at: (close - low) / (high - low) } : null,
  };
}
