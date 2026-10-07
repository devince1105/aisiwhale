"use client";

// What the signed-in admin's role may do (AD-09), for the pages to hide what it may not: the
// sign-in gate puts /me's permissions here. The API decides (403) whatever the page shows; this
// only spares a person buttons that would be refused. Outside a signed-in page — a test, a view
// rendered on its own — everything is shown, as before roles.
import { createContext, useContext, type ReactNode } from "react";

const Permissions = createContext<ReadonlySet<string> | null>(null);

export function PermissionsProvider({ permissions, children }: { permissions: readonly string[] | undefined; children: ReactNode }) {
  return <Permissions.Provider value={permissions ? new Set(permissions) : null}>{children}</Permissions.Provider>;
}

/** ``can("newsroom:edit")``: whether to show what needs it. */
export function useCan(): (key: string) => boolean {
  const allowed = useContext(Permissions);
  return (key) => allowed === null || allowed.has(key);
}
