// The newsroom's stories (T-517): what the sources brought, clustered; what is being made of them
// — a table (AD-05). The state to show is the table's filter (STORY_STATES).
import Link from "next/link";

import { DataTable, type Column, type SortControl } from "@/features/admin-ui/DataTable";
import { StatusLozenge } from "@/features/admin-ui/StatusLozenge";
import { peekClick } from "@/features/admin-ui/usePeek";

import { formatTime, label, STORY_STATE, type StorySummary } from "./model";

/** The states a person filters by. */
export const STORY_STATES = ["DISCOVERED", "SELECTED", "IN_PRODUCTION", "PUBLISHED", "DROPPED"] as const;

function columns(onPeek?: (id: string) => void): Column<StorySummary>[] {
  return [

  {
    key: "state",
    header: "狀態",
    className: "whitespace-nowrap",
    cell: (story) => {
      const [state, tone] = label(STORY_STATE, story.state);
      return <StatusLozenge tone={tone}>{state}</StatusLozenge>;
    },
  },
  {
    key: "title",
    header: "題材",
    sort: "title",
    cell: (story) => (
      <Link href={`/admin/newsroom/stories/${story.id}`} onClick={peekClick(onPeek, story.id)} className="font-medium hover:text-accent">
        {story.title}
      </Link>
    ),
  },
  {
    key: "score",
    header: "分數",
    sort: "score",
    align: "right",
    cell: (story) => Math.round(Number(story.score) * 100),
  },
  {
    key: "counts",
    header: "來源／主張",
    className: "whitespace-nowrap text-xs text-muted",
    cell: (story) => `${story.items} 則來源項目・${story.claims} 則主張`,
  },
  {
    key: "article",
    header: "文章",
    cell: (story) =>
      story.article ? (
        <Link href={`/admin/newsroom/articles/${story.article.id}`} className="text-xs text-accent underline">
          文章
        </Link>
      ) : null,
  },
  {
    key: "seen",
    header: "首次出現",
    sort: "first_seen_at",
    className: "whitespace-nowrap text-muted",
    cell: (story) => formatTime(story.first_seen_at),
  },
  ];
}

export function StoriesView({
  stories,
  sort,
  error = null,
  onPeek,
}: {
  stories: readonly StorySummary[] | undefined;
  /** A plain click on a title opens it beside the list (AD-07). */
  onPeek?: (id: string) => void;
  sort?: SortControl;
  error?: string | null;
}) {
  return (
    <DataTable
      label="題材"
      rows={stories}
      columns={columns(onPeek)}
      rowKey={(story) => story.id}
      sort={sort}
      error={error}
      empty="沒有題材。新增來源後，每 5 分鐘讀取一次並分群成題材。"
    />
  );
}
