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
