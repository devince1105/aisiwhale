"use client";

// The newsroom's two boards (AD-08): articles from draft to the site, stories from found to made.
// A column is one page of its state (50, newest change first), loaded on its own.
import { useInfiniteQuery, useQueries, useQueryClient } from "@tanstack/react-query";

import {
  approvalsQuery,
  articlesPageQuery,
  decideApproval,
  itemsOf,
  republishArticle,
  reviseArticle,
  startStory,
  storiesQuery,
  unpublishArticle,
  type ArticleState,
  type StoryState,
} from "@/api/queries";
import { ARTICLE_STATE, formatTime, label, STORY_STATE } from "@/features/newsroom/model";

import { Board, type BoardCard, type BoardColumn } from "./Board";
import type { Move } from "./moves";
import { useBoardMoves } from "./useBoardMoves";

const ARTICLE_COLUMNS: readonly ArticleState[] = ["DRAFT", "IN_REVIEW", "APPROVED", "PUBLISHED", "ARCHIVED", "REJECTED"];
const STORY_COLUMNS: readonly StoryState[] = ["DISCOVERED", "SELECTED", "IN_PRODUCTION", "PUBLISHED", "DROPPED"];
const PER_COLUMN = 50;

function columnsOf(keys: readonly string[], table: Record<string, [string, BoardColumn["tone"]]>): BoardColumn[] {
  return keys.map((key) => ({ key, label: label(table, key)[0], tone: label(table, key)[1] }));
}

export function ArticleBoard({ companyId, onOpen }: { companyId: string; onOpen?: (id: string) => void }) {
  const queryClient = useQueryClient();
  const columns = columnsOf(ARTICLE_COLUMNS, ARTICLE_STATE);
  const pages = useQueries({
    queries: ARTICLE_COLUMNS.map((state) => articlesPageQuery(companyId, { state, sort: "-updated_at", limit: PER_COLUMN })),
  });
  // a draft in review is decided through its approval
  const pending = useInfiniteQuery(approvalsQuery(companyId));
  const approvalOf = new Map(
    (itemsOf(pending.data) ?? []).flatMap((a) => (typeof a.payload.article_id === "string" ? [[a.payload.article_id, a.id] as const] : [])),
  );

  const run = async (card: BoardCard, move: Move, reason: string | null) => {
    if (move.action === "unpublish") return unpublishArticle(card.id, reason ?? "");
    if (move.action === "republish") return republishArticle(card.id);
    if (move.action === "revise") return reviseArticle(card.id, reason ?? "");
    const approval = approvalOf.get(card.id);
    if (!approval) throw new Error("找不到這篇的待審批，可能已經有人決定了");
    const decision = move.action === "approve" ? "approve" : move.action === "send_back" ? "revise" : "reject";
    return decideApproval(approval, decision, reason);
  };
  const moves = useBoardMoves({
    entity: "article",
    columnLabel: (key) => label(ARTICLE_STATE, key)[0],
    run,
    onDone: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ["newsroom"] }),
        queryClient.invalidateQueries({ queryKey: ["approvals", companyId] }),
      ]),
  });

  const loaded = Object.fromEntries(
    ARTICLE_COLUMNS.map((state, i) => [
      state,
      pages[i].data?.items.map<BoardCard>((a) => ({
        id: a.id,
        column: a.state,
        title: a.title,
        href: `/admin/newsroom/articles/${a.id}`,
        meta: `v${a.version ?? "—"}・${a.access === "members" ? "VIP" : a.access === "coin" ? `鯨幣 ${a.coin_price}` : "免費"}・${formatTime(a.updated_at)}`,
      })),
    ]),
  );
  const totals = Object.fromEntries(ARTICLE_COLUMNS.map((state, i) => [state, pages[i].data?.total ?? null]));
  const error = pages.find((p) => p.error)?.error;
  return (
    <>
      {error ? (
        <p role="alert" className="mb-3 text-sm text-danger">
          {error.message}
        </p>
      ) : null}
      <Board
        label="文章看板"
        columns={columns}
        cards={moves.place(loaded)}
        totals={moves.count(loaded, totals)}
        targets={moves.targets}
        onMove={moves.ask}
        onOpen={onOpen}
        busy={moves.busy}
      />
      {moves.dialog}
    </>
  );
}

export function StoryBoard({ companyId, onOpen }: { companyId: string; onOpen?: (id: string) => void }) {
  const queryClient = useQueryClient();
  const columns = columnsOf(STORY_COLUMNS, STORY_STATE);
  const pages = useQueries({
    queries: STORY_COLUMNS.map((state) => storiesQuery(companyId, state, { limit: PER_COLUMN })),
  });
  const moves = useBoardMoves({
    entity: "story",
    columnLabel: (key) => label(STORY_STATE, key)[0],
    run: (card) => startStory(card.id),
    onDone: () => queryClient.invalidateQueries({ queryKey: ["newsroom"] }),
  });
  const loaded = Object.fromEntries(
    STORY_COLUMNS.map((state, i) => [
      state,
      pages[i].data?.items.map<BoardCard>((s) => ({
        id: s.id,
        column: s.state,
        title: s.title,
        href: `/admin/newsroom/stories/${s.id}`,
        meta: `分數 ${Math.round(Number(s.score) * 100)}・${s.items} 則來源項目`,
      })),
    ]),
  );
  const totals = Object.fromEntries(STORY_COLUMNS.map((state, i) => [state, pages[i].data?.total ?? null]));
  const error = pages.find((p) => p.error)?.error;
  return (
    <>
      {error ? (
        <p role="alert" className="mb-3 text-sm text-danger">
          {error.message}
        </p>
      ) : null}
      <Board
        label="題材看板"
        columns={columns}
        cards={moves.place(loaded)}
        totals={moves.count(loaded, totals)}
        targets={moves.targets}
        onMove={moves.ask}
        onOpen={onOpen}
        busy={moves.busy}
      />
      {moves.dialog}
    </>
  );
}
