"use client";

import { AdminPage, PageHeader } from "@/features/admin-ui/PageHeader";
import { CompanyScope, type Company } from "@/features/company/CompanyScope";
import { useCompanyStream } from "@/features/company/useCompanyStream";
import type { AgentState } from "@/realtime/reducer";
import { useRealtime } from "@/stores/realtime";

import { Timeline } from "./Timeline";

const NO_EVENTS: never[] = [];
const NO_AGENTS: Record<string, AgentState> = {};

/** /timeline: the company's recent events as they arrive. */
export function TimelinePage() {
  return <CompanyScope>{(company) => <CompanyTimeline company={company} />}</CompanyScope>;
}

function CompanyTimeline({ company }: { company: Company }) {
  useCompanyStream(company.id);
  const current = useRealtime((state) => (state.company?.companyId === company.id ? state.company : null));
  return (
    <AdminPage>
      <PageHeader title={`${company.name} 的事件`} />
      <Timeline
        companyId={company.id}
        events={current?.recentEvents ?? NO_EVENTS}
        agents={current?.agents ?? NO_AGENTS}
      />
    </AdminPage>
  );
}
