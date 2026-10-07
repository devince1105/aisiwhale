"use client";

// The back office's keyboard (AD-03), Jira's habits: ⌘K or / for the command palette, ? for this
// list, g then a letter to go to a page, j and k to move down and up a list, Enter to open the row.
// None of them fires while typing (an input, a textarea, a select, an editable area), while an IME
// is composing, or while a dialog is open — the dialog has the keyboard then.
import { useEffect, useRef } from "react";

import { ADMIN_NAV } from "./nav";

export interface Shortcut {
  keys: string;
  label: string;
}

/** What the help sheet lists: every shortcut, the ``g`` ones from the navigation map. */
export const SHORTCUTS: readonly { group: string; items: readonly Shortcut[] }[] = [
  {
    group: "全域",
    items: [
      { keys: "⌘ K", label: "開啟指令面板（Windows：Ctrl K）" },
      { keys: "/", label: "開啟指令面板" },
      { keys: "?", label: "顯示這份快捷鍵說明" },
    ],
  },
  {
    group: "前往",
    items: ADMIN_NAV.flatMap((group) => group.items.map((item) => ({ keys: `g ${item.go}`, label: item.label }))),
  },
  {
    group: "列表",
    items: [
      { keys: "j", label: "下一列" },
      { keys: "k", label: "上一列" },
      { keys: "Enter", label: "開啟選取的那一列" },
    ],
  },
  {
    group: "審批收件匣（選取一張卡片時）",
    items: [
      { keys: "a", label: "核准（先確認）" },
      { keys: "r", label: "寫意見：游標移到意見欄，再按退回修改或駁回" },
    ],
  },
];

/** Typing somewhere: the keys are the text's, not the shortcuts'. */
export function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  return target.closest("input, textarea, select, [contenteditable='true']") !== null;
}

function dialogOpen(): boolean {
  return document.querySelector("dialog[open]") !== null;
}

let pendingSince = 0;
const SEQUENCE_MS = 1200;

/** ``g`` was pressed a moment ago and its letter has not come: an element that has keys of its
 * own (an approval card's ``a``) leaves the next one to the sequence. */
export function sequencePending(now = Date.now()): boolean {
  return pendingSince > 0 && now - pendingSince < SEQUENCE_MS;
}

export interface Hotkeys {
  /** ⌘K / Ctrl-K: works even while typing. */
  palette: () => void;
  /** ``/`` */
  search: () => void;
  /** ``?`` */
  help: () => void;
  /** ``g`` then a letter; returns whether the letter meant anything. */
  go: (letter: string) => boolean;
  /** ``j`` / ``k`` */
  row: (delta: 1 | -1) => void;
  /** Enter on a selected row. */
  openRow: () => boolean;
}

export function useHotkeys(handlers: Hotkeys, enabled = true): void {
  const latest = useRef(handlers);
  latest.current = handlers;
  useEffect(() => {
    if (!enabled) return;
    const onKey = (event: KeyboardEvent) => {
      const h = latest.current;
      if (event.isComposing || event.keyCode === 229) return; // 注音、倉頡 choosing a character
      if ((event.metaKey || event.ctrlKey) && !event.altKey && event.key.toLowerCase() === "k") {
        if (dialogOpen() && !document.querySelector("dialog[open][data-palette]")) return;
        event.preventDefault();
        h.palette();
        return;
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.defaultPrevented || isTyping(event.target) || dialogOpen()) return;

      if (sequencePending()) {
        pendingSince = 0;
        if (h.go(event.key.toLowerCase())) event.preventDefault();
        return;
      }
      switch (event.key) {
        case "g":
          pendingSince = Date.now();
          return;
        case "/":
          event.preventDefault();
          h.search();
          return;
        case "?":
          event.preventDefault();
          h.help();
          return;
        case "j":
          event.preventDefault();
          h.row(1);
          return;
        case "k":
          event.preventDefault();
          h.row(-1);
          return;
        case "Enter":
          if (h.openRow()) event.preventDefault();
          return;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      pendingSince = 0;
    };
  }, [enabled]);
}

// --- rows -------------------------------------------------------------------------------------

/** What a list row spreads on itself to take part in j / k: focusable by script, not by Tab. */
export const ROW = { "data-row": "", tabIndex: -1 } as const;

/** The ring a row shows while it is the selected one. */
export const ROW_FOCUS = "outline-none focus:ring-2 focus:ring-accent focus:ring-inset";

function rows(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>("main [data-row]"));
}

/** Select the next (1) or previous (-1) row of the page; the first when none is selected yet. */
export function moveRow(delta: 1 | -1): void {
  const all = rows();
  if (all.length === 0) return;
  const at = all.findIndex((row) => row.contains(document.activeElement));
  const next = at < 0 ? (delta > 0 ? 0 : all.length - 1) : Math.min(all.length - 1, Math.max(0, at + delta));
  all[next].focus();
  all[next].scrollIntoView?.({ block: "nearest" });
}

/** Enter on the selected row: follow its first link. */
export function openRow(): boolean {
  const active = document.activeElement;
  if (!(active instanceof HTMLElement) || !active.hasAttribute("data-row")) return false;
  const link = active.querySelector<HTMLAnchorElement>("a[href]");
  if (!link) return false;
  link.click();
  return true;
}
