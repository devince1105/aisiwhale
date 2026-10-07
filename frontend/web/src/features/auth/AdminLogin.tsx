"use client";

// /admin/login (D-055, D-230): the readers' own sign-in — Google, or an address and a password —
// through the back office's door. The API lets in an address on ADMIN_EMAILS that is proven to
// be theirs; the session is its httpOnly cookie. No token is typed in or kept here any more:
// the operator token is for scripts and CI, never for a browser.
import { useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { ThemeToggle } from "@/features/site/ThemeToggle";

import { adminGoogleUrl, afterLogin, loginAdmin, type AdminLoginResult } from "./adminAuth";

type State = "idle" | "sending" | Exclude<AdminLoginResult, "ok">;

const PROBLEM: Record<Exclude<State, "idle" | "sending">, string> = {
  wrong: "Email 或密碼不正確。",
  forbidden: "這個帳號不能進入後台：信箱不在管理員名單上，或還沒有完成 email 驗證。",
  limited: "嘗試太多次了，請稍後再試。",
  failed: "登入失敗，請稍後再試。",
};

const GOOGLE_PROBLEM: Record<string, string> = {
  not_admin: "這個 Google 帳號不能進入後台：信箱不在管理員名單上。",
  google_failed: "Google 登入沒有完成，請再試一次。",
  google_cancelled: "已取消 Google 登入。",
  google_email_unverified: "這個 Google 帳號的 email 尚未經 Google 驗證。",
  google_needs_verified_email: "這個 email 已有帳號但尚未驗證。請先用「忘記密碼」重設密碼，再用 Google 登入。",
  google_other_account_linked: "這個帳號已經連結了另一個 Google 帳號。",
};

export function AdminLogin() {
  const params = useSearchParams();
  const next = params?.get("next") ?? null;
  const googleError = params?.get("error") ?? null;
  const router = useRouter();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [state, setState] = useState<State>("idle");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setState("sending");
    const result = await loginAdmin(email.trim(), password).catch((): AdminLoginResult => "failed");
    if (result === "ok") {
      queryClient.clear(); // nothing fetched before signing in survives
      router.replace(afterLogin(next));
      return;
    }
    setState(result);
  }

  return (
    <main className="relative grid min-h-screen place-items-center p-4">
      <div className="absolute top-4 right-4 rounded-lg border border-line bg-surface">
        <ThemeToggle lang="zh-TW" />
      </div>
      <div className="grid w-full max-w-md gap-4 rounded-2xl border border-line bg-surface p-8">
        <h1 className="text-2xl font-semibold">登入後台</h1>
        <p className="text-sm leading-relaxed text-muted">
          用網站的帳號登入。只有管理員名單上、而且已完成 email 驗證的帳號能進入後台。
        </p>
        {googleError ? (
          <p className="text-sm text-danger" role="alert">
            {GOOGLE_PROBLEM[googleError] ?? GOOGLE_PROBLEM.google_failed}
          </p>
        ) : null}
        <a
          href={adminGoogleUrl(next)}
          className="rounded-lg border border-line px-4 py-2.5 text-center font-semibold"
          data-testid="admin-google"
        >
          使用 Google 繼續
        </a>
        <form onSubmit={submit} className="grid gap-3">
          <label className="grid gap-1.5 text-sm">
            Email
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="rounded-lg border border-line bg-canvas px-3 py-2 text-ink outline-none focus:border-accent"
            />
          </label>
          <label className="grid gap-1.5 text-sm">
            密碼
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded-lg border border-line bg-canvas px-3 py-2 text-ink outline-none focus:border-accent"
            />
          </label>
          <button
            type="submit"
            disabled={state === "sending"}
            className="rounded-lg bg-accent px-4 py-2.5 font-semibold text-accent-ink disabled:opacity-50"
          >
            登入
          </button>
          {state !== "idle" && state !== "sending" ? (
            <p className="text-sm text-danger" role="alert">
              {PROBLEM[state]}
            </p>
          ) : null}
        </form>
        <a href="/news/zh-TW/forgot-password" className="text-sm text-accent underline">
          忘記密碼？
        </a>
      </div>
    </main>
  );
}
