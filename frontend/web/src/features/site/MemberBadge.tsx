// Who is reading, in the site's header (D-025). Asked from the browser so the pages themselves
// stay cacheable: a signed-out visitor and a member get the same HTML, and this fills in after.
"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

import { SITE_COMPANY } from "@/config";

import { fetchMe, isMember, signOut, type Me } from "./auth";
import { useDismiss } from "./dismiss";
import { formatDate, words, type Lang } from "./i18n";

type State = { status: "loading" | "ready"; me: Me | null };

export function MemberBadge({ lang }: { lang: Lang }) {
  const w = words(lang);
  const [{ status, me }, setState] = useState<State>({ status: "loading", me: null });

  useEffect(() => {
    let live = true;
    fetchMe(SITE_COMPANY)
      .then((answer) => live && setState({ status: "ready", me: answer }))
      .catch(() => live && setState({ status: "ready", me: null }));
    return () => {
      live = false;
    };
  }, []);

  if (status === "loading") return <span className="text-sm text-muted" aria-hidden />;

  if (!me) {
    return (
      <a
        href={`/news/${lang}/login`}
        className="rounded-full border border-line px-3 py-1 text-sm hover:border-accent hover:text-accent"
        data-testid="sign-in"
      >
        {w.signIn}
      </a>
    );
  }

  return (
    <ReaderMenu
      lang={lang}
      me={me}
      onSignOut={async () => {
        await signOut();
        setState({ status: "ready", me: null });
      }}
    />
  );
}

/** The first letter of an address, as the reader's avatar shows it (D-087). */
export function initial(email: string): string {
  return (email.trim()[0] ?? "?").toUpperCase();
}

/** Signed in (D-087): a round avatar with the address's first letter, in place of the address;
 * it opens who they are — their address, a member's date — their watchlist, and sign-out. */
function ReaderMenu({ lang, me, onSignOut }: { lang: Lang; me: Me; onSignOut: () => void }) {
  const w = words(lang);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const menu = useId();
  useDismiss(box, open, useCallback(() => setOpen(false), []));
  return (
    <div ref={box} className="relative" data-testid="member-badge">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={menu}
        aria-label={w.account(me.email)}
        className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-sm font-semibold text-accent-ink ring-offset-2 ring-offset-surface hover:ring-2 hover:ring-accent/40"
        data-testid="avatar"
      >
        {initial(me.email)}
      </button>
      {open ? (
        <div
          id={menu}
          className="absolute right-0 z-40 mt-2 w-64 rounded-lg border border-line bg-surface py-2 text-sm shadow-lg"
        >
          <p className="truncate px-4 pb-2 text-muted" title={me.email}>
            {me.email}
          </p>
          {isMember(me) ? (
            <p className="px-4 pb-2 text-xs">
              {w.member}・{w.memberUntil} {formatDate(lang, me.member_until!)}
            </p>
          ) : null}
          <div className="border-t border-line pt-1">
            <a href={`/news/${lang}/watchlist`} className="block px-4 py-1.5 hover:bg-canvas hover:text-accent">
              {w.watch.title}
            </a>
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onSignOut();
              }}
              className="block w-full px-4 py-1.5 text-left hover:bg-canvas hover:text-accent"
            >
              {w.signOut}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
