"use client";

// A stock's price chart (D-059): the close as a line over day, week or month bars, its 5/10/20/
// 60/250 moving averages, and volume beneath, coloured by the bar's direction (rise red, fall
// green, as the rest of the site). The legend above follows the pointer and rests on the latest
// bar. Colours come from the page's own tokens, read again when the theme changes.
import {
  AreaSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type MouseEventParams,
  type Time,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";

import { AVERAGES, group, movingAverage, type Bar, type Interval } from "./chartMath";
import { words, type Lang } from "./i18n";

const MA_COLOURS: Record<number, string> = {
  5: "#6d8dff",
  10: "#a855f7",
  20: "#f97316",
  60: "#eab308",
  250: "#94a3b8",
};
const INTERVALS: Interval[] = ["day", "week", "month"];

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

export function StockChart({
  bars,
  lang,
  market,
  source,
}: {
  bars: Bar[];
  lang: Lang;
  market: string;
  source: string | null;
}) {
  const w = words(lang).chart;
  const box = useRef<HTMLDivElement>(null);
  const [interval, setInterval_] = useState<Interval>("day");
  const shown = useMemo(() => group(bars, interval), [bars, interval]);
  const averages = useMemo(
    () => Object.fromEntries(AVERAGES.map((n) => [n, movingAverage(shown, n)])) as Record<number, (number | null)[]>,
    [shown],
  );
  const [pointed, setPointed] = useState<number | null>(null);
  const [theme, setTheme] = useState(0);

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
      timeScale: { borderColor: colours.line },
      crosshair: { mode: CrosshairMode.Magnet },
      localization: { locale: lang === "en" ? "en-US" : "zh-TW" },
    });
    const time = (bar: Bar) => bar.d as Time;
    const price = chart.addSeries(AreaSeries, {
      lineColor: colours.accent,
      topColor: alpha(colours.accent, "40"),
      bottomColor: alpha(colours.accent, "00"),
      lineWidth: 2,
      priceLineVisible: false,
    });
    price.setData(shown.map((bar) => ({ time: time(bar), value: bar.c })));
    for (const n of AVERAGES) {
      const line = chart.addSeries(LineSeries, {
        color: MA_COLOURS[n],
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      line.setData(
        shown.flatMap((bar, i) => {
          const value = averages[n][i];
          return value === null ? [] : [{ time: time(bar), value }];
        }),
      );
    }
    const volume = chart.addSeries(
      HistogramSeries,
      { priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false },
      1,
    );
    volume.setData(
      shown.map((bar) => ({
        time: time(bar),
        value: bar.v,
        color: alpha(bar.c >= bar.o ? colours.rise : colours.fall, "b3"),
      })),
    );
    chart.panes()[1]?.setHeight(90);
    chart.timeScale().fitContent();

    const index = new Map(shown.map((bar, i) => [bar.d, i]));
    const onMove = (param: MouseEventParams<Time>) => {
      setPointed(param.time === undefined ? null : (index.get(String(param.time)) ?? null));
    };
    chart.subscribeCrosshairMove(onMove);
    return () => {
      chart.unsubscribeCrosshairMove(onMove);
      chart.remove();
    };
  }, [shown, averages, lang, theme]);

  if (!bars.length) {
    return <p className="text-sm text-muted">{w.none}</p>;
  }
  const at = pointed ?? shown.length - 1;
  const bar = shown[at];
  const previous = at > 0 ? shown[at - 1].c : null;
  const tone = (value: number) =>
    previous === null || value === previous ? "" : value > previous ? "text-rise" : "text-fall";
  const number = (value: number) =>
    value.toLocaleString(lang === "en" ? "en-US" : "zh-TW", { maximumFractionDigits: 2 });
  const shares = market === "tw" ? `${number(bar.v / 1000)} ${w.lots}` : number(bar.v);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs tabular-nums" data-testid="chart-legend">
          <span className="font-medium">{bar.d}</span>
          {(["o", "h", "l", "c"] as const).map((k) => (
            <span key={k}>
              <span className="text-muted">{w.ohlc[k]}</span> <span className={tone(bar[k])}>{number(bar[k])}</span>
            </span>
          ))}
          <span>
            <span className="text-muted">{w.volume}</span> {shares}
          </span>
        </div>
        <div className="flex overflow-hidden rounded-md border border-line text-xs" role="group" aria-label={w.title}>
          {INTERVALS.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => {
                setInterval_(value);
                setPointed(null);
              }}
              aria-pressed={interval === value}
              className={`px-3 py-1 ${interval === value ? "bg-accent text-accent-ink" : "text-muted"}`}
            >
              {w.intervals[value]}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 text-xs tabular-nums">
        {AVERAGES.map((n) => {
          const value = averages[n][at];
          return (
            <span key={n} style={{ color: MA_COLOURS[n] }}>
              MA{n} {value === null ? "--" : number(value)}
            </span>
          );
        })}
      </div>
      <div ref={box} className="mt-2 h-80 w-full" data-testid="stock-chart" />
      {source ? <p className="mt-2 text-xs text-muted">{w.source(source, source === "Tiingo")}</p> : null}
    </div>
  );
}
