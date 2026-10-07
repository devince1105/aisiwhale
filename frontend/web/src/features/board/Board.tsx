"use client";

// The production board (AD-08), Jira's: a column a state, a card a thing in it. A card is dragged
// only where a person may move it (moves.ts): while it is held, the columns it may go to light
// up and the others fade and take nothing. Each card also has a 移動到… menu with the same
// choices, for the keyboard and for a screen reader (dnd-kit's keyboard dragging works too).
// What a move does — and what it asks first — is the caller's (onMove).
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import type { Tone } from "@/events/describe";
import { ROW, ROW_FOCUS } from "@/features/admin-ui/hotkeys";
import { StatusLozenge } from "@/features/admin-ui/StatusLozenge";

export interface BoardColumn {
  key: string;
  label: string;
  tone: Tone;
}

export interface BoardCard {
  id: string;
  column: string;
  title: string;
  href: string;
  meta?: ReactNode;
}

export interface BoardProps {
  label: string;
  columns: readonly BoardColumn[];
  /** Each column's cards, or undefined while it loads. */
  cards: Record<string, readonly BoardCard[] | undefined>;
  /** How many a column has in all, when more than it shows. */
  totals?: Record<string, number | null>;
  targets: (card: BoardCard) => readonly string[];
  onMove: (card: BoardCard, to: string) => void;
  /** A plain click on a title (AD-07's peek). */
  onOpen?: (id: string) => void;
  /** Cards whose move is under way. */
  busy?: ReadonlySet<string>;
}

export function Board({ label, columns, cards, totals = {}, targets, onMove, onOpen, busy = new Set() }: BoardProps) {
  const [held, setHeld] = useState<BoardCard | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor));
  const allowed = held ? new Set(targets(held)) : null;
  const find = (id: string) =>
    Object.values(cards)
      .flatMap((list) => list ?? [])
      .find((card) => card.id === id) ?? null;

  const onDragStart = (event: DragStartEvent) => setHeld(find(String(event.active.id)));
  const onDragEnd = (event: DragEndEvent) => {
    const card = find(String(event.active.id));
    setHeld(null);
    const to = event.over ? String(event.over.id) : null;
    if (card && to && to !== card.column && targets(card).includes(to)) onMove(card, to);
  };

  return (
    <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd} onDragCancel={() => setHeld(null)}>
      <div role="region" aria-label={label} className="flex gap-3 overflow-x-auto pb-3">
        {columns.map((column) => (
          <Column
            key={column.key}
            column={column}
            cards={cards[column.key]}
            total={totals[column.key] ?? null}
            state={!allowed || held?.column === column.key ? "idle" : allowed.has(column.key) ? "open" : "closed"}
            columns={columns}
            targets={targets}
            onMove={onMove}
            onOpen={onOpen}
            busy={busy}
          />
        ))}
      </div>
    </DndContext>
  );
}

function Column({
  column,
  cards,
  total,
  state,
  columns,
  targets,
  onMove,
  onOpen,
  busy,
}: {
  column: BoardColumn;
  cards: readonly BoardCard[] | undefined;
  total: number | null;
  state: "idle" | "open" | "closed";
  columns: readonly BoardColumn[];
  targets: BoardProps["targets"];
  onMove: BoardProps["onMove"];
  onOpen?: (id: string) => void;
  busy: ReadonlySet<string>;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: column.key, disabled: state === "closed" });
  const shown = cards?.length ?? 0;
  return (
    <section
      ref={setNodeRef}
      aria-label={column.label}
      data-drop={state}
      className={`flex w-64 shrink-0 flex-col rounded-lg border bg-canvas transition-opacity ${
        state === "open" ? (isOver ? "border-accent bg-accent/10" : "border-accent/60 border-dashed") : "border-line"
      } ${state === "closed" ? "opacity-40" : ""}`}
    >
      <h2 className="flex items-center justify-between px-3 py-2 text-xs font-semibold">
        <StatusLozenge tone={column.tone}>{column.label}</StatusLozenge>
        <span className="text-muted tabular-nums">{total !== null && total > shown ? `${shown} / ${total}` : shown}</span>
      </h2>
      <ul className="grid min-h-16 content-start gap-2 px-2 pb-2">
        {cards === undefined ? (
          <li className="px-1 text-xs text-muted">載入中…</li>
        ) : cards.length === 0 ? (
          <li className="px-1 text-xs text-muted">沒有</li>
        ) : (
          cards.map((card) => (
            <Card key={card.id} card={card} columns={columns} targets={targets(card)} onMove={onMove} onOpen={onOpen} busy={busy.has(card.id)} />
          ))
        )}
      </ul>
    </section>
  );
}

function Card({
  card,
  columns,
  targets,
  onMove,
  onOpen,
  busy,
}: {
  card: BoardCard;
  columns: readonly BoardColumn[];
  targets: readonly string[];
  onMove: BoardProps["onMove"];
  onOpen?: (id: string) => void;
  busy: boolean;
}) {
  const movable = targets.length > 0 && !busy;
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: card.id, disabled: !movable });
  const style = transform ? { transform: `translate(${transform.x}px, ${transform.y}px)` } : undefined;
  return (
    <li
      ref={setNodeRef}
      style={style}
      {...ROW}
      data-card={card.id}
      aria-busy={busy || undefined}
      className={`rounded-md border border-line bg-surface p-2.5 text-sm shadow-sm ${ROW_FOCUS} ${isDragging ? "z-10 shadow-lg" : ""} ${busy ? "opacity-60" : ""}`}
    >
      <div className="flex items-start gap-1.5">
        {movable ? (
          <button
            type="button"
            aria-label={`拖曳「${card.title}」`}
            className="mt-0.5 cursor-grab touch-none rounded px-0.5 text-muted hover:text-ink active:cursor-grabbing"
            {...attributes}
            {...listeners}
          >
            ⠿
          </button>
        ) : null}
        <Link
          href={card.href}
          onClick={(event) => {
            if (!onOpen || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            onOpen(card.id);
          }}
          className="min-w-0 font-medium break-words hover:text-accent"
        >
          {card.title}
        </Link>
      </div>
      {card.meta ? <div className="mt-1 text-xs text-muted">{card.meta}</div> : null}
      {movable ? (
        <select
          aria-label={`把「${card.title}」移到`}
          value=""
          onChange={(event) => event.target.value && onMove(card, event.target.value)}
          className="mt-2 w-full rounded border border-line bg-canvas px-1.5 py-0.5 text-xs text-muted"
        >
          <option value="">移動到…</option>
          {targets.map((to) => (
            <option key={to} value={to}>
              {columns.find((c) => c.key === to)?.label ?? to}
            </option>
          ))}
        </select>
      ) : null}
    </li>
  );
}
