import Script from "next/script";
import type { ReactNode } from "react";

import { THEME_SCRIPT } from "@/features/site/theme";

import "./globals.css";
import { Providers } from "./providers";

export const metadata = {
  // what readers and the back office see is the brand, 艾矽鯨 (D-043); "autora" stays the
  // code's own name
  title: "艾矽鯨",
  description: "艾矽鯨 AiSiWhale：AI 科技投資動向",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // Browser extensions write attributes onto <html> before React loads (Immersive Translate
    // adds data-immersive-translate-page-theme), which React reports as a hydration mismatch.
    // This ignores attribute differences on this one element only, not on anything inside it.
    <html lang="zh-TW" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
        {/* the public site's saved light or dark, before the first paint (D-047) */}
        <Script id="site-theme" strategy="beforeInteractive" dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </body>
    </html>
  );
}
