"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import {
  approvalsQuery,
  decideApproval,
  failedWorkflowsQuery,
  projectsQuery,
  queryKeys,
  restartWorkflow,
} from "@/api/queries";
import { AdminPage, PageHeader } from "@/features/admin-ui/PageHeader";
import { CompanyScope, type Company } from "@/features/company/CompanyScope";
import { useCompanyStream } from "@/features/company/useCompanyStream";
import { useNow } from "@/hooks/useNow";
import type { AgentState } from "@/realtime/reducer";
import { useRealtime } from "@/stores/realtime";

import { ApprovalInbox } from "./ApprovalInbox";
import { ArticlePreview } from "./ArticlePreview";
import { FailedRuns } from "./FailedRuns";
import { approvalCard, type ApprovalState } from "./model";

const NO_AGENTS: Record<string, AgentState> = {};

/** /approvals: what the runtime is waiting for a human to decide. */
export function ApprovalsPage() {
  return <CompanyScope>{(company) => <CompanyApprovals company={company} />}</CompanyScope>;
}

function CompanyApprovals({ company }: { company: Company }) {
  useCompanyStream(company.id);
  const [state, setState] = useState<ApprovalState>("PENDING");
  const approvals = useQuery(approvalsQuery(company.id, state));
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
      <ApprovalInbox
        state={state}
        onState={setState}
        cards={approvals.data?.map((a) => approvalCard(a, agents, now, projectNames))}
        loadError={approvals.error?.message ?? null}
        decide={(id, decision, reason) => decideApproval(id, decision, reason)}
        live={connection.status === "live"}
        refresh={() => queryClient.invalidateQueries({ queryKey: ["approvals", company.id] })}
        preview={(card) =>
          card.article ? <ArticlePreview
              articleId={card.article.id}
              draftGroupId={card.article.draftGroupId}
              decision={card.state as ApprovalState}
            /> : null
        }
      />
      {/* the other thing the inbox is for: work that failed and could be run again (AC-9) */}
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

