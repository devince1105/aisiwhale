"use client";

// A stock's price chart (D-059): the close as a line, its 5/10/20/60/250 moving averages, and
// volume beneath, coloured by the bar's direction (rise red, fall green, as the rest of the site).
// Four views, as the watch page this follows has them: a US stock's last five days in 15-minute
// bars (Taiwan has no free intraday history), a year of days, five years of weeks, every month —
// each with its own span and its own time axis (9/24 for days, 13:30 within a day, 2026/9 for
// months). The legend above follows the pointer and rests on the latest bar. Colours come from the
// page's own tokens, read again when the theme changes.
import {
  AreaSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  TickMarkType,
  createChart,
  type IChartApi,
  type MouseEventParams,
  type Time,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";

import { fetchIntraday } from "./api";
import {
  AVERAGES,
  axisLabel,
  wallClock,
  fullLabel,
  group,
  movingAverage,
  partsOf,
  spanInDays,
  wallSeconds,
  type Bar,
  type View,
} from "./chartMath";
import { words, type Lang } from "./i18n";

/** An average's colour is its span, so 月線 is the same purple over days, weeks and months:
 * 週 blue, 月 purple, 季 orange, 半年 amber, 年 slate, and the monthly view's two and five years. */
const SPAN_COLOURS: [number, string][] = [
  [5, "#6d8dff"],
  [21, "#a855f7"],
  [65, "#f97316"],
  [130, "#eab308"],
  [260, "#94a3b8"],
  [520, "#ec4899"],
  [Infinity, "#06b6d4"],
];
const INTRADAY_COLOURS = ["#6d8dff", "#a855f7", "#f97316", "#eab308"];

function colourOf(view: View, n: number, place: number): string {
  if (view === "intraday") return INTRADAY_COLOURS[place] ?? "#94a3b8";
  const days = spanInDays(view, n);
  return SPAN_COLOURS.find(([upTo]) => days <= upTo)![1];
}
/** How many of the latest bars each view opens on: five days of 15 minutes, a year of days, five
 * years of weeks, every month. Earlier bars are a drag away. */
const OPENS_ON: Record<View, number> = { intraday: Infinity, day: 250, week: 262, month: Infinity };

const TICK_KIND: Record<number, "year" | "month" | "day" | "time"> = {
  [TickMarkType.Year]: "year",
  [TickMarkType.Month]: "month",
  [TickMarkType.DayOfMonth]: "day",
  [TickMarkType.Time]: "time",
  [TickMarkType.TimeWithSeconds]: "time",
};

interface Palette {
  text: string;
  line: string;
  accent: string;
  rise: string;
  fall: string;
}

function palette(element: HTMLElement): Palette {
  const style = getComputedStyle(element);
  const token = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
  return {
    text: token("--color-muted", "#5b6472"),
    line: token("--color-line", "#e3e6eb"),
    accent: token("--color-accent", "#2f5bea"),
    rise: token("--color-rise", "#d64545"),
    fall: token("--color-fall", "#1f9d55"),
  };
}

function alpha(colour: string, amount: string): string {
  return /^#[0-9a-f]{6}$/i.test(colour) ? `${colour}${amount}` : colour;
}

/** The chart's time for a bar: its day as it reads, or (15-minute bars) its wall-clock seconds. */
function timeOf(bar: Bar, view: View): Time {
  return (view === "intraday" ? wallSeconds(bar.d) : bar.d) as Time;
}

type Intraday = { state: "idle" | "loading" | "failed" } | { state: "ready"; source: string | null; bars: Bar[] };

/** Decimals for a price this size: a stock's two, a rate's more — the yen in NT$ is 0.2017, not
 * 0.2 (D-072). */
export function decimalsFor(price: number): number {
  const size = Math.abs(price);
  return size < 1 ? 4 : size < 10 ? 3 : 2;
}

export function StockChart({
  bars,
  lang,
  market,
  symbol,
  source,
  preparing = false,
  volume = true,
  closeOnly = false,
  decimals,
  monthly = false,
}: {
  bars: Bar[];
  lang: Lang;
  market: string;
  symbol: string;
  source: string | null;
  /** A Taiwan stock just asked for: its history is being fetched (D-061). */
  preparing?: boolean;
  /** Gold has none (D-070): no volume pane, and none in the legend. */
  volume?: boolean;
  /** Each day's close and nothing else (D-072: FRED's figures, a currency cross): the legend
   * gives the close alone. */
  closeOnly?: boolean;
  /** Its prices' decimals, when not a stock's (``decimalsFor``): a currency as a bank posts it,
   * a yield's two. */
  decimals?: number;
  /** A bar a month (the IMF's grain prices, D-080): its months only, no days or weeks. */
  monthly?: boolean;
}) {
  const w = words(lang).chart;
  const box = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<View>(monthly ? "month" : "day");
  const [intraday, setIntraday] = useState<Intraday>({ state: "idle" });
  // 15 minutes only when there are such bars to show: a US stock (Tiingo) or a Taiwan one (Fugle,
  // D-074) whose service answered with some
  const views: View[] = monthly
    ? ["month"]
    : intraday.state === "ready" && intraday.bars.length
      ? ["intraday", "day", "week", "month"]
      : ["day", "week", "month"];
  const shown = useMemo(() => {
    if (view === "intraday") return intraday.state === "ready" ? intraday.bars : [];
    return group(bars, view);
  }, [bars, view, intraday]);
  const averages = useMemo(
    () =>
      Object.fromEntries(AVERAGES[view].map((n) => [n, movingAverage(shown, n)])) as Record<number, (number | null)[]>,
    [shown, view],
  );
  const [pointed, setPointed] = useState<number | null>(null);
  const [theme, setTheme] = useState(0);

  // a stock's 15-minute bars are asked for once, after the page: the button appears if any came
  useEffect(() => {
    if ((market !== "us" && market !== "tw") || intraday.state !== "idle") return;
    setIntraday({ state: "loading" });
    const zone = market === "tw" ? "Asia/Taipei" : "America/New_York";
    fetchIntraday(symbol)
      .then((answer) =>
        setIntraday({
          state: "ready",
          source: answer.source ?? null,
          bars: answer.bars.map((b) => ({ d: wallClock(b.t, zone), o: b.o, h: b.h, l: b.l, c: b.c, v: b.v })),
        }),
      )
      .catch(() => setIntraday({ state: "failed" }));
  }, [market, intraday.state, symbol]);

  // the site's theme: the reader's pick (data-theme on the site root, set when they choose) or
  // else the system's. Redraw in the new colours when either changes.
  useEffect(() => {
    const redraw = () => setTheme((n) => n + 1);
    const root = box.current?.closest("[data-site]");
    const observer = new MutationObserver(redraw);
    if (root) observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    const system = window.matchMedia?.("(prefers-color-scheme: dark)");
    system?.addEventListener("change", redraw);
    return () => {
      observer.disconnect();
      system?.removeEventListener("change", redraw);
    };
  }, []);

  useEffect(() => {
    const element = box.current;
    if (!element || !shown.length) return;
    const colours = palette(element);
    const digits = decimals ?? decimalsFor(shown[shown.length - 1].c);
    const priceFormat = { type: "price" as const, precision: digits, minMove: 1 / 10 ** digits };
    const chart: IChartApi = createChart(element, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: colours.text,
        fontSize: 11,
        attributionLogo: true,
        panes: { separatorColor: colours.line },
      },
      grid: { vertLines: { color: alpha(colours.line, "80") }, horzLines: { color: alpha(colours.line, "80") } },
      rightPriceScale: { borderColor: colours.line },
      timeScale: {
        borderColor: colours.line,
        timeVisible: view === "intraday",
        tickMarkFormatter: (time: Time, type: TickMarkType) =>
          axisLabel(partsOf(time), view, TICK_KIND[type] ?? "day"),
      },
      crosshair: { mode: CrosshairMode.Magnet },
      localization: {
        locale: lang === "en" ? "en-US" : "zh-TW",
        timeFormatter: (time: Time) => fullLabel(partsOf(time), view),
      },
    });
    const price = chart.addSeries(AreaSeries, {
      lineColor: colours.accent,
      topColor: alpha(colours.accent, "40"),
      bottomColor: alpha(colours.accent, "00"),
      lineWidth: 2,
      priceLineVisible: false,
      priceFormat,
    });
    price.setData(shown.map((bar) => ({ time: timeOf(bar, view), value: bar.c })));
    for (const [place, n] of AVERAGES[view].entries()) {
      const line = chart.addSeries(LineSeries, {
        color: colourOf(view, n, place),
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
        priceFormat,
      });
      line.setData(
        shown.flatMap((bar, i) => {
          const value = averages[n][i];
          return value === null ? [] : [{ time: timeOf(bar, view), value }];
        }),
      );
    }
    if (volume) {
      const traded = chart.addSeries(
        HistogramSeries,
        { priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false },
        1,
      );
      traded.setData(
        shown.map((bar) => ({
          time: timeOf(bar, view),
          value: bar.v,
          color: alpha(bar.c >= bar.o ? colours.rise : colours.fall, "b3"),
        })),
      );
      chart.panes()[1]?.setHeight(90);
    }
    const opens = OPENS_ON[view];
    if (shown.length > opens) {
      chart.timeScale().setVisibleLogicalRange({ from: shown.length - opens, to: shown.length - 0.5 });
    } else {
      chart.timeScale().fitContent();
    }

    const index = new Map(shown.map((bar, i) => [String(timeOf(bar, view)), i]));
    const onMove = (param: MouseEventParams<Time>) => {
      setPointed(param.time === undefined ? null : (index.get(String(param.time)) ?? null));
    };
    chart.subscribeCrosshairMove(onMove);
    return () => {
      chart.unsubscribeCrosshairMove(onMove);
      chart.remove();
    };
  }, [shown, averages, view, lang, theme, volume, decimals]);

  if (!bars.length) {
    return (
      <p className="rounded-lg border border-line p-4 text-sm text-muted" data-testid="chart-empty">
        {preparing ? w.preparing : w.none}
      </p>
    );
  }
  const digits = decimals ?? (shown.length ? decimalsFor(shown[shown.length - 1].c) : 2);
  const number = (value: number, places = digits) =>
    value.toLocaleString(lang === "en" ? "en-US" : "zh-TW", { maximumFractionDigits: places });
  const at = Math.min(pointed ?? shown.length - 1, shown.length - 1);
  const bar = shown[at];
  const previous = at > 0 ? shown[at - 1].c : null;
  const tone = (value: number) =>
    previous === null || value === previous ? "" : value > previous ? "text-rise" : "text-fall";

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs tabular-nums" data-testid="chart-legend">
          {bar ? (
            <>
              <span className="font-medium">{fullLabel(partsOf(timeOf(bar, view)), view)}</span>
              {(closeOnly ? (["c"] as const) : (["o", "h", "l", "c"] as const)).map((k) => (
                <span key={k}>
                  <span className="text-muted">{w.ohlc[k]}</span> <span className={tone(bar[k])}>{number(bar[k])}</span>
                </span>
              ))}
              {volume ? (
                <span>
                  <span className="text-muted">{w.volume}</span>{" "}
                  {market === "tw" ? `${number(Math.round(bar.v / 1000), 0)} ${w.lots}` : number(bar.v, 0)}
                </span>
              ) : null}
            </>
          ) : null}
        </div>
        <div className="flex overflow-hidden rounded-md border border-line text-xs" role="group" aria-label={w.title}>
          {views.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => {
                setView(value);
                setPointed(null);
              }}
              aria-pressed={view === value}
              className={`px-3 py-1 ${view === value ? "bg-accent text-accent-ink" : "text-muted"}`}
            >
              {w.intervals[value]}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 text-xs tabular-nums">
        {bar
          ? AVERAGES[view].map((n, place) => {
              const value = averages[n]?.[at];
              return (
                <span key={n} style={{ color: colourOf(view, n, place) }} title={w.averageTitle(view, n)}>
                  {w.average(view, n)} {value === null || value === undefined ? "--" : number(value)}
                </span>
              );
            })
          : null}
      </div>
      <div ref={box} className="mt-2 h-80 w-full" data-testid="stock-chart" />
      <p className="mt-2 text-xs text-muted">
        {view === "intraday" ? `${market === "tw" ? w.intradayNoteTw : w.intradayNote} ` : ""}
        {source
          ? w.source(
              view === "intraday" && intraday.state === "ready" ? (intraday.source ?? source) : source,
              market === "us" && source === "Tiingo" && view !== "intraday",
            )
          : ""}
      </p>
    </div>
  );
}
