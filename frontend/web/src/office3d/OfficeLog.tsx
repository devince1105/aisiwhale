// The office log (D-136): a small panel over the office, newest first. Work is written plainly
// with a dot; the idle moments (a coffee, a chat) faintly, in italics — the page's own
// decoration, never to be read as work. It folds to a single line.
"use client";

import { useState } from "react";

import { personName } from "@/people";
import { useRealtime } from "@/stores/realtime";

import { useOfficeLog } from "./visual/officeLog";

const SHOWN = 12;

function clock(at: number): string {
  return new Date(at).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Taipei" });
}

export function OfficeLog() {
  const lines = useOfficeLog();
  const agents = useRealtime((s) => s.company?.agents);
  const [open, setOpen] = useState(true);
  const name = (id: string) => personName(agents?.[id]?.display_name) || "同事";
  return (
    <section
      aria-label="辦公室動態"
      className="pointer-events-auto absolute top-3 right-3 w-72 max-w-[calc(100%-4.5rem)] rounded-lg border border-line bg-surface/90 text-xs shadow-sm backdrop-blur"
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-3 py-1.5 text-left font-medium text-ink"
      >
        辦公室動態
        <span aria-hidden className="text-muted">
          {open ? "−" : "+"}
        </span>
      </button>
      {open ? (
        <ol className="max-h-52 overflow-y-auto border-t border-line px-3 py-1.5" data-testid="office-log">
          {lines.length === 0 ? <li className="py-0.5 text-muted">還沒有動靜。</li> : null}
          {lines.slice(0, SHOWN).map((line) => (
            <li
              key={line.id}
              data-kind={line.kind}
              className={`flex gap-2 py-0.5 ${line.kind === "life" ? "text-muted/80 italic" : "text-ink"}`}
            >
              <span className="shrink-0 tabular-nums text-muted">{clock(line.at)}</span>
              <span className="min-w-0">
                {line.kind === "work" ? <span aria-hidden className="mr-1 inline-block size-1.5 rounded-full bg-accent align-middle" /> : null}
                <span className={line.kind === "work" ? "font-medium" : undefined}>{name(line.agentId)}</span> {line.text}
              </span>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
