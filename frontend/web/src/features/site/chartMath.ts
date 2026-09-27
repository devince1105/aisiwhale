// The stock chart's arithmetic (D-059): daily bars into weeks and months, and moving averages.
// Pure, so the chart component only draws.

export interface Bar {
  d: string; // YYYY-MM-DD
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export type Interval = "day" | "week" | "month";

export const AVERAGES = [5, 10, 20, 60, 250] as const;

/** Monday of the week a day is in (ISO weeks), as YYYY-MM-DD. */
function weekOf(day: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  const back = (date.getUTCDay() + 6) % 7; // Monday 0 … Sunday 6
  date.setUTCDate(date.getUTCDate() - back);
  return date.toISOString().slice(0, 10);
}

/** Bars grouped by week or month: first open, highest high, lowest low, last close, summed
 * volume. Each group is dated by its last trading day, so the latest one is today's. */
export function group(bars: readonly Bar[], interval: Interval): Bar[] {
  if (interval === "day") return [...bars];
  const key = interval === "week" ? weekOf : (day: string) => day.slice(0, 7);
  const out: Bar[] = [];
  let current: Bar | null = null;
  let currentKey = "";
  for (const bar of bars) {
    const k = key(bar.d);
    if (current && k === currentKey) {
      current = {
        d: bar.d,
        o: current.o,
        h: Math.max(current.h, bar.h),
        l: Math.min(current.l, bar.l),
        c: bar.c,
        v: current.v + bar.v,
      };
      out[out.length - 1] = current;
    } else {
      current = { ...bar };
      currentKey = k;
      out.push(current);
    }
  }
  return out;
}

/** The ``n``-bar simple moving average of the closes; null until there are ``n`` bars. */
export function movingAverage(bars: readonly Bar[], n: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  bars.forEach((bar, i) => {
    sum += bar.c;
    if (i >= n) sum -= bars[i - n].c;
    out.push(i >= n - 1 ? sum / n : null);
  });
  return out;
}
