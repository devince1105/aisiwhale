// The back office's one map of itself (AD-02): the sidebar, the breadcrumbs and — later — the
// command palette all read these groups, so a page added here is reachable from every page.
import type { IconName } from "./icons";

export interface NavItem {
  key: string;
  label: string;
  /** The page the item opens; also the prefix its sub-pages live under. */
  href: string;
  icon: IconName;
  /** Other path prefixes that belong to this item (a detail page outside ``href``). */
  also?: readonly string[];
  /** A count shown beside the label. */
  count?: "pending-approvals";
  /** The second key of its ``g`` shortcut (AD-03): ``g`` then this letter opens it. */
  go: string;
}

export interface NavGroup {
  label: string;
  items: readonly NavItem[];
}

export const ADMIN_NAV: readonly NavGroup[] = [
  {
    label: "總覽",
    items: [
      { key: "dashboard", go: "d", label: "Dashboard", href: "/admin/dashboard", icon: "dashboard" },
      { key: "office", go: "o", label: "辦公室", href: "/admin/office", icon: "office" },
    ],
  },
  {
    label: "工作",
    items: [
      { key: "approvals", go: "i", label: "審批收件匣", href: "/admin/approvals", icon: "inbox", count: "pending-approvals" },
      { key: "cycles", go: "c", label: "每日週期", href: "/admin/cycles", icon: "cycle" },
      { key: "timeline", go: "t", label: "事件時間軸", href: "/admin/timeline", icon: "timeline", also: ["/admin/trace", "/admin/tasks"] },
    ],
  },
  {
    label: "新聞室",
    items: [
      { key: "stories", go: "s", label: "題材", href: "/admin/newsroom/stories", icon: "story" },
      { key: "articles", go: "a", label: "文章", href: "/admin/newsroom/articles", icon: "article" },
      { key: "sources", go: "f", label: "來源", href: "/admin/newsroom/sources", icon: "source" },
    ],
  },
  {
    label: "組織與會員",
    items: [
      { key: "agents", go: "p", label: "代理", href: "/admin/agents", icon: "agents" },
      { key: "memberships", go: "v", label: "VIP 授予", href: "/admin/memberships", icon: "member" },
    ],
  },
];

const under = (pathname: string, prefix: string) => pathname === prefix || pathname.startsWith(`${prefix}/`);

/** The group and item a path belongs to — the longest prefix wins — or null for a page the map
 * does not know. */
export function activeNav(pathname: string): { group: NavGroup; item: NavItem } | null {
  let best: { group: NavGroup; item: NavItem; length: number } | null = null;
  for (const group of ADMIN_NAV) {
    for (const item of group.items) {
      for (const prefix of [item.href, ...(item.also ?? [])]) {
        if (under(pathname, prefix) && (!best || prefix.length > best.length)) {
          best = { group, item, length: prefix.length };
        }
      }
    }
  }
  return best ? { group: best.group, item: best.item } : null;
}

export interface Crumb {
  label: string;
  href?: string;
}

/** Group › item, linked to the item's list when the page is below it. */
export function crumbsFor(pathname: string): Crumb[] {
  const found = activeNav(pathname);
  if (!found) return [];
  const { group, item } = found;
  return [{ label: group.label }, pathname === item.href ? { label: item.label } : { label: item.label, href: item.href }];
}
