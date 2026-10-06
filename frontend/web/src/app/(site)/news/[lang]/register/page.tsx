// Creating an account (D-230): an address and a password, then a link to confirm the address.
"use client";

import { use } from "react";

import { RegisterForm } from "@/features/site/AuthPages";
import { isLang, type Lang } from "@/features/site/i18n";

export default function RegisterPage({
  params,
  searchParams,
}: {
  params: Promise<{ lang: string }>;
  searchParams: Promise<{ next?: string }>;
}) {
  const { lang } = use(params);
  const { next } = use(searchParams);
  const language: Lang = isLang(lang) ? lang : "zh-TW";
  return <RegisterForm lang={language} next={next} />;
}
