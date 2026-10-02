// 聯絡我們 (D-165): a reader writes to the site. The message goes to the API, which emails it to
// the operator with the reader's address to reply to; nothing about the operator is on the page.
// Laid out as a financial data company's contact form is (Bloomberg's): what you need first, then
// who you are, then what sending agrees to. A field nobody sees catches bots: the API says "sent"
// to one and sends nothing.
"use client";

import Link from "next/link";
import { useState } from "react";

import { API_URL } from "@/config";

import { words, type Lang } from "./i18n";

const TOPICS = ["membership", "content", "partnership", "other"] as const;
type Topic = (typeof TOPICS)[number];
type State = "idle" | "sending" | "sent" | "failed" | "busy";

export interface ContactBody {
  name: string;
  email: string;
  phone: string;
  company: string;
  topic: Topic;
  message: string;
  lang: Lang;
  website: string;
}

export async function sendContact(body: ContactBody, fetcher: typeof fetch = fetch): Promise<"sent" | "failed" | "busy"> {
  try {
    const response = await fetcher(`${API_URL}/api/public/contact`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (response.ok) return "sent";
    return response.status === 429 ? "busy" : "failed";
  } catch {
    return "failed";
  }
}

export function ContactForm({ lang }: { lang: Lang }) {
  const w = words(lang).contactForm;
  const [body, setBody] = useState<Omit<ContactBody, "lang">>({
    name: "",
    email: "",
    phone: "",
    company: "",
    topic: "membership",
    message: "",
    website: "",
  });
  const [state, setState] = useState<State>("idle");
  const set = (key: keyof typeof body) => (event: { target: { value: string } }) =>
    setBody((was) => ({ ...was, [key]: event.target.value }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setState("sending");
    setState(await sendContact({ ...body, lang }));
  }

  if (state === "sent") {
    return (
      <p role="status" data-testid="contact-sent" className="rounded-lg border border-line bg-surface p-4 leading-relaxed">
        {w.sent}
      </p>
    );
  }

  const field = "w-full rounded-md border border-line bg-surface px-3 py-2 text-ink";
  const label = "grid gap-1.5 text-sm";
  const optional = <span className="text-muted">{w.optional}</span>;
  return (
    <form onSubmit={submit} className="grid gap-8" data-testid="contact-form">
      <fieldset className="grid gap-4">
        <legend className="mb-3 text-lg font-bold">{w.needTitle}</legend>
        <label className={label}>
          <span>{w.message}</span>
          <textarea
            required
            minLength={10}
            maxLength={4000}
            rows={6}
            value={body.message}
            onChange={set("message")}
            className={field}
            placeholder={w.messageHint}
          />
        </label>
        <div className="grid gap-2 text-sm" role="radiogroup" aria-label={w.topic}>
          <span>{w.topic}</span>
          {TOPICS.map((t) => (
            <label key={t} className="flex items-center gap-2">
              <input type="radio" name="topic" value={t} checked={body.topic === t} onChange={set("topic")} />
              {w.topics[t]}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="grid gap-4">
        <legend className="mb-3 text-lg font-bold">{w.youTitle}</legend>
        <label className={label}>
          <span>{w.name}</span>
          <input required maxLength={80} value={body.name} onChange={set("name")} className={field} autoComplete="name" />
        </label>
        <label className={label}>
          <span>{w.email}</span>
          <input required type="email" maxLength={200} value={body.email} onChange={set("email")} className={field} autoComplete="email" />
        </label>
        <label className={label}>
          <span>
            {w.phone} {optional}
          </span>
          <input type="tel" maxLength={30} value={body.phone} onChange={set("phone")} className={field} autoComplete="tel" />
        </label>
        <label className={label}>
          <span>
            {w.company} {optional}
          </span>
          <input maxLength={100} value={body.company} onChange={set("company")} className={field} autoComplete="organization" />
        </label>
      </fieldset>

      {/* for bots only: hidden from people and from screen readers, left empty by both */}
      <label aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
        Website
        <input tabIndex={-1} autoComplete="off" value={body.website} onChange={set("website")} name="website" />
      </label>

      <div className="grid gap-3">
        <p className="text-xs text-muted">
          {w.consent[0]}
          <Link href={`/news/${lang}/privacy`} className="text-accent underline">
            {w.privacyPolicy}
          </Link>
          {w.consent[1]}
        </p>
        <button
          type="submit"
          disabled={state === "sending"}
          className="w-full rounded-md bg-ink px-6 py-3 font-semibold text-canvas disabled:opacity-60"
        >
          {state === "sending" ? w.sending : w.send}
        </button>
        {state === "failed" ? <p role="alert" className="text-sm text-danger">{w.failed}</p> : null}
        {state === "busy" ? <p role="alert" className="text-sm text-danger">{w.busy}</p> : null}
      </div>
    </form>
  );
}
