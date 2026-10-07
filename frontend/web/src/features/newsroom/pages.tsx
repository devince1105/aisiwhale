"use client";

// The newsroom pages' data (T-517): each page loads through the typed client and stays fresh
// through the company's event stream (src/api/invalidation.ts); the views render.
import { parseEvent, type EventEnvelope } from "@autora/event-schema";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import {
  addSource,
  articleQuery,
  articlesPageQuery,
  type ArticleSort,
  republishArticle,
  setArticleAccess,
  setArticleSection,
  reviseArticle,
  sourcesQuery,
  startStory,
  storiesQuery,
  storyQuery,
  unpublishArticle,
  workflowEventsQuery,
  type Section,
  type SourceSort,
  type StorySort,
  type StoryState,
} from "@/api/queries";
import { AdminPage, PageHeader } from "@/features/admin-ui/PageHeader";
import { ListToolbar, Pager, sortControl, type FilterDef } from "@/features/admin-ui/DataTable";
import { ErrorState } from "@/features/admin-ui/states";
import { useListState } from "@/features/admin-ui/useListState";
import { CompanyScope, type Company } from "@/features/company/CompanyScope";
import { useCompanyStream } from "@/features/company/useCompanyStream";

import { ArticlesView } from "./ArticlesView";
import { ArticleView } from "./ArticleView";
import type { ArticleDetail, StoryDetail } from "./model";
import { Empty } from "./parts";
import { AddSourceForm, SourcesView } from "./SourcesView";
import { label, STORY_STATE } from "./model";
import { STORY_STATES, StoriesView } from "./StoriesView";
import { StoryView } from "./StoryView";
import { CoverPanel, coverWatch } from "./CoverPanel";

function Loading({ error }: { error: Error | null }) {
  return (
    <AdminPage width="read">{error ? <ErrorState>{error.message}</ErrorState> : <Empty>載入中…</Empty>}</AdminPage>
  );
}

/** The timeline of a workflow run (the latest one, when there are several). Events this page
 * cannot read (a newer type) are left out, as the realtime store does. */
function useTimeline(companyId: string, runIds: readonly string[]): EventEnvelope[] {
  const runId = runIds.at(-1);
  const events = useQuery({
    ...workflowEventsQuery(companyId, runId ?? "none"),
    enabled: Boolean(runId),
  });
  if (!runId) return [];
  return (events.data?.items ?? []).flatMap((raw) => {
    const parsed = parseEvent(raw);
    return parsed.ok ? [parsed.event] : [];
  });
}

// --- lists ------------------------------------------------------------------------------------

export function StoriesPage() {
  return <CompanyScope>{(company) => <CompanyStories company={company} />}</CompanyScope>;
}

const STORY_SORTS: readonly StorySort[] = ["-last_item_at", "last_item_at", "-score", "-first_seen_at", "title"];
const STORY_FILTER: FilterDef<"state"> = {
  key: "state",
  label: "狀態",
  options: STORY_STATES.map((state) => ({ value: state, label: label(STORY_STATE, state)[0] })),
};

function CompanyStories({ company }: { company: Company }) {
  useCompanyStream(company.id);
  const list = useListState(["state"], STORY_SORTS);
  const state = (STORY_STATES as readonly string[]).includes(list.filters.state ?? "") ? (list.filters.state as StoryState) : null;
  const page = useQuery(storiesQuery(company.id, state, { q: list.q, sort: list.sort, cursor: list.cursor }));
  return (
    <AdminPage>
      <PageHeader title={`${company.name} 的題材`} />
      <ListToolbar list={list} filters={[STORY_FILTER]} placeholder="搜尋題材標題…" views="stories" />
      <StoriesView stories={page.data?.items} sort={sortControl(list, STORY_SORTS, "-last_item_at")} error={page.error?.message} />
      <Pager list={list} shown={page.data?.items.length ?? 0} total={page.data?.total ?? null} nextCursor={page.data?.next_cursor} />
    </AdminPage>
  );
}

export function ArticlesPage() {
  return <CompanyScope>{(company) => <CompanyArticles company={company} />}</CompanyScope>;
}

const ARTICLE_SORTS: readonly ArticleSort[] = ["-updated_at", "updated_at", "-created_at", "title"];

function CompanyArticles({ company }: { company: Company }) {
  useCompanyStream(company.id);
  const list = useListState([], ARTICLE_SORTS);
  const page = useQuery(articlesPageQuery(company.id, { q: list.q, sort: list.sort, cursor: list.cursor }));
  return (
    <AdminPage>
      <PageHeader title={`${company.name} 的文章`} />
      <ListToolbar list={list} placeholder="搜尋標題或網址代稱…" views="articles" />
      <ArticlesView articles={page.data?.items} sort={sortControl(list, ARTICLE_SORTS, "-updated_at")} error={page.error?.message} />
      <Pager list={list} shown={page.data?.items.length ?? 0} total={page.data?.total ?? null} nextCursor={page.data?.next_cursor} />
    </AdminPage>
  );
}

export function SourcesPage() {
  return <CompanyScope>{(company) => <CompanySources company={company} />}</CompanyScope>;
}

const SOURCE_SORTS: readonly SourceSort[] = ["created_at", "-created_at", "name"];

function CompanySources({ company }: { company: Company }) {
  useCompanyStream(company.id);
  const list = useListState([], SOURCE_SORTS);
  const page = useQuery(sourcesQuery(company.id, { q: list.q, sort: list.sort, cursor: list.cursor }));
  const queryClient = useQueryClient();
  return (
    <AdminPage>
      <PageHeader title={`${company.name} 的來源`} />
      <ListToolbar list={list} placeholder="搜尋名稱或網址…" />
      <SourcesView sources={page.data?.items} sort={sortControl(list, SOURCE_SORTS, "created_at")} error={page.error?.message} />
      <Pager list={list} shown={page.data?.items.length ?? 0} total={page.data?.total ?? null} nextCursor={page.data?.next_cursor} />
      <h2 id="add-source" className="mt-8 mb-3 text-lg font-semibold">
        新增來源
      </h2>
      <AddSourceForm
        onAdd={async (body) => {
          await addSource(company.id, body);
          await queryClient.invalidateQueries({ queryKey: ["newsroom", "sources", company.id] });
        }}
      />
    </AdminPage>
  );
}

// --- details ----------------------------------------------------------------------------------

export function StoryPage({ storyId }: { storyId: string }) {
  const story = useQuery(storyQuery(storyId));
  if (!story.data) return <Loading error={story.error} />;
  return <LoadedStory story={story.data} />;
}

function LoadedStory({ story }: { story: StoryDetail }) {
  useCompanyStream(story.company_id);
  const events = useTimeline(story.company_id, story.workflow_run_ids);
  const queryClient = useQueryClient();
  const start = useMutation({
    mutationFn: () => startStory(story.id),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["newsroom"] }),
  });
  return (
    <StoryView
      story={story}
      events={events}
      onStart={() => start.mutate()}
      starting={start.isPending}
      startError={start.error?.message ?? null}
    />
  );
}

export function ArticlePage({ articleId }: { articleId: string }) {
  const requested = Number(useSearchParams().get("version")) || null;
  const article = useQuery({ ...articleQuery(articleId, requested), ...coverWatch });
  if (!article.data) return <Loading error={article.error} />;
  return <LoadedArticle article={article.data} />;
}

function LoadedArticle({ article }: { article: ArticleDetail }) {
  useCompanyStream(article.company_id);
  const [lang, setLang] = useState(article.primary_lang);
  const events = useTimeline(article.company_id, article.workflow_run_ids);
  const queryClient = useQueryClient();
  const onSettled = () => queryClient.invalidateQueries({ queryKey: ["newsroom"] });
  const unpublish = useMutation({ mutationFn: (reason: string) => unpublishArticle(article.id, reason), onSettled });
  const republish = useMutation({ mutationFn: () => republishArticle(article.id), onSettled });
  const revise = useMutation({ mutationFn: (reason: string) => reviseArticle(article.id, reason), onSettled });
  const access = useMutation({ mutationFn: (to: "free" | "members") => setArticleAccess(article.id, to), onSettled });
  const section = useMutation({ mutationFn: (to: Section | null) => setArticleSection(article.id, to), onSettled });
  return (
    <ArticleView
      article={article}
      lang={lang}
      onLang={setLang}
      events={events}
      onSite={{
        unpublish: (reason) => unpublish.mutate(reason),
        republish: () => republish.mutate(),
        revise: (reason) => revise.mutate(reason),
        setAccess: (to) => access.mutate(to),
        setSection: (to) => section.mutate(to),
        busy: unpublish.isPending || republish.isPending || revise.isPending || access.isPending || section.isPending,
        error: (unpublish.error ?? republish.error ?? revise.error ?? access.error ?? section.error)?.message ?? null,
      }}
      cover={<CoverPanel articleId={article.id} cover={article.cover} asked={article.cover_asked} />}
    />
  );
}
