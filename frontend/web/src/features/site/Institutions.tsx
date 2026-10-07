// 機構排行 and an institution's page (HD-11, D-217): every 13F filer's quarter by the value of
// its US holdings, searched and sorted — the brokers' "all institutions" list, in Taiwan's words
// (持股, 兆, 億) — and a page for each, its largest holdings, its biggest buys and sells and an
// estimate of what it bought and sold. Server-rendered; a search is a plain GET form. The numbers
// are SEC's filings and arithmetic on them, never advice.
import Link from "next/link";

import type {
  PublicInstitution,
  PublicInstitutionHolding,
  PublicRankRow,
  PublicRanking,
} from "./api";
import { formatDate, words, type Lang } from "./i18n";
import { portfolioHref, quarterOf, watchHref } from "./Portfolios";

export type RankSort = "value" | "change" | "filed";

export interface RankingParams {
  period?: string;
  q?: string;
  sort?: RankSort;
  order?: "desc" | "asc";
  page?: number;
}

export const RANK_PAGE = 50;

export function rankingHref(lang: Lang, params: RankingParams = {}): string {
  const query = new URLSearchParams();
  if (params.period) query.set("period", params.period);
  if (params.q) query.set("q", params.q);
  if (params.sort && params.sort !== "value") query.set("sort", params.sort);
  if (params.order === "asc") query.set("order", "asc");
  if (params.page && params.page > 1) query.set("page", String(params.page));
  const shown = query.toString();
  return `/news/${lang}/holdings/institutions${shown ? `?${shown}` : ""}`;
}

export function institutionHref(
  lang: Lang,
  cik: string,
  period?: string,
): string {
  return `/news/${lang}/holdings/institutions/${cik}${period ? `?period=${period}` : ""}`;
}

const SCALES: [number, string][] = [
  [1e12, "兆"],
  [1e8, "億"],
  [1e4, "萬"],
];

/** A large US$ amount, as Taiwan's press writes it — 6.73 兆, 9,991.25 億 — or in English
 * US$6.73T; ``signed`` puts its sign in front (+1,234.56 億, −912.35 億). */
export function bigUsd(lang: Lang, value: number, signed = false): string {
  const sign = signed
    ? value > 0
      ? "+"
      : value < 0
        ? "−"
        : ""
    : value < 0
      ? "−"
      : "";
  const size = Math.abs(value);
  if (lang === "zh-TW") {
    const [unit, word] = SCALES.find(([at]) => size >= at) ?? [1, ""];
    const shown = new Intl.NumberFormat(lang, {
      minimumFractionDigits: unit > 1 ? 2 : 0,
      maximumFractionDigits: 2,
    }).format(size / unit);
    return `${sign}${shown}${word ? ` ${word}` : ""}`;
  }
  const short = new Intl.NumberFormat(lang, {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(size);
  return `${sign}US$${short}`;
}

function count(lang: Lang, value: number): string {
  return new Intl.NumberFormat(lang).format(value);
}

function tone(value: number | null | undefined): string {
  return !value ? "text-muted" : value > 0 ? "text-rise" : "text-fall";
}

function pct(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(2)}%`;
}

function Breadcrumb({
  lang,
  here,
}: {
  lang: Lang;
  here: { label: string; href?: string }[];
}) {
  const r = words(lang).ranking;
  return (
    <nav aria-label="breadcrumb" className="text-sm text-muted">
      <Link href={watchHref(lang, "people")} className="hover:text-accent">
        {r.back}
      </Link>{" "}
      ›{" "}
      <Link href={watchHref(lang, "groups")} className="hover:text-accent">
        {r.groups}
      </Link>
      {here.map(({ label, href }) => (
        <span key={label}>
          {" "}
          ›{" "}
          {href ? (
            <Link href={href} className="hover:text-accent">
              {label}
            </Link>
          ) : (
            label
          )}
        </span>
      ))}
    </nav>
  );
}

/** A filer's units, where they need saying: filed in thousands (converted), or not yet known. */
function Units({
  row,
  lang,
}: {
  row: Pick<PublicRankRow, "in_thousands" | "in_doubt">;
  lang: Lang;
}) {
  const r = words(lang).ranking;
  if (row.in_thousands)
    return (
      <span className="block text-xs whitespace-normal text-muted">
        {r.inThousands}
      </span>
    );
  if (row.in_doubt)
    return (
      <span className="block text-xs whitespace-normal text-muted">
        {r.inDoubt}
      </span>
    );
  return null;
}

function Change({
  row,
  lang,
}: {
  row: Pick<PublicRankRow, "change_usd" | "change_pct">;
  lang: Lang;
}) {
  const r = words(lang).ranking;
  if (row.change_usd === null || row.change_usd === undefined)
    return <span className="text-muted">{r.noPrevious}</span>;
  const share = row.change_pct !== null && row.change_pct !== undefined;
  return (
    <span className={tone(row.change_usd)}>
      {/* a phone has room for the percentage only */}
      <span className={share ? "hidden sm:block" : "block"}>
        {bigUsd(lang, row.change_usd, true)}
      </span>
      {share ? (
        <span className="block sm:text-xs">
          {pct(row.change_pct as number)}
        </span>
      ) : null}
    </span>
  );
}

function RankRow({
  row,
  lang,
  period,
}: {
  row: PublicRankRow;
  lang: Lang;
  period: string;
}) {
  const r = words(lang).ranking;
  return (
    <tr data-testid="rank-row">
      <td className="py-2 pr-2 text-muted">{row.rank}</td>
      <td className="max-w-[9rem] py-2 pr-3 sm:max-w-[18rem]">
        <Link
          href={institutionHref(lang, row.cik, period)}
          className="block truncate font-semibold hover:text-accent"
        >
          {row.name}
        </Link>
        {row.profile ? (
          <Link
            href={portfolioHref(lang, row.profile)}
            className="mt-0.5 inline-block rounded-full border border-line px-2 text-xs text-muted hover:text-accent"
          >
            {r.followed}
          </Link>
        ) : null}
        {row.name !== row.filed_name ? (
          <span className="hidden truncate text-xs text-muted sm:block">
            {row.filed_name}
          </span>
        ) : null}
      </td>
      <td className="py-2 text-right whitespace-nowrap">
        {bigUsd(lang, row.value_usd)}
        <Units row={row} lang={lang} />
      </td>
      <td className="py-2 pl-3 text-right whitespace-nowrap">
        <Change row={row} lang={lang} />
      </td>
      <td className="hidden py-2 text-right sm:table-cell">
        {count(lang, row.entries)}
      </td>
      <td className="hidden py-2 text-right text-date md:table-cell">
        {formatDate(lang, row.filed)}
      </td>
    </tr>
  );
}

function SortLink({
  lang,
  params,
  sort,
  label,
  align = "right",
}: {
  lang: Lang;
  params: RankingParams;
  sort: RankSort;
  label: string;
  align?: "left" | "right";
}) {
  const current = (params.sort ?? "value") === sort;
  const order = current && params.order !== "asc" ? "asc" : "desc";
  return (
    <Link
      href={rankingHref(lang, { ...params, sort, order, page: 1 })}
      aria-current={current ? "true" : undefined}
      className={`hover:text-ink ${current ? "font-semibold text-ink" : ""} ${align === "right" ? "ml-auto" : ""}`}
    >
      {label}
      {current ? (params.order === "asc" ? " ↑" : " ↓") : ""}
    </Link>
  );
}

/** The whole ranking: search, the quarters, the table sorted, a page of it. */
export function RankingView({
  ranking,
  lang,
  params,
}: {
  ranking: PublicRanking;
  lang: Lang;
  params: RankingParams;
}) {
  const r = words(lang).ranking;
  const period = ranking.period;
  const page = params.page ?? 1;
  const pages = Math.max(1, Math.ceil(ranking.total / RANK_PAGE));
  const keep = {
    ...params,
    period: period === ranking.periods[0] ? undefined : period,
  };
  return (
    <article className="mx-auto max-w-[56rem] px-4 pt-4 pb-12">
      <Breadcrumb lang={lang} here={[{ label: r.title }]} />
      <header className="mt-4">
        <h1 className="text-3xl font-bold">{r.heading}</h1>
        {ranking.filers ? (
          <p className="mt-2 text-sm text-muted">
            {r.intro(quarterOf(lang, period), count(lang, ranking.filers))}
          </p>
        ) : null}
      </header>

      <form
        method="get"
        action={rankingHref(lang)}
        role="search"
        className="mt-6 flex flex-wrap items-center gap-2"
      >
        <label className="sr-only" htmlFor="ranking-q">
          {r.search}
        </label>
        <input
          id="ranking-q"
          name="q"
          type="search"
          defaultValue={params.q ?? ""}
          placeholder={r.searchPlaceholder}
          className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm"
        />
        {keep.period ? (
          <input type="hidden" name="period" value={keep.period} />
        ) : null}
        {params.sort && params.sort !== "value" ? (
          <input type="hidden" name="sort" value={params.sort} />
        ) : null}
        {params.order === "asc" ? (
          <input type="hidden" name="order" value="asc" />
        ) : null}
        <button
          type="submit"
          className="rounded-lg bg-ink px-4 py-2 text-sm text-surface"
        >
          {r.submit}
        </button>
        {params.q ? (
          <Link
            href={rankingHref(lang, { ...keep, q: undefined, page: 1 })}
            className="text-sm text-muted hover:text-ink"
          >
            {r.clear}
          </Link>
        ) : null}
      </form>

      {ranking.periods.length > 1 ? (
        <nav aria-label={r.quarters} className="mt-4 flex flex-wrap gap-2">
          {ranking.periods.map((p) => (
            <Link
              key={p}
              href={rankingHref(lang, {
                ...params,
                period: p === ranking.periods[0] ? undefined : p,
                page: 1,
              })}
              aria-current={p === period ? "page" : undefined}
              className={`rounded-full border px-3 py-1 text-xs ${
                p === period
                  ? "border-ink bg-ink font-semibold text-surface"
                  : "border-line text-muted hover:text-ink"
              }`}
            >
              {quarterOf(lang, p)}
            </Link>
          ))}
        </nav>
      ) : null}

      <p className="mt-4 text-xs text-muted">{r.changeNote}</p>

      {ranking.rows.length ? (
        <div className="mt-3 overflow-x-auto">
          <table
            className="w-full text-sm tabular-nums"
            data-testid="ranking-table"
          >
            <thead className="text-xs text-muted">
              <tr className="border-b border-line text-left">
                <th className="py-2 pr-2 font-normal whitespace-nowrap">
                  {r.rank}
                </th>
                <th className="py-2 font-normal">{r.name}</th>
                <th className="py-2 text-right font-normal whitespace-nowrap">
                  <SortLink
                    lang={lang}
                    params={keep}
                    sort="value"
                    label={r.value}
                  />
                </th>
                <th className="py-2 text-right font-normal whitespace-nowrap">
                  <SortLink
                    lang={lang}
                    params={keep}
                    sort="change"
                    label={r.change}
                  />
                </th>
                <th className="hidden py-2 text-right font-normal sm:table-cell">
                  {r.entries}
                </th>
                <th className="hidden py-2 text-right font-normal md:table-cell">
                  <SortLink
                    lang={lang}
                    params={keep}
                    sort="filed"
                    label={r.filed}
                  />
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {ranking.rows.map((row) => (
                <RankRow key={row.cik} row={row} lang={lang} period={period} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-6 text-muted">
          {params.q ? r.noMatch(params.q) : r.empty}
        </p>
      )}

      {ranking.total ? (
        <nav
          aria-label={r.page(page, pages)}
          className="mt-4 flex items-center justify-between text-sm"
        >
          <span className="text-muted">
            {r.total(count(lang, ranking.total))}・{r.page(page, pages)}
          </span>
          <span className="flex gap-4">
            {page > 1 ? (
              <Link
                href={rankingHref(lang, { ...keep, page: page - 1 })}
                className="text-accent hover:underline"
              >
                {r.prev}
              </Link>
            ) : null}
            {page < pages ? (
              <Link
                href={rankingHref(lang, { ...keep, page: page + 1 })}
                className="text-accent hover:underline"
              >
                {r.next}
              </Link>
            ) : null}
          </span>
        </nav>
      ) : null}

      <p className="mt-8 text-xs text-muted">{r.note}</p>
    </article>
  );
}

/** The ranking's first ten, under the institutions' cards on 持股觀察. */
export function TopRanking({
  ranking,
  lang,
}: {
  ranking: PublicRanking;
  lang: Lang;
}) {
  const r = words(lang).ranking;
  if (!ranking.rows.length) return null;
  return (
    <section
      aria-labelledby="top-ranking"
      className="mt-10"
      data-testid="top-ranking"
    >
      <div className="flex items-baseline justify-between gap-4">
        <h2 id="top-ranking" className="text-xl font-bold">
          {r.top}
        </h2>
        <Link
          href={rankingHref(lang)}
          className="text-sm text-accent hover:underline"
        >
          {r.seeAll} →
        </Link>
      </div>
      <p className="mt-1 text-xs text-muted">
        {quarterOf(lang, ranking.period)}
      </p>
      <table className="mt-3 w-full text-sm tabular-nums">
        <thead className="text-xs text-muted">
          <tr className="border-b border-line text-left">
            <th className="py-2 pr-2 font-normal whitespace-nowrap">
              {r.rank}
            </th>
            <th className="py-2 font-normal">{r.name}</th>
            <th className="py-2 text-right font-normal whitespace-nowrap">
              {r.value}
            </th>
            <th className="py-2 text-right font-normal whitespace-nowrap">
              {r.change}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {ranking.rows.map((row) => (
            <tr key={row.cik} data-testid="rank-row">
              <td className="py-2 pr-2 text-muted">{row.rank}</td>
              <td className="py-2 pr-3">
                <Link
                  href={institutionHref(lang, row.cik)}
                  className="font-semibold hover:text-accent"
                >
                  {row.name}
                </Link>
              </td>
              <td className="py-2 text-right whitespace-nowrap">
                {bigUsd(lang, row.value_usd)}
                <Units row={row} lang={lang} />
              </td>
              <td className="py-2 pl-3 text-right whitespace-nowrap">
                <Change row={row} lang={lang} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function HoldingName({
  row,
  lang,
}: {
  row: PublicInstitutionHolding;
  lang: Lang;
}) {
  return (
    <>
      {row.symbol ? (
        <Link
          href={`/news/${lang}/stocks/${row.symbol}`}
          className="font-semibold hover:text-accent"
        >
          {row.symbol}
        </Link>
      ) : null}
      <span
        className={`block truncate ${row.symbol ? "text-xs text-muted" : ""}`}
      >
        {row.name}
      </span>
      {/* Alphabet is two lines, CL A and CL C: the class tells them apart */}
      <span className="block truncate text-xs text-muted">
        {row.title_of_class}
      </span>
    </>
  );
}

function Moves({
  rows,
  lang,
  heading,
  id,
}: {
  rows: PublicInstitutionHolding[];
  lang: Lang;
  heading: string;
  id: string;
}) {
  const n = words(lang).institution;
  const changes = words(lang).stock.changes;
  return (
    <section aria-labelledby={id} className="min-w-0">
      <h3 id={id} className="font-semibold">
        {heading}
      </h3>
      {rows.length ? (
        <ul className="mt-2 divide-y divide-line text-sm tabular-nums">
          {rows.map((row) => (
            <li
              key={row.cusip}
              className="flex items-baseline justify-between gap-3 py-2"
              data-testid="move"
            >
              <span className="min-w-0">
                <HoldingName row={row} lang={lang} />
                <span className="block text-xs text-muted">
                  {row.change ? (changes[row.change] ?? row.change) : ""}
                  {row.split ? `・${n.split(row.split)}` : ""}
                </span>
              </span>
              <span className={`shrink-0 ${tone(row.traded_usd)}`}>
                {row.traded_usd !== null && row.traded_usd !== undefined
                  ? bigUsd(lang, row.traded_usd, true)
                  : "—"}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-muted">{n.noMoves}</p>
      )}
    </section>
  );
}

/** An institution's page: its quarter's numbers and what was worked out from its tables. */
export function InstitutionView({
  page,
  lang,
  loginHref,
}: {
  page: PublicInstitution;
  lang: Lang;
  /** Where a reader not signed in goes for the rest (D-159). */
  loginHref: string;
}) {
  const r = words(lang).ranking;
  const n = words(lang).institution;
  const changes = words(lang).stock.changes;
  const quarter = quarterOf(lang, page.period);
  return (
    <article className="mx-auto max-w-[46rem] px-4 pt-4 pb-12">
      <Breadcrumb
        lang={lang}
        here={[
          { label: r.title, href: rankingHref(lang) },
          { label: page.name },
        ]}
      />

      <header className="mt-4">
        <h1 className="text-3xl font-bold">{page.name}</h1>
        <p className="mt-1 text-sm text-muted">
          {page.name !== page.filed_name ? `${page.filed_name}・` : ""}
          {n.cik(page.cik)}
          {page.profile ? (
            <>
              {"・"}
              <Link
                href={portfolioHref(lang, page.profile)}
                className="text-accent hover:underline"
              >
                {n.card}
              </Link>
            </>
          ) : null}
        </p>
        <p className="mt-1 text-sm text-muted">
          {n.quarter(quarter)}
          {page.rank ? `・${n.rank(count(lang, page.rank))}` : ""}
        </p>
      </header>

      {page.periods.length > 1 ? (
        <nav aria-label={r.quarters} className="mt-4 flex flex-wrap gap-2">
          {page.periods.map((p) => (
            <Link
              key={p}
              href={institutionHref(
                lang,
                page.cik,
                p === page.periods[0] ? undefined : p,
              )}
              aria-current={p === page.period ? "page" : undefined}
              className={`rounded-full border px-3 py-1 text-xs ${
                p === page.period
                  ? "border-ink bg-ink font-semibold text-surface"
                  : "border-line text-muted hover:text-ink"
              }`}
            >
              {quarterOf(lang, p)}
            </Link>
          ))}
        </nav>
      ) : null}

      <dl
        className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4"
        data-testid="institution-figures"
      >
        <div>
          <dt className="text-xs text-muted">{n.value}</dt>
          <dd className="text-xl font-bold tabular-nums">
            {bigUsd(lang, page.value_usd)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{n.change}</dt>
          <dd className="text-xl font-bold tabular-nums">
            <Change
              row={{ change_usd: page.change_usd, change_pct: null }}
              lang={lang}
            />
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{n.entries}</dt>
          <dd className="text-xl font-bold tabular-nums">
            {count(lang, page.entries)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{n.netBought}</dt>
          <dd
            className={`text-xl font-bold tabular-nums ${tone(page.net_bought_usd)}`}
          >
            {page.net_bought_usd !== null && page.net_bought_usd !== undefined
              ? bigUsd(lang, page.net_bought_usd, true)
              : "—"}
          </dd>
        </div>
      </dl>
      {page.in_thousands ? (
        <p className="mt-3 text-xs text-muted">{n.inThousands}</p>
      ) : null}
      {page.in_doubt ? (
        <p className="mt-3 text-xs text-muted">{n.inDoubt}</p>
      ) : null}
      <p className="mt-3 text-xs text-muted">{r.changeNote}</p>

      {page.status === "queued" ? (
        <p
          className="mt-6 rounded-lg border border-line px-4 py-3 text-sm"
          data-testid="queued"
        >
          {n.queued}
        </p>
      ) : page.status === "failed" ? (
        <p className="mt-6 rounded-lg border border-line px-4 py-3 text-sm text-muted">
          {n.failed}
        </p>
      ) : (
        <>
          <details className="mt-6 rounded-lg border border-line bg-surface px-4 py-3 text-sm">
            <summary className="cursor-pointer font-semibold">
              {n.netBought}
            </summary>
            <p className="mt-2 text-muted">{n.netNote}</p>
            {page.previous_period ? (
              <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-muted">
                {Object.entries(page.counts).map(([kind, value]) =>
                  n.counts[kind] ? (
                    <li key={kind}>
                      {n.counts[kind]} {count(lang, value)}
                    </li>
                  ) : null,
                )}
              </ul>
            ) : (
              <p className="mt-2 text-muted">{n.noPrevious}</p>
            )}
          </details>

          <section aria-labelledby="holdings" className="mt-8">
            <h2 id="holdings" className="text-xl font-bold">
              {n.top}
            </h2>
            {page.stocks && page.stock_value_usd ? (
              <p className="mt-1 text-sm text-muted">
                {n.topNote(
                  count(lang, page.stocks),
                  bigUsd(lang, page.stock_value_usd),
                )}
              </p>
            ) : null}
            <div className="mt-3 overflow-x-auto">
              <table
                className="w-full text-sm tabular-nums"
                data-testid="institution-table"
              >
                <thead className="text-xs text-muted">
                  <tr className="border-b border-line text-left">
                    <th className="py-2 font-normal">
                      {words(lang).portfolio.stock}
                    </th>
                    <th className="py-2 font-normal">
                      {words(lang).portfolio.change}
                    </th>
                    <th className="hidden py-2 text-right font-normal sm:table-cell">
                      {words(lang).portfolio.shares}
                    </th>
                    <th className="py-2 text-right font-normal whitespace-nowrap">
                      {words(lang).portfolio.value}
                    </th>
                    <th className="py-2 text-right font-normal whitespace-nowrap">
                      {words(lang).portfolio.weight}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {page.top.map((row) => (
                    <tr key={row.cusip}>
                      <td className="max-w-[9rem] py-2 pr-3 sm:max-w-[14rem]">
                        <HoldingName row={row} lang={lang} />
                      </td>
                      <td className="py-2">
                        {row.change ? (changes[row.change] ?? row.change) : "—"}
                        {row.split ? (
                          <span className="block text-xs text-muted">
                            {n.split(row.split)}
                          </span>
                        ) : null}
                        {row.change && row.traded_usd === null ? (
                          <span className="block text-xs text-muted">
                            {n.corporate}
                          </span>
                        ) : null}
                      </td>
                      <td className="hidden py-2 text-right sm:table-cell">
                        {count(lang, row.shares)}
                      </td>
                      <td className="py-2 text-right whitespace-nowrap">
                        {bigUsd(lang, row.value_usd)}
                      </td>
                      <td className="py-2 text-right whitespace-nowrap">
                        {row.weight_pct !== null && row.weight_pct !== undefined
                          ? `${row.weight_pct.toFixed(2)}%`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {page.locked ? (
              <p className="mt-3 rounded-lg border border-accent/40 px-4 py-3 text-sm">
                {n.locked(count(lang, page.top_total))}{" "}
                <Link
                  href={loginHref}
                  className="font-semibold text-accent hover:underline"
                >
                  {words(lang).portfolio.signIn}
                </Link>
              </p>
            ) : null}
          </section>

          {!page.locked && page.previous_period ? (
            <div className="mt-8 grid gap-8 sm:grid-cols-2">
              <Moves
                rows={page.bought}
                lang={lang}
                heading={n.bought}
                id="bought"
              />
              <Moves rows={page.sold} lang={lang} heading={n.sold} id="sold" />
            </div>
          ) : null}
        </>
      )}

      <section aria-labelledby="filings" className="mt-8">
        <h2 id="filings" className="text-xl font-bold">
          {n.filings}
        </h2>
        <p className="mt-1 text-sm text-muted">{n.filingsNote}</p>
        <ul className="mt-3 divide-y divide-line text-sm">
          {page.filings.map((filing) => (
            <li
              key={filing.accession}
              className="flex flex-wrap items-baseline justify-between gap-x-4 py-2"
            >
              <span>
                {filing.form}
                <span className="ml-2 text-xs text-date">
                  {words(lang).portfolio.filed(formatDate(lang, filing.filed))}
                </span>
              </span>
              <a
                href={filing.url}
                rel="noopener nofollow"
                className="text-accent hover:underline"
              >
                SEC ↗
              </a>
            </li>
          ))}
        </ul>
      </section>
      <p className="mt-8 text-xs text-muted">{r.note}</p>
    </article>
  );
}
