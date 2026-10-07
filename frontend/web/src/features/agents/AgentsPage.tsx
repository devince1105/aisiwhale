"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { agentsQuery, decideAgent, hireAgent, rolesQuery, type AgentAction } from "@/api/queries";
import { AdminPage, PageHeader } from "@/features/admin-ui/PageHeader";
import { CompanyScope, type Company } from "@/features/company/CompanyScope";
import { useCompanyStream } from "@/features/company/useCompanyStream";

import { ErrorState } from "@/features/admin-ui/states";

import { AgentsView, HireForm } from "./AgentsView";

/** /agents: who works at this company, and hiring one more. */
export function AgentsPage() {
  return <CompanyScope>{(company) => <CompanyAgents company={company} />}</CompanyScope>;
}

function CompanyAgents({ company }: { company: Company }) {
  useCompanyStream(company.id);
  const agents = useQuery(agentsQuery(company.id));
  const roles = useQuery(rolesQuery());
  const queryClient = useQueryClient();

  return (
    <AdminPage width="read">
      <PageHeader title={`${company.name} 的代理`} />
      {agents.error ? <ErrorState>{agents.error.message}</ErrorState> : null}
      <AgentsView
        agents={agents.data}
        onDecide={async (agentId: string, action: AgentAction) => {
          await decideAgent(company.id, agentId, action);
          await queryClient.invalidateQueries({ queryKey: ["agents", company.id] });
        }}
      />
      <h2 className="mt-8 mb-3 text-lg font-semibold">雇用代理</h2>
      <HireForm
        roles={roles.data?.roles}
        taken={(agents.data ?? []).map((a) => a.role)}
        onHire={async (agent) => {
          await hireAgent(company.id, agent);
          await queryClient.invalidateQueries({ queryKey: ["agents", company.id] });
        }}
      />
    </AdminPage>
  );
}
