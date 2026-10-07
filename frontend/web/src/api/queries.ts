// Server state (T-308, 3d-office/05 §5): TanStack Query options for what the realtime store does
// not hold (run details, traces, task history, approvals...). Each factory returns plain query
// options, so pages use them with useQuery / useSuspenseQuery and tests call queryFn directly.
// Freshness comes from events: src/api/invalidation.ts invalidates the matching keys.
import { infiniteQueryOptions, QueryClient, queryOptions, type InfiniteData } from "@tanstack/react-query";

import { api as defaultApi, unwrap, type ApiClient, type Schemas } from "./client";
import type { operations } from "./schema.gen";

/** One of the site's sections (D-047), as the API spells them. */
export type Section = NonNullable<Schemas["ArticleSectionBody"]["section"]>;

export const queryKeys = {
  companies: () => ["companies"] as const,
  agents: (companyId: string) => ["agents", companyId] as const,
  run: (runId: string) => ["run", runId] as const,
  trace: (runId: string) => ["trace", runId] as const,
  task: (taskId: string) => ["task", taskId] as const,
  approvals: (companyId: string, state = "PENDING") => ["approvals", companyId, state] as const,
  kpis: (companyId: string) => ["kpis", companyId] as const,
  /** Newsroom pages (T-517): every key starts with "newsroom", so one invalidation covers them. */
  stories: (companyId: string, state: string | null) => ["newsroom", "stories", companyId, state] as const,
  story: (storyId: string) => ["newsroom", "story", storyId] as const,
  articles: (companyId: string) => ["newsroom", "articles", companyId] as const,
  article: (articleId: string, version: number | null) => ["newsroom", "article", articleId, version] as const,
  sources: (companyId: string) => ["newsroom", "sources", companyId] as const,
  workflowEvents: (companyId: string, runId: string) => ["newsroom", "events", companyId, runId] as const,
  roles: () => ["roles"] as const,
  /** The company's days (T-608). */
  org: (companyId: string) => ["org", companyId] as const,
  officeTheme: (companyId: string) => ["officeTheme", companyId] as const,
  officeHours: () => ["officeHours"] as const,
  failedWorkflows: (companyId: string) => ["workflows", "failed", companyId] as const,
  cycles: (companyId: string) => ["cycles", companyId] as const,
  cycle: (cycleId: string) => ["cycle", cycleId] as const,
  /** Budgets and capital (D-054). */
  finance: (companyId: string) => ["finance", companyId] as const,
  /** Projects, with who paused them and why (D-056). */
  projects: (companyId: string) => ["projects", companyId] as const,
  /** VIP given by an admin for internal testing (D-228): by company slug, all or running only. */
  comps: (companySlug: string, running: boolean) => ["memberships", "comps", companySlug, running] as const,
  /** A reader's Whale Coins in the back office (P3-C-2), and the ledger's check. */
  coinWallet: (companySlug: string, email: string, cursor: string | null) => ["coins", "wallet", companySlug, email, cursor] as const,
  coinReconcile: () => ["coins", "reconcile"] as const,
  /** The office's team group (D-109). */
  team: (companyId: string) => ["team", companyId] as const,
};

// --- lists, a page at a time (AD-04) ---------------------------------------------------------

/** What every back-office list returns: ?cursor=&limit=&q=&sort= → a page. */
export interface Page<T> {
  items: T[];
  next_cursor?: string | null;
  total: number;
}

export const PAGE_SIZE = 50;

/** The rows of every page loaded so far; undefined while the first is loading. */
export function itemsOf<T>(data: InfiniteData<Page<T>> | undefined): T[] | undefined {
  return data?.pages.flatMap((page) => page.items);
}

/** How many rows the list has in all (the filters', not the pages loaded). */
export function totalOf<T>(data: InfiniteData<Page<T>> | undefined): number | null {
  return data?.pages[0]?.total ?? null;
}

const paged = {
  initialPageParam: null as string | null,
  getNextPageParam: <T,>(last: Page<T>) => last.next_cursor ?? null,
};

type QueryOf<K extends keyof operations> = NonNullable<operations[K]["parameters"]["query"]>;
export type ApprovalSort = NonNullable<QueryOf<"list_approvals_api_approvals_get">["sort"]>;
export type StorySort = NonNullable<QueryOf<"list_stories_api_companies__company_id__stories_get">["sort"]>;
export type ArticleSort = NonNullable<QueryOf<"list_articles_api_companies__company_id__articles_get">["sort"]>;
export type SourceSort = NonNullable<QueryOf<"list_sources_api_companies__company_id__sources_get">["sort"]>;
export type CompSort = NonNullable<QueryOf<"list_comps_api_admin_memberships_comps_get">["sort"]>;
export type AuditSort = NonNullable<QueryOf<"list_admin_actions_api_admin_audit_get">["sort"]>;

/** One page of a table (AD-05): what the address says — the words, the order, the page. */
export interface ListArgs<S extends string> {
  q?: string | null;
  sort?: S | null;
  cursor?: string | null;
  limit?: number;
}

function listQuery<S extends string>(args: ListArgs<S>) {
  return {
    limit: args.limit ?? PAGE_SIZE,
    ...(args.cursor ? { cursor: args.cursor } : {}),
    ...(args.q ? { q: args.q } : {}),
    ...(args.sort ? { sort: args.sort } : {}),
  };
}

/** The query a list sends for one page: the cursor only after the first, ``q`` only when set. */
function pageQuery(cursor: string | null, q?: string | null, limit = PAGE_SIZE) {
  return { limit, ...(cursor ? { cursor } : {}), ...(q ? { q } : {}) };
}

export function companiesQuery(api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.companies(),
    queryFn: async () => unwrap(await api.GET("/api/companies")),
  });
}

export function agentsQuery(companyId: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.agents(companyId),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/companies/{company_id}/agents", {
          params: { path: { company_id: companyId } },
        }),
      ),
  });
}

export function runQuery(runId: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.run(runId),
    queryFn: async () =>
      unwrap(await api.GET("/api/runs/{run_id}", { params: { path: { run_id: runId } } })),
  });
}

export function traceQuery(runId: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.trace(runId),
    queryFn: async () =>
      unwrap(await api.GET("/api/runs/{run_id}/trace", { params: { path: { run_id: runId } } })),
  });
}

export function taskQuery(taskId: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.task(taskId),
    queryFn: async () =>
      unwrap(await api.GET("/api/tasks/{task_id}", { params: { path: { task_id: taskId } } })),
  });
}

export type ApprovalState = "PENDING" | "APPROVED" | "REJECTED" | "RETURNED" | "EXPIRED";

/** The inbox, a page at a time (AD-04), oldest first. */
export function approvalsQuery(
  companyId: string,
  state: ApprovalState = "PENDING",
  args: Pick<ListArgs<ApprovalSort>, "q" | "sort"> = {},
  api: ApiClient = defaultApi,
) {
  return infiniteQueryOptions({
    queryKey: [...queryKeys.approvals(companyId, state), "list", args] as const,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET("/api/approvals", {
          params: {
            query: { company_id: companyId, state, ...pageQuery(pageParam, args.q), ...(args.sort ? { sort: args.sort } : {}) },
          },
        }),
      ),
    ...paged,
  });
}

/** How many wait for a decision: the inbox's total, asked with one row. */
export function pendingCountQuery(companyId: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: [...queryKeys.approvals(companyId, "PENDING"), "count"] as const,
    queryFn: async () =>
      unwrap(await api.GET("/api/approvals", { params: { query: { company_id: companyId, limit: 1 } } })).total,
  });
}

/**
 * KPIs are aggregates the event stream cannot rebuild (model costs are not events), so they are
 * server state: refetched when an event says they changed, and every minute while shown.
 */
/** The org chart (T-600): who the company's departments are, and what they are called. */
export function orgQuery(companyId: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.org(companyId),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/companies/{company_id}/org", {
          params: { path: { company_id: companyId } },
        }),
      ),
    staleTime: 5 * 60_000, // an org chart changes when somebody is hired, not every minute
  });
}

export function cyclesQuery(companyId: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.cycles(companyId),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/companies/{company_id}/cycles", {
          params: { path: { company_id: companyId } },
        }),
      ),
    refetchInterval: 60_000,
  });
}

export function cycleQuery(cycleId: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.cycle(cycleId),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/cycles/{cycle_id}", {
          params: { path: { cycle_id: cycleId } },
        }),
      ),
  });
}

export function kpisQuery(companyId: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.kpis(companyId),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/companies/{company_id}/kpis", {
          params: { path: { company_id: companyId } },
        }),
      ),
    refetchInterval: 60_000,
  });
}

// --- newsroom (T-517) -------------------------------------------------------------------------

export type StoryState = "DISCOVERED" | "SELECTED" | "IN_PRODUCTION" | "PUBLISHED" | "DROPPED" | "IGNORED";

/** One page of stories (AD-05), as the table's address asks. */
export function storiesQuery(
  companyId: string,
  state: StoryState | null = null,
  args: ListArgs<StorySort> = {},
  api: ApiClient = defaultApi,
) {
  return queryOptions({
    queryKey: [...queryKeys.stories(companyId, state), args] as const,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/companies/{company_id}/stories", {
          params: { path: { company_id: companyId }, query: { ...(state ? { state } : {}), ...listQuery(args) } },
        }),
      ),
  });
}

export function storyQuery(storyId: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.story(storyId),
    queryFn: async () =>
      unwrap(await api.GET("/api/stories/{story_id}", { params: { path: { story_id: storyId } } })),
  });
}

/** One page of articles (AD-05), as the table's address asks. */
export type ArticleState = NonNullable<QueryOf<"list_articles_api_companies__company_id__articles_get">["state"]>;

export function articlesPageQuery(
  companyId: string,
  args: ListArgs<ArticleSort> & { state?: ArticleState | null } = {},
  api: ApiClient = defaultApi,
) {
  return queryOptions({
    queryKey: [...queryKeys.articles(companyId), "page", args] as const,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/companies/{company_id}/articles", {
          params: { path: { company_id: companyId }, query: { ...listQuery(args), ...(args.state ? { state: args.state } : {}) } },
        }),
      ),
  });
}

/** Articles a page at a time, newest change first: the team chat's titles. */
export function articlesQuery(companyId: string, q: string | null = null, api: ApiClient = defaultApi) {
  return infiniteQueryOptions({
    queryKey: [...queryKeys.articles(companyId), q] as const,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET("/api/companies/{company_id}/articles", {
          params: { path: { company_id: companyId }, query: pageQuery(pageParam, q) },
        }),
      ),
    ...paged,
  });
}

export function articleQuery(articleId: string, version: number | null = null, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.article(articleId, version),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/articles/{article_id}", {
          params: { path: { article_id: articleId }, query: version ? { version } : {} },
        }),
      ),
  });
}

/** One page of sources (AD-05), as the table's address asks. */
export function sourcesQuery(companyId: string, args: ListArgs<SourceSort> = {}, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: [...queryKeys.sources(companyId), args] as const,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/companies/{company_id}/sources", {
          params: { path: { company_id: companyId }, query: listQuery(args) },
        }),
      ),
  });
}

/** The command palette's search (AD-03 on AD-04): a few articles and stories whose titles
 * have every word typed. */
export function adminSearchQuery(companyId: string, q: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: ["newsroom", "search", companyId, q] as const,
    queryFn: async () => {
      const query = pageQuery(null, q, 5);
      const [articles, stories] = await Promise.all([
        api.GET("/api/companies/{company_id}/articles", { params: { path: { company_id: companyId }, query } }).then(unwrap),
        api.GET("/api/companies/{company_id}/stories", { params: { path: { company_id: companyId }, query } }).then(unwrap),
      ]);
      return { articles: articles.items, stories: stories.items };
    },
    staleTime: 30_000,
  });
}

/** One workflow run's events (its timeline): they carry the run's id as correlation. */
export function workflowEventsQuery(companyId: string, runId: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.workflowEvents(companyId, runId),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/events", {
          params: { query: { company_id: companyId, correlation_id: runId, limit: 500 } },
        }),
      ),
  });
}

// --- commands (REST only; the WebSocket carries no commands, 05 §2) --------------------------

export async function decideApproval(
  approvalId: string,
  decision: "approve" | "reject" | "revise",
  reason: string | null = null,
  api: ApiClient = defaultApi,
) {
  return unwrap(
    await api.POST("/api/approvals/{approval_id}/decide", {
      params: { path: { approval_id: approvalId } },
      body: { decision, reason },
    }),
  );
}

/** Take a published article off the site (D-044). The reason is kept with its history. */
export async function unpublishArticle(articleId: string, reason: string, api: ApiClient = defaultApi) {
  return unwrap(
    await api.POST("/api/articles/{article_id}/unpublish", {
      params: { path: { article_id: articleId } },
      body: { reason },
    }),
  );
}

/** Show the next photo from marketing's search as the article's cover (D-142). */
export async function swapCover(articleId: string, api: ApiClient = defaultApi) {
  return unwrap(await api.POST("/api/articles/{article_id}/cover/swap", { params: { path: { article_id: articleId } } }));
}

/** Look for the cover in a person's own words (D-233): the first photo found is the cover, and
 * swapping goes through the rest of that search. */
export async function searchCover(articleId: string, query: string, api: ApiClient = defaultApi) {
  return unwrap(
    await api.POST("/api/articles/{article_id}/cover/search", {
      params: { path: { article_id: articleId } },
      body: { query },
    }),
  );
}

/** 請行銷換圖 (D-233): marketing finds another cover with the person's words; the article is
 * not sent back. */
export async function askCover(articleId: string, ask: string, api: ApiClient = defaultApi) {
  return unwrap(
    await api.POST("/api/articles/{article_id}/cover/ask", {
      params: { path: { article_id: articleId } },
      body: { ask },
    }),
  );
}

/** Take the article's cover off (D-142); swapping puts one back. */
export async function removeCover(articleId: string, api: ApiClient = defaultApi) {
  return unwrap(await api.DELETE("/api/articles/{article_id}/cover", { params: { path: { article_id: articleId } } }));
}

/** Change a published article (D-045): the site keeps the published version until the new one. */
export async function reviseArticle(articleId: string, reason: string, api: ApiClient = defaultApi) {
  return unwrap(
    await api.POST("/api/articles/{article_id}/revise", {
      params: { path: { article_id: articleId } },
      body: { reason },
    }),
  );
}

/** Make an article VIP (members read all of it) or free again (D-025, D-159). */
export async function setArticleAccess(articleId: string, access: "free" | "members", api: ApiClient = defaultApi) {
  return unwrap(
    await api.POST("/api/articles/{article_id}/access", {
      params: { path: { article_id: articleId } },
      body: { access },
    }),
  );
}

/** Put an article in a section of the site, or back to what its sources say (null) (D-208). */
export async function setArticleSection(articleId: string, section: Section | null, api: ApiClient = defaultApi) {
  return unwrap(
    await api.POST("/api/articles/{article_id}/section", {
      params: { path: { article_id: articleId } },
      body: { section },
    }),
  );
}

/** Put an article that was taken down back on the site (D-044). */
export async function republishArticle(articleId: string, api: ApiClient = defaultApi) {
  return unwrap(
    await api.POST("/api/articles/{article_id}/republish", { params: { path: { article_id: articleId } } }),
  );
}

/** Runs that ended badly and could be started again (AC-9). */
export function failedWorkflowsQuery(companyId: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.failedWorkflows(companyId),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/companies/{company_id}/workflows/failed", {
          params: { path: { company_id: companyId } },
        }),
      ),
    refetchInterval: 30_000,
  });
}

/** Start a failed run again. The company may still refuse: read the decision in the result. */
export async function restartWorkflow(
  companyId: string,
  workflowRunId: string,
  api: ApiClient = defaultApi,
) {
  return unwrap(
    await api.POST("/api/companies/{company_id}/workflows/{workflow_run_id}/restart", {
      params: { path: { company_id: companyId, workflow_run_id: workflowRunId } },
    }),
  );
}

export async function startWorkflow(
  companyId: string,
  body: { template: string; project_id: string; params?: Record<string, unknown> },
  api: ApiClient = defaultApi,
) {
  return unwrap(
    await api.POST("/api/companies/{company_id}/workflows", {
      params: { path: { company_id: companyId } },
      body: { ...body, params: body.params ?? {} },
    }),
  );
}

export function rolesQuery(api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.roles(),
    queryFn: async () => unwrap(await api.GET("/api/roles")),
    staleTime: Infinity, // the runtime's roles change with a deploy, not with the data
  });
}

export type NewAgent = Schemas["NewAgent"];

/** Hire an agent (T-517 follow-up): it appears in the office and takes its role's tasks. */
export async function hireAgent(companyId: string, body: NewAgent, api: ApiClient = defaultApi) {
  return unwrap(
    await api.POST("/api/companies/{company_id}/agents", {
      params: { path: { company_id: companyId } },
      body,
    }),
  );
}

export type AgentAction = "pause" | "resume" | "retire";

/** Stop an agent taking work, put it back, or let it go (T-517 follow-up). */
export async function decideAgent(
  companyId: string,
  agentId: string,
  action: AgentAction,
  reason: string | null = null,
  api: ApiClient = defaultApi,
) {
  const paths = {
    pause: "/api/companies/{company_id}/agents/{agent_id}/pause",
    resume: "/api/companies/{company_id}/agents/{agent_id}/resume",
    retire: "/api/companies/{company_id}/agents/{agent_id}/retire",
  } as const;
  return unwrap(
    await api.POST(paths[action], {
      params: { path: { company_id: companyId, agent_id: agentId } },
      body: { reason },
    }),
  );
}

export async function startStory(storyId: string, projectId: string | null = null, api: ApiClient = defaultApi) {
  return unwrap(
    await api.POST("/api/stories/{story_id}/start", {
      params: { path: { story_id: storyId } },
      body: { project_id: projectId },
    }),
  );
}

/** 團隊群組 (D-109): the group's latest messages before ``before`` (a seq), oldest first. */
export async function fetchTeamFeed(companyId: string, before: number | null = null, api: ApiClient = defaultApi) {
  return unwrap(
    await api.GET("/api/companies/{company_id}/team/feed", {
      params: { path: { company_id: companyId }, query: before ? { before } : {} },
    }),
  );
}

export function teamFeedQuery(companyId: string, api: ApiClient = defaultApi) {
  return queryOptions({ queryKey: queryKeys.team(companyId), queryFn: () => fetchTeamFeed(companyId, null, api) });
}

/** A note to the group, or a brief: a story for the newsroom, started at once (D-109). */
export async function postTeamMessage(
  companyId: string,
  text: string,
  kind: "note" | "brief" = "note",
  section: Section | null = null,
  api: ApiClient = defaultApi,
) {
  return unwrap(
    await api.POST("/api/companies/{company_id}/team/messages", {
      params: { path: { company_id: companyId } },
      // a brief's section on the site (D-208): a story from a sentence has no sources to say it
      body: { text, kind, ...(kind === "brief" && section ? { section } : {}) },
    }),
  );
}

export type NewSource = Schemas["NewSource"];

export async function addSource(companyId: string, body: NewSource, api: ApiClient = defaultApi) {
  return unwrap(
    await api.POST("/api/companies/{company_id}/sources", {
      params: { path: { company_id: companyId } },
      body,
    }),
  );
}

/** Defaults: data is kept until an event invalidates it; errors are not retried in a loop. */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 60_000, retry: 1, refetchOnWindowFocus: false },
      mutations: { retry: 0 },
    },
  });
}

export type Finance = Schemas["FinanceOut"];
export type BudgetInput = Schemas["BudgetIn"];

/** The company's balance and budget envelopes (D-054): operator-only on the API. */
export function financeQuery(companyId: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.finance(companyId),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/companies/{company_id}/finance", {
          params: { path: { company_id: companyId } },
        }),
      ),
    refetchInterval: 60_000,
  });
}

/** Set one envelope, as the AllocateBudget command; raising it re-queues the work it blocked. */
export async function setBudget(companyId: string, body: BudgetInput, api: ApiClient = defaultApi) {
  return unwrap(
    await api.POST("/api/companies/{company_id}/finance/budgets", {
      params: { path: { company_id: companyId } },
      body,
    }),
  );
}

/** Money put into the company; ``requestId`` makes a double submit one row. */
export async function addCapital(
  companyId: string,
  amount: string,
  memo: string | null,
  requestId: string,
  api: ApiClient = defaultApi,
) {
  return unwrap(
    await api.POST("/api/companies/{company_id}/finance/capital", {
      params: { path: { company_id: companyId } },
      body: { amount, memo, request_id: requestId },
    }),
  );
}

export type ProjectLine = Schemas["ProjectOut"];

export function projectsQuery(companyId: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.projects(companyId),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/companies/{company_id}/projects", {
          params: { path: { company_id: companyId } },
        }),
      ),
    refetchInterval: 60_000,
  });
}

/** Pause or resume a project, as the PauseProject / ResumeProject command (D-056). */
/** When the AI staff work (D-193), and whether a person just called them in (D-205): read from
 * the settings and the API's memory — no database — so asked every minute. */
export function officeHoursQuery(api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.officeHours(),
    queryFn: async () => unwrap(await api.GET("/api/office-hours")),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

/** The office's style (D-178): the company's, the same in every browser and on the site. */
export function officeThemeQuery(companyId: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.officeTheme(companyId),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/companies/{company_id}/office-theme", {
          params: { path: { company_id: companyId } },
        }),
      ).theme,
    staleTime: 5 * 60_000,
  });
}

export async function setOfficeTheme(companyId: string, theme: Schemas["OfficeThemeBody"]["theme"], api: ApiClient = defaultApi) {
  return unwrap(
    await api.PUT("/api/companies/{company_id}/office-theme", {
      params: { path: { company_id: companyId } },
      body: { theme },
    }),
  ).theme;
}

export async function decideProject(
  companyId: string,
  projectId: string,
  action: "pause" | "resume",
  reason: string | null = null,
  api: ApiClient = defaultApi,
) {
  const paths = {
    pause: "/api/companies/{company_id}/projects/{project_id}/pause",
    resume: "/api/companies/{company_id}/projects/{project_id}/resume",
  } as const;
  return unwrap(
    await api.POST(paths[action], {
      params: { path: { company_id: companyId, project_id: projectId } },
      body: { reason },
    }),
  );
}

export type Comp = Schemas["Comp"];
export type GrantCompInput = Schemas["GrantComp"];

/** VIP given by an admin (D-228, P2): newest first; ``running`` keeps only those giving access now. */
export function compsQuery(
  companySlug: string,
  running = false,
  args: ListArgs<CompSort> = {},
  api: ApiClient = defaultApi,
) {
  return queryOptions({
    queryKey: [...queryKeys.comps(companySlug, running), args] as const,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/admin/memberships/comps", {
          params: { query: { company: companySlug, running, ...listQuery(args) } },
        }),
      ),
  });
}

export type AdminAction = Schemas["AdminActionOut"];

/** Who did what in the back office (AD-06): a page of it, newest first. ``companyId`` null:
 * every company's, and what belongs to none. */
export function auditQuery(
  companyId: string | null,
  filters: { failed?: boolean | null; target_type?: string | null },
  args: ListArgs<AuditSort> = {},
  api: ApiClient = defaultApi,
) {
  return queryOptions({
    queryKey: ["audit", companyId, filters, args] as const,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/admin/audit", {
          params: {
            query: {
              ...(companyId ? { company_id: companyId } : {}),
              ...(filters.failed != null ? { failed: filters.failed } : {}),
              ...(filters.target_type ? { target_type: filters.target_type } : {}),
              ...listQuery(args),
            },
          },
        }),
      ),
  });
}

export type ActivityEntry = Schemas["ActivityEntry"];

/** One article's, story's or approval's history (AD-07). Under "newsroom" for the newsroom's,
 * so the events that change them refresh it too. */
export function activityQuery(targetType: "article" | "story" | "approval", targetId: string, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: [targetType === "approval" ? "approvals" : "newsroom", "activity", targetType, targetId] as const,
    queryFn: async () =>
      unwrap(await api.GET("/api/admin/activity", { params: { query: { target_type: targetType, target_id: targetId } } })),
  });
}

/** Give a reader VIP until a date, with a reason. No order, payment or revenue (D-228). */
export async function grantComp(body: GrantCompInput, api: ApiClient = defaultApi) {
  return unwrap(await api.POST("/api/admin/memberships/comps", { body }));
}

/** End a comp now. The row keeps who, when and why; access falls back to whatever else runs. */
export async function revokeComp(grantId: string, reason: string, api: ApiClient = defaultApi) {
  return unwrap(
    await api.POST("/api/admin/memberships/comps/{grant_id}/revoke", {
      params: { path: { grant_id: grantId } },
      body: { reason },
    }),
  );
}

export type AdminCoinWallet = Schemas["AdminWallet"];
export type AdminCoinMovement = Schemas["AdminMovement"];
export type CoinAdjustment = Schemas["Adjustment"];
export type CoinReconciliation = Schemas["Reconciliation"];

/** A reader's wallet, found by address: tier, cap, balance and every movement, newest first. */
export function coinWalletQuery(companySlug: string, email: string, cursor: string | null = null, api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.coinWallet(companySlug, email, cursor),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/admin/coins/wallet", {
          params: { query: { email, company: companySlug, ...(cursor ? { cursor } : {}) } },
        }),
      ),
    enabled: email.length > 0,
  });
}

/** Coins up or down for a reader, with a reason; past the tier's cap only with ``override_cap``.
 * ``request_id`` is made once per form and kept on a retry, so a double submit is one. */
export async function adjustCoins(body: CoinAdjustment, api: ApiClient = defaultApi) {
  return unwrap(await api.POST("/api/admin/coins/adjustments", { body }));
}

/** The whole ledger checked against itself, now. Reads only. */
export function coinReconcileQuery(api: ApiClient = defaultApi) {
  return queryOptions({
    queryKey: queryKeys.coinReconcile(),
    queryFn: async () => unwrap(await api.GET("/api/admin/coins/reconcile")),
  });
}
