// The site's sign-in pages (D-230): sign in, create an account, forget and reset a password, and
// confirm an email. Every answer that could say whether an address has an account is worded the
// same either way. Nothing that proves who somebody is is kept in browser storage: the session is
// the API's httpOnly cookie.
"use client";

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { SITE_COMPANY } from "@/config";
import {
  fetchMe,
  forgotPassword,
  googleStartUrl,
  login,
  register,
  resendVerification,
  resetPassword,
  verifyEmail,
  type Outcome,
} from "@/features/site/auth";
import { words, type Lang } from "@/features/site/i18n";

type Words = ReturnType<typeof words>["auth"];

function problem(w: Words, outcome: Outcome): string | null {
  if (outcome === "ok") return null;
  if (outcome === "wrong") return w.wrong;
  if (outcome === "invalid") return w.invalid;
  if (outcome === "limited") return w.limited;
  return w.failed;
}

function Page({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="mx-auto max-w-md px-4 py-12">
      <h1 className="text-2xl font-bold">{title}</h1>
      {hint ? <p className="mt-3 text-muted">{hint}</p> : null}
      <div className="mt-6 flex flex-col gap-3">{children}</div>
    </section>
  );
}

function Field({
  label,
  type,
  value,
  onChange,
  autoComplete,
}: {
  label: string;
  type: "email" | "password";
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      {label}
      <input
        type={type}
        required
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete={autoComplete}
        className="rounded-lg border border-line bg-surface px-3 py-2 text-base"
      />
    </label>
  );
}

function Submit({ busy, children }: { busy: boolean; children: ReactNode }) {
  return (
    <button
      type="submit"
      disabled={busy}
      className="rounded-lg bg-accent px-4 py-2 font-semibold text-surface disabled:opacity-60"
    >
      {children}
    </button>
  );
}

function Notice({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" }) {
  return tone === "warn" ? (
    <p className="text-sm text-warn" role="alert">
      {children}
    </p>
  ) : (
    <p className="rounded-lg border border-line bg-surface p-4" role="status">
      {children}
    </p>
  );
}

function onwardsFor(lang: Lang, next?: string): string {
  return next?.startsWith("/") ? next : `/news/${lang}`;
}

/** Already signed in: there is nothing to do here, so go on (a full load, so the header knows). */
function useGoOnIfSignedIn(onwards: string): void {
  useEffect(() => {
    let live = true;
    fetchMe(SITE_COMPANY)
      .then((me) => live && me && window.location.replace(onwards))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [onwards]);
}

export function LoginForm({ lang, next, error }: { lang: Lang; next?: string; error?: string }) {
  const w = words(lang).auth;
  const onwards = onwardsFor(lang, next);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome>("ok");
  useGoOnIfSignedIn(onwards);
  const googleProblem = error
    ? ((w.googleErrors as Record<string, string>)[error] ?? w.googleErrors.google_failed)
    : null;
  const nextQuery = next?.startsWith("/") ? `?next=${encodeURIComponent(next)}` : "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    const result = await login(email.trim(), password);
    if (result === "ok") {
      window.location.replace(onwards);
      return;
    }
    setOutcome(result);
    setBusy(false);
  }

  return (
    <Page title={words(lang).loginTitle} hint={words(lang).loginHint}>
      {googleProblem ? <Notice tone="warn">{googleProblem}</Notice> : null}
      <a
        href={googleStartUrl(lang, next)}
        className="rounded-lg border border-line px-4 py-2 text-center font-semibold"
        data-testid="google-sign-in"
      >
        {w.google}
      </a>
      <p className="text-center text-sm text-muted">{w.or}</p>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Field label={w.email} type="email" value={email} onChange={setEmail} autoComplete="email" />
        <Field
          label={w.password}
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
        />
        <Submit busy={busy}>{w.login}</Submit>
        {problem(w, outcome) ? <Notice tone="warn">{problem(w, outcome)}</Notice> : null}
      </form>
      <div className="flex justify-between text-sm">
        <a href={`/news/${lang}/forgot-password`} className="text-accent underline">
          {w.forgot}
        </a>
        <a href={`/news/${lang}/register${nextQuery}`} className="text-accent underline">
          {w.create}
        </a>
      </div>
    </Page>
  );
}

export function RegisterForm({ lang, next }: { lang: Lang; next?: string }) {
  const w = words(lang).auth;
  const onwards = onwardsFor(lang, next);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome>("ok");
  const [sent, setSent] = useState<{ signedIn: boolean } | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    const result = await register(email.trim(), password, lang);
    if (result !== "ok") {
      setOutcome(result);
      setBusy(false);
      return;
    }
    // a new account signs in with the password just chosen; an address that already had one
    // does not — and either way the page says the same thing: look in the inbox
    const signedIn = (await login(email.trim(), password)) === "ok";
    setSent({ signedIn });
    setBusy(false);
  }

  if (sent) {
    return (
      <Page title={w.registerTitle}>
        <Notice>{w.registerSent}</Notice>
        {sent.signedIn ? (
          <a href={onwards} className="text-accent underline">
            {w.continue}
          </a>
        ) : null}
      </Page>
    );
  }
  return (
    <Page title={w.registerTitle} hint={w.registerHint}>
      <a
        href={googleStartUrl(lang, next)}
        className="rounded-lg border border-line px-4 py-2 text-center font-semibold"
      >
        {w.google}
      </a>
      <p className="text-center text-sm text-muted">{w.or}</p>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Field label={w.email} type="email" value={email} onChange={setEmail} autoComplete="email" />
        <Field
          label={w.password}
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
        />
        <p className="text-xs text-muted">{w.passwordRule}</p>
        <Submit busy={busy}>{w.create}</Submit>
        {problem(w, outcome) ? <Notice tone="warn">{problem(w, outcome)}</Notice> : null}
      </form>
      <a href={`/news/${lang}/login`} className="text-sm text-accent underline">
        {w.haveAccount}
      </a>
    </Page>
  );
}

export function ForgotForm({ lang }: { lang: Lang }) {
  const w = words(lang).auth;
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setOutcome(await forgotPassword(email.trim(), lang));
    setBusy(false);
  }

  return (
    <Page title={w.forgotTitle} hint={w.forgotHint}>
      {outcome === "ok" ? (
        <Notice>{w.forgotSent}</Notice>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Field label={w.email} type="email" value={email} onChange={setEmail} autoComplete="email" />
          <Submit busy={busy}>{w.forgotSend}</Submit>
          {outcome ? <Notice tone="warn">{problem(w, outcome)}</Notice> : null}
        </form>
      )}
    </Page>
  );
}

export function ResetForm({ lang, token }: { lang: Lang; token?: string }) {
  const w = words(lang).auth;
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(token ? null : "expired");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    setBusy(true);
    const result = await resetPassword(token, password);
    if (result === "ok") {
      window.location.replace(`/news/${lang}`);
      return;
    }
    setOutcome(result);
    setBusy(false);
  }

  if (outcome === "expired") {
    return (
      <Page title={w.resetTitle}>
        <Notice tone="warn">{w.resetExpired}</Notice>
        <a href={`/news/${lang}/forgot-password`} className="text-accent underline">
          {w.forgotTitle}
        </a>
      </Page>
    );
  }
  return (
    <Page title={w.resetTitle} hint={w.resetHint}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Field
          label={w.newPassword}
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
        />
        <p className="text-xs text-muted">{w.passwordRule}</p>
        <Submit busy={busy}>{w.resetSubmit}</Submit>
        {outcome ? <Notice tone="warn">{problem(w, outcome)}</Notice> : null}
      </form>
    </Page>
  );
}

/**
 * The other end of the confirmation link. A one-time token and an effect that may run twice
 * (React's development double-invoke, a refresh, a browser prefetch) do not get along: the
 * exchange happens once per token.
 */
export function VerifyEmail({ lang, token }: { lang: Lang; token?: string }) {
  const w = words(lang).auth;
  const [state, setState] = useState<"working" | "done" | "expired">(token ? "working" : "expired");
  const [resent, setResent] = useState(false);
  const tried = useRef<string | null>(null);

  useEffect(() => {
    if (!token || tried.current === token) return;
    tried.current = token;
    void verifyEmail(token).then(async (result) => {
      if (result === "ok") return setState("done");
      // already confirmed by the first of two runs? then it is done, not expired
      const me = await fetchMe().catch(() => null);
      setState(me?.email_verified ? "done" : "expired");
    });
  }, [token]);

  async function resend() {
    setResent((await resendVerification(lang)) === "ok");
  }

  return (
    <Page title={w.verifyTitle}>
      {state === "working" ? <p data-testid="verify-state">{w.verifying}</p> : null}
      {state === "done" ? (
        <>
          <Notice>{w.verified}</Notice>
          <a href={`/news/${lang}`} className="text-accent underline">
            {w.continue}
          </a>
        </>
      ) : null}
      {state === "expired" ? (
        <>
          <Notice tone="warn">{w.verifyExpired}</Notice>
          {resent ? (
            <Notice>{w.resent}</Notice>
          ) : (
            <button type="button" onClick={resend} className="text-left text-accent underline">
              {w.resend}
            </button>
          )}
        </>
      ) : null}
    </Page>
  );
}
