"use client";

// Every back-office page's frame (AD-01): two widths — a list page wide, a page to read narrower —
// and one header: where the page is (breadcrumbs from the navigation map), its title, a line under
// it, and the page's actions on the right.
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import type { ReactNode } from "react";

import { withCompany } from "@/features/company/CompanyScope";

import { crumbsFor, type Crumb } from "./nav";

const WIDTH = { wide: "max-w-7xl", read: "max-w-5xl" } as const;

export function AdminPage({ width = "wide", children }: { width?: keyof typeof WIDTH; children: ReactNode }) {
  return <main className={`mx-auto w-full ${WIDTH[width]} px-4 pt-6 pb-12 md:px-6`}>{children}</main>;
}

export function PageHeader({
  title,
  description,
  actions,
  crumbs,
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  /** Crumbs after the map's own (a detail page's parent, say); the title is the last one. */
  crumbs?: readonly Crumb[];
  children?: ReactNode;
}) {
  const pathname = usePathname() ?? "";
  const company = useSearchParams()?.get("company") ?? null;
  const trail = [...crumbsFor(pathname), ...(crumbs ?? [])];
  return (
    <header className="mb-6">
      {trail.length ? (
        <nav aria-label="麵包屑" className="mb-2 text-xs text-muted">
          <ol className="flex flex-wrap items-center gap-1">
            {trail.map((crumb, index) => (
              <li key={`${crumb.label}-${index}`} className="flex items-center gap-1">
                {index > 0 ? <span aria-hidden="true">/</span> : null}
                {crumb.href ? (
                  <Link href={company ? withCompany(crumb.href, company) : crumb.href} className="hover:text-ink hover:underline">
                    {crumb.label}
                  </Link>
                ) : (
                  <span>{crumb.label}</span>
                )}
              </li>
            ))}
          </ol>
        </nav>
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold break-words">{title}</h1>
          {description ? <div className="mt-1 text-sm text-muted">{description}</div> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </header>
  );
}
