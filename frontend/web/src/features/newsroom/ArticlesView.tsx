// The newsroom's articles (T-517): drafts, in review, published — a table (AD-05).
import Link from "next/link";

import { DataTable, type Column, type SortControl } from "@/features/admin-ui/DataTable";
import { StatusLozenge } from "@/features/admin-ui/StatusLozenge";
import { peekClick } from "@/features/admin-ui/usePeek";

import { ARTICLE_STATE, formatTime, label, type ArticleSummary } from "./model";

function columns(onPeek?: (id: string) => void): Column<ArticleSummary>[] {
  return [

  {
    key: "state",
    header: "狀態",
    className: "whitespace-nowrap",
    cell: (article) => {
      const [state, tone] = label(ARTICLE_STATE, article.state);
      return <StatusLozenge tone={tone}>{state}</StatusLozenge>;
    },
  },
  {
    key: "title",
    header: "標題",
    sort: "title",
    cell: (article) => (
      <Link href={`/admin/newsroom/articles/${article.id}`} onClick={peekClick(onPeek, article.id)} className="font-medium hover:text-accent">
        {article.title}
      </Link>
    ),
  },
  {
    key: "version",
    header: "版本",
    className: "whitespace-nowrap",
    cell: (article) => (
      <>
        v{article.version ?? "—"}
        {article.revision_count ? <span className="text-muted">（修訂 {article.revision_count} 次）</span> : null}
      </>
    ),
  },
  { key: "langs", header: "語言", className: "whitespace-nowrap", cell: (article) => article.langs.join(" / ") },
  { key: "views", header: "瀏覽", align: "right", cell: (article) => article.views.toLocaleString() },
  {
    key: "updated",
    header: "更新",
    sort: "updated_at",
    className: "whitespace-nowrap text-muted",
    cell: (article) => formatTime(article.updated_at),
  },
  ];
}

export function ArticlesView({
  articles,
  sort,
  error = null,
  onPeek,
}: {
  articles: readonly ArticleSummary[] | undefined;
  /** A plain click on a title opens it beside the list (AD-07). */
  onPeek?: (id: string) => void;
  sort?: SortControl;
  error?: string | null;
}) {
  return (
    <DataTable
      label="文章"
      rows={articles}
      columns={columns(onPeek)}
      rowKey={(article) => article.id}
      sort={sort}
      error={error}
      empty="還沒有文章。寫手寫出第一份草稿後就會出現在這裡。"
    />
  );
}
