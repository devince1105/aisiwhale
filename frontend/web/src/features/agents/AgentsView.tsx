"use client";

// The company's agents, and the form that hires one (T-517 follow-up). Until the CEO decides the
// staffing itself (Phase 6), this is how a company gets its desks filled.
import { useState, type FormEvent } from "react";

import type { Schemas } from "@/api/client";
import type { AgentAction, NewAgent } from "@/api/queries";
import { Button } from "@/features/admin-ui/Button";
import { ConfirmDialog } from "@/features/admin-ui/Dialog";
import { ROW, ROW_FOCUS } from "@/features/admin-ui/hotkeys";
import { EmptyState, ErrorState, LoadingState } from "@/features/admin-ui/states";
import { Face } from "@/features/agent-panel/Face";
import { ROLE_LABEL, STATE_LABEL } from "@/features/agent-panel/model";
import type { ActivityState } from "@/realtime/snapshot";
import { personName } from "@/people";

export type Agent = Schemas["AgentOut"];

const STATUS_LABEL: Record<string, string> = { active: "在職", paused: "暫停中", retired: "已離職" };

export function AgentsView({
  agents,
  onDecide,
}: {
  agents: readonly Agent[] | undefined;
  onDecide: (agentId: string, action: AgentAction) => Promise<unknown>;
}) {
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function decide(agentId: string, action: AgentAction) {
    setBusy(agentId);
    setError(null);
    try {
      await onDecide(agentId, action);
      setConfirming(null);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(null);
    }
  }

  if (!agents) return <LoadingState />;
  if (agents.length === 0) return <EmptyState>這間公司還沒有代理。</EmptyState>;
  const leaving = agents.find((agent) => agent.id === confirming);
  return (
    <>
      {error ? <ErrorState>{error}</ErrorState> : null}
      <ul className="mt-2 divide-y divide-line rounded-lg border border-line bg-surface text-sm">
        {agents.map((agent) => (
          <li key={agent.id} {...ROW} className={`flex flex-wrap items-center gap-3 px-4 py-3 ${ROW_FOCUS}`}>
            <Face name={agent.display_name} role={agent.role} avatarKey={agent.avatar_key} size={28} />
            <span className="font-medium">{personName(agent.display_name)}</span>
            <span className="text-muted">{ROLE_LABEL[agent.role] ?? agent.role}</span>
            <span className="grow" />
            <span className="text-xs text-muted">
              {STATUS_LABEL[agent.status] ?? agent.status}
              {agent.activity ? `・${STATE_LABEL[agent.activity.state as ActivityState] ?? agent.activity.state}` : ""}
            </span>
            <Button
              size="sm"
              disabled={busy === agent.id}
              onClick={() => decide(agent.id, agent.status === "paused" ? "resume" : "pause")}
            >
              {agent.status === "paused" ? "恢復工作" : "暫停"}
            </Button>
            <Button size="sm" variant="subtle" onClick={() => setConfirming(agent.id)}>
              解雇
            </Button>
          </li>
        ))}
      </ul>
      {leaving ? (
        <ConfirmDialog
          title={`確定讓 ${personName(leaving.display_name)} 離職？`}
          confirmLabel="確定解雇"
          busy={busy === leaving.id}
          error={error}
          onConfirm={() => decide(leaving.id, "retire")}
          onCancel={() => setConfirming(null)}
        >
          不能復職。
        </ConfirmDialog>
      ) : null}
    </>
  );
}

export function HireForm({
  roles,
  taken,
  onHire,
}: {
  roles: readonly string[] | undefined;
  taken: readonly string[];
  onHire: (agent: NewAgent) => Promise<unknown>;
}) {
  const [role, setRole] = useState("");
  const [name, setName] = useState("");
  const [budget, setBudget] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const chosen = role || roles?.[0] || "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onHire({
        role: chosen,
        display_name: name.trim(),
        per_run_usd: budget ? budget : null,
        description: null,
        tools: [],
        avatar_key: "default",
      });
      setName("");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-3 rounded border border-line bg-surface p-4 text-sm sm:grid-cols-3">
      <label className="grid gap-1">
        角色
        <select value={chosen} onChange={(e) => setRole(e.target.value)} className="rounded border border-line bg-canvas px-2 py-1">
          {(roles ?? []).map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r] ?? r}
              {taken.includes(r) ? "（已有人）" : ""}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1">
        名字
        <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="例：Rae" className="rounded border border-line bg-canvas px-2 py-1" />
      </label>
      <label className="grid gap-1">
        單次執行上限（USD，選填）
        <input type="number" min="0" step="0.1" value={budget} onChange={(e) => setBudget(e.target.value)} className="rounded border border-line bg-canvas px-2 py-1" />
      </label>
      <div className="flex items-center gap-3 sm:col-span-3">
        <button type="submit" disabled={busy || !chosen} className="rounded bg-accent px-3 py-1 text-accent-ink disabled:opacity-50">
          {busy ? "雇用中…" : "雇用"}
        </button>
        <span className="text-xs text-muted">雇用後會出現在辦公室，並開始承接這個角色的任務。</span>
        {error ? <span className="text-danger">{error}</span> : null}
      </div>
    </form>
  );
}
