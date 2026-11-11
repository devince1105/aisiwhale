// What the address asks a sign-in page (?next=, ?error=, ?token=), read in the browser. Read on
// the server, it made each of those pages rendered per request; read here, the page is built once
// and kept, and the form fills in what was asked as it starts. Inside a <Suspense>.
"use client";

import { useSearchParams } from "next/navigation";
import type { ReactNode } from "react";

export function Asked<K extends string>({
  keys,
  children,
}: {
  keys: readonly K[];
  children: (asked: Partial<Record<K, string>>) => ReactNode;
}) {
  const query = useSearchParams();
  const asked: Partial<Record<K, string>> = {};
  for (const key of keys) {
    const value = query.get(key);
    if (value !== null) asked[key] = value;
  }
  return children(asked);
}
