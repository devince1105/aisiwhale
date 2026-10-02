// Cloudflare Turnstile (D-166): a check that the reader is a person, mostly without a click.
// Cloudflare's script draws it and hands back a one-time token, which the form sends with the
// message for the API to check. A token is good once and for a few minutes: ``resetKey`` asks
// for a new one, after a send that did not go through.
"use client";

import { useEffect, useRef } from "react";

import type { Lang } from "./i18n";

const SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

interface TurnstileApi {
  render(el: HTMLElement, options: Record<string, unknown>): string;
  reset(id: string): void;
  remove(id: string): void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let loading: Promise<TurnstileApi> | null = null;

function loadTurnstile(): Promise<TurnstileApi> {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SCRIPT;
    script.async = true;
    script.onload = () => (window.turnstile ? resolve(window.turnstile) : reject(new Error("turnstile")));
    script.onerror = () => {
      loading = null;
      reject(new Error("turnstile"));
    };
    document.head.appendChild(script);
  });
  return loading;
}

export function Turnstile({
  siteKey,
  lang,
  onToken,
  resetKey,
}: {
  siteKey: string;
  lang: Lang;
  onToken: (token: string | null) => void;
  resetKey: number;
}) {
  const box = useRef<HTMLDivElement>(null);
  const widget = useRef<string | null>(null);
  const report = useRef(onToken);
  report.current = onToken;

  useEffect(() => {
    let live = true;
    loadTurnstile()
      .then((api) => {
        if (!live || !box.current || widget.current) return;
        widget.current = api.render(box.current, {
          sitekey: siteKey,
          language: lang === "en" ? "en" : "zh-tw",
          theme: "auto",
          callback: (token: string) => report.current(token),
          "expired-callback": () => report.current(null),
          "error-callback": () => report.current(null),
        });
      })
      .catch(() => report.current(null));
    return () => {
      live = false;
      if (widget.current) window.turnstile?.remove(widget.current);
      widget.current = null;
    };
  }, [siteKey, lang]);

  useEffect(() => {
    if (resetKey && widget.current) {
      window.turnstile?.reset(widget.current);
      report.current(null);
    }
  }, [resetKey]);

  return <div ref={box} data-testid="turnstile" />;
}
