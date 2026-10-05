// Approval inbox (T-313): the operator's list of decisions the runtime is waiting for. The list
// is server state (GET /api/approvals); deciding is a REST command, and the list is refreshed by
// the APPROVAL_* event it causes (api/invalidation.ts), not by editing the cache.
import type { Schemas } from "@/api/client";
import { formatDuration } from "@/features/agent-panel/model";
import type { AgentState } from "@/realtime/reducer";
import { personName } from "@/people";

export type Approval = Schemas["ApprovalOut"];
export type ApprovalState = "PENDING" | "APPROVED" | "REJECTED" | "RETURNED" | "EXPIRED";
/** ``revise``: send it back with what to change (D-044). */
export type Decision = "approve" | "reject" | "revise";

export const STATES: { id: ApprovalState; label: string }[] = [
  { id: "PENDING", label: "待審批" },
  { id: "APPROVED", label: "已核准" },
  { id: "RETURNED", label: "已退回修改" },
  { id: "REJECTED", label: "已駁回" },
  { id: "EXPIRED", label: "已過期" },
];

/**
 * What to call each kind of decision. An open map on purpose: the backend stores the kind as a
 * token and a domain names its own (§9), so a kind this page has never seen shows its token
 * rather than nothing — "article" is the newsroom's word, kept here only as a translation.
 */
const KIND_LABEL: Record<string, string> = {
  tool_call: "工具呼叫",
  command: "指令",
  project: "專案",
  kill: "終止專案",
  strategy: "策略",
  article: "文章",
  official_report: "名人交易申報",
};

const ACTOR_KIND: Record<string, string> = { system: "系統", human: "人員", agent: "代理" };

export interface ApprovalCard {
  id: string;
  state: string;
  kind: string;
  action: string | null;
  summary: string;
  requester: string;
  /** What will run once approved: the tool's arguments, else the whole payload. */
  details: unknown;
  waiting: string;
  /** When the deadline is, and what happens then: an article nobody decided goes to the CEO
   * (D-157); anything else — or one she already had — expires and is asked again (D-131). */
  expires: { at: string; in: string | null; soon: boolean; then: "ceo" | "expire" } | null;
  /** The CEO is deciding it now (D-157); a person still may, and whoever is first counts. */
  withCeo: boolean;
  taskId: string | null;
  runId: string | null;
  /** A decision task (an article to approve) can be sent back; a paused agent run cannot. */
  canSendBack: boolean;
  /** The article to read before deciding (D-046): its id and the draft that was submitted. */
  article: { id: string; draftGroupId: string | null } | null;
  /** A transcribed official's transaction report to check against its scan (D-051). */
  officialReport: OfficialReportCheck | null;
  /** An executive's command (pause a project, a new strategy…): what it is and what each button
   * does, in words (D-201). Null for anything else, which keeps 核准 / 駁回. */
  command: CommandChoice | null;
  decision: { by: string; at: string; reason: string | null } | null;
}

/**
 * What approving a command does, and what saying no keeps (D-201). A bare 核准 read as agreeing
 * with one's own note: on 10/02 two of the CEO's requests to pause the newsroom were approved
 * with the note 「請繼續運作、不要暫停」, and it wrote nothing for three days. So the buttons name
 * the outcome, and the card names the project instead of its id.
 */
export interface CommandChoice {
  title: string;
  /** The executive's reason, or the strategy itself. */
  body: string | null;
  /** What happens once approved. */
  effect: string | null;
  approve: string;
  reject: string;
}

function named(names: Record<string, string>, id: unknown): string {
  const key = String(id ?? "");
  return names[key] ? `「${names[key]}」` : `（${key.slice(0, 8)}）`;
}

export function commandChoice(
  payload: Record<string, unknown>,
  projects: Record<string, string> = {},
  agents: Record<string, AgentState> = {},
): CommandChoice | null {
  if (typeof payload.command !== "string") return null;
  const args = (payload.args ?? {}) as Record<string, unknown>;
  const reason = typeof args.reason === "string" && args.reason.trim() ? args.reason.trim() : null;
  switch (payload.command) {
    case "PauseProject":
      return {
        title: `暫停專案${named(projects, args.project_id)}`,
        body: reason,
        effect: "核准後這個專案停工：不再開始新的工作（新聞室不排稿，不會有新文章），直到有人在儀表板按「恢復專案」。",
        approve: "核准：暫停專案",
        reject: "駁回：繼續運作",
      };
    case "ResumeProject":
      return {
        title: `恢復專案${named(projects, args.project_id)}`,
        body: reason,
        effect: "核准後專案恢復運作，下一個週期起照常開始工作。",
        approve: "核准：恢復專案",
        reject: "駁回：維持暫停",
      };
    case "KillProject":
      return {
        title: `終止專案${named(projects, args.project_id)}`,
        body: reason,
        effect: "核准後這個專案永久結束，不能再恢復。",
        approve: "核准：終止專案",
        reject: "駁回：繼續運作",
      };
    case "UpdateStrategy":
      return {
        title: "更新公司策略",
        body: typeof args.summary === "string" ? args.summary : null,
        effect: "核准後執行長往後每個週期都照這份策略規劃。",
        approve: "核准：採用新策略",
        reject: "駁回：維持原策略",
      };
    case "CreateProject":
      return {
        title: `新專案「${String(args.name ?? "")}」`,
        body: typeof args.description === "string" ? args.description : null,
        effect: "核准後建立這個專案，開始花預算做事。",
        approve: "核准：建立專案",
        reject: "駁回：不建立",
      };
    case "AllocateBudget":
      return {
        title: `撥預算 NT$${String(args.amount ?? "")}`,
        body: reason,
        effect: null,
        approve: "核准：撥這筆預算",
        reject: "駁回：不撥",
      };
    case "PauseAgent": {
      const id = String(args.agent_id ?? "");
      return {
        title: `暫停員工「${personName(agents[id]?.display_name) || id.slice(0, 8)}」`,
        body: reason,
        effect: "核准後這位員工不再接任務，直到有人恢復。",
        approve: "核准：暫停這位員工",
        reject: "駁回：繼續工作",
      };
    }
    default:
      return null;
  }
}

export interface OfficialReportCheck {
  url: string;
  person: string;
  receivedOn: string;
  pages: number;
  rows: number;
  unreadable: number;
  stockRows: number;
  /** "p.2 #66 NVDA sale 2026-02-05 $250,001 - $500,000": each with its page, to find it. */
  stocks: string[];
}

function officialReport(kind: string, payload: Record<string, unknown>): OfficialReportCheck | null {
  if (kind !== "official_report" || typeof payload.report !== "string") return null;
  const n = (v: unknown) => (typeof v === "number" ? v : 0);
  return {
    url: payload.report,
    person: String(payload.person ?? ""),
    receivedOn: String(payload.received_on ?? ""),
    pages: n(payload.pages),
    rows: n(payload.rows),
    unreadable: n(payload.unreadable),
    stockRows: n(payload.stock_rows),
    stocks: Array.isArray(payload.stocks) ? payload.stocks.map(String) : [],
  };
}

function actorName(actor: Record<string, unknown> | null, agents: Record<string, AgentState>): string {
  if (!actor) return "—";
  const id = String(actor.id ?? "");
  if (actor.kind === "agent") return personName(agents[id]?.display_name) || `代理 ${id.slice(0, 8)}`;
  return `${ACTOR_KIND[String(actor.kind)] ?? String(actor.kind)} ${id}`.trim();
}

/** The article requests were once titled 「核准發布：…」, which read as if it had been; they are
 * requests (D-141), and the older rows are shown with the new word. */
export function approvalCard(
  approval: Approval,
  agents: Record<string, AgentState>,
  now: Date,
  projects: Record<string, string> = {},
): ApprovalCard {
  const payload = approval.payload as Record<string, unknown>;
  const expiresMs = approval.expires_at ? Date.parse(approval.expires_at) - now.getTime() : null;
  return {
    id: approval.id,
    state: approval.state,
    kind: KIND_LABEL[approval.kind] ?? approval.kind,
    action: approval.action,
    summary: approval.summary.replace(/^核准發布：/, "申請發布："),
    requester: actorName(approval.requested_by, agents),
    details: payload.args ?? payload,
    waiting: formatDuration(Math.max(0, now.getTime() - Date.parse(approval.created_at))),
    expires: approval.expires_at
      ? {
          at: approval.expires_at,
          in: expiresMs !== null && expiresMs > 0 ? formatDuration(expiresMs) : null,
          soon: expiresMs !== null && expiresMs < 60 * 60 * 1000,
          then: approval.action === "approve_article" && !payload.delegated && !payload.delegated_before ? "ceo" : "expire",
        }
      : null,
    withCeo: approval.state === "PENDING" && Boolean(payload.delegated),
    taskId: approval.task_id,
    runId: approval.run_id,
    canSendBack: Boolean(approval.task_id) && !approval.run_id,
    article:
      typeof payload.article_id === "string"
        ? {
            id: payload.article_id,
            draftGroupId: typeof payload.draft_group_id === "string" ? payload.draft_group_id : null,
          }
        : null,
    officialReport: officialReport(approval.kind, payload),
    command: commandChoice(payload, projects, agents),
    decision: approval.decided_at
      ? { by: actorName(approval.decided_by, agents), at: approval.decided_at, reason: approval.reason }
      : null,
  };
}
