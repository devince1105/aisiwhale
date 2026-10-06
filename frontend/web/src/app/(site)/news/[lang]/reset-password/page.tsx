// The other end of the reset link (D-230): set the new password; every other session ends.
"use client";

import { use } from "react";

import { ResetForm } from "@/features/site/AuthPages";
import { isLang, type Lang } from "@/features/site/i18n";

export default function ResetPasswordPage({
  params,
  searchParams,
}: {
  params: Promise<{ lang: string }>;
  searchParams: Promise<{ token?: string }>;
}) {
  const { lang } = use(params);
  const { token } = use(searchParams);
  const language: Lang = isLang(lang) ? lang : "zh-TW";
  return <ResetForm lang={language} token={token} />;
}
