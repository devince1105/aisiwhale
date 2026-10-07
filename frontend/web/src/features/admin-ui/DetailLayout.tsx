// A detail page's two columns (AD-07), Jira's issue view: what it is on the left, its properties,
// what can be done to it and its history on the right — under the content on a narrow screen.
import type { ReactNode } from "react";

export function DetailLayout({ main, side }: { main: ReactNode; side: ReactNode }) {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="min-w-0">{main}</div>
      <aside aria-label="屬性與活動" className="grid content-start gap-4">
        {side}
      </aside>
    </div>
  );
}

/** The properties box: label, value, one a line. */
export function Properties({ title = "屬性", rows }: { title?: string; rows: readonly [string, ReactNode][] }) {
  return (
    <section aria-label={title} className="rounded-lg border border-line bg-surface">
      <h2 className="border-b border-line px-3 py-2 text-sm font-semibold">{title}</h2>
      <dl className="grid grid-cols-[6rem_minmax(0,1fr)] gap-x-3 gap-y-2 px-3 py-3 text-sm">
        {rows.map(([name, value]) => (
          <div key={name} className="contents">
            <dt className="text-muted">{name}</dt>
            <dd className="min-w-0 break-words">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
