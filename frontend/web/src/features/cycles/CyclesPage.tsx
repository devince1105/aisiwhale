"use client";

import { useSuspenseQuery } from "@tanstack/react-query";

import { cyclesQuery } from "@/api/queries";
import { AdminPage, PageHeader } from "@/features/admin-ui/PageHeader";
import { CompanyScope, type Company } from "@/features/company/CompanyScope";

import { CyclesView } from "./CyclesView";

/** The company's days: ?company=<id>, or the first company. */
export function CyclesPage() {
  return (
    <CompanyScope>
      {(company) => <CompanyCycles company={company} />}
    </CompanyScope>
  );
}

function CompanyCycles({ company }: { company: Company }) {
  const { data } = useSuspenseQuery(cyclesQuery(company.id));
  return (
    <AdminPage width="read">
      <PageHeader title={`${company.name} 的營運週期`} />
      <CyclesView cycles={data} />
    </AdminPage>
  );
}
