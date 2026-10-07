"use client";

// A move on the board, start to end (AD-08): ask (moves.ts says whether a reason is needed),
// show the card where it is going at once, send it, and then either keep it there until the
// list says so — an approval is the workflow's to carry out, a moment later — or put it back
// and say why. Drags and the 移動到… menu both come here.
import { useState, type ReactNode } from "react";

import { ConfirmDialog } from "@/features/admin-ui/Dialog";
import { useCan } from "@/features/admin-ui/permissions";
import { useToast } from "@/features/admin-ui/Toast";

import type { BoardCard } from "./Board";
import { MOVE_INFO, MOVE_NEEDS, MOVES, moveFor, type Entity, type Move } from "./moves";

interface Moving {
  card: BoardCard;
  move: Move;
}

export function useBoardMoves({
  entity,
  columnLabel,
  run,
  onDone,
}: {
  entity: Entity;
  columnLabel: (key: string) => string;
  /** Send the move; throws when refused. */
  run: (card: BoardCard, move: Move, reason: string | null) => Promise<unknown>;
  /** After a move went through: refresh what the board shows. */
  onDone: () => unknown;
}): {
  /** Lay the moves still settling over what the lists say. */
  place: (columns: Record<string, readonly BoardCard[] | undefined>) => Record<string, readonly BoardCard[] | undefined>;
  /** The columns' totals, with the moves still settling counted where they are going. */
  count: (
    columns: Record<string, readonly BoardCard[] | undefined>,
    totals: Record<string, number | null>,
  ) => Record<string, number | null>;
  busy: ReadonlySet<string>;
  targets: (card: BoardCard) => string[];
  ask: (card: BoardCard, to: string) => void;
  dialog: ReactNode;
} {
  const toast = useToast();
  const can = useCan();
  const [asking, setAsking] = useState<Moving | null>(null);
  // card id -> where it is going, and the card as it was (to put it back)
  const [moved, setMoved] = useState<Record<string, Moving>>({});
  const [busy, setBusy] = useState<ReadonlySet<string>>(new Set());

  const send = async ({ card, move }: Moving, reason: string | null) => {
    const verb = MOVE_INFO[move.action].verb;
    setMoved((now) => ({ ...now, [card.id]: { card, move } }));
    setBusy((now) => new Set(now).add(card.id));
    try {
      await run(card, move, reason);
      toast(`已${verb}：${card.title}`);
      await onDone();
    } catch (error) {
      setMoved((now) => {
        const next = { ...now };
        delete next[card.id];
        return next;
      });
      toast(`沒有${verb}「${card.title}」：${error instanceof Error ? error.message : String(error)}`, "danger");
    } finally {
      setBusy((now) => {
        const next = new Set(now);
        next.delete(card.id);
        return next;
      });
    }
  };

  // still where it was: the list has not caught up yet
  const settlingIn = (columns: Record<string, readonly BoardCard[] | undefined>) =>
    Object.values(moved).filter(({ card, move }) => (columns[move.from] ?? []).some((c) => c.id === card.id));

  const count = (columns: Record<string, readonly BoardCard[] | undefined>, totals: Record<string, number | null>) => {
    const out = { ...totals };
    for (const { move } of settlingIn(columns)) {
      if (out[move.from] != null) out[move.from] = out[move.from]! - 1;
      if (out[move.to] != null) out[move.to] = out[move.to]! + 1;
    }
    return out;
  };

  const place = (columns: Record<string, readonly BoardCard[] | undefined>) => {
    const settling = settlingIn(columns);
    const leaving = new Set(settling.map(({ card }) => card.id));
    const out: Record<string, readonly BoardCard[] | undefined> = {};
    for (const [key, list] of Object.entries(columns)) {
      const arriving = settling
        .filter(({ move }) => move.to === key)
        .map(({ card }) => ({ ...card, column: key, meta: <span className="text-accent">處理中…（{columnLabel(key)}）</span> }));
      out[key] = list === undefined ? undefined : [...arriving, ...list.filter((c) => !leaving.has(c.id))];
    }
    return out;
  };

  const ask = (card: BoardCard, to: string) => {
    const move = moveFor(entity, card.column, to);
    if (move) setAsking({ card, move });
  };

  const info = asking ? MOVE_INFO[asking.move.action] : null;
  const dialog =
    asking && info ? (
      <ConfirmDialog
        title={`${info.verb}「${asking.card.title}」？`}
        confirmLabel={info.verb}
        tone={info.tone}
        reason={
          info.reason === "required"
            ? { placeholder: asking.move.action === "send_back" || asking.move.action === "revise" ? "要改什麼（必填，寫手照這段改）" : "理由（必填）", maxLength: 8000 }
            : undefined
        }
        onConfirm={(reason) => {
          const now = asking;
          setAsking(null);
          void send(now, reason || null);
        }}
        onCancel={() => setAsking(null)}
      >
        {columnLabel(asking.move.from)} → {columnLabel(asking.move.to)}
      </ConfirmDialog>
    ) : null;

  // only the moves this role may make (AD-09)
  const targets = (card: BoardCard) =>
    MOVES[entity].filter((m) => m.from === card.column && can(MOVE_NEEDS[m.action])).map((m) => m.to);
  return { place, count, busy, targets, ask, dialog };
}
