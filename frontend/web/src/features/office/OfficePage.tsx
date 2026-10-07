"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { kpisQuery, pendingCountQuery, officeHoursQuery, officeThemeQuery, orgQuery, queryKeys, setOfficeTheme } from "@/api/queries";
import { AgentPanel } from "@/features/agent-panel/AgentPanel";
import { CompanyScope, type Company } from "@/features/company/CompanyScope";
import { useCompanyStream } from "@/features/company/useCompanyStream";
import { dashboardModel } from "@/features/dashboard/model";
import { useNow } from "@/hooks/useNow";
import { OfficeCanvas, parseView, type OfficeView, type ThemeId } from "@/office3d/OfficeCanvas";
import { useRealtime, type RealtimeState } from "@/stores/realtime";
import { useUi } from "@/stores/ui";

import { DepartmentStrip, departmentNames as departmentNames_, departmentsOf } from "./Departments";
import { MiniDashboardView } from "./MiniDashboard";
import { TeamChat } from "./TeamChat";
import { CHAT_TYPES } from "./chatModel";

const CHAT_OPEN = "autora:team-chat";

/** Whether the team group is showing (D-109): open unless the operator closed it, remembered in
 * this browser; and how many of its messages came while it was closed. */
function useTeamChat(companyId: string): [boolean, (open: boolean) => void, number] {
  const [open, setOpenState] = useState(true);
  useEffect(() => {
    try {
      if (localStorage.getItem(CHAT_OPEN) === "closed") setOpenState(false);
    } catch {
      // storage closed: open
    }
  }, []);
  const latest = useRealtime((s) => {
    if (s.company?.companyId !== companyId) return 0;
    const events = s.company.recentEvents;
    for (let i = events.length - 1; i >= 0; i--) if (CHAT_TYPES.has(events[i].event_type)) return events[i].seq ?? 0;
    return 0;
  });
  const count = useRealtime((s) => s.company?.recentEvents);
  const [seen, setSeen] = useState(0);
  const unread = open ? 0 : (count ?? []).filter((e) => CHAT_TYPES.has(e.event_type) && (e.seq ?? 0) > seen).length;
  const setOpen = (next: boolean) => {
    setOpenState(next);
    setSeen(latest);
    try {
      localStorage.setItem(CHAT_OPEN, next ? "open" : "closed");
    } catch {
      // not remembered: it still opens or closes now
    }
  };
  return [open, setOpen, seen === 0 && !open ? 0 : unread];
}

const VIEWS: { id: OfficeView; label: string }[] = [
  { id: "auto", label: "自動" },
  { id: "3d", label: "3D" },
  { id: "2d", label: "2D" },
];

/**
 * /office (T-411): the office (3D or the 2D board), the dashboard's numbers in a strip, the
 * connection, and the agent detail panel of whoever is selected — by clicking an avatar or a card.
 * ?view=3d|2d overrides the automatic choice; ?department=<key> opens inside one department.
 */
export function OfficePage() {
  return <CompanyScope>{(company) => <CompanyOffice company={company} />}</CompanyScope>;
}

/**
 * Keeps ?department=<key> and the entered department in step (T-600 batch 3).
 *
 * The URL is the shareable half: a link to a department opens inside it, and entering one from
 * the strip puts it in the address bar. The roster is what resolves the key to a room, so the
 * link waits for the stream rather than guessing where the department is.
 */
function useDepartmentInUrl(realtime: ReturnType<typeof useRealtime<RealtimeState | null>>) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const wanted = params.get("department");
  const entered = useUi((s) => s.focusedDepartment);
  const enter = useUi((s) => s.enterDepartment);
  const known = useMemo(() => departmentsOf(Object.values(realtime?.agents ?? {})), [realtime]);
  /** The last key taken *from* the URL, so leaving a room is not read as a link into it. */
  const applied = useRef<string | null>(null);

  useEffect(() => {
    const key = entered?.key ?? null;
    const setUrl = (next: string | null) => {
      const query = new URLSearchParams(params);
      if (next) query.set("department", next);
      else query.delete("department");
      applied.current = next;
      router.replace(`${pathname}?${query}`);
    };

    if (wanted === key) {
      applied.current = key;
      return;
    }
    if (wanted && applied.current !== wanted) {
      // a link into a department. The roster is what resolves it to a room and arrives on the
      // stream a moment later, so until it does the link stands rather than being erased.
      const found = known.find((d) => d.key === wanted);
      if (found) {
        applied.current = wanted;
        enter({ key: found.key, zone: found.zone });
      } else if (known.length) {
        setUrl(key); // this company has no such department: the address bar follows the office
      }
      return;
    }
    setUrl(key); // the operator entered or left a room
  }, [wanted, entered, enter, known, params, pathname, router]);
}

function CompanyOffice({ company }: { company: Company }) {
  useCompanyStream(company.id);
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const view = parseView(params.get("view"));
  const setView = (next: OfficeView) => {
    const query = new URLSearchParams(params);
    if (next === "auto") query.delete("view");
    else query.set("view", next);
    router.replace(`${pathname}?${query}`);
  };
  const realtime = useRealtime((s) => (s.company?.companyId === company.id ? s.company : null));
  useDepartmentInUrl(realtime);
  const connection = useRealtime((s) => s.connection);
  const now = useNow();
  const kpis = useQuery(kpisQuery(company.id));
  const org = useQuery(orgQuery(company.id));
  const departmentNames = useMemo(() => departmentNames_(org.data), [org.data]);
  const pending = useQuery(pendingCountQuery(company.id));
  // the office's style is the company's (D-178): the same in every browser, and the site's
  // AI 編輯部 shows the site's company in it
  const queries = useQueryClient();
  const officeTheme = useQuery(officeThemeQuery(company.id));
  const hours = useQuery(officeHoursQuery());
  const chooseTheme = useMutation({
    mutationFn: (theme: ThemeId) => setOfficeTheme(company.id, theme),
    onMutate: (theme) => queries.setQueryData(queryKeys.officeTheme(company.id), theme),
    onSettled: () => queries.invalidateQueries({ queryKey: queryKeys.officeTheme(company.id) }),
  });
  const model = dashboardModel(realtime, kpis.data, connection, now);
  // what the office settled on (``auto`` is decided in the canvas, by asking the browser)
  const [mode, setMode] = useState<"2d" | "3d">("3d");
  const [chatOpen, setChatOpen, unread] = useTeamChat(company.id);

  return (
    <main
      className="flex h-[calc(100dvh-var(--admin-bar,0px))] flex-col bg-canvas text-ink"
      // which view is on screen; the page keeps the back office's own colours in both (D-245: the
      // 2D view's terminal green, page and all, was out of place in it)
      data-terminal={mode === "2d"}
    >
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <p className="text-xs tracking-widest text-muted uppercase">Office</p>
          <h1 className="flex items-center gap-2 text-lg font-semibold">
            {company.name} 的辦公室
            <OffDuty hours={hours.data} />
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <div role="group" aria-label="顯示方式" className="flex rounded-lg border border-line p-0.5">
            {VIEWS.map((v) => (
              <button
                key={v.id}
                type="button"
                aria-pressed={view === v.id}
                onClick={() => setView(v.id)}
                className={`rounded-md px-3 py-1 text-sm ${view === v.id ? "bg-accent text-canvas" : "text-muted"}`}
              >
                {v.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setChatOpen(!chatOpen)}
            aria-pressed={chatOpen}
            className={`relative rounded-lg border px-3 py-1 text-sm ${chatOpen ? "border-accent text-accent" : "border-line text-muted hover:text-ink"}`}
            data-testid="team-chat-toggle"
          >
            團隊群組
            {unread ? (
              <span className="absolute -top-1.5 -right-1.5 min-w-5 rounded-full bg-danger px-1 text-center text-[11px] leading-5 text-white" aria-label={`${unread} 則新訊息`}>
                {unread > 99 ? "99+" : unread}
              </span>
            ) : null}
          </button>
        </div>
      </header>
      <MiniDashboardView model={model} pendingApprovals={pending.data ?? null} />
      <DepartmentStrip companyId={company.id} />
      <div className="flex min-h-0 flex-1">
        {/* clipped to its own area: a name tag near the edge must not sit over the team group */}
        <div className="relative min-w-0 flex-1 overflow-hidden">
          {/* the detail panel is max-w-md (448 px) on the right while someone is selected */}
          <OfficeCanvas
            view={view}
            onViewChange={setView}
            onMode={setMode}
            selectionInsetRight={448}
            departmentNames={departmentNames}
            theme={officeTheme.data}
            onTheme={(theme) => chooseTheme.mutate(theme)}
            boardLook="site"
          />
        </div>
        {/* the team group beside the office (D-109); on a narrow screen, over it */}
        {chatOpen ? (
          <div className="absolute inset-y-0 right-0 z-30 w-full max-w-sm lg:static lg:w-auto lg:max-w-none">
            <TeamChat companyId={company.id} onClose={() => setChatOpen(false)} />
          </div>
        ) : null}
      </div>
      <AgentPanel />
    </main>
  );
}

/** Out of hours (D-193): a quiet office is closed, not broken — and when it opens again. */
/** How long after a person acts the office says the worker was called in (D-205): one call's length. */
const CALLED_FOR_MS = 60 * 60 * 1000;

export function OffDuty({
  hours,
  now = new Date(),
}: {
  hours: { on_duty: boolean; next_start?: string | null; timezone: string; called_at?: string | null } | undefined;
  now?: Date;
}) {
  if (!hours || hours.on_duty) return null;
  const opens = hours.next_start
    ? new Intl.DateTimeFormat("zh-TW", { weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: hours.timezone }).format(
        new Date(hours.next_start),
      )
    : null;
  // D-205: what you just did in the back office called the worker in, off its shifts
  const called = hours.called_at ? now.getTime() - Date.parse(hours.called_at) < CALLED_FOR_MS : false;
  return (
    <span
      data-testid="off-duty"
      title={called ? "你剛才在後台的操作已通知員工，約 1 分鐘內臨時上班處理（加班：每天最多 4 小時、每月 46 小時）" : undefined}
      className="rounded-full border border-line px-2 py-0.5 text-xs font-normal text-muted"
    >
      下班中{called ? "・已通知加班" : ""}
      {opens ? `・${opens} 上班` : ""}
    </span>
  );
}
