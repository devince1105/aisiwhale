"use client";

// Whale Coins in the back office (P3-C-2, D-235): is the ledger whole, what does a reader hold,
// and an adjustment up or down with a reason. Opening the page checks the ledger — a read, never
// a write; the only thing that writes is the adjustment, after a confirmation that says what
// will change. A movement is never edited: a mistake is put right by another adjustment.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  adjustCoins,
  coinReconcileQuery,
  coinWalletQuery,
  type AdminCoinMovement,
  type AdminCoinWallet,
} from "@/api/queries";
import { Button } from "@/features/admin-ui/Button";
import { DataTable, type Column } from "@/features/admin-ui/DataTable";
import { ConfirmDialog } from "@/features/admin-ui/Dialog";
import { AdminPage, PageHeader } from "@/features/admin-ui/PageHeader";
import { StatusLozenge } from "@/features/admin-ui/StatusLozenge";
import { CompanyScope, type Company } from "@/features/company/CompanyScope";

export const MAX_ADJUSTMENT = 10_000;
const REASON_MAX = 500;

const KINDS: Record<string, string> = {
  MONTHLY_GRANT: "每月發放",
  PROMOTION_GRANT: "活動發放",
  ADMIN_ADJUSTMENT: "平台調整",
  SPEND: "使用",
  REFUND: "退回",
};
const TIERS: Record<string, string> = { free: "一般會員", vip: "VIP" };

function when(iso: string): string {
  return new Date(iso).toLocaleString("zh-TW", { dateStyle: "medium", timeStyle: "short" });
}

/** What an adjustment of ``amount`` would do to ``wallet``: the balance after, and whether it
 * goes past the tier's cap (only up can) or below zero (only down can). */
export function preview(wallet: Pick<AdminCoinWallet, "balance" | "cap">, amount: number) {
  const after = wallet.balance + amount;
  return { after, pastCap: amount > 0 && after > wallet.cap, belowZero: after < 0 };
}

/** /admin/coins */
export function CoinsAdminPage() {
  return <CompanyScope>{(company) => <CompanyCoins company={company} />}</CompanyScope>;
}

export function CompanyCoins({ company }: { company: Company }) {
  const [typed, setTyped] = useState("");
  const [email, setEmail] = useState("");
  return (
    <AdminPage>
      <PageHeader title="鯨幣" description="讀者的鯨幣餘額與明細，以及平台調整。帳務只增不改；更正要再做一筆反向調整。" />
      <Reconcile />
      <form
        aria-label="查詢讀者"
        className="mt-6 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          setEmail(typed.trim().toLowerCase());
        }}
      >
        <label className="grid flex-1 gap-1">
          <span className="text-xs text-muted">讀者 Email</span>
          <input
            type="email"
            required
            maxLength={254}
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            className="rounded border border-line bg-canvas px-2 py-1"
          />
        </label>
        <Button type="submit" disabled={!typed.trim()}>
          查詢
        </Button>
      </form>
      {email ? <Wallet key={email} company={company} email={email} /> : null}
    </AdminPage>
  );
}

/** The ledger checked against itself, each time the page opens. */
function Reconcile() {
  const check = useQuery(coinReconcileQuery());
  return (
    <section aria-label="對帳" data-testid="coins-reconcile" className="rounded-lg border border-line bg-surface p-4 text-sm">
      {check.isPending ? (
        <p className="text-muted">對帳中…</p>
      ) : check.error ? (
        <p role="alert" className="text-danger">
          無法對帳：{check.error.message}
        </p>
      ) : check.data.ok ? (
        <p>
          <StatusLozenge tone="ok">帳務一致</StatusLozenge>
          <span className="ml-2 text-muted">讀者共持有 {(check.data.totals.held_by_readers ?? 0).toLocaleString("zh-TW")} 幣</span>
        </p>
      ) : (
        <div role="alert">
          <StatusLozenge tone="danger">帳務不一致</StatusLozenge>
          <ul className="mt-2 list-disc pl-5 text-danger">
            {check.data.problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function Wallet({ company, email }: { company: Company; email: string }) {
  const [cursors, setCursors] = useState<string[]>([]);
  const cursor = cursors.at(-1) ?? null;
  const wallet = useQuery(coinWalletQuery(company.slug, email, cursor));
  if (wallet.isPending) return <p className="mt-6 text-muted">載入中…</p>;
  if (wallet.error) {
    return (
      <p role="alert" className="mt-6 text-danger">
        {wallet.error.message.startsWith("404") ? `找不到讀者 ${email}。` : `無法載入：${wallet.error.message}`}
      </p>
    );
  }
  const w = wallet.data;
  return (
    <>
      <section data-testid="coins-wallet" className="mt-6 flex flex-wrap items-baseline gap-x-8 gap-y-2 rounded-lg border border-line bg-surface p-4">
        <span className="break-all">{w.email}</span>
        <span>
          <StatusLozenge tone={w.tier === "vip" ? "ok" : "neutral"}>{TIERS[w.tier]}</StatusLozenge>
          <span className="ml-2 text-sm text-muted">上限 {w.cap.toLocaleString("zh-TW")}</span>
        </span>
        <span className="text-2xl font-bold tabular-nums">{w.balance.toLocaleString("zh-TW")} 幣</span>
      </section>
      <AdjustForm company={company} wallet={w} />
      <h2 className="mt-8 mb-3 text-lg font-semibold">明細</h2>
      <DataTable
        label="鯨幣明細"
        rows={w.history.items}
        columns={COLUMNS}
        rowKey={(m) => m.id}
        rowTestId={(m) => `coin-${m.id}`}
        empty="沒有任何鯨幣紀錄。"
      />
      <div className="mt-3 flex items-center gap-3 text-sm">
        <span className="text-muted">共 {w.history.total} 筆</span>
        {cursors.length ? (
          <Button size="sm" onClick={() => setCursors([])}>
            第一頁
          </Button>
        ) : null}
        {w.history.next_cursor ? (
          <Button size="sm" onClick={() => setCursors([...cursors, w.history.next_cursor as string])}>
            下一頁
          </Button>
        ) : null}
      </div>
    </>
  );
}

const COLUMNS: Column<AdminCoinMovement>[] = [
  { key: "when", header: "時間", className: "whitespace-nowrap", cell: (m) => when(m.occurred_at) },
  { key: "kind", header: "種類", cell: (m) => KINDS[m.kind] ?? m.kind },
  {
    key: "amount",
    header: "數量",
    align: "right",
    className: "tabular-nums",
    cell: (m) => (m.amount > 0 ? `+${m.amount}` : String(m.amount)),
  },
  { key: "after", header: "餘額", align: "right", className: "tabular-nums", cell: (m) => m.balance_after },
  {
    key: "cap",
    header: "上限",
    className: "text-xs text-muted",
    cell: (m) => (m.meta.override_cap ? <StatusLozenge tone="danger">override</StatusLozenge> : (m.cap ?? "—")),
  },
  {
    key: "who",
    header: "執行者與理由",
    className: "text-xs break-all text-muted",
    cell: (m) => (
      <>
        {typeof m.actor.id === "string" ? m.actor.id : "—"}
        {m.reason ? <div>{m.reason}</div> : null}
      </>
    ),
  },
];

function AdjustForm({ company, wallet }: { company: Company; wallet: AdminCoinWallet }) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [override, setOverride] = useState(false);
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const [asking, setAsking] = useState(false);
  const queryClient = useQueryClient();
  const n = Number(amount);
  const valid = Number.isInteger(n) && n !== 0 && Math.abs(n) <= MAX_ADJUSTMENT && reason.trim() !== "";
  const shown = valid ? preview(wallet, n) : null;
  const adjust = useMutation({
    mutationFn: () =>
      adjustCoins({
        email: wallet.email,
        amount: n,
        reason: reason.trim(),
        override_cap: override,
        request_id: requestId,
        company: company.slug,
      }),
    onSuccess: async () => {
      setAsking(false);
      setAmount("");
      setReason("");
      setOverride(false);
      setRequestId(crypto.randomUUID()); // a new adjustment is a new request
      await queryClient.invalidateQueries({ queryKey: ["coins"] });
    },
  });
  // The confirmation is a <dialog> with a <form> of its own: kept outside this form, never inside
  // it — a form within a form is not HTML, and a browser submits the inner one natively (a
  // reload, no adjustment) instead of letting React handle it.
  return (
    <>
      <form
        aria-label="調整鯨幣"
        className="mt-4 flex flex-wrap items-end gap-3 rounded-lg border border-line bg-surface p-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (valid) setAsking(true);
        }}
      >
        <label className="grid gap-1">
          <span className="text-xs text-muted">數量（正數加、負數扣）</span>
          <input
            type="number"
            required
            step={1}
            min={-MAX_ADJUSTMENT}
            max={MAX_ADJUSTMENT}
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            className="w-32 rounded border border-line bg-canvas px-2 py-1"
          />
        </label>
        <label className="grid flex-1 gap-1">
          <span className="text-xs text-muted">理由（必填，讀者看不到）</span>
          <input
            required
            maxLength={REASON_MAX}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className="rounded border border-line bg-canvas px-2 py-1"
          />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={override} onChange={(event) => setOverride(event.target.checked)} />
          超過上限（override）
        </label>
        <Button type="submit" variant="primary" disabled={!valid || adjust.isPending}>
          調整
        </Button>
        {shown?.pastCap && !override ? (
          <p role="status" className="w-full text-sm text-danger">
            會超過{TIERS[wallet.tier]}上限 {wallet.cap.toLocaleString("zh-TW")}；要超過請勾選 override。
          </p>
        ) : null}
        {adjust.isError && !asking ? (
          <p role="alert" className="w-full text-sm text-danger">
            沒有調整：{adjust.error.message}
          </p>
        ) : null}
      </form>
        {asking && shown ? (
          <ConfirmDialog
            title={n > 0 ? `加 ${n} 幣？` : `扣 ${-n} 幣？`}
            confirmLabel="確認調整"
            tone={shown.pastCap ? "danger" : "primary"}
            busy={adjust.isPending}
            error={adjust.isError ? adjust.error.message : null}
            onConfirm={() => adjust.mutate()}
            onCancel={() => setAsking(false)}
          >
            <p>
              {wallet.email}：目前 {wallet.balance.toLocaleString("zh-TW")} → 調整後 {shown.after.toLocaleString("zh-TW")}
            </p>
            {shown.pastCap && override ? (
              <p className="mt-2 font-semibold text-danger" data-testid="override-warning">
                這會超過{TIERS[wallet.tier]}上限 {wallet.cap.toLocaleString("zh-TW")}，確定要 override 嗎？
              </p>
            ) : null}
            <p className="mt-2">理由：{reason.trim()}</p>
          </ConfirmDialog>
        ) : null}
    </>
  );
}
