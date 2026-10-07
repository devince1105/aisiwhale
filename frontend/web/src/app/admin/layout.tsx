// The back office's frame (D-160): light or dark as the operator picks, the same pick as the
// public site's (one per browser, theme.ts). The sidebar and top bar — with the theme button —
// are the signed-in pages' (TokenGate → AdminShell, AD-02); the login page has its own button.
import type { ReactNode } from "react";

export default function AdminRoot({ children }: { children: ReactNode }) {
  return (
    // data-theme is written by the toggle once the page runs: not a mismatch to report
    <div data-admin suppressHydrationWarning className="min-h-dvh bg-canvas text-ink">
      {children}
    </div>
  );
}
