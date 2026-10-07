"use client";

import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import { taskQuery, traceQuery } from "@/api/queries";
import { AdminPage, PageHeader } from "@/features/admin-ui/PageHeader";
import { ErrorState, LoadingState } from "@/features/admin-ui/states";
import { useCompanyStream } from "@/features/company/useCompanyStream";

import { traceRows, traceSummary } from "./model";
import { TaskView, TraceView } from "./TraceView";

async function loadBlob(runId: string, seq: number): Promise<unknown> {
  return unwrap(
    await api.GET("/api/runs/{run_id}/steps/{seq}/blob", {
      params: { path: { run_id: runId, seq } },
      parseAs: "json",
    }),
  );
}

// loading and failing inside the shell too (AD-14): the breadcrumbs stay, and the states look
// like every other page's
const loading = (title: string) => (
  <AdminPage width="read">
    <PageHeader title={title} />
    <LoadingState />
  </AdminPage>
);
const failed = (title: string, text: string) => (
  <AdminPage width="read">
    <PageHeader title={title} />
    <ErrorState>{text}</ErrorState>
  </AdminPage>
);

/** /trace/[runId]: the run's real events and steps. Stays live through the company stream. */
export function TracePage({ runId }: { runId: string }) {
  const trace = useQuery(traceQuery(runId));
  const task = useQuery({ ...taskQuery(trace.data?.task_id ?? ""), enabled: Boolean(trace.data) });
  useCompanyStream(trace.data?.company_id ?? null);

  if (trace.isPending) return loading("執行軌跡");
  if (trace.error) return failed("執行軌跡", `無法載入軌跡：${trace.error.message}`);
  const rows = traceRows(trace.data);
  return (
    <TraceView
      trace={trace.data}
      rows={rows}
      summary={traceSummary(trace.data, rows)}
      taskName={task.data?.display_name ?? null}
      loadBlob={(seq) => loadBlob(runId, seq)}
    />
  );
}

/** /tasks/[taskId]: the task and every attempt, each linking to its trace. */
export function TaskPage({ taskId }: { taskId: string }) {
  const task = useQuery(taskQuery(taskId));
  useCompanyStream(task.data?.company_id ?? null);
  if (task.isPending) return loading("任務");
  if (task.error) return failed("任務", `無法載入任務：${task.error.message}`);
  return <TaskView task={task.data} />;
}
