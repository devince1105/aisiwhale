// Everything a reader sees (D-047): the site's type and its light or dark. The reader's saved
// pick is put on <html> before the first paint by the root layout's script (theme.ts); this root
// follows it (globals.css), and the toggle writes the pick on it once it is made.
import type { ReactNode } from "react";

import { coffee, sans, serif } from "@/features/site/fonts";

export default function SiteRoot({ children }: { children: ReactNode }) {
  return (
    // data-theme is written by the toggle once the page runs: not a mismatch to report
    <div data-site suppressHydrationWarning className={`${sans.variable} ${serif.variable} ${coffee.variable} bg-surface font-reading text-ink`}>
      {children}
    </div>
  );
}
