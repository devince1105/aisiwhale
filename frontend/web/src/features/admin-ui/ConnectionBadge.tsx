"use client";

// Whether the page's live data is live (D-007): one badge, in the back office's top bar (AD-02).
import { connectionModel, type DashboardModel } from "@/features/dashboard/model";
import { useNow } from "@/hooks/useNow";
import { useRealtime } from "@/stores/realtime";

const CONNECTION_LABEL: Record<DashboardModel["connection"]["status"], string> = {
  idle: "未連線",
  connecting: "連線中",
  live: "即時",
  reconnecting: "重新連線中",
  offline: "離線",
  unauthorized: "權杖無效",
  not_found: "找不到公司",
};

const DOT: Record<DashboardModel["connection"]["status"], string> = {
  idle: "bg-neutral",
  connecting: "bg-warn",
  live: "bg-ok",
  reconnecting: "bg-warn",
  offline: "bg-danger",
  unauthorized: "bg-danger",
  not_found: "bg-danger",
};

export function ConnectionBadge({ connection }: { connection: DashboardModel["connection"] }) {
  const stale = connection.staleSeconds;
  return (
    <span
      role="status"
      data-status={connection.status}
      className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-xs text-muted"
    >
      <span aria-hidden className={`size-2 rounded-full ${DOT[connection.status]}`} />
      {CONNECTION_LABEL[connection.status]}
      {stale !== null && connection.status !== "live" ? `・資料可能已過期 ${stale} 秒` : null}
    </span>
  );
}

/** The badge for the stream the page opened (useCompanyStream); nothing on a page without one. */
export function LiveStatus() {
  const connection = useRealtime((state) => state.connection);
  const hasData = useRealtime((state) => state.company !== null);
  if (connection.status === "idle") return null;
  return <Ticking connection={connection} hasData={hasData} />;
}

function Ticking({ connection, hasData }: { connection: Parameters<typeof connectionModel>[0]; hasData: boolean }) {
  const now = useNow();
  return <ConnectionBadge connection={connectionModel(connection, hasData, now)} />;
}
