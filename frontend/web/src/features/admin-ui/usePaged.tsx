"use client";

// A back-office list loaded a page at a time (AD-04): its rows so far, and the line under it.
import { useInfiniteQuery, type InfiniteData, type UseInfiniteQueryOptions } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { itemsOf, totalOf, type Page } from "@/api/queries";

import { LoadMore } from "./states";

export function usePaged<T, K extends readonly unknown[]>(
  options: UseInfiniteQueryOptions<Page<T>, Error, InfiniteData<Page<T>>, K, string | null>,
): { items: T[] | undefined; total: number | null; error: Error | null; footer: ReactNode } {
  const query = useInfiniteQuery(options);
  const items = itemsOf(query.data);
  const total = totalOf(query.data);
  return {
    items,
    total,
    error: query.error,
    footer: (
      <LoadMore
        shown={items?.length ?? 0}
        total={total}
        more={query.hasNextPage}
        loading={query.isFetchingNextPage}
        onMore={() => void query.fetchNextPage()}
      />
    ),
  };
}
