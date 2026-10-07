"use client";

// VIP given by an admin, for internal testing (D-228, P2-B): who has it, until when, why, and
// ending one. A comp is not a sale — no order, payment or revenue — and ending one only takes
// away what the comp gave; the server works out what is left. Nothing here decides access.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { compsQuery, grantComp, revokeComp, type Comp } from "@/api/queries";
import { Button } from "@/features/admin-ui/Button";
import { ConfirmDialog } from "@/features/admin-ui/Dialog";
import { AdminPage, PageHeader } from "@/features/admin-ui/PageHeader";
import { StatusLozenge } from "@/features/admin-ui/StatusLozenge";
import { EmptyState, ErrorState, LoadingState } from "@/features/admin-ui/states";
import { CompanyScope, type Company } from "@/features/company/CompanyScope";

const DAY = 24 * 60 * 60 * 1000;
const REASON_MAX = 500;

/** A ``datetime-local`` value, in the browser's own time zone, ``days`` from now. */
export function localInput(days: number, now: Date = new Date()): string {
  const at = new Date(now.getTime() + days * DAY);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}T${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

/** What a comp is doing now, in the words the page shows. */
export function compStatus(comp: Comp): "有效中" | "已撤銷" | "已到期" {
  if (comp.running) return "有效中";
  return comp.revoked_at ? "已撤銷" : "已到期";
}

function when(iso: string): string {
  return new Date(iso).toLocaleString("zh-TW", { dateStyle: "medium", timeStyle: "short" });
}

function actorOf(actor: Record<string, unknown> | null): string {
  return actor && typeof actor.id === "string" ? actor.id : "—";
}

/** /admin/memberships: VIP given for testing, and giving or ending one. */
export function CompsPage() {
  return <CompanyScope>{(company) => <CompanyComps company={company} />}</CompanyScope>;
}

function CompanyComps({ company }: { company: Company }) {
  const [running, setRunning] = useState(false);
  const comps = useQuery(compsQuery(company.slug, running));
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["memberships", "comps", company.slug] });

  return (
    <AdminPage>
      <PageHeader
        title={`${company.name} 的 VIP 授予`}
        description="內部測試用（D-228）：不建立訂單、付款或營收，結帳仍關閉。"
      />

      <GrantForm companySlug={company.slug} onDone={refresh} />

      <div className="mt-8 mb-3 flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold">授予紀錄</h2>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={running} onChange={(e) => setRunning(e.target.checked)} />
          只看有效中
        </label>
      </div>
      {comps.error ? <ErrorState>無法載入：{comps.error.message}</ErrorState> : null}
      <CompsTable comps={comps.data} onRevoked={refresh} />
    </AdminPage>
  );
}

function GrantForm({ companySlug, onDone }: { companySlug: string; onDone: () => unknown }) {
  const [email, setEmail] = useState("");
  const [until, setUntil] = useState(() => localInput(30));
  const [reason, setReason] = useState("");
  const grant = useMutation({
    mutationFn: () =>
      grantComp({ email: email.trim(), until: new Date(until).toISOString(), reason: reason.trim(), company: companySlug }),
    onSuccess: async () => {
      setEmail("");
      setReason("");
      await onDone();
    },
  });
  return (
    <form
      aria-label="授予 VIP"
      className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-surface p-4"
      onSubmit={(e) => {
        e.preventDefault();
        grant.mutate();
      }}
    >
      <label className="grid flex-1 gap-1">
        <span className="text-xs text-muted">讀者 Email（須已註冊）</span>
        <input
          required
          type="email"
          maxLength={254}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded border border-line bg-canvas px-2 py-1"
        />
      </label>
      <label className="grid gap-1">
        <span className="text-xs text-muted">到期時間</span>
        <input
          required
          type="datetime-local"
          min={localInput(0)}
          value={until}
          onChange={(e) => setUntil(e.target.value)}
          className="rounded border border-line bg-canvas px-2 py-1"
        />
      </label>
      <label className="grid w-full gap-1">
        <span className="text-xs text-muted">理由（必填）</span>
        <input
          required
          maxLength={REASON_MAX}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="例：內測鯨幣流程"
          className="rounded border border-line bg-canvas px-2 py-1"
        />
      </label>
      <Button type="submit" variant="primary" disabled={grant.isPending || !email.trim() || !reason.trim()}>
        授予 VIP
      </Button>
      {grant.isError ? (
        <p role="alert" className="w-full text-sm text-danger">
          沒有授予：{grant.error.message}
        </p>
      ) : null}
      {grant.isSuccess ? (
        <p role="status" className="w-full text-sm text-muted">
          已授予 {grant.data.email}，到 {when(grant.data.expires_at)}。
        </p>
      ) : null}
    </form>
  );
}

export function CompsTable({ comps, onRevoked }: { comps: Comp[] | undefined; onRevoked: () => unknown }) {
  if (comps === undefined) return <LoadingState />;
  if (comps.length === 0) return <EmptyState>沒有授予紀錄。</EmptyState>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-muted">
          <tr>
            <th className="py-2 pr-3">讀者</th>
            <th className="py-2 pr-3">狀態</th>
            <th className="py-2 pr-3">期間</th>
            <th className="py-2 pr-3">理由</th>
            <th className="py-2 pr-3">授予者</th>
            <th className="py-2" />
          </tr>
        </thead>
        <tbody>
          {comps.map((comp) => (
            <CompRow key={comp.id} comp={comp} onRevoked={onRevoked} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

const STATUS_TONE = { 有效中: "ok", 已撤銷: "danger", 已到期: "neutral" } as const;

function CompRow({ comp, onRevoked }: { comp: Comp; onRevoked: () => unknown }) {
  const [asking, setAsking] = useState(false);
  const revoke = useMutation({
    mutationFn: (reason: string) => revokeComp(comp.id, reason),
    onSuccess: async () => {
      setAsking(false);
      await onRevoked();
    },
  });
  const status = compStatus(comp);
  return (
    <tr className="border-t border-line align-top" data-testid={`comp-${comp.id}`}>
      <td className="py-2 pr-3 break-all">{comp.email ?? "（讀者已不存在）"}</td>
      <td className="py-2 pr-3 whitespace-nowrap">
        <StatusLozenge tone={STATUS_TONE[status]}>{status}</StatusLozenge>
      </td>
      <td className="py-2 pr-3 whitespace-nowrap">
        {when(comp.started_at)} – {when(comp.expires_at)}
        {comp.revoked_at ? <div className="text-xs text-muted">撤銷於 {when(comp.revoked_at)}</div> : null}
      </td>
      <td className="py-2 pr-3">
        {comp.reason}
        {comp.revoke_reason ? <div className="text-xs text-muted">撤銷理由：{comp.revoke_reason}</div> : null}
      </td>
      <td className="py-2 pr-3 text-xs break-all text-muted">
        {actorOf(comp.actor)}
        {comp.revoked_by ? <div>撤銷：{actorOf(comp.revoked_by)}</div> : null}
      </td>
      <td className="py-2 text-right">
        {comp.running ? (
          <Button size="sm" onClick={() => setAsking(true)}>
            撤銷
          </Button>
        ) : null}
        {asking ? (
          <ConfirmDialog
            title={`撤銷 ${comp.email ?? "這位讀者"} 的 VIP？`}
            confirmLabel="確認撤銷"
            reason={{ placeholder: "撤銷理由（必填）", maxLength: REASON_MAX }}
            busy={revoke.isPending}
            error={revoke.isError ? `沒有撤銷：${revoke.error.message}` : null}
            onConfirm={(reason) => revoke.mutate(reason)}
            onCancel={() => setAsking(false)}
          >
            只結束這筆授予給的 VIP；讀者自己付費的部分不受影響。
          </ConfirmDialog>
        ) : null}
      </td>
    </tr>
  );
}
