"use client";

// /admin/approvals/report (AD-12, the ERP's approval report): how the approvals have gone over
// 7, 30 or 90 days — how many were decided and how, how long a decision took (median, P90), how
// many ran out and were asked again; the same by kind and by who decided; and what is waiting
// too long right now. The window is the address's, so a link shows the same report.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type { ReactNode } from "react";

import { approvalReportQuery, type ApprovalReport } from "@/api/queries";
import { AdminPage, PageHeader } from "@/features/admin-ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/features/admin-ui/states";
import { useListState } from "@/features/admin-ui/useListState";
import { CompanyScope, withCompany, type Company } from "@/features/company/CompanyScope";

import { kindLabel } from "./model";

export const WINDOWS = [7, 30, 90] as const;
const DEFAULT_DAYS = 30;

type Outcomes = ApprovalReport["total"];

export function ApprovalReportPage() {
  return <CompanyScope>{(company) => <CompanyReport company={company} />}</CompanyScope>;
}

function CompanyReport({ company }: { company: Company }) {
  const list = useListState(["days"]);
  const days = WINDOWS.find((d) => String(d) === list.filters.days) ?? DEFAULT_DAYS;
  const report = useQuery(approvalReportQuery(company.id, days));
  return (
    <AdminPage width="read">
      <PageHeader
        title={`${company.name} 的審批報表`}
        description="決定了多少、怎麼決定、花多久；逾時重新送審的次數；以及現在等太久的。比率以已決定的件數為分母。"
        actions={<WindowSwitch days={days} onDays={(d) => list.set({ filters: { days: d === DEFAULT_DAYS ? null : String(d) } })} />}
      />
      {report.error ? <ErrorState>{report.error.message}</ErrorState> : null}
      {report.data ? <ApprovalReportView report={report.data} inbox={withCompany("/admin/approvals", company.id)} /> : report.error ? null : <LoadingState />}
    </AdminPage>
  );
}

function WindowSwitch({ days, onDays }: { days: number; onDays: (days: number) => void }) {
  return (
    <div role="group" aria-label="期間" className="inline-flex overflow-hidden rounded-md border border-line">
      {WINDOWS.map((d) => (
        <button
          key={d}
          type="button"
          aria-pressed={d === days}
          onClick={() => onDays(d)}
          className={`px-3 py-1 text-sm ${d === days ? "bg-accent text-accent-ink" : "bg-surface text-ink hover:bg-canvas"}`}
        >
          近 {d} 天
        </button>
      ))}
    </div>
  );
}

function hours(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value < 1 ? `${Math.round(value * 60)} 分鐘` : `${value.toFixed(1)} 小時`;
}

function rate(part: number, whole: number): string {
  return whole ? `${Math.round((part / whole) * 100)}%` : "—";
}

function Tile({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {note ? <div className="mt-0.5 text-xs text-muted">{note}</div> : null}
    </div>
  );
}

/** The share approved, as a thin bar beside its number: one series, one hue. */
function RateBar({ part, whole }: { part: number; whole: number }) {
  const share = whole ? part / whole : 0;
  return (
    <span className="flex items-center gap-2">
      <span aria-hidden="true" className="h-1.5 w-16 overflow-hidden rounded-full bg-neutral/20">
        <span className="block h-full rounded-full bg-accent" style={{ width: `${share * 100}%` }} />
      </span>
      <span className="tabular-nums">{rate(part, whole)}</span>
    </span>
  );
}

const TH = "px-3 py-2 text-left text-xs font-semibold whitespace-nowrap text-muted";
const TD = "px-3 py-2 whitespace-nowrap tabular-nums";

export function ApprovalReportView({ report, inbox }: { report: ApprovalReport; inbox: string }) {
  const t = report.total;
  return (
    <div className="flex flex-col gap-6">
      <section aria-label="總覽" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Tile label="已決定" value={t.decided} note={`近 ${report.days} 天`} />
        <Tile label="核准率" value={rate(t.approved, t.decided)} note={`退回 ${rate(t.returned, t.decided)}・駁回 ${rate(t.rejected, t.decided)}`} />
        <Tile label="決定所需時間（中位數）" value={hours(t.median_hours)} note={`P90 ${hours(t.p90_hours)}`} />
        <Tile label="逾時重新送審" value={t.expired} note="無人決定、自動重送的次數" />
      </section>

      <section aria-label="等待中">
        <h2 className="mb-2 text-base font-semibold">
          等待中 {report.pending} 件，超過 {report.stuck_hours} 小時 {report.stuck_total} 件
        </h2>
        {report.stuck.length === 0 ? (
          <EmptyState>沒有等超過 {report.stuck_hours} 小時的審批。</EmptyState>
        ) : (
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
            {report.stuck.map((s) => (
              <li key={s.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2 text-sm">
                <span className="text-xs text-muted">{kindLabel(s.kind)}</span>
                <span className="min-w-0 flex-1">{s.summary}</span>
                <span className="text-warn tabular-nums">已等 {hours(s.waited_hours)}</span>
              </li>
            ))}
          </ul>
        )}
        {report.stuck_total > report.stuck.length ? (
          <p className="mt-1 text-xs text-muted">只列等最久的 {report.stuck.length} 件。</p>
        ) : null}
        <Link href={inbox} className="mt-2 inline-block text-sm text-accent hover:underline">
          到審批收件匣處理
        </Link>
      </section>

      <section aria-label="依種類">
        <h2 className="mb-2 text-base font-semibold">依種類</h2>
        {report.kinds.length === 0 ? (
          <EmptyState>近 {report.days} 天沒有決定或逾時的審批。</EmptyState>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full text-sm">
              <thead className="border-b border-line">
                <tr>
                  <th className={TH}>種類</th>
                  <th className={TH}>已決定</th>
                  <th className={TH}>核准率</th>
                  <th className={TH}>退回</th>
                  <th className={TH}>駁回</th>
                  <th className={TH}>逾時</th>
                  <th className={TH}>中位數</th>
                  <th className={TH}>P90</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {report.kinds.map((k) => (
                  <KindRow key={k.kind} label={kindLabel(k.kind)} outcomes={k} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section aria-label="依決定者">
        <h2 className="mb-2 text-base font-semibold">依決定者</h2>
        {report.deciders.length === 0 ? (
          <EmptyState>近 {report.days} 天沒有人做過決定。</EmptyState>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full text-sm">
              <thead className="border-b border-line">
                <tr>
                  <th className={TH}>決定者</th>
                  <th className={TH}>已決定</th>
                  <th className={TH}>核准率</th>
                  <th className={TH}>退回</th>
                  <th className={TH}>駁回</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {report.deciders.map((d) => (
                  <tr key={d.label}>
                    <td className="px-3 py-2 whitespace-nowrap">{d.label}</td>
                    <td className={TD}>{d.decided}</td>
                    <td className={TD}>
                      <RateBar part={d.approved} whole={d.decided} />
                    </td>
                    <td className={TD}>{d.returned}</td>
                    <td className={TD}>{d.rejected}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function KindRow({ label, outcomes: o }: { label: string; outcomes: Outcomes }) {
  return (
    <tr>
      <td className="px-3 py-2 whitespace-nowrap">{label}</td>
      <td className={TD}>{o.decided}</td>
      <td className={TD}>
        <RateBar part={o.approved} whole={o.decided} />
      </td>
      <td className={TD}>{o.returned}</td>
      <td className={TD}>{o.rejected}</td>
      <td className={TD}>{o.expired}</td>
      <td className={TD}>{hours(o.median_hours)}</td>
      <td className={TD}>{hours(o.p90_hours)}</td>
    </tr>
  );
}
