"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { Suspense, useCallback, useEffect, type ReactNode } from "react";

import { AdminShell } from "@/features/admin-ui/AdminShell";
import { PermissionsProvider } from "@/features/admin-ui/permissions";

import { fetchAdminMe, loginHref, signOutAdmin } from "./adminAuth";

export const ADMIN_ME_KEY = ["admin-me"] as const;

/**
 * The back office's door (D-055, D-230). Children render for an admin signed in — the API's
 * httpOnly cookie, nothing in browser storage; anybody else is sent to /admin/login and back.
 * A 401 anywhere calls `useAskAgain()`'s function, which asks the API again. Inside, the
 * back office's shell (AD-02): its sidebar, top bar and sign-out.
 */
export function TokenGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const me = useQuery({ queryKey: ADMIN_ME_KEY, queryFn: fetchAdminMe, retry: false, staleTime: 60_000 });
  const signedOut = me.isSuccess && me.data === null;

  useEffect(() => {
    if (!signedOut) return;
    // the query from the address bar, not useSearchParams: that would need a Suspense boundary
    // around every page this gate wraps
    router.replace(loginHref(`${pathname}${window.location.search}`));
  }, [signedOut, pathname, router]);

  const queryClient = useQueryClient();
  const signOut = async () => {
    await signOutAdmin().catch(() => undefined);
    queryClient.clear(); // nothing fetched as this admin survives
    router.replace("/admin/login");
  };

  if (me.data) {
    // the shell reads ?company=; the boundary lets a page without dynamic params prerender
    return (
      <Suspense>
        <PermissionsProvider permissions={me.data.permissions}>
          <AdminShell email={me.data.email} role={me.data.role ?? null} onSignOut={signOut}>
            {children}
          </AdminShell>
        </PermissionsProvider>
      </Suspense>
    );
  }
  return (
    <main className="grid min-h-screen place-items-center p-4 text-sm text-muted">
      {me.isError ? "連不到後端 API。" : "確認登入中…"}
    </main>
  );
}

/** After a 401: ask the API again who is signing in, so the gate sends a signed-out visit to
 * /admin/login. */
export function useAskAgain(): () => void {
  const queryClient = useQueryClient();
  return useCallback(() => void queryClient.invalidateQueries({ queryKey: ADMIN_ME_KEY }), [queryClient]);
}
