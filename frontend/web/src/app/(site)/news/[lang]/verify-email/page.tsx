// The other end of the confirmation link (D-230): the address is proven. Signs nobody in.
"use client";

import { use } from "react";

import { VerifyEmail } from "@/features/site/AuthPages";
import { isLang, type Lang } from "@/features/site/i18n";

export default function VerifyEmailPage({
  params,
  searchParams,
}: {
  params: Promise<{ lang: string }>;
  searchParams: Promise<{ token?: string }>;
}) {
  const { lang } = use(params);
  const { token } = use(searchParams);
  const language: Lang = isLang(lang) ? lang : "zh-TW";
  return <VerifyEmail lang={language} token={token} />;
}
