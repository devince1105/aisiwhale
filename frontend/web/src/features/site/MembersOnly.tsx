// What a reader sees instead of the rest of a locked story (D-025, D-034, D-159).
//
// A VIP story (``members``): the opening fades out, and one button says what to do — 我要成為
// VIP 會員看全文 — which opens the plans, a month or a year at a time; and signing in as one, for
// a reader who has already paid. Choosing a plan opens an order and hands the reader to PAYUNi's
// payment page (T-702); a site with no store yet says so instead of pretending to be a dead end,
// and a reader who is not signed in is sent to sign in first, because an order has to be for
// somebody.
//
// A 持股觀察 story (``sign_in``): free, for a reader who signs in — so the button signs in.
"use client";

import Link from "next/link";
import { useState } from "react";

import { PlanPicker } from "./PlanPicker";
import { words, type Lang } from "./i18n";

type Lock = "members" | "sign_in";

export function MembersOnly({
  lang,
  path,
  company,
  lock = "members",
}: {
  lang: Lang;
  path: string;
  company?: string;
  lock?: Lock;
}) {
  const w = words(lang);
  const loginHref = `/news/${lang}/login?next=${encodeURIComponent(path)}`;
  const [plans, setPlans] = useState(false);
  const button =
    "mx-auto block w-fit rounded-full bg-accent px-6 py-2.5 font-semibold text-accent-ink shadow-sm hover:opacity-90";

  return (
    <div className="relative">
      {/* the opening fades into the notice, as on a paper's site: there is more, and here is how */}
      <div aria-hidden className="pointer-events-none absolute inset-x-0 -top-24 h-24 bg-gradient-to-b from-transparent to-canvas" />
      {lock === "sign_in" ? (
        <aside data-testid="sign-in-to-read" className="mt-8 rounded-lg border border-line bg-surface p-6 text-center">
          <h2 className="text-lg font-semibold">{w.signInToRead}</h2>
          <p className="mt-2 text-muted">{w.signInToReadWhy}</p>
          <Link href={loginHref} className={`mt-4 ${button}`}>
            {w.signInToReadCta}
          </Link>
        </aside>
      ) : (
        <aside data-testid="members-only" className="mt-8 rounded-lg border border-line bg-surface p-6">
          <p className="text-center">
            <span className="rounded-full bg-accent px-2.5 py-0.5 text-xs font-semibold text-accent-ink">VIP</span>
          </p>
          <h2 className="mt-2 text-center text-lg font-semibold">{w.membersOnly}</h2>
          <p className="mt-2 text-center text-muted">{w.membersOnlyWhy}</p>
          {plans ? (
            <div className="mt-4">
              <PlanPicker lang={lang} loginHref={loginHref} company={company} />
            </div>
          ) : (
            <button type="button" onClick={() => setPlans(true)} className={`mt-4 ${button}`}>
              {w.membersOnlyCta}
            </button>
          )}
          <p className="mt-4 text-center text-sm text-muted">
            {w.membersOnlyAlready}{" "}
            <Link href={loginHref} className="text-accent underline">
              {w.signIn}
            </Link>
          </p>
        </aside>
      )}
    </div>
  );
}
