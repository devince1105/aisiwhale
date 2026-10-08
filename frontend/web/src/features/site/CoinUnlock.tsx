// A COIN story's paywall (P4, D-249): what it costs and what the reader holds, one button to
// unlock it, and a confirmation that says what the balance will be — then the page again, whole.
//
// Not signed in, the button signs in and comes back here. Too few coins, it says how many more
// and links to the wallet. The confirmation has no <form>: two buttons, so it can never be a
// form inside another one (P3-C's lesson). Unlocking twice — a double click, another tab — is
// the server's to make one: it spends once.
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { fetchCoins } from "./coins";
import { words, type Lang } from "./i18n";
import { unlockArticle } from "./unlocks";

const BUTTON =
  "mx-auto block w-fit rounded-full bg-accent px-6 py-2.5 font-semibold text-accent-ink shadow-sm hover:opacity-90 disabled:opacity-50";

export function CoinUnlock({
  lang,
  path,
  articleId,
  price,
  company,
}: {
  lang: Lang;
  path: string;
  articleId: string;
  price: number;
  company?: string;
}) {
  const w = words(lang).unlock;
  const router = useRouter();
  const loginHref = `/news/${lang}/login?next=${encodeURIComponent(path)}`;
  const walletHref = `/news/${lang}/coins`;
  // undefined: still asking; "signed-out"; or what they hold (null: could not be read)
  const [held, setHeld] = useState<number | null | "signed-out" | undefined>(undefined);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [short, setShort] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    void fetchCoins({ company, limit: 1 }).then((wallet) => {
      if (!live) return;
      setHeld(wallet === "signed-out" ? "signed-out" : wallet === null ? null : wallet.balance);
    });
    return () => {
      live = false;
    };
  }, [company]);

  const number = (n: number) => n.toLocaleString(lang);

  async function unlock() {
    setBusy(true);
    setFailed(false);
    const done = await unlockArticle(articleId);
    setBusy(false);
    if (done.kind === "unlocked") {
      setAsking(false);
      router.refresh(); // the page again, from the server: the whole of it now
    } else if (done.kind === "short") {
      setAsking(false);
      setHeld(done.held);
      setShort(done.need - done.held);
    } else if (done.kind === "signed-out") {
      router.push(loginHref);
    } else {
      setFailed(true);
    }
  }

  const signedOut = held === "signed-out";
  const balance = typeof held === "number" ? held : null;
  const notEnough = short ?? (balance !== null && balance < price ? price - balance : null);

  return (
    <aside data-testid="coin-only" className="mt-8 rounded-lg border border-line bg-surface p-6 text-center">
      <p>
        <span className="rounded-full bg-accent px-2.5 py-0.5 text-xs font-semibold text-accent-ink">{w.badge(price)}</span>
      </p>
      <h2 className="mt-2 text-lg font-semibold">{w.title(price)}</h2>
      <p className="mt-2 text-muted">{w.why}</p>
      {balance !== null ? (
        <p data-testid="coin-balance" className="mt-3 text-sm">
          {w.balance(number(balance))}
        </p>
      ) : null}
      {signedOut ? (
        <Link href={loginHref} className={`mt-4 ${BUTTON}`}>
          {w.signIn}
        </Link>
      ) : notEnough !== null ? (
        <div role="status" className="mt-4">
          <p className="font-semibold text-danger">{w.short(notEnough)}</p>
          <Link href={walletHref} className="mt-2 inline-block text-accent underline">
            {w.wallet}
          </Link>
        </div>
      ) : (
        <button type="button" disabled={held === undefined} onClick={() => setAsking(true)} className={`mt-4 ${BUTTON}`}>
          {w.cta(price)}
        </button>
      )}
      {failed && !asking ? (
        <p role="alert" className="mt-3 text-sm text-danger">
          {w.failed}
        </p>
      ) : null}
      {asking ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="coin-unlock-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4"
        >
          <div className="w-full max-w-sm rounded-lg border border-line bg-surface p-6 text-left shadow-lg">
            <h3 id="coin-unlock-title" className="text-lg font-semibold">
              {w.confirmTitle(price)}
            </h3>
            {balance !== null ? (
              <p className="mt-3">{w.confirmBody(number(balance), number(balance - price))}</p>
            ) : null}
            {failed ? (
              <p role="alert" className="mt-3 text-sm text-danger">
                {w.failed}
              </p>
            ) : null}
            <div className="mt-5 flex justify-end gap-3">
              <button
                type="button"
                disabled={busy}
                onClick={() => setAsking(false)}
                className="rounded-full border border-line px-4 py-2 text-sm"
              >
                {w.cancel}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void unlock()}
                className="rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-ink disabled:opacity-50"
              >
                {busy ? w.busy : w.confirm}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </aside>
  );
}
