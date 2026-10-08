// A reader's Whale Coins (P3-C): what they hold, what their tier gives a month, and every
// movement, newest first — a spend on a story names it, with a link while it is on the site
// (P4). Read only: unlocking is on the story's page. Filled in the browser from the
// reader's cookie; a visitor who is not signed in is sent to sign in and brought back.
"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { SITE_COMPANY } from "@/config";

import { fetchCoins, monthState, type CoinMovement, type CoinWallet } from "./coins";
import { formatDate, words, type Lang } from "./i18n";

type State =
  | { status: "loading" }
  | { status: "failed" }
  | { status: "ready"; wallet: CoinWallet; items: CoinMovement[]; next: string | null };

export function CoinsPage({ lang }: { lang: Lang }) {
  const w = words(lang).coins;
  const [state, setState] = useState<State>({ status: "loading" });
  const [more, setMore] = useState(false);
  const live = useRef(true);

  useEffect(() => {
    live.current = true;
    void fetchCoins({ company: SITE_COMPANY }).then((wallet) => {
      if (!live.current) return;
      if (wallet === "signed-out") {
        const back = `/news/${lang}/coins`;
        window.location.replace(`/news/${lang}/login?next=${encodeURIComponent(back)}`);
        return;
      }
      setState(
        wallet
          ? { status: "ready", wallet, items: wallet.history.items, next: wallet.history.next_cursor ?? null }
          : { status: "failed" },
      );
    });
    return () => {
      live.current = false;
    };
  }, [lang]);

  async function loadMore() {
    if (state.status !== "ready" || !state.next) return;
    setMore(true);
    const page = await fetchCoins({ company: SITE_COMPANY, cursor: state.next });
    setMore(false);
    if (!live.current || !page || page === "signed-out") return;
    setState({
      ...state,
      items: [...state.items, ...page.history.items],
      next: page.history.next_cursor ?? null,
    });
  }

  if (state.status === "loading") return <p className="text-muted">…</p>;
  if (state.status === "failed") {
    return (
      <p role="alert" className="text-muted">
        {w.failed}
      </p>
    );
  }

  const { wallet, items, next } = state;
  const month = wallet.monthly;
  const said = monthState(wallet);
  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-bold">{w.title}</h1>

      <section className="mt-6 rounded-lg border border-line bg-surface p-6" data-testid="coins-balance">
        <p className="text-sm text-muted">{w.balance}</p>
        <p className="mt-1 text-4xl font-bold tabular-nums">{wallet.balance.toLocaleString(lang)}</p>
        <p className="mt-3 text-sm">
          {w.tier[wallet.tier]}
          {month.amount != null && month.cap != null ? `・${w.terms(month.amount, month.cap)}` : null}
        </p>
        <p className="mt-1 text-sm text-muted" data-testid="coins-month">
          {w.month[said]}
        </p>
      </section>

      <section className="mt-8">
        <h2 className="text-lg font-semibold">{w.history}</h2>
        {items.length === 0 ? (
          <p className="mt-3 text-muted">{w.empty}</p>
        ) : (
          <ul className="mt-3 divide-y divide-line" data-testid="coins-history">
            {items.map((m) => (
              <li key={m.id} className="flex items-baseline justify-between gap-4 py-2 text-sm">
                <span>
                  <span className="font-medium">{w.kinds[m.kind] ?? m.kind}</span>
                  {m.kind === "MONTHLY_GRANT" && m.amount === 0 ? (
                    <span className="ml-2 text-muted">{w.capped}</span>
                  ) : null}
                  {m.article ? (
                    m.article.path ? (
                      <Link href={m.article.path} className="ml-2 text-accent underline" data-testid="coin-article">
                        {m.article.title}
                      </Link>
                    ) : (
                      <span className="ml-2" data-testid="coin-article">
                        {m.article.title}
                      </span>
                    )
                  ) : null}
                  <span className="ml-2 text-muted">{formatDate(lang, m.occurred_at)}</span>
                </span>
                <span className="tabular-nums">
                  <span className={m.amount < 0 ? "text-danger" : m.amount > 0 ? "text-accent" : "text-muted"}>
                    {m.amount > 0 ? "+" : ""}
                    {m.amount.toLocaleString(lang)}
                  </span>
                  <span className="ml-3 text-muted">{w.after(m.balance_after.toLocaleString(lang))}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
        {next ? (
          <button
            type="button"
            onClick={() => void loadMore()}
            disabled={more}
            className="mt-4 rounded border border-line px-3 py-1.5 text-sm disabled:opacity-50"
          >
            {w.more}
          </button>
        ) : null}
      </section>

      <section className="mt-10 rounded-lg border border-line p-4 text-sm leading-relaxed text-muted">
        <h2 className="font-semibold text-ink">{w.aboutTitle}</h2>
        <p className="mt-2">{w.about}</p>
        <p className="mt-2">
          <a href={`/news/${lang}/terms`} className="text-accent underline">
            {w.termsLink}
          </a>
        </p>
      </section>
    </div>
  );
}
