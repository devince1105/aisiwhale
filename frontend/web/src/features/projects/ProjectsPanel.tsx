"use client";

// Projects on the admin dashboard (D-056): which are running, which are paused and by whom, and
// a button for each direction. Both are the PauseProject / ResumeProject commands the CEO uses,
// so a refusal (a project already in that state) comes back as the command's own reason.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { decideProject, projectsQuery, queryKeys, type ProjectLine } from "@/api/queries";

const STATES: Record<string, string> = {
  ACTIVE: "進行中",
  PAUSED: "已暫停",
  KILLED: "已終止",
  COMPLETED: "已完成",
  PROPOSED: "提案中",
};
const PAUSED_BY: Record<string, string> = { ceo: "CEO", human: "操作者", kill_criteria: "停損條件" };

export function ProjectsPanel({ companyId }: { companyId: string }) {
  const projects = useQuery(projectsQuery(companyId));
  return (
    <section className="mt-8" aria-labelledby="projects-heading">
      <h2 id="projects-heading" className="mb-3 text-lg font-semibold">
        專案
      </h2>
      {projects.data ? (
        <ProjectsView companyId={companyId} projects={projects.data} />
      ) : (
        <p className="text-sm text-muted">{projects.isError ? "讀不到專案。" : "載入中…"}</p>
      )}
    </section>
  );
}

export function ProjectsView({ companyId, projects }: { companyId: string; projects: ProjectLine[] }) {
  if (!projects.length) return <p className="text-sm text-muted">還沒有專案。</p>;
  return (
    <ul className="divide-y divide-line rounded-xl border border-line bg-surface text-sm" data-testid="projects">
      {projects.map((project) => (
        <ProjectRow key={project.id} companyId={companyId} project={project} />
      ))}
    </ul>
  );
}

function ProjectRow({ companyId, project }: { companyId: string; project: ProjectLine }) {
  const client = useQueryClient();
  const [reason, setReason] = useState("");
  const paused = project.state === "PAUSED";
  const action = paused ? "resume" : "pause";
  const decide = useMutation({
    mutationFn: () => decideProject(companyId, project.id, action, reason.trim() || null),
    onSuccess: () => setReason(""),
    onSettled: () => {
      client.invalidateQueries({ queryKey: queryKeys.projects(companyId) });
      client.invalidateQueries({ queryKey: queryKeys.finance(companyId) });
    },
  });
  const refused = decide.data && decide.data.outcome !== "done" ? decide.data.reason ?? decide.data.decision : null;
  const canDecide = project.state === "ACTIVE" || paused;

  return (
    <li className="grid gap-2 px-5 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{project.name}</span>
        <span
          className={
            paused
              ? "rounded border border-danger-line bg-danger-soft px-2 py-0.5 text-xs text-danger"
              : "rounded border border-line px-2 py-0.5 text-xs text-muted"
          }
        >
          {STATES[project.state] ?? project.state}
        </span>
      </div>
      {paused ? (
        <p className="text-xs text-muted" data-testid="pause-note">
          由 {PAUSED_BY[project.paused_by ?? ""] ?? "（不明）"} 暫停
          {project.paused_at ? `・${new Date(project.paused_at).toLocaleString("zh-TW")}` : ""}
          {project.pause_reason ? `：${project.pause_reason}` : ""}
          。暫停期間這個專案的新聞工作都不會開始。
        </p>
      ) : null}
      {canDecide ? (
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            decide.mutate();
          }}
        >
          <input
            value={reason}
            maxLength={500}
            onChange={(e) => setReason(e.target.value)}
            placeholder={paused ? "恢復原因（選填）" : "暫停原因（選填）"}
            aria-label={paused ? "恢復原因" : "暫停原因"}
            className="min-w-48 flex-1 rounded border border-line bg-canvas px-2 py-1"
          />
          <button
            type="submit"
            disabled={decide.isPending}
            className={
              paused
                ? "rounded border border-line px-3 py-1 disabled:opacity-50"
                : "rounded border border-danger-line bg-danger-soft px-3 py-1 text-danger disabled:opacity-50"
            }
          >
            {paused ? "恢復專案" : "暫停專案"}
          </button>
        </form>
      ) : null}
      {refused ? <p className="text-xs text-danger" role="alert">沒有執行：{refused}</p> : null}
      {decide.isError ? <p className="text-xs text-danger" role="alert">操作失敗：{String(decide.error)}</p> : null}
    </li>
  );
}
