// What a list or a page says while it loads, when it has nothing, and when it failed.
import type { ReactNode } from "react";

export function LoadingState({ children = "載入中…" }: { children?: ReactNode }) {
  return <p className="py-6 text-sm text-muted">{children}</p>;
}

export function EmptyState({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line px-4 py-8 text-center text-sm text-muted">
      <p>{children}</p>
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded-lg border border-danger-line bg-danger-soft px-4 py-3 text-sm text-danger">
      {children}
    </p>
  );
}

/** Under a list loaded a page at a time (AD-04): how many of how many, and the next page. */
export function LoadMore({
  shown,
  total,
  more,
  loading,
  onMore,
}: {
  shown: number;
  total: number | null;
  more: boolean;
  loading: boolean;
  onMore: () => void;
}) {
  if (total === null || total === 0) return null;
  return (
    <div className="mt-3 flex items-center justify-between gap-3 text-xs text-muted" data-testid="load-more">
      <span className="tabular-nums">
        顯示 {shown} / 共 {total} 筆
      </span>
      {more ? (
        <button
          type="button"
          onClick={onMore}
          disabled={loading}
          className="rounded-md border border-line bg-surface px-3 py-1 text-sm text-ink hover:bg-canvas disabled:opacity-50"
        >
          {loading ? "載入中…" : "載入更多"}
        </button>
      ) : null}
    </div>
  );
}
