// An article as this reader may read it (D-025, D-249): the page as kept for everybody, then, if
// it holds back the rest, the browser asks for the reader's own copy (readerVersion.tsx).
"use client";

import type { PublicArticle } from "./api";
import { ArticleView } from "./ArticleView";
import type { Lang } from "./i18n";
import { ReaderRefresh, useReaderVersion } from "./readerVersion";

export function ArticleReader({ article, lang, slug }: { article: PublicArticle; lang: Lang; slug: string }) {
  const [shown, refresh] = useReaderVersion(
    article,
    `/api/public/articles/${encodeURIComponent(lang)}/${encodeURIComponent(slug)}`,
    article.locked,
  );
  return (
    <ReaderRefresh.Provider value={refresh}>
      <ArticleView article={shown} lang={lang} />
    </ReaderRefresh.Provider>
  );
}
