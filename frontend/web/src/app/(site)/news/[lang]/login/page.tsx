// Signing in (D-230): Google, or an address and a password. A Google sign-in that could not
// finish comes back here with ?error=<reason>.
"use client";

import { use } from "react";

import { LoginForm } from "@/features/site/AuthPages";
import { isLang, type Lang } from "@/features/site/i18n";

export default function LoginPage({
  params,
  searchParams,
}: {
  params: Promise<{ lang: string }>;
  searchParams: Promise<{ next?: string; error?: string }>;
}) {
  const { lang } = use(params);
  const { next, error } = use(searchParams);
  const language: Lang = isLang(lang) ? lang : "zh-TW";
  return <LoginForm lang={language} next={next} error={error} />;
}
