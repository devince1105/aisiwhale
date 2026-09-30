// A long passage on an approval card, folded (D-140): the decision's note can run to 8,000
// characters (D-139) and a payload to a screenful, and the card should stay a card. A short one
// shows whole; a long one shows its first lines, faded out, with a button to open and close it —
// kept on screen while open, since an open note can be taller than the window.
"use client";

import { useState, type ReactNode } from "react";

/** Longer than this (characters or lines) folds. */
export const FOLD_CHARS = 240;
export const FOLD_LINES = 6;

export function isLong(text: string): boolean {
  return text.length > FOLD_CHARS || text.split("\n").length > FOLD_LINES;
}

export function Folded({
  text,
  children,
  className = "",
}: {
  text: string;
  children?: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const long = isLong(text);
  const body = children ?? (
    <p className="leading-relaxed break-words whitespace-pre-wrap">{text}</p>
  );
  if (!long) return <div className={className}>{body}</div>;
  return (
    <div className={className} data-folded={open ? "open" : "closed"}>
      <div
        className={open ? undefined : "max-h-28 overflow-hidden"}
        style={
          open
            ? undefined
            : {
                maskImage: "linear-gradient(to bottom, black 55%, transparent)",
                WebkitMaskImage:
                  "linear-gradient(to bottom, black 55%, transparent)",
              }
        }
      >
        {body}
      </div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className={`mt-1 text-sm text-accent underline ${open ? "sticky bottom-2 rounded bg-canvas px-2 py-0.5 shadow-sm" : ""}`}
      >
        {open
          ? "收合"
          : `展開全部（${text.length.toLocaleString("zh-TW")} 字）`}
      </button>
    </div>
  );
}
