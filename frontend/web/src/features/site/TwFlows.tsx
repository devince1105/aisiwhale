// Taiwan's three institutional investors (HD-12, D-217): a Taiwan stock's last trading days of
// 外資、投信、自營商 net buying, in 張 as Taiwan counts them, its foreign ownership ratio, and a
// trading day's ranking of the most bought and sold. The exchanges' own figures (TWSE, TPEx),
// shown as they are; server-rendered.
import Link from "next/link";

import type { PublicFlowRanking, PublicTwFlows } from "./api";
import { formatDate, words, type Lang } from "./i18n";

export type FlowGroup = "foreign" | "trust" | "dealer" | "total";
export type FlowSide = "buy" | "sell";
const GROUPS: readonly FlowGroup[] = ["foreign", "trust", "dealer", "total"];
const SIDES: readonly FlowSide[] = ["buy", "sell"];

/** Shares as lots of a thousand — 張 — signed: +1,234, −567. */
export function lots(lang: Lang, shares: number | null | undefined): string {
  if (shares === null || shares === undefined) return "—";
  const lot = Math.round(shares / 1000);
  const sign = lot > 0 ? "+" : lot < 0 ? "−" : "";
  return `${sign}${new Intl.NumberFormat(lang).format(Math.abs(lot))}`;
}

function tone(shares: number | null | undefined): string {
  const lot = shares ? Math.round(shares / 1000) : 0;
  return lot > 0 ? "text-rise" : lot < 0 ? "text-fall" : "text-muted";
}

/** A Taiwan stock's page: its last trading days of the three, their sums, its foreign ratio. */
export function TwFlowsSection({
  flows,
  lang,
}: {
  flows: PublicTwFlows | null | undefined;
  lang: Lang;
}) {
  const t = words(lang).twFlows;
  return (
    <section
      className="mt-10"
      aria-labelledby="tw-flows"
      data-testid="tw-flows"
    >
      <h2 id="tw-flows" className="text-xl font-bold">
        {t.heading}
      </h2>
      {!flows || !flows.days.length ? (
        <p className="mt-3 text-muted">{t.none}</p>
      ) : (
        <>
          {flows.foreign_ratio !== null && flows.foreign_ratio !== undefined ? (
            <p className="mt-3 text-sm" data-testid="foreign-ratio">
              <span className="text-muted">{t.ratio}</span>{" "}
              <span className="text-lg font-bold tabular-nums">
                {flows.foreign_ratio.toFixed(2)}%
              </span>
              {flows.foreign_ratio_change !== null &&
              flows.foreign_ratio_change !== undefined ? (
                <span
                  className={`ml-2 text-xs ${flows.foreign_ratio_change > 0 ? "text-rise" : flows.foreign_ratio_change < 0 ? "text-fall" : "text-muted"}`}
                >
                  {t.ratioChange(
                    `${flows.foreign_ratio_change > 0 ? "+" : flows.foreign_ratio_change < 0 ? "−" : ""}${Math.abs(flows.foreign_ratio_change).toFixed(2)}`,
                  )}
                </span>
              ) : null}
              {flows.foreign_ratio_day ? (
                <span className="ml-2 text-xs text-date">
                  {t.asOf(formatDate(lang, flows.foreign_ratio_day))}
                </span>
              ) : null}
            </p>
          ) : null}
          {flows.sums.length ? (
            <dl
              className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4"
              data-testid="flow-sums"
            >
              {GROUPS.map((group) => (
                <div key={group}>
                  <dt className="text-xs text-muted">{t[group]}</dt>
                  {flows.sums.map((sum) => (
                    <dd key={sum.days} className="tabular-nums">
                      <span className="text-xs text-muted">
                        {t.sum(sum.days)}{" "}
                      </span>
                      <span className={tone(sum[group])}>
                        {lots(lang, sum[group])}
                      </span>
                    </dd>
                  ))}
                </div>
              ))}
            </dl>
          ) : null}
          <table
            className="mt-3 w-full text-sm tabular-nums"
            data-testid="flow-days"
          >
            <thead className="text-xs text-muted">
              <tr className="border-b border-line text-left">
                <th className="py-2 font-normal">{t.day}</th>
                {GROUPS.map((group) => (
                  <th key={group} className="py-2 text-right font-normal">
                    {t[group]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {flows.days.map((day) => (
                <tr key={day.day}>
                  <td className="py-2 text-date whitespace-nowrap">
                    {formatDate(lang, day.day)}
                  </td>
                  {GROUPS.map((group) => (
                    <td
                      key={group}
                      className={`py-2 text-right whitespace-nowrap ${tone(day[group])}`}
                    >
                      {lots(lang, day[group])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-muted">{t.unit}</p>
          <p className="mt-1 text-xs text-muted">{t.note}</p>
        </>
      )}
    </section>
  );
}

/** The ranking's two markets: the US filers' 13F, and Taiwan's three institutional investors. */
export function MarketSwitch({
  lang,
  market,
}: {
  lang: Lang;
  market: "us" | "tw";
}) {
  const t = words(lang).twFlows;
  return (
    <Chips
      label={t.market.us}
      items={["us", "tw"] as const}
      current={market}
      href={(m) =>
        m === "us" ? `/news/${lang}/holdings/institutions` : twRankingHref(lang)
      }
      name={(m) => t.market[m]}
    />
  );
}

export interface FlowParams {
  day?: string;
  group?: FlowGroup;
  side?: FlowSide;
}

export function twRankingHref(lang: Lang, params: FlowParams = {}): string {
  const query = new URLSearchParams();
  if (params.day) query.set("day", params.day);
  if (params.group && params.group !== "foreign")
    query.set("group", params.group);
  if (params.side === "sell") query.set("side", "sell");
  const shown = query.toString();
  return `/news/${lang}/holdings/institutions/tw${shown ? `?${shown}` : ""}`;
}

function Chips<T extends string>({
  label,
  items,
  current,
  href,
  name,
}: {
  label: string;
  items: readonly T[];
  current: T;
  href: (item: T) => string;
  name: (item: T) => string;
}) {
  return (
    <nav aria-label={label} className="flex flex-wrap gap-2">
      {items.map((item) => (
        <Link
          key={item}
          href={href(item)}
          aria-current={item === current ? "page" : undefined}
          className={`rounded-full border px-3 py-1 text-xs ${
            item === current
              ? "border-ink bg-ink font-semibold text-surface"
              : "border-line text-muted hover:text-ink"
          }`}
        >
          {name(item)}
        </Link>
      ))}
    </nav>
  );
}

/** A trading day's most bought (or sold) by one of the three, stocks only. */
export function TwRankingView({
  ranking,
  lang,
  params,
}: {
  ranking: PublicFlowRanking;
  lang: Lang;
  params: FlowParams;
}) {
  const t = words(lang).twFlows;
  const group = (ranking.group ?? "foreign") as FlowGroup;
  const side = (ranking.side ?? "buy") as FlowSide;
  const keep = {
    ...params,
    day:
      ranking.day && ranking.day !== ranking.days[0] ? ranking.day : undefined,
  };
  return (
    <>
      <header className="mt-4">
        <h1 className="text-3xl font-bold">{t.rankingHeading}</h1>
        {ranking.day ? (
          <p className="mt-2 text-sm text-muted">
            {t.rankingIntro(formatDate(lang, ranking.day))}
          </p>
        ) : null}
      </header>
      {ranking.day ? (
        <div className="mt-6 space-y-3">
          <Chips
            label={t.groups.total}
            items={GROUPS}
            current={group}
            href={(g) => twRankingHref(lang, { ...keep, group: g })}
            name={(g) => t.groups[g]}
          />
          <Chips
            label={t.sides.buy}
            items={SIDES}
            current={side}
            href={(s) => twRankingHref(lang, { ...keep, group, side: s })}
            name={(s) => t.sides[s]}
          />
          {ranking.days.length > 1 ? (
            <Chips
              label={t.days}
              items={ranking.days.slice(0, 10)}
              current={ranking.day}
              href={(d) =>
                twRankingHref(lang, {
                  group,
                  side,
                  day: d === ranking.days[0] ? undefined : d,
                })
              }
              name={(d) => formatDate(lang, d)}
            />
          ) : null}
        </div>
      ) : null}
      {ranking.rows.length ? (
        <table
          className="mt-4 w-full text-sm tabular-nums"
          data-testid="tw-ranking-table"
        >
          <thead className="text-xs text-muted">
            <tr className="border-b border-line text-left">
              <th className="py-2 pr-2 font-normal whitespace-nowrap">
                {words(lang).ranking.rank}
              </th>
              <th className="py-2 font-normal">{t.stock}</th>
              <th className="py-2 text-right font-normal whitespace-nowrap">
                {t.net}
              </th>
              <th className="py-2 text-right font-normal whitespace-nowrap">
                {t.ratio}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {ranking.rows.map((row) => (
              <tr key={row.symbol} data-testid="tw-rank-row">
                <td className="py-2 pr-2 text-muted">{row.rank}</td>
                <td className="py-2 pr-3">
                  <Link
                    href={`/news/${lang}/stocks/${row.symbol}`}
                    className="font-semibold hover:text-accent"
                  >
                    {row.name}
                  </Link>
                  <span className="ml-2 text-xs text-muted">{row.symbol}</span>
                </td>
                <td
                  className={`py-2 text-right whitespace-nowrap ${tone(row.net)}`}
                >
                  {lots(lang, row.net)}
                </td>
                <td className="py-2 text-right whitespace-nowrap text-muted">
                  {row.foreign_ratio !== null && row.foreign_ratio !== undefined
                    ? `${row.foreign_ratio.toFixed(2)}%`
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="mt-6 text-muted">{t.empty}</p>
      )}
      <p className="mt-6 text-xs text-muted">{t.unit}</p>
      <p className="mt-1 text-xs text-muted">{t.note}</p>
    </>
  );
}
