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

// --- time on the chart ----------------------------------------------------------------------------

/** What the chart shows: a US stock's 15-minute bars (intraday), or days grouped. */
export type View = "intraday" | Interval;

/** Each view's moving averages, in its own bars. Across the days, weeks and months the same
 * names mean the same span, as a Taiwan reader knows them: 月線 is 20 days, 4 weeks; 季線 60 days,
 * 13 weeks, 3 months; 年線 240 days, 52 weeks, 12 months. The 15-minute bars have plain counts. */
export const AVERAGES: Record<View, readonly number[]> = {
  intraday: [5, 10, 20, 60],
  day: [5, 20, 60, 120, 240],
  week: [4, 13, 26, 52],
  month: [3, 6, 12, 24, 60],
};

/** A bar's start in US Eastern wall-clock time, "YYYY-MM-DD HH:mm": the market's own hours. */
export function eastern(iso: string): string {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(new Date(iso))
      .map((p) => [p.type, p.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
}

/** A wall-clock "YYYY-MM-DD HH:mm" as the chart's seconds: drawn as it reads, not shifted. */
export function wallSeconds(d: string): number {
  const [day, time = "00:00"] = d.split(" ");
  const [y, m, dd] = day.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  return Date.UTC(y, m - 1, dd, hh, mm) / 1000;
}

export interface Parts {
  y: number;
  m: number;
  d: number;
  hh: number;
  mm: number;
}

/** The chart's time back as parts: seconds (intraday), "YYYY-MM-DD", or {year, month, day}. */
export function partsOf(time: unknown): Parts {
  if (typeof time === "number") {
    const t = new Date(time * 1000);
    return { y: t.getUTCFullYear(), m: t.getUTCMonth() + 1, d: t.getUTCDate(), hh: t.getUTCHours(), mm: t.getUTCMinutes() };
  }
  if (typeof time === "string") {
    const [y, m, d] = time.slice(0, 10).split("-").map(Number);
    return { y, m, d, hh: 0, mm: 0 };
  }
  const day = time as { year: number; month: number; day: number };
  return { y: day.year, m: day.month, d: day.day, hh: 0, mm: 0 };
}

const two = (n: number) => String(n).padStart(2, "0");

/** A tick on the time axis, as each view reads it: trading days as 9/24, a new day of 15-minute
 * bars as its date and the rest as times, months as 2026/9; a new year as the year. */
export function axisLabel(p: Parts, view: View, kind: "year" | "month" | "day" | "time"): string {
  if (view === "intraday") return kind === "time" ? `${two(p.hh)}:${two(p.mm)}` : `${p.m}/${p.d}`;
  if (view === "month") return kind === "year" ? `${p.y}` : `${p.y}/${p.m}`;
  return kind === "year" ? `${p.y}` : `${p.m}/${p.d}`;
}

/** A bar's date in the legend and under the crosshair. */
export function fullLabel(p: Parts, view: View): string {
  if (view === "intraday") return `${p.m}/${p.d} ${two(p.hh)}:${two(p.mm)}`;
  if (view === "month") return `${p.y}/${p.m}`;
  return `${p.y}/${p.m}/${p.d}`;
}

/** Roughly how many trading days an average spans: what its colour says, in every view. */
export function spanInDays(view: View, n: number): number {
  return view === "week" ? n * 5 : view === "month" ? n * 21 : n;
}
