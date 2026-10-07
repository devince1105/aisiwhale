"use client";

// A table's state lives in the address (AD-05): the words searched (q), the order (sort), the
// filters, and the page — the page's cursor, the cursors before it (prev, so 上一頁 needs no
// history) and where it starts (from, for "第 51–100 筆"). A reload shows the same page, a link
// shows a colleague the same view, and the browser's back undoes the last change. Everything else
// on the address (?company=) is kept.
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import { PAGE_SIZE } from "@/api/queries";

/** The parameters a page change writes; a search, a sort or a filter starts at the first page. */
const PAGING = ["cursor", "prev", "from"] as const;
/** What a saved view keeps (the rest is the page, or which company). */
export const VIEW_KEYS = ["q", "sort"] as const;
const FIRST = "0";

export interface ListState<S extends string, F extends string> {
  q: string;
  sort: S | null;
  filters: Record<F, string | null>;
  cursor: string | null;
  /** The first row's number on this page, from 1. */
  from: number;
  hasPrev: boolean;
  /** Change the search, the sort or filters (null clears one); back to the first page. */
  set: (changes: { q?: string | null; sort?: S | null; filters?: Partial<Record<F, string | null>> }) => void;
  next: (cursor: string) => void;
  prev: () => void;
  first: () => void;
  /** The search, sort and filters as an address query (for a saved view). */
  view: string;
  /** Apply a saved view's query. */
  applyView: (view: string) => void;
}

export function useListState<S extends string, F extends string = never>(
  filterKeys: readonly F[] = [],
  sorts: readonly S[] = [],
): ListState<S, F> {
  const params = useSearchParams() ?? new URLSearchParams();
  const pathname = usePathname() ?? "";
  const router = useRouter();
  const search = params.toString();

  const go = useCallback(
    (next: URLSearchParams, push: boolean) => {
      const query = next.toString();
      const href = query ? `${pathname}?${query}` : pathname;
      if (push) router.push(href, { scroll: false });
      else router.replace(href, { scroll: false });
    },
    [pathname, router],
  );

  return useMemo(() => {
    const current = new URLSearchParams(search);
    const sortParam = current.get("sort");
    const sort = sortParam && (sorts as readonly string[]).includes(sortParam) ? (sortParam as S) : null;
    const prevStack = (current.get("prev") ?? "").split(".").filter(Boolean);
    const from = Math.max(1, Number(current.get("from")) || 1);
    const filters = Object.fromEntries(filterKeys.map((k) => [k, current.get(k)])) as Record<F, string | null>;
    const fresh = () => {
      const next = new URLSearchParams(search);
      for (const key of PAGING) next.delete(key);
      return next;
    };
    const viewKeys = [...VIEW_KEYS, ...filterKeys];
    return {
      q: current.get("q") ?? "",
      sort,
      filters,
      cursor: current.get("cursor"),
      from,
      hasPrev: prevStack.length > 0,
      set: (changes) => {
        const next = fresh();
        const put = (key: string, value: string | null | undefined) => {
          if (value === undefined) return;
          if (value === null || value === "") next.delete(key);
          else next.set(key, value);
        };
        put("q", changes.q === undefined ? undefined : (changes.q?.trim() ?? null));
        put("sort", changes.sort);
        for (const [key, value] of Object.entries(changes.filters ?? {})) put(key, value as string | null);
        go(next, false);
      },
      next: (cursor) => {
        const next = new URLSearchParams(search);
        next.set("prev", [...prevStack, current.get("cursor") ?? FIRST].join("."));
        next.set("cursor", cursor);
        next.set("from", String(from + PAGE_SIZE));
        go(next, true);
      },
      prev: () => {
        const next = new URLSearchParams(search);
        const back = prevStack.at(-1);
        const rest = prevStack.slice(0, -1);
        if (!back || back === FIRST) next.delete("cursor");
        else next.set("cursor", back);
        if (rest.length) next.set("prev", rest.join("."));
        else next.delete("prev");
        const start = from - PAGE_SIZE;
        if (start > 1) next.set("from", String(start));
        else next.delete("from");
        go(next, true);
      },
      first: () => go(fresh(), true),
      view: new URLSearchParams(viewKeys.flatMap((k) => (current.get(k) ? [[k, current.get(k)!]] : []))).toString(),
      applyView: (view) => {
        const next = fresh();
        for (const key of viewKeys) next.delete(key);
        new URLSearchParams(view).forEach((value, key) => {
          if ((viewKeys as readonly string[]).includes(key)) next.set(key, value);
        });
        go(next, false);
      },
    };
    // filterKeys and sorts are each table's constants, so not dependencies
  }, [search, go]);
}
