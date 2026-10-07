// The pages last opened in this browser (AD-03): the command palette's first search, before any
// list can be searched on the server (AD-04). Detail pages only — the sections are in the map.
export interface Visit {
  href: string;
  title: string;
  /** The section it belongs to (文章, 題材…). */
  section: string;
}

const KEY = "autora.admin.recent";
const KEEP = 8;

export function recentVisits(): Visit[] {
  try {
    const raw = JSON.parse(window.localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(raw)
      ? raw.filter((v): v is Visit => typeof v?.href === "string" && typeof v?.title === "string" && typeof v?.section === "string")
      : [];
  } catch {
    return [];
  }
}

export function rememberVisit(visit: Visit): void {
  try {
    const rest = recentVisits().filter((v) => v.href !== visit.href);
    window.localStorage.setItem(KEY, JSON.stringify([visit, ...rest].slice(0, KEEP)));
  } catch {
    // storage blocked: the palette just has nothing recent
  }
}
