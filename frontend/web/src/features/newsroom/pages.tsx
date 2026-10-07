"use client";

// The newsroom pages' data (T-517): each page loads through the typed client and stays fresh
// through the company's event stream (src/api/invalidation.ts); the views render.
import { parseEvent, type EventEnvelope } from "@autora/event-schema";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
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
import { buttonClass } from "@/features/admin-ui/Button";
import { ListToolbar, Pager, sortControl, type FilterDef } from "@/features/admin-ui/DataTable";
import { Drawer } from "@/features/admin-ui/Dialog";
import { ErrorState } from "@/features/admin-ui/states";
import { useListState } from "@/features/admin-ui/useListState";
import { useCan } from "@/features/admin-ui/permissions";
import { usePeek } from "@/features/admin-ui/usePeek";
import { ViewSwitch } from "@/features/admin-ui/ViewSwitch";
import { ArticleBoard, StoryBoard } from "@/features/board/Boards";
import { ActivityTimeline } from "@/features/audit/ActivityTimeline";
import { CompanyScope, type Company } from "@/features/company/CompanyScope";
import { useCompanyStream } from "@/features/company/useCompanyStream";

import { ArticlesView } from "./ArticlesView";
import { ArticleProperties, ArticleView } from "./ArticleView";
import type { ArticleDetail, StoryDetail } from "./model";
import { Empty } from "./parts";
import { AddSourceForm, SourcesView } from "./SourcesView";
import { label, STORY_STATE } from "./model";
import { STORY_STATES, StoriesView } from "./StoriesView";
import { StoryProperties, StoryView } from "./StoryView";
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
  const list = useListState(["state", "view"], STORY_SORTS);
  const board = list.filters.view === "board";
  const state = (STORY_STATES as readonly string[]).includes(list.filters.state ?? "") ? (list.filters.state as StoryState) : null;
  const page = useQuery({ ...storiesQuery(company.id, state, { q: list.q, sort: list.sort, cursor: list.cursor }), enabled: !board });
  const peek = usePeek();
  return (
    <AdminPage>
      <PageHeader title={`${company.name} 的題材`} actions={<ViewSwitch board={board} onBoard={(on) => list.set({ filters: { view: on ? "board" : null } })} />} />
      {board ? null : <ListToolbar list={list} filters={[STORY_FILTER]} placeholder="搜尋題材標題…" views="stories" />}
      {peek.peek ? <StoryPeek storyId={peek.peek} onClose={peek.close} /> : null}
      {board ? (
        <StoryBoard companyId={company.id} onOpen={peek.open} />
      ) : (
        <>
          <StoriesView
            stories={page.data?.items}
            sort={sortControl(list, STORY_SORTS, "-last_item_at")}
            error={page.error?.message}
            onPeek={peek.open}
          />
          <Pager list={list} shown={page.data?.items.length ?? 0} total={page.data?.total ?? null} nextCursor={page.data?.next_cursor} />
        </>
      )}
    </AdminPage>
  );
}

export function ArticlesPage() {
  return <CompanyScope>{(company) => <CompanyArticles company={company} />}</CompanyScope>;
}

const ARTICLE_SORTS: readonly ArticleSort[] = ["-updated_at", "updated_at", "-created_at", "title"];

function CompanyArticles({ company }: { company: Company }) {
  useCompanyStream(company.id);
  const list = useListState(["view"], ARTICLE_SORTS);
  const board = list.filters.view === "board";
  const page = useQuery({ ...articlesPageQuery(company.id, { q: list.q, sort: list.sort, cursor: list.cursor }), enabled: !board });
  const peek = usePeek();
  return (
    <AdminPage>
      <PageHeader title={`${company.name} 的文章`} actions={<ViewSwitch board={board} onBoard={(on) => list.set({ filters: { view: on ? "board" : null } })} />} />
      {board ? null : <ListToolbar list={list} placeholder="搜尋標題或網址代稱…" views="articles" />}
      {board ? (
        <ArticleBoard companyId={company.id} onOpen={peek.open} />
      ) : (
        <ArticlesView
          articles={page.data?.items}
          sort={sortControl(list, ARTICLE_SORTS, "-updated_at")}
          error={page.error?.message}
          onPeek={peek.open}
        />
      )}
      {peek.peek ? <ArticlePeek articleId={peek.peek} onClose={peek.close} /> : null}
      {board ? null : <Pager list={list} shown={page.data?.items.length ?? 0} total={page.data?.total ?? null} nextCursor={page.data?.next_cursor} />}
    </AdminPage>
  );
}

export function SourcesPage() {
  return <CompanyScope>{(company) => <CompanySources company={company} />}</CompanyScope>;
}

const SOURCE_SORTS: readonly SourceSort[] = ["created_at", "-created_at", "name"];

function CompanySources({ company }: { company: Company }) {
  const can = useCan();
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
      {can("newsroom:edit") ? (
      <AddSourceForm
        onAdd={async (body) => {
          await addSource(company.id, body);
          await queryClient.invalidateQueries({ queryKey: ["newsroom", "sources", company.id] });
        }}
      />
      ) : null}
    </AdminPage>
  );
}

// --- peeks (AD-07): a row beside its list -----------------------------------------------------

function ArticlePeek({ articleId, onClose }: { articleId: string; onClose: () => void }) {
  const article = useQuery(articleQuery(articleId, null));
  const text = article.data ? article.data.languages[article.data.primary_lang] : undefined;
  return (
    <Drawer title={article.data?.title ?? "文章"} wide onClose={onClose}>
      <div className="grid gap-4 p-4">
        {article.error ? <ErrorState>{article.error.message}</ErrorState> : null}
        {article.data ? (
          <>
            <Link href={`/admin/newsroom/articles/${articleId}`} className={`${buttonClass("primary")} justify-self-start`}>
              開啟完整頁面
            </Link>
            {text?.summary ? <p className="text-sm text-muted">{text.summary}</p> : null}
            <ArticleProperties article={article.data} />
            <ActivityTimeline targetType="article" targetId={articleId} />
          </>
        ) : (
          <Empty>載入中…</Empty>
        )}
      </div>
    </Drawer>
  );
}

function StoryPeek({ storyId, onClose }: { storyId: string; onClose: () => void }) {
  const story = useQuery(storyQuery(storyId));
  return (
    <Drawer title={story.data?.title ?? "題材"} wide onClose={onClose}>
      <div className="grid gap-4 p-4">
        {story.error ? <ErrorState>{story.error.message}</ErrorState> : null}
        {story.data ? (
          <>
            <Link href={`/admin/newsroom/stories/${storyId}`} className={`${buttonClass("primary")} justify-self-start`}>
              開啟完整頁面
            </Link>
            {story.data.summary ? <p className="text-sm text-muted">{story.data.summary}</p> : null}
            <StoryProperties story={story.data} />
            <ActivityTimeline targetType="story" targetId={storyId} />
          </>
        ) : (
          <Empty>載入中…</Empty>
        )}
      </div>
    </Drawer>
  );
}

// --- details ----------------------------------------------------------------------------------

export function StoryPage({ storyId }: { storyId: string }) {
  const story = useQuery(storyQuery(storyId));
  if (!story.data) return <Loading error={story.error} />;
  return <LoadedStory story={story.data} />;
}

function LoadedStory({ story }: { story: StoryDetail }) {
  const can = useCan();
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
      activity={<ActivityTimeline targetType="story" targetId={story.id} />}
      events={events}
      onStart={can("newsroom:edit") ? () => start.mutate() : undefined}
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
  const can = useCan();
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
      onSite={can("newsroom:edit") ? {
        unpublish: (reason) => unpublish.mutate(reason),
        republish: () => republish.mutate(),
        revise: (reason) => revise.mutate(reason),
        setAccess: (to) => access.mutate(to),
        setSection: (to) => section.mutate(to),
        busy: unpublish.isPending || republish.isPending || revise.isPending || access.isPending || section.isPending,
        error: (unpublish.error ?? republish.error ?? revise.error ?? access.error ?? section.error)?.message ?? null,
      } : undefined}
      activity={<ActivityTimeline targetType="article" targetId={article.id} />}
      cover={<CoverPanel articleId={article.id} cover={article.cover} asked={article.cover_asked} />}
    />
  );
}
