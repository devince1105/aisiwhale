// Signing in (D-230): Google, or an address and a password. A Google sign-in that could not
// finish comes back here with ?error=<reason>.
"use client";

import { Suspense, use } from "react";

import { Asked } from "@/features/site/Asked";
import { LoginForm } from "@/features/site/AuthPages";
import { isLang, type Lang } from "@/features/site/i18n";

export default function LoginPage({
  params,
}: {
  params: Promise<{ lang: string }>;
}) {
  const { lang } = use(params);
  const language: Lang = isLang(lang) ? lang : "zh-TW";
  return (
    // the query is read in the browser, so the page is built once and kept (Asked.tsx)
    <Suspense fallback={null}>
      <Asked keys={["next", "error"] as const}>{(q) => <LoginForm lang={language} next={q.next} error={q.error} />}</Asked>
    </Suspense>
  );
}
