"use client";

// /admin/settings/access (AD-09): who may open the back office, and as what — an owner's page.
// The owners from ADMIN_EMAILS, the people an owner let in with their roles, and what each role
// may do. Every change here is in 操作紀錄 (AD-06).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { accessQuery, changeRole, letIn, takeOut, type AccessMember, type AdminRoleName } from "@/api/queries";
import { Button } from "@/features/admin-ui/Button";
import { DataTable, type Column } from "@/features/admin-ui/DataTable";
import { ConfirmDialog } from "@/features/admin-ui/Dialog";
import { AdminPage, PageHeader } from "@/features/admin-ui/PageHeader";
import { ErrorState, LoadingState } from "@/features/admin-ui/states";
import { useToast } from "@/features/admin-ui/Toast";
import { ADMIN_ME_KEY } from "@/features/auth/TokenGate";
import type { AdminMe } from "@/features/auth/adminAuth";

export const ROLE_LABEL: Record<AdminRoleName, string> = { owner: "擁有者", editor: "編輯", finance: "財務", viewer: "檢視" };
const ROLES = Object.keys(ROLE_LABEL) as AdminRoleName[];

/** What each permission key lets a person do, in words. */
export const PERMISSION_LABEL: Record<string, string> = {
  "newsroom:edit": "新聞室：開始製作、上下架、修改文章、閱讀權限、分類、首圖、來源、團隊群組留言",
  "approvals:decide": "審批：核准、退回修改、駁回",
  "projects:manage": "暫停、恢復專案",
  "workflows:run": "啟動、重跑工作流程",
  "agents:manage": "雇用、暫停、解雇代理",
  "company:manage": "建立公司、辦公室風格",
  "finance:edit": "預算、增資",
  "memberships:grant": "授予、撤銷 VIP",
  "coins:adjust": "調整鯨幣",
  "coins:view": "查看讀者的鯨幣明細",
  "audit:view": "查看操作紀錄",
  "access:manage": "管理角色與權限（本頁）",
  "system:settings": "系統設定：上班時段、加班上限、聯絡表單上限",
  "trading:view": "查看交易紀錄：決定、訂單、損益（D-248，交易頁上線後生效）",
  "trading:approve": "核准交易代理提出的交易（D-248，交易頁上線後生效）",
  "self:prefs": "自己的通知設定",
};

function when(iso: string): string {
  return new Date(iso).toLocaleString("zh-TW", { dateStyle: "medium", timeStyle: "short" });
}

export function AccessPage() {
  const access = useQuery(accessQuery());
  const me = useQueryClient().getQueryData<AdminMe | null>(ADMIN_ME_KEY);
  const [leaving, setLeaving] = useState<AccessMember | null>(null);
  const queryClient = useQueryClient();
  const toast = useToast();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["access"] });
  const change = useMutation({
    mutationFn: ({ member, role }: { member: AccessMember; role: AdminRoleName }) => changeRole(member.reader_id, role),
    onSuccess: async (member) => {
      toast(`${member.email} 現在是${ROLE_LABEL[member.role]}`);
      await refresh();
    },
    onError: (error) => toast(`沒有改：${error.message}`, "danger"),
  });
  const remove = useMutation({
    mutationFn: (member: AccessMember) => takeOut(member.reader_id),
    onSuccess: async (_, member) => {
      setLeaving(null);
      toast(`${member.email} 已不能再進後台`);
      await refresh();
    },
  });

  const columns: Column<AccessMember>[] = [
    { key: "email", header: "Email", className: "break-all", cell: (m) => m.email },
    {
      key: "role",
      header: "角色",
      cell: (m) =>
        me?.email === m.email ? (
          <span title="不能改自己的角色">{ROLE_LABEL[m.role]}</span>
        ) : (
          <select
            aria-label={`${m.email} 的角色`}
            value={m.role}
            disabled={change.isPending}
            onChange={(e) => change.mutate({ member: m, role: e.target.value as AdminRoleName })}
            className="rounded-md border border-line bg-canvas px-2 py-1 text-sm"
          >
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {ROLE_LABEL[role]}
              </option>
            ))}
          </select>
        ),
    },
    { key: "by", header: "授權者", className: "text-xs text-muted break-all", cell: (m) => String(m.granted_by.id ?? "—") },
    { key: "at", header: "更新", className: "whitespace-nowrap text-muted", cell: (m) => when(m.updated_at) },
    {
      key: "out",
      header: "",
      align: "right",
      cell: (m) =>
        me?.email === m.email ? null : (
          <Button size="sm" variant="subtle" onClick={() => setLeaving(m)}>
            移除
          </Button>
        ),
    },
  ];

  return (
    <AdminPage width="read">
      <PageHeader title="角色與權限" description="誰能進後台、能做什麼。擁有者可以加入其他人並指定角色；每一次變更都記在操作紀錄。" />
      {access.error ? <ErrorState>{access.error.message}</ErrorState> : null}
      {!access.data ? (
        <LoadingState />
      ) : (
        <div className="grid gap-8">
          <section aria-label="擁有者">
            <h2 className="mb-2 text-lg font-semibold">擁有者（ADMIN_EMAILS）</h2>
            <p className="mb-2 text-sm text-muted">由伺服器的環境變數設定，在這裡不能修改。操作者權杖也等同擁有者，只給機器使用。</p>
            <ul className="grid gap-1 text-sm">
              {access.data.owners.map((email) => (
                <li key={email} className="rounded-md border border-line bg-surface px-3 py-2">
                  {email}
                </li>
              ))}
            </ul>
          </section>

          <section aria-label="其他管理員">
            <h2 className="mb-2 text-lg font-semibold">其他管理員</h2>
            <LetInForm onDone={refresh} />
            <div className="mt-3">
              <DataTable label="管理員" rows={access.data.members} columns={columns} rowKey={(m) => m.reader_id} empty="還沒有加入任何人。" />
            </div>
          </section>

          <section aria-label="各角色的權限">
            <h2 className="mb-2 text-lg font-semibold">各角色能做什麼</h2>
            <p className="mb-2 text-sm text-muted">所有角色都能檢視後台；下表是「修改」需要的權限。</p>
            <div className="overflow-x-auto rounded-lg border border-line bg-surface">
              <table aria-label="角色權限表" className="w-full text-sm">
                <thead className="border-b border-line text-xs text-muted">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">權限</th>
                    {ROLES.map((role) => (
                      <th key={role} className="px-3 py-2 font-medium">
                        {ROLE_LABEL[role]}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {(access.data.roles.owner ?? []).map((key) => [key, PERMISSION_LABEL[key] ?? key] as const).map(([key, label]) => (
                    <tr key={key}>
                      <th scope="row" className="px-3 py-2 text-left font-normal">
                        {label}
                        <span className="ml-2 text-xs text-muted">{key}</span>
                      </th>
                      {ROLES.map((role) => {
                        const has = access.data.roles[role]?.includes(key);
                        return (
                          <td key={role} className="px-3 py-2 text-center" aria-label={has ? "可以" : "不可以"}>
                            {has ? <span className="text-ok">✓</span> : <span className="text-muted">—</span>}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
      {leaving ? (
        <ConfirmDialog
          title={`移除 ${leaving.email}？`}
          confirmLabel="移除"
          busy={remove.isPending}
          error={remove.isError ? remove.error.message : null}
          onConfirm={() => remove.mutate(leaving)}
          onCancel={() => setLeaving(null)}
        >
          他之後不能再進後台；他的帳號和過去的操作紀錄都會保留。
        </ConfirmDialog>
      ) : null}
    </AdminPage>
  );
}

function LetInForm({ onDone }: { onDone: () => unknown }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<AdminRoleName>("viewer");
  const add = useMutation({
    mutationFn: () => letIn(email.trim(), role),
    onSuccess: async () => {
      setEmail("");
      await onDone();
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    add.mutate();
  };
  return (
    <form aria-label="加入管理員" onSubmit={submit} className="flex flex-wrap items-end gap-2 rounded-lg border border-line bg-surface p-3">
      <label className="grid flex-1 gap-1 text-sm">
        <span className="text-xs text-muted">讀者 Email（須已在網站註冊，驗證 email 後才能登入後台）</span>
        <input required type="email" maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} className="rounded-md border border-line bg-canvas px-2 py-1" />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="text-xs text-muted">角色</span>
        <select value={role} onChange={(e) => setRole(e.target.value as AdminRoleName)} className="rounded-md border border-line bg-canvas px-2 py-1">
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </select>
      </label>
      <Button type="submit" variant="primary" disabled={add.isPending || !email.trim()}>
        加入
      </Button>
      {add.isError ? (
        <p role="alert" className="w-full text-sm text-danger">
          沒有加入：{add.error.message}
        </p>
      ) : null}
    </form>
  );
}
