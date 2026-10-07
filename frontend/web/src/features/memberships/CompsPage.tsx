"use client";

// VIP given by an admin, for internal testing (D-228, P2-B): who has it, until when, why, and
// ending one. A comp is not a sale — no order, payment or revenue — and ending one only takes
// away what the comp gave; the server works out what is left. Nothing here decides access.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { compsQuery, grantComp, revokeComp, type Comp, type CompSort } from "@/api/queries";
import { Button } from "@/features/admin-ui/Button";
import { DataTable, ListToolbar, Pager, sortControl, type Column, type FilterDef, type SortControl } from "@/features/admin-ui/DataTable";
import { ConfirmDialog } from "@/features/admin-ui/Dialog";
import { AdminPage, PageHeader } from "@/features/admin-ui/PageHeader";
import { StatusLozenge } from "@/features/admin-ui/StatusLozenge";
import { useCan } from "@/features/admin-ui/permissions";
import { useListState } from "@/features/admin-ui/useListState";
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

const COMP_SORTS: readonly CompSort[] = ["-created_at", "created_at", "-expires_at", "expires_at"];
const RUNNING: FilterDef<"running"> = { key: "running", label: "狀態", options: [{ value: "1", label: "有效中" }] };

function CompanyComps({ company }: { company: Company }) {
  const can = useCan();
  const list = useListState(["running"], COMP_SORTS);
  const page = useQuery(compsQuery(company.slug, list.filters.running === "1", { q: list.q, sort: list.sort, cursor: list.cursor }));
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["memberships", "comps", company.slug] });

  return (
    <AdminPage>
      <PageHeader
        title={`${company.name} 的 VIP 授予`}
        description="內部測試用（D-228）：不建立訂單、付款或營收，結帳仍關閉。"
      />

      {can("memberships:grant") ? <GrantForm companySlug={company.slug} onDone={refresh} /> : null}

      <h2 className="mt-8 mb-3 text-lg font-semibold">授予紀錄</h2>
      <ListToolbar list={list} filters={[RUNNING]} placeholder="搜尋 email 或理由…" views="comps" />
      <CompsTable
        comps={page.data?.items}
        onRevoked={refresh}
        sort={sortControl(list, COMP_SORTS, "-created_at")}
        error={page.error ? `無法載入：${page.error.message}` : null}
      />
      <Pager list={list} shown={page.data?.items.length ?? 0} total={page.data?.total ?? null} nextCursor={page.data?.next_cursor} />
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

const STATUS_TONE = { 有效中: "ok", 已撤銷: "danger", 已到期: "neutral" } as const;

function columns(onRevoked: () => unknown, mayRevoke: boolean): Column<Comp>[] {
  return [
    { key: "email", header: "讀者", className: "break-all", cell: (comp) => comp.email ?? "（讀者已不存在）" },
    {
      key: "status",
      header: "狀態",
      className: "whitespace-nowrap",
      cell: (comp) => <StatusLozenge tone={STATUS_TONE[compStatus(comp)]}>{compStatus(comp)}</StatusLozenge>,
    },
    {
      key: "period",
      header: "期間",
      sort: "expires_at",
      className: "whitespace-nowrap",
      cell: (comp) => (
        <>
          {when(comp.started_at)} – {when(comp.expires_at)}
          {comp.revoked_at ? <div className="text-xs text-muted">撤銷於 {when(comp.revoked_at)}</div> : null}
        </>
      ),
    },
    {
      key: "reason",
      header: "理由",
      cell: (comp) => (
        <>
          {comp.reason}
          {comp.revoke_reason ? <div className="text-xs text-muted">撤銷理由：{comp.revoke_reason}</div> : null}
        </>
      ),
    },
    {
      key: "actor",
      header: "授予者",
      sort: "created_at",
      className: "text-xs break-all text-muted",
      cell: (comp) => (
        <>
          {actorOf(comp.actor)}
          {comp.revoked_by ? <div>撤銷：{actorOf(comp.revoked_by)}</div> : null}
        </>
      ),
    },
    ...(mayRevoke ? [{ key: "revoke", header: "", align: "right" as const, cell: (comp: Comp) => <RevokeOne comp={comp} onRevoked={onRevoked} /> }] : []),
  ];
}

export function CompsTable({
  comps,
  onRevoked,
  sort,
  error = null,
}: {
  comps: Comp[] | undefined;
  onRevoked: () => unknown;
  sort?: SortControl;
  error?: string | null;
}) {
  const [revoking, setRevoking] = useState<Comp[] | null>(null);
  const can = useCan();
  return (
    <>
      <DataTable
        label="授予紀錄"
        rows={comps}
        columns={columns(onRevoked, can("memberships:grant"))}
        rowKey={(comp) => comp.id}
        rowTestId={(comp) => `comp-${comp.id}`}
        sort={sort}
        error={error}
        empty="沒有授予紀錄。"
        bulk={can("memberships:grant") ? [{ label: "撤銷選取的授予", tone: "danger", run: (rows) => setRevoking(rows.filter((c) => c.running)) }] : undefined}
      />
      {revoking ? <RevokeMany comps={revoking} onDone={onRevoked} onClose={() => setRevoking(null)} /> : null}
    </>
  );
}

/** The checked comps that are still running, ended with one reason, one after another. */
function RevokeMany({ comps, onDone, onClose }: { comps: Comp[]; onDone: () => unknown; onClose: () => void }) {
  const [failed, setFailed] = useState<string | null>(null);
  const revoke = useMutation({
    mutationFn: async (reason: string) => {
      const errors: string[] = [];
      for (const comp of comps) {
        try {
          await revokeComp(comp.id, reason);
        } catch (error) {
          errors.push(`${comp.email ?? comp.id}：${error instanceof Error ? error.message : String(error)}`);
        }
      }
      return errors;
    },
    onSuccess: async (errors) => {
      await onDone();
      if (errors.length) setFailed(errors.join("；"));
      else onClose();
    },
  });
  if (comps.length === 0) {
    return (
      <ConfirmDialog title="沒有可撤銷的授予" confirmLabel="知道了" tone="primary" onConfirm={onClose} onCancel={onClose}>
        選取的授予都已經撤銷或到期。
      </ConfirmDialog>
    );
  }
  return (
    <ConfirmDialog
      title={`撤銷 ${comps.length} 筆 VIP 授予？`}
      confirmLabel="確認撤銷"
      reason={{ placeholder: "撤銷理由（必填，套用到每一筆）", maxLength: REASON_MAX }}
      busy={revoke.isPending}
      error={failed ? `有些沒有撤銷：${failed}` : revoke.isError ? revoke.error.message : null}
      onConfirm={(reason) => revoke.mutate(reason)}
      onCancel={onClose}
    >
      {comps.map((c) => c.email ?? c.id).join("、")}。只結束授予給的 VIP；讀者自己付費的部分不受影響。
    </ConfirmDialog>
  );
}

function RevokeOne({ comp, onRevoked }: { comp: Comp; onRevoked: () => unknown }) {
  const [asking, setAsking] = useState(false);
  const revoke = useMutation({
    mutationFn: (reason: string) => revokeComp(comp.id, reason),
    onSuccess: async () => {
      setAsking(false);
      await onRevoked();
    },
  });
  if (!comp.running) return null;
  return (
    <>
      <Button size="sm" onClick={() => setAsking(true)}>
        撤銷
      </Button>
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
    </>
  );
}
