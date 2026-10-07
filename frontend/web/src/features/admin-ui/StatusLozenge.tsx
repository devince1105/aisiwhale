// One status label for every kind of thing the back office shows (AD-01) — a story, an article,
// an approval, a comp — in the event vocabulary's tones (events/describe.ts): grey for not
// started, blue for under way, amber for waiting on someone, green for done, red for failed.
import type { ReactNode } from "react";

import type { Tone } from "@/events/describe";

const TONE: Record<Tone, string> = {
  neutral: "bg-neutral/20 text-muted",
  think: "bg-neutral/20 text-ink",
  work: "bg-accent/15 text-accent",
  review: "bg-warn/15 text-warn",
  ok: "bg-ok/15 text-ok",
  warn: "bg-warn/15 text-warn",
  danger: "bg-danger-soft text-danger",
};

export function StatusLozenge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span data-tone={tone} className={`inline-block rounded px-1.5 py-0.5 text-xs leading-none font-semibold whitespace-nowrap ${TONE[tone]}`}>
      {children}
    </span>
  );
}
