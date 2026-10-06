// The holdings dashboard (HD-06, D-217): a card for each followed 13F filer on the 持股觀察 tab —
// its simulated one-year return, the latest quarter's two biggest moves, a ring of its five
// largest holdings — and a page for each, with the whole table, the quarters and the filings.
// After the brokers' "smart money" cards, in Taiwan's words; server-rendered; the numbers are
// facts and arithmetic, never advice, and the method says what the return is and is not.
import Link from "next/link";

import type { PublicPortfolio, PublicPortfolioCard } from "./api";
import { formatDate, words, type Lang } from "./i18n";
import { listHref } from "./links";

type Card = PublicPortfolioCard;
type Holding = Card["holdings"][number];

export function portfolioHref(lang: Lang, slug: string): string {
  return `/news/${lang}/holdings/people/${slug}`;
}

/** 持股觀察's three tabs (HD-06): the big names' cards, the big holders' (groups: a company's
 * own investments, a state fund), and the stories. */
export const VIEWS = ["people", "groups", "news"] as const;
export type View = (typeof VIEWS)[number];

export function isView(value: unknown): value is View {
  return typeof value === "string" && (VIEWS as readonly string[]).includes(value);
}

/** Which cards a tab shows: a person's or a public official's; a company's or a fund's. */
export const KINDS: Record<Exclude<View, "news">, readonly string[]> = {
  people: ["person", "official"],
  groups: ["company", "fund"],
};

export function watchHref(lang: Lang, view: View): string {
  return view === "people" ? listHref(lang, "watch") : `${listHref(lang, "watch")}&view=${view}`;
}

export function WatchTabs({ lang, view }: { lang: Lang; view: View }) {
  const w = words(lang).portfolio;
  return (
    <nav aria-label={w.tabsLabel} className="flex gap-1 border-b border-line pt-4 print:hidden" data-testid="watch-tabs">
      {VIEWS.map((id) => (
        <Link
          key={id}
          href={watchHref(lang, id)}
          aria-current={id === view ? "page" : undefined}
          className={`-mb-px border-b-2 px-3 py-2 text-sm whitespace-nowrap ${
            id === view ? "border-accent font-semibold text-ink" : "border-transparent text-muted hover:text-ink"
          }`}
        >
          {w.tabs[id]}
        </Link>
      ))}
    </nav>
  );
}

/** +18.94%, −1.28%: a fraction as a signed percentage. */
export function signedPct(fraction: number, digits = 2): string {
  const pct = fraction * 100;
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
  return `${sign}${Math.abs(pct).toFixed(digits)}%`;
}

function tone(value: number): string {
  return value > 0 ? "text-rise" : value < 0 ? "text-fall" : "text-muted";
}

function usd(lang: Lang, value: number): string {
  return `US$${new Intl.NumberFormat(lang, { notation: "compact", maximumFractionDigits: 1 }).format(value)}`;
}

function count(lang: Lang, value: number): string {
  return new Intl.NumberFormat(lang).format(value);
}

/** 2026 年第 2 季, Q2 2026: the quarter a 13F reports. */
export function quarterOf(lang: Lang, period: string): string {
  const [year, month] = period.split("-").map(Number);
  return words(lang).portfolio.quarter(year, Math.floor((month - 1) / 3) + 1);
}

const CHANGE_TONE: Record<string, string> = {
  new: "text-rise",
  increased: "text-rise",
  decreased: "text-fall",
  sold_out: "text-fall",
  unchanged: "text-muted",
};

export interface Photo {
  src: string;
  /** From Wikimedia Commons: who took it, under what licence (null: the public domain), and the
   * file's page there. A photo the site's operator supplied has none of these (``supplied``). */
  author?: string;
  license?: string | null;
  licenseUrl?: string | null;
  page?: string;
  /** Supplied by the site's operator (2026-10-06: 段永平, 杜肯米勒, 麥可・貝瑞 and Temasek's,
   * for whom Commons has none); where it comes from is the operator's to confirm. */
  supplied?: boolean;
  /** Who is in it, where that is not the card's own subject: NVIDIA's card shows its chief. */
  pictured?: { zh: string; en: string };
}

export interface Ceo {
  zh: string;
  en: string;
  photo: Photo;
}

/** The Magnificent Seven's chief executives as of October 2026 (Apple's since 1 September),
 * their names as Taiwan's press writes them (祖克柏, not 扎克伯格; John Ternus, as he is
 * written), with photos in the public domain or under CC BY from Wikimedia Commons, cropped
 * square to the face. */
export const CEOS: Record<string, Ceo> = {
  AAPL: {
    zh: "John Ternus",
    en: "John Ternus",
    photo: {
      src: "/ceos/aapl.jpg",
      author: "Tessa Bury",
      license: "CC BY 4.0",
      licenseUrl: "https://creativecommons.org/licenses/by/4.0/",
      page: "https://commons.wikimedia.org/wiki/File:John_Ternus_at_the_Apple_50th_Anniversary_Kickoff_(cropped).jpg",
    },
  },
  MSFT: {
    zh: "納德拉",
    en: "Satya Nadella",
    photo: {
      src: "/ceos/msft.jpg",
      author: "OFFICIAL LEWEB PHOTOS",
      license: "CC BY 2.0",
      licenseUrl: "https://creativecommons.org/licenses/by/2.0/",
      page: "https://commons.wikimedia.org/wiki/File:Satya_Nadella.jpg",
    },
  },
  GOOGL: {
    zh: "皮查伊",
    en: "Sundar Pichai",
    photo: {
      src: "/ceos/googl.jpg",
      author: "Lukasz Kobus – European Commission",
      license: "CC BY 4.0",
      licenseUrl: "https://creativecommons.org/licenses/by/4.0/",
      page: "https://commons.wikimedia.org/wiki/File:Sundar_Pichai_-_2023_(cropped).jpg",
    },
  },
  AMZN: {
    zh: "賈西",
    en: "Andy Jassy",
    photo: {
      src: "/ceos/amzn.jpg",
      author: "Steve Jurvetson",
      license: "CC BY 2.0",
      licenseUrl: "https://creativecommons.org/licenses/by/2.0/",
      page: "https://commons.wikimedia.org/wiki/File:Andy_Jassy_in_2016.jpg",
    },
  },
  META: {
    zh: "祖克柏",
    en: "Mark Zuckerberg",
    photo: {
      src: "/ceos/meta.jpg",
      author: "Anthony Quintano",
      license: "CC BY 2.0",
      licenseUrl: "https://creativecommons.org/licenses/by/2.0/",
      page: "https://commons.wikimedia.org/wiki/File:Mark_Zuckerberg_F8_2019_Keynote_(32830578717)_(cropped).jpg",
    },
  },
  NVDA: {
    zh: "黃仁勳",
    en: "Jensen Huang",
    photo: {
      src: "/ceos/nvda.jpg",
      author: "Peter Dasilva",
      license: "CC BY 4.0",
      licenseUrl: "https://creativecommons.org/licenses/by/4.0/",
      page: "https://commons.wikimedia.org/wiki/File:Jensen_Huang_(cropped)_(2024).jpg",
    },
  },
  TSLA: {
    zh: "馬斯克",
    en: "Elon Musk",
    photo: {
      src: "/ceos/tsla.jpg",
      author: "The White House",
      license: null,
      licenseUrl: null,
      page: "https://commons.wikimedia.org/wiki/File:The_White_House_-_54409525537_(cropped).jpg",
    },
  },
};

/** Faces at the rings' centres (D-217): photos in the public domain or under CC BY from
 * Wikimedia Commons, cropped square to the face, credited on each person page; where Commons has
 * none, a photo the site's operator supplied. A card without one keeps a monogram. */
export const PHOTOS: Record<string, Photo> = {
  buffett: {
    src: "/people/buffett.jpg",
    author: "USA International Trade Administration",
    license: null,
    licenseUrl: null,
    page: "https://commons.wikimedia.org/wiki/File:Warren_Buffett_at_the_2015_SelectUSA_Investment_Summit_(cropped).jpg",
  },
  soros: {
    src: "/people/soros.jpg",
    author: "Aris Oikonomou – European Commission",
    license: "CC BY 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by/4.0/",
    page: "https://commons.wikimedia.org/wiki/File:George_Soros_-_May_31,_2017.jpg",
  },
  "cathie-wood": {
    src: "/people/cathie-wood.jpg",
    author: "Steve Jurvetson",
    license: "CC BY 2.0",
    licenseUrl: "https://creativecommons.org/licenses/by/2.0/",
    page: "https://commons.wikimedia.org/wiki/File:Cathie_Wood.jpg",
  },
  ackman: {
    src: "/people/ackman.jpg",
    author: "Senate Democrats",
    license: "CC BY 2.0",
    licenseUrl: "https://creativecommons.org/licenses/by/2.0/",
    page: "https://commons.wikimedia.org/wiki/File:Bill_Ackman,_2016.jpg",
  },
  "duan-yongping": { src: "/people/duan-yongping.jpg", supplied: true },
  druckenmiller: { src: "/people/druckenmiller.jpg", supplied: true },
  burry: { src: "/people/burry.jpg", supplied: true },
  temasek: { src: "/people/temasek.jpg", supplied: true },
  // the company's card shows its chief, as the brokers' cards do; the title says whose holdings
  // they are (輝達（公司）持股) and the credit who is pictured
  nvidia: { ...CEOS.NVDA.photo, pictured: { zh: "黃仁勳（輝達執行長）", en: "Jensen Huang, NVIDIA's chief executive" } },
};

/** Where there is no photo: a person's first character, a company's or a fund's name. */
function Monogram({ card, lang, size }: { card: Pick<Card, "name" | "kind">; lang: Lang; size: number }) {
  const text =
    card.kind !== "person"
      ? card.name
      : lang.startsWith("zh")
        ? card.name.slice(0, 1)
        : card.name
            .split(" ")
            .map((part) => part[0])
            .join("")
            .slice(0, 2);
  const font = card.kind !== "person" ? size * (text.length > 3 ? 0.17 : 0.22) : size * 0.34;
  return (
    <text x="50" y="50" textAnchor="middle" dominantBaseline="central" fontSize={font} fontWeight={700} fill="currentColor">
      {text}
    </text>
  );
}

const SHADES = [1, 0.78, 0.6, 0.45, 0.32];

/** The five largest as a ring, the rest as one grey arc; a ticker on each arc wide enough. */
export function Ring({
  card,
  lang,
  size = 112,
}: {
  card: Pick<Card, "slug" | "name" | "kind" | "holdings" | "others_weight">;
  lang: Lang;
  size?: number;
}) {
  const photo = PHOTOS[card.slug];
  const clip = `face-${card.slug}-${size}`;
  const r = 38;
  const around = 2 * Math.PI * r;
  const arcs: { holding: Holding | null; weight: number; start: number }[] = [];
  let start = 0;
  for (const holding of card.holdings) {
    arcs.push({ holding, weight: holding.weight, start });
    start += holding.weight;
  }
  if (card.others_weight > 0.0005) arcs.push({ holding: null, weight: card.others_weight, start });
  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      role="img"
      aria-label={words(lang).portfolio.ring(card.name)}
      className="shrink-0 text-accent"
    >
      <g transform="rotate(-90 50 50)">
        {arcs.map(({ holding, weight, start: at }, i) => (
          <circle
            key={holding?.symbol ?? holding?.name ?? "others"}
            cx="50"
            cy="50"
            r={r}
            fill="none"
            stroke="currentColor"
            strokeOpacity={holding ? SHADES[i] : 0.14}
            strokeWidth="16"
            // a hair of a gap between arcs, so two of a shade read as two
            strokeDasharray={`${Math.max(weight * around - 0.8, 0.2)} ${around}`}
            strokeDashoffset={-at * around}
          />
        ))}
      </g>
      {arcs.map(({ holding, weight, start: at }) => {
        if (!holding?.symbol || weight < 0.08) return null;
        const angle = (at + weight / 2) * 2 * Math.PI - Math.PI / 2;
        const x = 50 + r * Math.cos(angle);
        const y = 50 + r * Math.sin(angle);
        return (
          <g key={holding.symbol} className="text-ink">
            <circle cx={x} cy={y} r="9.5" className="fill-surface" stroke="currentColor" strokeOpacity="0.15" />
            <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fontSize={holding.symbol.length > 4 ? 4.6 : 5.6} fontWeight={700} fill="currentColor">
              {holding.symbol}
            </text>
          </g>
        );
      })}
      <circle cx="50" cy="50" r="27" className="fill-surface" />
      {photo ? (
        <>
          <clipPath id={clip}>
            <circle cx="50" cy="50" r="26" />
          </clipPath>
          <image href={photo.src} x="24" y="24" width="52" height="52" clipPath={`url(#${clip})`} preserveAspectRatio="xMidYMid slice" />
        </>
      ) : (
        <g className="text-ink">
          <Monogram card={card} lang={lang} size={100} />
        </g>
      )}
    </svg>
  );
}

/** The return, or why there is none: still being checked (整理中), or too little priced. */
function Return({ card, lang, large = false }: { card: Card; lang: Lang; large?: boolean }) {
  const w = words(lang).portfolio;
  const size = large ? "text-4xl" : "text-3xl";
  if (card.return_pct !== null && card.return_pct !== undefined) {
    return (
      <p className="flex flex-wrap items-baseline gap-x-2">
        <span className={`${size} font-bold tabular-nums ${tone(card.return_pct)}`}>{signedPct(card.return_pct)}</span>
        <span className="text-sm text-muted">{w.returnLabel}</span>
      </p>
    );
  }
  return (
    <p className="flex flex-wrap items-baseline gap-x-2" title={card.pending ? w.pendingNote : w.noReturnNote}>
      <span className={`${size} font-bold text-muted`}>{card.pending ? w.pending : "—"}</span>
      <span className="text-sm text-muted">{w.returnLabel}</span>
    </p>
  );
}

function Moves({ card, lang }: { card: Card; lang: Lang }) {
  const w = words(lang);
  if (!card.moves.length) return <p className="mt-2 text-sm text-muted">{w.portfolio.noMoves}</p>;
  return (
    <ul className="mt-2 space-y-1 text-sm">
      {card.moves.map((move) => (
        <li key={`${move.symbol ?? move.name}-${move.change}`} className="flex items-baseline gap-x-2">
          <span className="w-[4.5rem] shrink-0 truncate font-semibold">{move.symbol ?? move.name}</span>
          <span className="tabular-nums whitespace-nowrap">
            {move.shares_change_pct !== null && move.shares_change_pct !== undefined
              ? signedPct(move.shares_change_pct / 100)
              : ""}
          </span>
          <span className={`whitespace-nowrap ${CHANGE_TONE[move.change] ?? "text-muted"}`}>
            {w.stock.changes[move.change] ?? move.change}
          </span>
        </li>
      ))}
    </ul>
  );
}

function Filed({ card, lang }: { card: Card; lang: Lang }) {
  const w = words(lang).portfolio;
  return (
    <p className="mt-3 text-xs text-muted">
      <span className="text-date">{w.filed(formatDate(lang, card.filed))}</span>
      <span className="whitespace-nowrap">・{quarterOf(lang, card.period)}</span>
    </p>
  );
}

/** The 持股觀察 tab's cards, two to a row on a wide screen. */
export function PortfolioCards({ cards, lang, heading }: { cards: Card[]; lang: Lang; heading?: string }) {
  const w = words(lang).portfolio;
  return (
    <section aria-labelledby="portfolios" className="pt-6 pb-2">
      <h2 id="portfolios" className="text-xl font-bold">
        {heading ?? w.heading}
      </h2>
      {/* two to a row only where a card keeps room for its moves beside its ring (440 px) */}
      <ul className="mt-4 grid gap-4 xl:grid-cols-2" data-testid="portfolio-cards">
        {cards.map((card) => (
          <li key={card.slug}>
            <Link
              href={portfolioHref(lang, card.slug)}
              className="flex h-full items-center gap-4 rounded-xl border border-line bg-surface p-5 transition hover:border-accent/60"
              data-testid="portfolio-card"
            >
              <div className="min-w-0 flex-1">
                <h3 className="text-lg font-bold">{w.title(card.name, card.kind)}</h3>
                <div className="mt-1">
                  <Return card={card} lang={lang} />
                </div>
                <Moves card={card} lang={lang} />
                <Filed card={card} lang={lang} />
              </div>
              <Ring card={card} lang={lang} />
            </Link>
          </li>
        ))}
      </ul>
      {cards.some((card) => PHOTOS[card.slug]) ? <p className="mt-3 text-xs text-muted">{w.photosNote}</p> : null}
    </section>
  );
}

/** A photo's credit, as its licence asks: who took it, under what, from where, and that it was
 * cropped; or that the site's operator supplied it. */
function Credit({ photo, lang }: { photo: Photo; lang: Lang }) {
  const w = words(lang).portfolio;
  if (photo.supplied) {
    return (
      <p className="mt-2 text-xs text-muted" data-testid="photo-credit">
        {w.photo}
        {w.supplied}
      </p>
    );
  }
  return (
    <p className="mt-2 text-xs text-muted" data-testid="photo-credit">
      {w.photo}
      {photo.pictured ? w.pictured(lang.startsWith("zh") ? photo.pictured.zh : photo.pictured.en) : null}
      {photo.author}
      {w.sep}
      {photo.licenseUrl ? (
        <a href={photo.licenseUrl} rel="license noopener" className="hover:text-accent hover:underline">
          {photo.license}
        </a>
      ) : (
        w.publicDomain
      )}
      {w.sep}
      <a href={photo.page} rel="noopener" className="hover:text-accent hover:underline">
        {w.commons}
      </a>
      {w.cropped}
    </p>
  );
}

/** A person page: the card at large, the method, the quarters, the whole table, the filings. */
export function PortfolioView({
  portfolio,
  lang,
  loginHref,
}: {
  portfolio: PublicPortfolio;
  lang: Lang;
  /** Where a reader not signed in goes for the rest of the table (D-159). */
  loginHref: string;
}) {
  const w = words(lang);
  const p = w.portfolio;
  const held = portfolio.positions.filter((row) => row.value_usd > 0).length;
  return (
    <article className="mx-auto max-w-[46rem] px-4 pt-4 pb-12">
      <nav aria-label="breadcrumb" className="text-sm text-muted">
        <Link href={listHref(lang, "watch")} className="hover:text-accent">
          {p.back}
        </Link>{" "}
        › {portfolio.name}
      </nav>

      <header className="mt-4 flex flex-wrap items-center gap-6">
        <Ring card={portfolio} lang={lang} size={168} />
        <div className="min-w-0 flex-1">
          <h1 className="text-3xl font-bold">{p.title(portfolio.name, portfolio.kind)}</h1>
          <p className="mt-1 text-sm text-muted">{p.entity(portfolio.entity)}</p>
          {p.kindNote[portfolio.kind] ? <p className="mt-1 text-sm text-muted">{p.kindNote[portfolio.kind]}</p> : null}
          <div className="mt-3">
            <Return card={portfolio} lang={lang} large />
          </div>
          {portfolio.return_start && portfolio.return_through ? (
            <p className="mt-1 text-xs text-muted">
              {p.span(formatDate(lang, portfolio.return_start), formatDate(lang, portfolio.return_through))}
              {portfolio.coverage !== null && portfolio.coverage !== undefined
                ? `・${p.coverage(`${Math.round(portfolio.coverage * 100)}%`)}`
                : ""}
            </p>
          ) : null}
          {portfolio.return_pct === null || portfolio.return_pct === undefined ? (
            <p className="mt-1 text-xs text-muted">{portfolio.pending ? p.pendingNote : p.noReturnNote}</p>
          ) : null}
        </div>
      </header>
      {PHOTOS[portfolio.slug] ? <Credit photo={PHOTOS[portfolio.slug]} lang={lang} /> : null}

      <details className="mt-6 rounded-lg border border-line bg-surface px-4 py-3 text-sm">
        <summary className="cursor-pointer font-semibold">{p.method}</summary>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted">
          {p.methodSteps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </details>

      <p className="mt-4 text-sm text-muted">{p.lag(formatDate(lang, portfolio.period))}</p>

      <section aria-labelledby="moves" className="mt-8">
        <h2 id="moves" className="text-xl font-bold">
          {p.moves}
        </h2>
        <Moves card={portfolio} lang={lang} />
      </section>

      {portfolio.stretches.length ? (
        <section aria-labelledby="stretches" className="mt-8">
          <h2 id="stretches" className="text-xl font-bold">
            {p.stretches}
          </h2>
          <table className="mt-3 w-full text-sm tabular-nums">
            <thead className="text-xs text-muted">
              <tr className="border-b border-line text-left">
                <th className="py-2 font-normal">{p.period}</th>
                <th className="py-2 text-right font-normal">{p.stretchReturn}</th>
                <th className="py-2 text-right font-normal">{p.stretchCoverage}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {portfolio.stretches.map((stretch) => (
                <tr key={stretch.start}>
                  <td className="py-2">
                    {formatDate(lang, stretch.start)} – {stretch.end ? formatDate(lang, stretch.end) : "…"}
                  </td>
                  <td className={`py-2 text-right ${stretch.growth ? tone(stretch.growth - 1) : "text-muted"}`}>
                    {stretch.growth ? signedPct(stretch.growth - 1) : "—"}
                  </td>
                  <td className="py-2 text-right text-muted">{Math.round(stretch.coverage * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      <section aria-labelledby="holdings" className="mt-8">
        <h2 id="holdings" className="text-xl font-bold">
          {p.holdings}
        </h2>
        <p className="mt-1 text-sm text-muted">{p.holdingsNote(count(lang, held), usd(lang, portfolio.long_value_usd))}</p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[34rem] text-sm tabular-nums" data-testid="portfolio-table">
            <thead className="text-xs text-muted">
              <tr className="border-b border-line text-left">
                <th className="py-2 font-normal">{p.stock}</th>
                <th className="py-2 font-normal">{p.change}</th>
                <th className="py-2 text-right font-normal">{p.shares}</th>
                <th className="py-2 text-right font-normal">{p.value}</th>
                <th className="py-2 text-right font-normal">{p.weight}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {portfolio.positions.map((row) => (
                <tr key={`${row.symbol ?? row.name}-${row.change}`}>
                  <td className="max-w-[14rem] py-2 pr-3">
                    {row.symbol ? (
                      <Link href={`/news/${lang}/stocks/${row.symbol}`} className="font-semibold hover:text-accent">
                        {row.symbol}
                      </Link>
                    ) : null}
                    <span className="block truncate text-xs text-muted">{row.name}</span>
                  </td>
                  <td className={`py-2 ${row.change ? (CHANGE_TONE[row.change] ?? "") : "text-muted"}`}>
                    {row.change ? (w.stock.changes[row.change] ?? row.change) : p.unknown}
                    {row.shares_change_pct !== null && row.shares_change_pct !== undefined ? (
                      <span className="ml-1">{signedPct(row.shares_change_pct / 100)}</span>
                    ) : null}
                  </td>
                  <td className="py-2 text-right">
                    {count(lang, row.shares)}
                    {row.change && row.change !== "unchanged" && row.previous_shares ? (
                      <span className="block text-xs text-muted">{p.was(count(lang, row.previous_shares))}</span>
                    ) : null}
                  </td>
                  <td className="py-2 text-right">{row.value_usd ? usd(lang, row.value_usd) : "—"}</td>
                  <td className="py-2 text-right">{row.value_usd ? `${(row.weight * 100).toFixed(2)}%` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {portfolio.locked ? (
          <p className="mt-3 rounded-lg border border-accent/40 px-4 py-3 text-sm">
            {p.locked(count(lang, portfolio.positions_total))}{" "}
            <Link href={loginHref} className="font-semibold text-accent hover:underline">
              {p.signIn}
            </Link>
          </p>
        ) : null}
      </section>

      <section aria-labelledby="filings" className="mt-8">
        <h2 id="filings" className="text-xl font-bold">
          {p.filings}
        </h2>
        <p className="mt-1 text-sm text-muted">{p.filingsNote}</p>
        <ul className="mt-3 divide-y divide-line text-sm">
          {portfolio.quarters.map((quarter) => (
            <li key={quarter.period} className="flex flex-wrap items-baseline justify-between gap-x-4 py-2">
              <span>
                {quarterOf(lang, quarter.period)}
                <span className="ml-2 text-xs text-date">{p.filed(formatDate(lang, quarter.filed))}</span>
              </span>
              <span className="flex gap-3">
                {quarter.filings.map((url) => (
                  <a key={url} href={url} rel="noopener nofollow" className="text-accent hover:underline">
                    SEC ↗
                  </a>
                ))}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}
