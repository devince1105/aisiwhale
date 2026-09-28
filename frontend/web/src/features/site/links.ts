// The front page's addresses (D-047, D-065, D-084), in a module of their own: the list and its
// calendar both build them.
import type { Filter, Lang } from "./i18n";

/** The front page's address for a tab or a section, a page and a day (page 1, "all" and no day
 * are left out). */
export function listHref(lang: Lang, filter: Filter | null, page = 1, day: string | null = null): string {
  const query = new URLSearchParams();
  if (filter) query.set("section", filter);
  if (day) query.set("date", day);
  if (page > 1) query.set("page", String(page));
  const qs = query.toString();
  return `/news/${lang}${qs ? `?${qs}` : ""}`;
}
