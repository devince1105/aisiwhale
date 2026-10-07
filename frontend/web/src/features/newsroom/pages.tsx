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
  articlesQuery,
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
  type StoryState,
} from "@/api/queries";
import { AdminPage, PageHeader } from "@/features/admin-ui/PageHeader";
import { ErrorState } from "@/features/admin-ui/states";
import { CompanyScope, type Company } from "@/features/company/CompanyScope";
import { useCompanyStream } from "@/features/company/useCompanyStream";

import { ArticlesView } from "./ArticlesView";
import { ArticleView } from "./ArticleView";
import type { ArticleDetail, StoryDetail } from "./model";
import { Empty } from "./parts";
import { AddSourceForm, SourcesView } from "./SourcesView";
import { StoriesView, type StoryFilter } from "./StoriesView";
import { StoryView } from "./StoryView";
import { CoverPanel } from "./CoverPanel";

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

function CompanyStories({ company }: { company: Company }) {
  useCompanyStream(company.id);
  const [filter, setFilter] = useState<StoryFilter>("ALL");
  const stories = useQuery(storiesQuery(company.id, filter === "ALL" ? null : (filter as StoryState)));
  return (
    <AdminPage>
      <PageHeader title={`${company.name} 的題材`} />
      {stories.error ? <ErrorState>{stories.error.message}</ErrorState> : null}
      <StoriesView stories={stories.data} filter={filter} onFilter={setFilter} />
    </AdminPage>
  );
}

export function ArticlesPage() {
  return <CompanyScope>{(company) => <CompanyArticles company={company} />}</CompanyScope>;
}

function CompanyArticles({ company }: { company: Company }) {
  useCompanyStream(company.id);
  const articles = useQuery(articlesQuery(company.id));
  return (
    <AdminPage>
      <PageHeader title={`${company.name} 的文章`} />
      {articles.error ? <ErrorState>{articles.error.message}</ErrorState> : null}
      <ArticlesView articles={articles.data} />
    </AdminPage>
  );
}

export function SourcesPage() {
  return <CompanyScope>{(company) => <CompanySources company={company} />}</CompanyScope>;
}

function CompanySources({ company }: { company: Company }) {
  useCompanyStream(company.id);
  const sources = useQuery(sourcesQuery(company.id));
  const queryClient = useQueryClient();
  return (
    <AdminPage>
      <PageHeader title={`${company.name} 的來源`} />
      {sources.error ? <ErrorState>{sources.error.message}</ErrorState> : null}
      <SourcesView sources={sources.data} />
      <h2 className="mt-8 mb-3 text-lg font-semibold">新增來源</h2>
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
  const article = useQuery(articleQuery(articleId, requested));
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
      cover={<CoverPanel articleId={article.id} cover={article.cover} />}
    />
  );
}
