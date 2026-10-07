"use client";

// /admin/audit (AD-06): who did what in the back office, newest first — every change through its
// door, refused ones too, as the API wrote them down (admin_actions). One table (AD-05): this
// company's by default or every company's, done or refused, by what was changed.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { auditQuery, type AdminAction, type AuditSort } from "@/api/queries";
import { DataTable, ListToolbar, Pager, sortControl, type Column, type FilterDef } from "@/features/admin-ui/DataTable";
import { AdminPage, PageHeader } from "@/features/admin-ui/PageHeader";
import { StatusLozenge } from "@/features/admin-ui/StatusLozenge";
import { useListState } from "@/features/admin-ui/useListState";
import { CompanyScope, type Company } from "@/features/company/CompanyScope";

/** What each back-office change is called, by its route. */
export const ACTION_LABEL: Record<string, string> = {
  "/api/companies": "建立公司",
  "/api/companies/{company_id}/office-theme": "辦公室風格",
  "/api/companies/{company_id}/agents/{agent_id}/pause": "暫停代理",
  "/api/companies/{company_id}/agents/{agent_id}/resume": "恢復代理",
  "/api/companies/{company_id}/agents/{agent_id}/retire": "解雇代理",
  "/api/companies/{company_id}/agents": "雇用代理",
  "/api/approvals/{approval_id}/decide": "審批決定",
  "/api/companies/{company_id}/workflows/{workflow_run_id}/restart": "重跑工作流程",
  "/api/companies/{company_id}/workflows": "啟動工作流程",
  "/api/companies/{company_id}/finance/budgets": "設定預算",
  "/api/companies/{company_id}/finance/capital": "增資",
  "/api/companies/{company_id}/projects/{project_id}/pause": "暫停專案",
  "/api/companies/{company_id}/projects/{project_id}/resume": "恢復專案",
  "/api/admin/memberships/comps": "授予 VIP",
  "/api/admin/memberships/comps/{grant_id}/revoke": "撤銷 VIP",
  "/api/stories/{story_id}/start": "開始製作",
  "/api/articles/{article_id}/cover/swap": "換一張首圖",
  "/api/articles/{article_id}/cover/search": "重找首圖",
  "/api/articles/{article_id}/cover/ask": "請行銷換圖",
  "/api/articles/{article_id}/cover": "拿掉首圖",
  "/api/articles/{article_id}/access": "閱讀權限",
  "/api/articles/{article_id}/section": "文章分類",
  "/api/articles/{article_id}/unpublish": "下架",
  "/api/articles/{article_id}/republish": "重新上架",
  "/api/articles/{article_id}/revise": "修改文章",
  "/api/companies/{company_id}/sources": "新增來源",
  "/api/companies/{company_id}/team/messages": "團隊群組留言",
};

const TARGET_LABEL: Record<string, string> = {
  article: "文章",
  story: "題材",
  approval: "審批",
  agent: "代理",
  project: "專案",
  grant: "VIP 授予",
  workflow_run: "工作流程",
  company: "公司",
};

/** Where a target can be opened. */
function targetHref(type: string | null, id: string | null): string | null {
  if (!type || !id) return null;
  if (type === "article") return `/admin/newsroom/articles/${id}`;
  if (type === "story") return `/admin/newsroom/stories/${id}`;
  return null;
}

function when(iso: string): string {
  return new Date(iso).toLocaleString("zh-TW", { dateStyle: "medium", timeStyle: "medium" });
}

function outcome(status: number): [string, "ok" | "warn" | "danger"] {
  if (status < 400) return ["完成", "ok"];
  if (status < 500) return [`被拒 ${status}`, "warn"];
  return [`錯誤 ${status}`, "danger"];
}

export const COLUMNS: readonly Column<AdminAction>[] = [
  { key: "at", header: "時間", sort: "created_at", className: "whitespace-nowrap tabular-nums text-muted", cell: (a) => when(a.created_at) },
  { key: "who", header: "誰", className: "break-all", cell: (a) => a.actor_label },
  {
    key: "action",
    header: "動作",
    cell: (a) => (
      <span title={`${a.method} ${a.route}`}>
        {ACTION_LABEL[a.route] ?? a.action}
        {a.method === "DELETE" ? <span className="ml-1 text-xs text-muted">（刪除）</span> : null}
      </span>
    ),
  },
  {
    key: "target",
    header: "對象",
    className: "text-xs",
    cell: (a) => {
      if (!a.target_type) return <span className="text-muted">—</span>;
      const href = targetHref(a.target_type, a.target_id);
      const name = `${TARGET_LABEL[a.target_type] ?? a.target_type} ${a.target_id?.slice(0, 8) ?? ""}`;
      return href ? (
        <Link href={href} className="text-accent underline">
          {name}
        </Link>
      ) : (
        <span className="text-muted">{name}</span>
      );
    },
  },
  {
    key: "outcome",
    header: "結果",
    className: "whitespace-nowrap",
    cell: (a) => {
      const [text, tone] = outcome(a.status);
      return <StatusLozenge tone={tone}>{text}</StatusLozenge>;
    },
  },
  {
    key: "input",
    header: "送出的內容",
    className: "max-w-sm",
    cell: (a) =>
      Object.keys(a.input).length ? (
        <details>
          <summary className="cursor-pointer text-xs text-accent">展開</summary>
          <pre className="mt-1 max-h-60 overflow-auto rounded bg-canvas p-2 text-xs break-words whitespace-pre-wrap">
            {JSON.stringify(a.input, null, 2)}
          </pre>
        </details>
      ) : (
        <span className="text-xs text-muted">—</span>
      ),
  },
];

const SORTS: readonly AuditSort[] = ["-created_at", "created_at"];
type Filter = "scope" | "result" | "target";
const FILTERS: readonly FilterDef<Filter>[] = [
  { key: "scope", label: "範圍", anyLabel: "這間公司", options: [{ value: "all", label: "所有公司" }] },
  {
    key: "result",
    label: "結果",
    options: [
      { value: "done", label: "完成" },
      { value: "refused", label: "被拒或錯誤" },
    ],
  },
  { key: "target", label: "對象", options: Object.entries(TARGET_LABEL).map(([value, label]) => ({ value, label })) },
];

export function AuditPage() {
  return <CompanyScope>{(company) => <CompanyAudit company={company} />}</CompanyScope>;
}

function CompanyAudit({ company }: { company: Company }) {
  const list = useListState<AuditSort, Filter>(["scope", "result", "target"], SORTS);
  const result = list.filters.result;
  const page = useQuery(
    auditQuery(
      list.filters.scope === "all" ? null : company.id,
      { failed: result === "refused" ? true : result === "done" ? false : null, target_type: list.filters.target },
      { q: list.q, sort: list.sort, cursor: list.cursor },
    ),
  );
  return (
    <AdminPage>
      <PageHeader
        title={`${company.name} 的操作紀錄`}
        description="後台每一次修改都會記在這裡（包括被拒絕的），紀錄不能修改或刪除。只看不改的動作不記錄。"
      />
      <ListToolbar list={list} filters={FILTERS} placeholder="搜尋動作、對象 id 或操作者…" views="audit" />
      <DataTable
        label="操作紀錄"
        rows={page.data?.items}
        columns={COLUMNS}
        rowKey={(a) => a.id}
        sort={sortControl(list, SORTS, "-created_at")}
        error={page.error?.message}
        empty="還沒有任何操作紀錄。"
      />
      <Pager list={list} shown={page.data?.items.length ?? 0} total={page.data?.total ?? null} nextCursor={page.data?.next_cursor} />
    </AdminPage>
  );
}
