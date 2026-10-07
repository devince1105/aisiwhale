"use client";

// The back office's shell (AD-02): a sidebar with the company switcher and every page (nav.ts),
// collapsible to icons and a drawer on a phone; a top bar with the live badge, the theme and who
// is signed in. Pages draw only their own content (AdminPage, PageHeader).
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";

import { approvalsQuery } from "@/api/queries";
import { useCompanyChoice, withCompany } from "@/features/company/CompanyScope";
import { ThemeToggle } from "@/features/site/ThemeToggle";

import { Button } from "./Button";
import { LiveStatus } from "./ConnectionBadge";
import { Drawer } from "./Dialog";
import { Icon } from "./icons";
import { activeNav, ADMIN_NAV, type NavItem } from "./nav";

const COLLAPSED = "autora.admin.sidebar";

function savedCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSED) === "1";
  } catch {
    return false;
  }
}

function saveCollapsed(collapsed: boolean): void {
  try {
    window.localStorage.setItem(COLLAPSED, collapsed ? "1" : "0");
  } catch {
    // storage blocked: the sidebar opens expanded next time
  }
}

export function AdminShell({ email, onSignOut, children }: { email: string | null; onSignOut: () => void; children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const pathname = usePathname() ?? "";
  useEffect(() => setCollapsed(savedCollapsed()), []);
  // a link followed in the phone's drawer closes it
  useEffect(() => setMenuOpen(false), [pathname]);

  const toggle = () => {
    setCollapsed(!collapsed);
    saveCollapsed(!collapsed);
  };

  return (
    // --admin-bar: the top bar's height, for a page that fills the rest of the screen (the office)
    <div className="flex min-h-dvh" style={{ "--admin-bar": "3rem" } as CSSProperties}>
      <aside
        data-testid="admin-sidebar"
        className={`sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-line bg-surface md:flex print:hidden ${collapsed ? "w-14" : "w-60"}`}
      >
        <SidebarContent collapsed={collapsed} />
        <div className="border-t border-line p-2">
          <Button
            variant="subtle"
            size="sm"
            onClick={toggle}
            aria-label={collapsed ? "展開側欄" : "收合側欄"}
            title={collapsed ? "展開側欄" : "收合側欄"}
            className="w-full"
          >
            <Icon name={collapsed ? "expand" : "collapse"} className="size-4" />
          </Button>
        </div>
      </aside>
      {menuOpen ? (
        <Drawer title="後台選單" side="left" onClose={() => setMenuOpen(false)}>
          <SidebarContent collapsed={false} />
        </Drawer>
      ) : null}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-(--admin-bar) items-center gap-3 border-b border-line bg-surface px-3 md:px-4 print:hidden">
          <Button variant="subtle" size="sm" className="md:hidden" onClick={() => setMenuOpen(true)} aria-label="開啟選單">
            <Icon name="menu" />
          </Button>
          <span className="grow" />
          <LiveStatus />
          <ThemeToggle lang="zh-TW" />
          <span data-testid="admin-who" className="hidden max-w-48 truncate text-xs text-muted sm:inline">
            {email ?? "操作者權杖"}
          </span>
          <Button variant="subtle" size="sm" onClick={onSignOut}>
            登出
          </Button>
        </header>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}

function SidebarContent({ collapsed }: { collapsed: boolean }) {
  const pathname = usePathname() ?? "";
  const { requested, company } = useCompanyChoice();
  // the address's company before the list has loaded, so the links keep it from the start
  const companyId = company?.id ?? requested;
  const active = activeNav(pathname)?.item.key ?? null;
  const pending = useQuery({ ...approvalsQuery(companyId ?? ""), enabled: Boolean(companyId) });
  const counts: Record<NonNullable<NavItem["count"]>, number> = { "pending-approvals": pending.data?.length ?? 0 };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className={`flex h-12 shrink-0 items-center border-b border-line ${collapsed ? "justify-center" : "px-4"}`}>
        <Link href={companyId ? withCompany("/admin/dashboard", companyId) : "/admin/dashboard"} className="font-semibold" title="AiSiWhale 後台">
          {collapsed ? "艾" : "艾矽鯨 後台"}
        </Link>
      </div>
      {collapsed ? null : <CompanySwitcher />}
      <nav aria-label="後台導覽" className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {ADMIN_NAV.map((group) => (
          <div key={group.label} className="mb-3">
            {collapsed ? (
              <div className="mx-2 my-2 border-t border-line" aria-hidden="true" />
            ) : (
              <p className="px-2 pb-1 text-[11px] font-semibold tracking-wider text-muted">{group.label}</p>
            )}
            <ul className="grid gap-0.5">
              {group.items.map((item) => {
                const current = item.key === active;
                const count = item.count ? counts[item.count] : 0;
                return (
                  <li key={item.key}>
                    <Link
                      href={companyId ? withCompany(item.href, companyId) : item.href}
                      aria-current={current ? "page" : undefined}
                      title={collapsed ? item.label : undefined}
                      aria-label={collapsed ? item.label : undefined}
                      className={`relative flex items-center gap-2.5 rounded-md py-1.5 text-sm ${collapsed ? "justify-center px-0" : "px-2"} ${
                        current ? "bg-accent/10 font-medium text-accent" : "text-ink hover:bg-canvas"
                      }`}
                    >
                      <Icon name={item.icon} />
                      {collapsed ? null : <span className="grow truncate">{item.label}</span>}
                      {count > 0 ? (
                        <span
                          data-testid={`nav-count-${item.key}`}
                          className={`rounded-full bg-warn px-1.5 text-[11px] leading-5 font-medium text-canvas tabular-nums ${collapsed ? "absolute -top-1 -right-1" : ""}`}
                        >
                          {count > 99 ? "99+" : count}
                        </span>
                      ) : null}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
    </div>
  );
}

/** Which company the pages show (D-041), in sight: switching keeps the section and drops the
 * rest — a detail page belongs to the company it came from, so its list opens instead. */
function CompanySwitcher() {
  const pathname = usePathname() ?? "";
  const router = useRouter();
  const { companies, company } = useCompanyChoice();
  if (!companies.data || companies.data.length === 0) return null;
  const switchTo = (id: string) => {
    const section = activeNav(pathname)?.item.href ?? "/admin/dashboard";
    router.push(withCompany(section, id));
  };
  return (
    <label className="block border-b border-line px-3 py-2">
      <span className="mb-1 block text-[11px] font-semibold tracking-wider text-muted">公司</span>
      <select
        value={company?.id ?? ""}
        onChange={(event) => switchTo(event.target.value)}
        className="w-full rounded-md border border-line bg-canvas px-2 py-1 text-sm"
      >
        {companies.data.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
    </label>
  );
}
