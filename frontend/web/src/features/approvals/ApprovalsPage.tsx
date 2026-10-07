"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";

import {
  approvalsQuery,
  decideApproval,
  failedWorkflowsQuery,
  projectsQuery,
  queryKeys,
  restartWorkflow,
  type ApprovalSort,
} from "@/api/queries";
import { ListToolbar } from "@/features/admin-ui/DataTable";
import { AdminPage, PageHeader } from "@/features/admin-ui/PageHeader";
import { useListState } from "@/features/admin-ui/useListState";
import { ActivityTimeline } from "@/features/audit/ActivityTimeline";
import { usePaged } from "@/features/admin-ui/usePaged";
import { CompanyScope, type Company } from "@/features/company/CompanyScope";
import { useCompanyStream } from "@/features/company/useCompanyStream";
import { useNow } from "@/hooks/useNow";
import type { AgentState } from "@/realtime/reducer";
import { useRealtime } from "@/stores/realtime";

import { ApprovalInbox } from "./ApprovalInbox";
import { ArticlePreview } from "./ArticlePreview";
import { FailedRuns } from "./FailedRuns";
import { approvalCard, STATES, type ApprovalState } from "./model";

const APPROVAL_SORTS: readonly ApprovalSort[] = ["created_at", "-created_at"];

const NO_AGENTS: Record<string, AgentState> = {};

/** /approvals: what the runtime is waiting for a human to decide. */
export function ApprovalsPage() {
  return <CompanyScope>{(company) => <CompanyApprovals company={company} />}</CompanyScope>;
}

function CompanyApprovals({ company }: { company: Company }) {
  useCompanyStream(company.id);
  // the tab, the words and the order are the address's (AD-05): a link to the inbox opens the
  // same view, and back undoes a change
  const list = useListState(["state"], APPROVAL_SORTS);
  const state = STATES.some((s) => s.id === list.filters.state) ? (list.filters.state as ApprovalState) : "PENDING";
  const approvals = usePaged(approvalsQuery(company.id, state, { q: list.q, sort: list.sort }));
  const failed = useQuery(failedWorkflowsQuery(company.id));
  // a command names its project by id; the card says which one it is (D-201)
  const projects = useQuery(projectsQuery(company.id));
  const projectNames = useMemo(
    () => Object.fromEntries((projects.data ?? []).map((p) => [p.id, p.name])),
    [projects.data],
  );
  const queryClient = useQueryClient();
  const current = useRealtime((s) => (s.company?.companyId === company.id ? s.company : null));
  const connection = useRealtime((s) => s.connection);
  const now = useNow();
  const agents = current?.agents ?? NO_AGENTS;

  return (
    <AdminPage width="read">
      <PageHeader title={`${company.name} 的審批收件匣`} />
      <ListToolbar list={list} placeholder="搜尋摘要或動作…" views="approvals" density={false} />
      <label className="mb-3 flex items-center gap-2 text-xs text-muted">
        順序
        <select
          aria-label="順序"
          value={list.sort ?? "created_at"}
          onChange={(event) => list.set({ sort: event.target.value === "created_at" ? null : (event.target.value as ApprovalSort) })}
          className="rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink"
        >
          <option value="created_at">等最久的在上</option>
          <option value="-created_at">最新的在上</option>
        </select>
      </label>
      <ApprovalInbox
        state={state}
        onState={(next) => list.set({ filters: { state: next === "PENDING" ? null : next } })}
        cards={approvals.items?.map((a) => approvalCard(a, agents, now, projectNames))}
        loadError={approvals.error?.message ?? null}
        decide={(id, decision, reason) => decideApproval(id, decision, reason)}
        live={connection.status === "live"}
        refresh={() => queryClient.invalidateQueries({ queryKey: ["approvals", company.id] })}
        activity={(card) => <ActivityTimeline targetType="approval" targetId={card.id} />}
        preview={(card) =>
          card.article ? <ArticlePreview
              articleId={card.article.id}
              draftGroupId={card.article.draftGroupId}
              decision={card.state as ApprovalState}
            /> : null
        }
      />
      {/* the other thing the inbox is for: work that failed and could be run again (AC-9) */}
      {approvals.footer}
      <FailedRuns
        runs={failed.data}
        onRestart={async (runId) => {
          const result = await restartWorkflow(company.id, runId);
          await queryClient.invalidateQueries({ queryKey: queryKeys.failedWorkflows(company.id) });
          return result;
        }}
      />
    </AdminPage>
  );
}

