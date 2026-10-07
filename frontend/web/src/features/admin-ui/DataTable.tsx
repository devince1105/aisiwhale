"use client";

// The back office's table (AD-05), Jira's issue list without a library: columns as data, a
// header that sorts on the server, rows that j / k walk, check boxes and a bar of what can be done
// to the checked rows, and two densities. Around it, from the same file: the toolbar (search,
// filter chips, saved views, density) and the pager — both read and write the address
// (useListState), so what the table shows is what the link says.
import {
  useState,
  useSyncExternalStore,
  type FormEvent,
  type ReactNode,
} from "react";

import { Button } from "./Button";
import { ROW, ROW_FOCUS } from "./hotkeys";
import { Icon } from "./icons";
import { EmptyState, ErrorState, LoadingState } from "./states";
import type { ListState } from "./useListState";

// --- density ----------------------------------------------------------------------------------

export type Density = "comfortable" | "compact";
const DENSITY_KEY = "autora.admin.density";
const densityListeners = new Set<() => void>();

function readDensity(): Density {
  try {
    return window.localStorage.getItem(DENSITY_KEY) === "compact"
      ? "compact"
      : "comfortable";
  } catch {
    return "comfortable";
  }
}

function setDensity(density: Density): void {
  try {
    window.localStorage.setItem(DENSITY_KEY, density);
  } catch {
    // storage blocked: it changes for now, not for next time
  }
  densityListeners.forEach((listener) => listener());
}

/** One density for every table in this browser. */
export function useDensity(): Density {
  return useSyncExternalStore(
    (listener) => {
      densityListeners.add(listener);
      return () => densityListeners.delete(listener);
    },
    readDensity,
    () => "comfortable",
  );
}

// --- the table --------------------------------------------------------------------------------

export interface Column<T> {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
  /** The sort this column's header asks for; the opposite direction too when it is allowed. */
  sort?: string;
  align?: "right";
  /** Extra classes for its cells (a width, no wrapping…). */
  className?: string;
}

export interface BulkAction<T> {
  label: string;
  tone?: "danger";
  run: (rows: T[]) => void;
}

export interface SortControl {
  value: string | null;
  /** The order the server uses when none is asked for. */
  fallback: string;
  allowed: readonly string[];
  onSort: (sort: string) => void;
}

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  label,
  empty,
  error = null,
  sort,
  bulk,
  rowTestId,
}: {
  rows: readonly T[] | undefined;
  columns: readonly Column<T>[];
  rowKey: (row: T) => string;
  /** The table's accessible name. */
  label: string;
  empty: ReactNode;
  error?: string | null;
  sort?: SortControl;
  /** Check boxes, and what can be done to the checked rows. */
  bulk?: readonly BulkAction<T>[];
  rowTestId?: (row: T) => string;
}) {
  const density = useDensity();
  const [checked, setChecked] = useState<ReadonlySet<string>>(new Set());
  if (error) return <ErrorState>{error}</ErrorState>;
  if (!rows) return <LoadingState />;
  if (rows.length === 0) return <EmptyState>{empty}</EmptyState>;

  // only rows still on the page count as checked
  const onPage = new Set(rows.map(rowKey));
  const picked = rows.filter((row) => checked.has(rowKey(row)));
  const all = picked.length === rows.length;
  const pad = density === "compact" ? "px-3 py-1" : "px-3 py-2.5";
  const toggle = (key: string) => {
    const next = new Set([...checked].filter((k) => onPage.has(k)));
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setChecked(next);
  };

  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      {bulk && picked.length ? (
        <div
          role="toolbar"
          aria-label="批次動作"
          className="flex items-center gap-2 border-b border-line bg-accent/5 px-3 py-2 text-sm"
        >
          <span className="font-medium">已選 {picked.length} 筆</span>
          {bulk.map((action) => (
            <Button
              key={action.label}
              size="sm"
              variant={action.tone === "danger" ? "danger" : "default"}
              onClick={() => action.run(picked)}
            >
              {action.label}
            </Button>
          ))}
          <Button
            size="sm"
            variant="subtle"
            onClick={() => setChecked(new Set())}
          >
            取消選取
          </Button>
        </div>
      ) : null}
      <table aria-label={label} className="w-full text-left text-sm">
        <thead className="border-b border-line text-xs text-muted">
          <tr>
            {bulk ? (
              <th className={`${pad} w-8`}>
                <input
                  type="checkbox"
                  aria-label="全選這一頁"
                  checked={all}
                  onChange={() => setChecked(all ? new Set() : new Set(onPage))}
                />
              </th>
            ) : null}
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={`${pad} font-medium whitespace-nowrap ${column.align === "right" ? "text-right" : ""}`}
                aria-sort={ariaSort(column, sort)}
              >
                {column.sort && sort ? (
                  <SortButton column={column} sort={sort} />
                ) : (
                  column.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((row) => {
            const key = rowKey(row);
            return (
              <tr
                key={key}
                {...ROW}
                className={`${ROW_FOCUS} ${checked.has(key) ? "bg-accent/5" : ""}`}
                data-key={key}
                data-testid={rowTestId?.(row)}
              >
                {bulk ? (
                  <td className={pad}>
                    <input
                      type="checkbox"
                      aria-label="選取這一列"
                      checked={checked.has(key)}
                      onChange={() => toggle(key)}
                    />
                  </td>
                ) : null}
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={`${pad} align-top ${column.align === "right" ? "text-right tabular-nums" : ""} ${column.className ?? ""}`}
                  >
                    {column.cell(row)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Which way a column is sorted now, for the header's aria-sort. */
function ariaSort<T>(
  column: Column<T>,
  sort: SortControl | undefined,
): "ascending" | "descending" | undefined {
  if (!column.sort || !sort) return undefined;
  const now = sort.value ?? sort.fallback;
  if (now === column.sort) return "ascending";
  if (now === `-${column.sort}`) return "descending";
  return undefined;
}

/** A header that sorts by its column; again, the other way when the server has that order. */
function SortButton<T>({
  column,
  sort,
}: {
  column: Column<T>;
  sort: SortControl;
}) {
  const base = column.sort!;
  const now = sort.value ?? sort.fallback;
  const options = [`-${base}`, base].filter((s) => sort.allowed.includes(s));
  const on = options.includes(now);
  const next = on ? (options.find((s) => s !== now) ?? now) : options[0];
  const arrow = !on ? "" : now.startsWith("-") ? " ↓" : " ↑";
  return (
    <button
      type="button"
      onClick={() => sort.onSort(next)}
      className={`font-medium hover:text-ink ${on ? "text-ink" : ""}`}
    >
      {column.header}
      {arrow}
    </button>
  );
}

// --- the toolbar ------------------------------------------------------------------------------

export interface FilterDef<F extends string> {
  key: F;
  label: string;
  options: readonly { value: string; label: string }[];
}

export function ListToolbar<S extends string, F extends string>({
  list,
  filters = [],
  placeholder = "搜尋…",
  views,
  density: withDensity = true,
}: {
  list: ListState<S, F>;
  filters?: readonly FilterDef<F>[];
  placeholder?: string;
  /** The key a table's saved views are kept under; none: no saved views. */
  views?: string;
  /** The row-height switch; off where the list is not a table (the approval cards). */
  density?: boolean;
}) {
  const density = useDensity();
  // what is typed, until Enter: the address changes once per search, not per letter
  const [typed, setTyped] = useState<{ for: string; text: string } | null>(
    null,
  );
  const text = typed && typed.for === list.q ? typed.text : list.q;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    list.set({ q: text });
  };
  return (
    <div className="mb-3 grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <form
          role="search"
          onSubmit={submit}
          className="flex min-w-48 flex-1 items-center gap-2 rounded-md border border-line bg-surface px-2 sm:max-w-sm"
        >
          <svg
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.6}
            aria-hidden="true"
            className="size-4 shrink-0 text-muted"
          >
            <circle cx="9" cy="9" r="5.5" />
            <path d="M13 13l4 4" strokeLinecap="round" />
          </svg>
          <input
            type="search"
            aria-label="搜尋"
            placeholder={placeholder}
            value={text}
            onChange={(event) =>
              setTyped({ for: list.q, text: event.target.value })
            }
            className="h-8 w-full bg-transparent text-sm outline-none placeholder:text-muted"
          />
        </form>
        {filters.map((filter) => (
          <label
            key={filter.key}
            className="flex h-8 items-center gap-1 rounded-md border border-line bg-surface px-2 text-sm"
          >
            <span className="text-muted">{filter.label}</span>
            <select
              aria-label={filter.label}
              value={list.filters[filter.key] ?? ""}
              onChange={(event) =>
                list.set({
                  filters: {
                    [filter.key]: event.target.value || null,
                  } as Partial<Record<F, string | null>>,
                })
              }
              className="bg-transparent outline-none"
            >
              <option value="">全部</option>
              {filter.options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        ))}
        <span className="grow" />
        {withDensity ? <DensitySwitch density={density} /> : null}
      </div>
      <ActiveFilters list={list} filters={filters} />
      {views ? <SavedViews list={list} storageKey={views} /> : null}
    </div>
  );
}

function DensitySwitch({ density }: { density: Density }) {
  return (
    <div
      role="group"
      aria-label="列高"
      className="flex rounded-md border border-line p-0.5 text-xs"
    >
      {(
        [
          ["comfortable", "寬鬆"],
          ["compact", "緊湊"],
        ] as const
      ).map(([value, name]) => (
        <button
          key={value}
          type="button"
          aria-pressed={density === value}
          onClick={() => setDensity(value)}
          className={`rounded px-2 py-0.5 ${density === value ? "bg-canvas font-medium" : "text-muted"}`}
        >
          {name}
        </button>
      ))}
    </div>
  );
}

/** What narrows the list now, each with a way to take it off. */
function ActiveFilters<S extends string, F extends string>({
  list,
  filters,
}: {
  list: ListState<S, F>;
  filters: readonly FilterDef<F>[];
}) {
  const chips = [
    ...(list.q
      ? [
          {
            key: "q",
            text: `搜尋：${list.q}`,
            clear: () => list.set({ q: null }),
          },
        ]
      : []),
    ...filters.flatMap((filter) => {
      const value = list.filters[filter.key];
      if (!value) return [];
      const name =
        filter.options.find((o) => o.value === value)?.label ?? value;
      return [
        {
          key: filter.key,
          text: `${filter.label}：${name}`,
          clear: () =>
            list.set({
              filters: { [filter.key]: null } as Partial<
                Record<F, string | null>
              >,
            }),
        },
      ];
    }),
  ];
  if (chips.length === 0) return null;
  return (
    <ul
      aria-label="目前的篩選"
      className="flex flex-wrap items-center gap-1.5 text-xs"
    >
      {chips.map((chip) => (
        <li
          key={chip.key}
          className="flex items-center gap-1 rounded-full bg-accent/10 py-0.5 pr-1 pl-2.5 text-accent"
        >
          {chip.text}
          <button
            type="button"
            onClick={chip.clear}
            aria-label={`取消「${chip.text}」`}
            className="rounded-full p-0.5 hover:bg-accent/15"
          >
            <Icon name="close" className="size-3" />
          </button>
        </li>
      ))}
      {chips.length > 1 ? (
        <li>
          <button
            type="button"
            onClick={() =>
              list.set({
                q: null,
                filters: Object.fromEntries(
                  filters.map((f) => [f.key, null]),
                ) as Partial<Record<F, string | null>>,
              })
            }
            className="px-1 text-muted underline"
          >
            全部清除
          </button>
        </li>
      ) : null}
    </ul>
  );
}

// --- saved views ------------------------------------------------------------------------------

interface SavedView {
  name: string;
  view: string;
}

function readViews(key: string): SavedView[] {
  try {
    const raw = JSON.parse(window.localStorage.getItem(key) ?? "[]");
    return Array.isArray(raw)
      ? raw.filter(
          (v): v is SavedView =>
            typeof v?.name === "string" && typeof v?.view === "string",
        )
      : [];
  } catch {
    return [];
  }
}

function writeViews(key: string, views: SavedView[]): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(views));
  } catch {
    // storage blocked: the views last until the page is left
  }
}

/** 我的篩選器: a search and its filters, named and kept in this browser (D-234 ③). */
function SavedViews<S extends string, F extends string>({
  list,
  storageKey,
}: {
  list: ListState<S, F>;
  storageKey: string;
}) {
  const key = `autora.admin.views.${storageKey}`;
  const [views, setViews] = useState<SavedView[] | null>(null);
  const [naming, setNaming] = useState<string | null>(null);
  const shown = views ?? (typeof window === "undefined" ? [] : readViews(key));
  const save = (next: SavedView[]) => {
    setViews(next);
    writeViews(key, next);
  };
  if (!list.view && shown.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs">
      <span className="text-muted">我的篩選器</span>
      {shown.map((view) => (
        <span
          key={view.name}
          className="flex items-center rounded-full border border-line"
        >
          <button
            type="button"
            onClick={() => list.applyView(view.view)}
            aria-pressed={view.view === list.view}
            className={`rounded-l-full py-0.5 pr-1 pl-2.5 ${view.view === list.view ? "font-medium text-accent" : ""}`}
          >
            {view.name}
          </button>
          <button
            type="button"
            onClick={() => save(shown.filter((v) => v.name !== view.name))}
            aria-label={`刪除篩選器「${view.name}」`}
            className="rounded-r-full p-1 text-muted hover:text-ink"
          >
            <Icon name="close" className="size-3" />
          </button>
        </span>
      ))}
      {list.view && !shown.some((v) => v.view === list.view) ? (
        naming === null ? (
          <button
            type="button"
            onClick={() => setNaming("")}
            className="text-accent underline"
          >
            儲存目前的篩選
          </button>
        ) : (
          <form
            className="flex items-center gap-1"
            onSubmit={(event) => {
              event.preventDefault();
              const name = naming.trim();
              if (!name) return;
              save([
                ...shown.filter((v) => v.name !== name),
                { name, view: list.view },
              ]);
              setNaming(null);
            }}
          >
            <input
              autoFocus
              aria-label="篩選器名稱"
              value={naming}
              onChange={(e) => setNaming(e.target.value)}
              maxLength={40}
              placeholder="名稱"
              className="h-6 w-28 rounded border border-line bg-canvas px-1.5"
            />
            <Button type="submit" size="sm" disabled={!naming.trim()}>
              儲存
            </Button>
            <Button size="sm" variant="subtle" onClick={() => setNaming(null)}>
              取消
            </Button>
          </form>
        )
      ) : null}
    </div>
  );
}

// --- the pager --------------------------------------------------------------------------------

export function Pager<S extends string, F extends string>({
  list,
  shown,
  total,
  nextCursor,
}: {
  list: ListState<S, F>;
  shown: number;
  total: number | null;
  nextCursor: string | null | undefined;
}) {
  if (!total) return null;
  const to = list.from + shown - 1;
  return (
    <nav
      aria-label="分頁"
      className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted"
    >
      <span className="tabular-nums">
        第 {list.from}–{to} 筆，共 {total} 筆
      </span>
      <span className="flex gap-1.5">
        {list.hasPrev ? (
          <>
            <Button size="sm" variant="subtle" onClick={list.first}>
              第一頁
            </Button>
            <Button size="sm" onClick={list.prev}>
              上一頁
            </Button>
          </>
        ) : null}
        {nextCursor ? (
          <Button size="sm" onClick={() => list.next(nextCursor)}>
            下一頁
          </Button>
        ) : null}
      </span>
    </nav>
  );
}

/** The table's sort control from the address: ``allowed`` is the endpoint's sorts, ``fallback``
 * the one it uses when none is asked for. */
export function sortControl<S extends string, F extends string>(
  list: ListState<S, F>,
  allowed: readonly S[],
  fallback: S,
): SortControl {
  return {
    value: list.sort,
    fallback,
    allowed,
    onSort: (sort) => list.set({ sort: sort as S }),
  };
}
