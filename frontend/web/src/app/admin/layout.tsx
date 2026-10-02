// The back office's frame (D-160): light or dark as the operator picks, the same pick as the
// public site's (one per browser, theme.ts), and a button for it in the corner of every page —
// the pages draw their own headers, so the button floats rather than sitting in one of them.
import type { ReactNode } from "react";

import { ThemeToggle } from "@/features/site/ThemeToggle";

export default function AdminRoot({ children }: { children: ReactNode }) {
  return (
    // data-theme is written by the toggle once the page runs: not a mismatch to report
    <div data-admin suppressHydrationWarning className="min-h-dvh bg-canvas text-ink">
      {children}
      <div className="fixed bottom-4 left-4 z-50 rounded-lg border border-line bg-surface shadow-sm print:hidden">
        <ThemeToggle lang="zh-TW" />
      </div>
    </div>
  );
}
