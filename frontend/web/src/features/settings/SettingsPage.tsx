"use client";

// /admin/settings (AD-11): what the back office tunes while everything runs — the AI staff's
// shifts, their overtime limits, the contact form's daily cap. Each shows whether it is the
// environment's or set here, saves after a check, goes back to the environment's on reset, and
// keeps its last changes (before → after, by whom). An owner's page.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { resetSetting, saveSetting, settingsQuery, type SettingView } from "@/api/queries";
import { Button } from "@/features/admin-ui/Button";
import { ConfirmDialog } from "@/features/admin-ui/Dialog";
import { AdminPage, PageHeader } from "@/features/admin-ui/PageHeader";
import { StatusLozenge } from "@/features/admin-ui/StatusLozenge";
import { ErrorState, LoadingState } from "@/features/admin-ui/states";
import { useToast } from "@/features/admin-ui/Toast";

function shown(value: unknown): string {
  if (value === null || value === undefined) return "（環境預設）";
  if (value === "") return "（空白：全天上班）";
  return String(value);
}

function when(iso: string): string {
  return new Date(iso).toLocaleString("zh-TW", { dateStyle: "medium", timeStyle: "short" });
}

export function SettingsPage() {
  const settings = useQuery(settingsQuery());
  return (
    <AdminPage width="read">
      <PageHeader
        title="系統設定"
        description="在這裡改的值不必重新部署：網站與 API 立刻生效，AI 員工在下一次上班巡檢或臨時上班時生效。密鑰與連線設定仍在環境變數。"
      />
      {settings.error ? <ErrorState>{settings.error.message}</ErrorState> : null}
      {!settings.data ? <LoadingState /> : <div className="grid gap-4">{settings.data.map((s) => <SettingCard key={s.key} setting={s} />)}</div>}
    </AdminPage>
  );
}

function SettingCard({ setting }: { setting: SettingView }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [draft, setDraft] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const text = draft ?? String(setting.value ?? "");
  const done = (views: SettingView[]) => {
    queryClient.setQueryData(settingsQuery().queryKey, views);
    setDraft(null);
  };
  const save = useMutation({
    mutationFn: () => saveSetting(setting.key, setting.kind === "shifts" ? text : Number(text)),
    onSuccess: (views) => {
      done(views);
      toast(`已儲存：${setting.label}`);
    },
  });
  const reset = useMutation({
    mutationFn: () => resetSetting(setting.key),
    onSuccess: (views) => {
      done(views);
      setResetting(false);
      toast(`已改回環境預設：${setting.label}`);
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  const changed = draft !== null && draft !== String(setting.value ?? "");
  return (
    <section aria-label={setting.label} className="rounded-lg border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold">{setting.label}</h2>
        <StatusLozenge tone={setting.overridden ? "work" : "neutral"}>{setting.overridden ? "後台設定" : "環境預設"}</StatusLozenge>
        <span className="text-xs text-muted">{setting.key}</span>
      </div>
      <p className="mt-1 text-sm text-muted">{setting.help}</p>
      <form onSubmit={submit} className="mt-3 flex flex-wrap items-end gap-2">
        <label className="grid min-w-48 flex-1 gap-1 text-sm">
          <span className="text-xs text-muted">
            {setting.kind === "shifts" ? "班表" : `數值${setting.minimum != null ? `（${setting.minimum}–${setting.maximum}）` : ""}`}
          </span>
          <input
            aria-label={setting.label}
            type={setting.kind === "shifts" ? "text" : "number"}
            step={setting.kind === "count" ? 1 : 0.5}
            min={setting.minimum ?? undefined}
            max={setting.maximum ?? undefined}
            value={text}
            onChange={(e) => setDraft(e.target.value)}
            className="rounded-md border border-line bg-canvas px-2 py-1.5 font-mono"
          />
        </label>
        <Button type="submit" variant="primary" disabled={!changed || save.isPending}>
          儲存
        </Button>
        {setting.overridden ? (
          <Button variant="subtle" onClick={() => setResetting(true)}>
            改回環境預設
          </Button>
        ) : null}
      </form>
      {save.isError ? (
        <p role="alert" className="mt-2 text-sm text-danger">
          沒有儲存：{save.error.message}
        </p>
      ) : null}
      <p className="mt-2 text-xs text-muted">環境預設：{shown(setting.default)}</p>
      {setting.changes.length ? (
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer text-accent">最近的修改（{setting.changes.length}）</summary>
          <ol className="mt-1 grid gap-1">
            {setting.changes.map((change, i) => (
              <li key={i} className="text-muted">
                {when(change.at)}・{change.actor_label}：{shown(change.before)} → {shown(change.after)}
              </li>
            ))}
          </ol>
        </details>
      ) : null}
      {resetting ? (
        <ConfirmDialog
          title={`把「${setting.label}」改回環境預設？`}
          confirmLabel="改回"
          tone="primary"
          busy={reset.isPending}
          error={reset.isError ? reset.error.message : null}
          onConfirm={() => reset.mutate()}
          onCancel={() => setResetting(false)}
        >
          目前：{shown(setting.value)} → 環境預設：{shown(setting.default)}
        </ConfirmDialog>
      ) : null}
    </section>
  );
}
