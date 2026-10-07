"use client";

import { useSuspenseQuery } from "@tanstack/react-query";

import { cycleQuery } from "@/api/queries";

import { AdminPage } from "@/features/admin-ui/PageHeader";

import { CycleDetailView } from "./CycleDetailView";

export function CycleDetailPage({ cycleId }: { cycleId: string }) {
  const { data } = useSuspenseQuery(cycleQuery(cycleId));
  return (
    <AdminPage width="read">
      <div className="flex flex-col gap-6">
        <CycleDetailView cycle={data} />
      </div>
    </AdminPage>
  );
}
