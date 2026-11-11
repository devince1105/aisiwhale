// Creating an account (D-230): an address and a password, then a link to confirm the address.
"use client";

import { Suspense, use } from "react";

import { Asked } from "@/features/site/Asked";
import { RegisterForm } from "@/features/site/AuthPages";
import { isLang, type Lang } from "@/features/site/i18n";

export default function RegisterPage({
  params,
}: {
  params: Promise<{ lang: string }>;
}) {
  const { lang } = use(params);
  const language: Lang = isLang(lang) ? lang : "zh-TW";
  return (
    // the query is read in the browser, so the page is built once and kept (Asked.tsx)
    <Suspense fallback={null}>
      <Asked keys={["next"] as const}>{(q) => <RegisterForm lang={language} next={q.next} />}</Asked>
    </Suspense>
  );
}
