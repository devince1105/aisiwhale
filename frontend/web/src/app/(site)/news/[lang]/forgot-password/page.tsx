// Asking for a link to set a new password (D-230) — also how an account with no password yet
// (one that signed in with the old links, or came by Google) gets one.
"use client";

import { use } from "react";

import { ForgotForm } from "@/features/site/AuthPages";
import { isLang, type Lang } from "@/features/site/i18n";

export default function ForgotPasswordPage({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = use(params);
  const language: Lang = isLang(lang) ? lang : "zh-TW";
  return <ForgotForm lang={language} />;
}
