"use client";

// The top bar's bell (AD-10): how many approvals wait in this company — refreshed by the same
// APPROVAL_* events that refresh the inbox, so a new one shows within a moment — and, opened, the
// oldest of them with those about to run out marked, the way to the inbox, and one's own switch
// for the daily email of what waits.
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { approvalsQuery, itemsOf, pendingCountQuery, prefsQuery, savePrefs } from "@/api/queries";
import { withCompany } from "@/features/company/CompanyScope";

import { Icon } from "./icons";
import { StatusLozenge } from "./StatusLozenge";

const SHOWN = 8;
const SOON_MS = 2 * 60 * 60 * 1000;

function waited(iso: string, now: number): string {
  const minutes = Math.max(1, Math.round((now - Date.parse(iso)) / 60_000));
  if (minutes < 60) return `${minutes} 分鐘`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `${hours} 小時` : `${Math.round(hours / 24)} 天`;
}

export function NotificationBell({ companyId, personal }: { companyId: string | null; personal: boolean }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const count = useQuery({ ...pendingCountQuery(companyId ?? ""), enabled: Boolean(companyId) });
  const list = useInfiniteQuery({ ...approvalsQuery(companyId ?? ""), enabled: open && Boolean(companyId) });
  const prefs = useQuery({ ...prefsQuery(), enabled: open && personal });
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: (approvals_digest: boolean) => savePrefs({ approvals_digest }),
    onSuccess: (saved) => queryClient.setQueryData(prefsQuery().queryKey, saved),
  });

  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  const waiting = count.data ?? 0;
  const items = (itemsOf(list.data) ?? []).slice(0, SHOWN);
  const now = Date.now();
  return (
    <div ref={box} className="relative">
      <button
        type="button"
        aria-label={waiting ? `通知：${waiting} 件等待審批` : "通知"}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="relative rounded-md p-1.5 text-muted hover:bg-canvas hover:text-ink"
      >
        <Icon name="bell" />
        {waiting ? (
          <span data-testid="bell-count" className="absolute -top-0.5 -right-0.5 min-w-4 rounded-full bg-warn px-1 text-center text-[10px] leading-4 font-semibold text-canvas tabular-nums">
            {waiting > 99 ? "99+" : waiting}
          </span>
        ) : null}
      </button>
      {open ? (
        <div role="dialog" aria-label="通知" className="absolute right-0 z-30 mt-2 w-[min(22rem,calc(100vw-2rem))] rounded-lg border border-line bg-surface shadow-xl">
          <p className="border-b border-line px-3 py-2 text-sm font-semibold">{waiting ? `${waiting} 件等待審批` : "沒有等待審批的項目"}</p>
          {items.length ? (
            <ul className="max-h-80 divide-y divide-line overflow-y-auto">
              {items.map((approval) => {
                const left = approval.expires_at ? Date.parse(approval.expires_at) - now : null;
                return (
                  <li key={approval.id} className="px-3 py-2 text-sm">
                    <p className="line-clamp-2 break-words">{approval.summary}</p>
                    <p className="mt-0.5 flex items-center gap-2 text-xs text-muted">
                      已等 {waited(approval.created_at, now)}
                      {left !== null && left <= SOON_MS ? <StatusLozenge tone="warn">{left <= 0 ? "已到期" : "快到期"}</StatusLozenge> : null}
                    </p>
                  </li>
                );
              })}
            </ul>
          ) : null}
          <div className="flex items-center justify-between gap-2 border-t border-line px-3 py-2 text-sm">
            {companyId ? (
              <Link href={withCompany("/admin/approvals", companyId)} onClick={() => setOpen(false)} className="text-accent underline">
                前往審批收件匣
              </Link>
            ) : (
              <span />
            )}
            {personal ? (
              <label className="flex items-center gap-1.5 text-xs text-muted">
                <input
                  type="checkbox"
                  checked={prefs.data?.approvals_digest ?? true}
                  disabled={!prefs.data || save.isPending}
                  onChange={(event) => save.mutate(event.target.checked)}
                />
                每日 email 摘要
              </label>
            ) : null}
          </div>
          {save.isError ? (
            <p role="alert" className="px-3 pb-2 text-xs text-danger">
              沒有存：{save.error.message}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
