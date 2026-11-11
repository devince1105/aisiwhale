// The other end of the reset link (D-230): set the new password; every other session ends.
"use client";

import { Suspense, use } from "react";

import { Asked } from "@/features/site/Asked";
import { ResetForm } from "@/features/site/AuthPages";
import { isLang, type Lang } from "@/features/site/i18n";

export default function ResetPasswordPage({
  params,
}: {
  params: Promise<{ lang: string }>;
}) {
  const { lang } = use(params);
  const language: Lang = isLang(lang) ? lang : "zh-TW";
  return (
    // the query is read in the browser, so the page is built once and kept (Asked.tsx)
    <Suspense fallback={null}>
      <Asked keys={["token"] as const}>{(q) => <ResetForm lang={language} token={q.token} />}</Asked>
    </Suspense>
  );
}
