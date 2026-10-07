// What the command palette offers (AD-03), and how a query picks from it.
import { withCompany } from "@/features/company/CompanyScope";

import type { IconName } from "./icons";
import { ADMIN_NAV, type NavGroup } from "./nav";
import type { Visit } from "./recent";

export interface Command {
  id: string;
  group: "最近瀏覽" | "前往" | "切換公司" | "動作" | "搜尋結果";
  label: string;
  /** Shown after the label, and searched too. */
  hint?: string;
  icon?: IconName;
  keys?: string;
  run: () => void;
}

export interface CommandContext {
  companyId: string | null;
  companies: readonly { id: string; name: string }[];
  recent: readonly Visit[];
  go: (href: string) => void;
  toggleSidebar: () => void;
  showHelp: () => void;
  signOut: () => void;
  /** The pages this role may open (AD-09); every page when not given. */
  nav?: readonly NavGroup[];
}

export function buildCommands(ctx: CommandContext): Command[] {
  const at = (href: string) => (ctx.companyId ? withCompany(href, ctx.companyId) : href);
  return [
    ...ctx.recent.map<Command>((visit) => ({
      id: `recent:${visit.href}`,
      group: "最近瀏覽",
      label: visit.title,
      hint: visit.section,
      run: () => ctx.go(visit.href),
    })),
    ...(ctx.nav ?? ADMIN_NAV).flatMap((group) =>
      group.items.map<Command>((item) => ({
        id: `go:${item.key}`,
        group: "前往",
        label: item.label,
        hint: group.label,
        icon: item.icon,
        keys: `g ${item.go}`,
        run: () => ctx.go(at(item.href)),
      })),
    ),
    ...ctx.companies
      .filter((company) => company.id !== ctx.companyId)
      .map<Command>((company) => ({
        id: `company:${company.id}`,
        group: "切換公司",
        label: company.name,
        hint: "切換公司",
        run: () => ctx.go(withCompany("/admin/dashboard", company.id)),
      })),
    { id: "action:sidebar", group: "動作", label: "收合／展開側欄", run: ctx.toggleSidebar },
    { id: "action:help", group: "動作", label: "鍵盤快捷鍵", keys: "?", run: ctx.showHelp },
    { id: "action:signout", group: "動作", label: "登出", run: ctx.signOut },
  ];
}

/** Every word of the query somewhere in the label or the hint, ignoring case; labels that start
 * with the query first. Nothing typed: everything, in order. */
export function pick(commands: readonly Command[], query: string): Command[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return [...commands];
  const found = commands.filter((c) => {
    const text = `${c.label} ${c.hint ?? ""}`.toLowerCase();
    return words.every((w) => text.includes(w));
  });
  const first = words.join(" ");
  return [
    ...found.filter((c) => c.label.toLowerCase().startsWith(first)),
    ...found.filter((c) => !c.label.toLowerCase().startsWith(first)),
  ];
}

/** The server's matches for what was typed (AD-04's ``q``): articles and stories by title. */
export function searchCommands(
  found: { articles: readonly { id: string; title: string }[]; stories: readonly { id: string; title: string }[] },
  go: (href: string) => void,
): Command[] {
  return [
    ...found.articles.map<Command>((a) => ({
      id: `article:${a.id}`,
      group: "搜尋結果",
      label: a.title,
      hint: "文章",
      icon: "article",
      run: () => go(`/admin/newsroom/articles/${a.id}`),
    })),
    ...found.stories.map<Command>((s) => ({
      id: `story:${s.id}`,
      group: "搜尋結果",
      label: s.title,
      hint: "題材",
      icon: "story",
      run: () => go(`/admin/newsroom/stories/${s.id}`),
    })),
  ];
}
