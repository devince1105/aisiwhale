// The article's cover where a person decides (D-142): the photo marketing chose, whose it is, and
// 換一張 (the next photo from the same search, no model call) or 拿掉 (none; marketing picks no
// other). With the person's own words (D-233), 重找 searches the library at once, and 請行銷換圖
// hands them to marketing, who looks again (or generates one); either way the article is not sent
// back. On a published article the site changes with it.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import type { Schemas } from "@/api/client";
import { askCover, removeCover, searchCover, swapCover } from "@/api/queries";
import { coverSrc } from "@/features/site/Cover";

export type CoverView = Schemas["CoverView"];

export function CoverPanel({
  articleId,
  cover,
  asked = false,
}: {
  articleId: string;
  cover: CoverView | null | undefined;
  /** Marketing is finding a new one now (the article's ``cover_asked``): the page asks the API
   * for the article again meanwhile (``coverWatch``), and the new one shows when it is in. */
  asked?: boolean;
}) {
  const queryClient = useQueryClient();
  const refresh = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ["newsroom", "article", articleId] }),
    [queryClient, articleId],
  );
  const swap = useMutation({ mutationFn: () => swapCover(articleId), onSettled: refresh });
  const remove = useMutation({ mutationFn: () => removeCover(articleId), onSettled: refresh });
  const search = useMutation({ mutationFn: (query: string) => searchCover(articleId, query), onSettled: refresh });
  const ask = useMutation({ mutationFn: (words: string) => askCover(articleId, words), onSettled: refresh });
  const busy = swap.isPending || remove.isPending || search.isPending || ask.isPending || asked;
  const error = swap.error ?? remove.error ?? search.error ?? ask.error;
  const words = (
    <CoverWords
      busy={busy}
      // a cover a person took off is put back first (放回一張 or 重找), then marketing may change it
      canAsk={cover?.state !== "removed"}
      onSearch={(query) => search.mutate(query)}
      onAsk={(text) => ask.mutate(text)}
    />
  );
  const status = asked ? (
    <p role="status" className="text-muted">
      行銷正在找新的首圖，找到後這裡會自動換上。
    </p>
  ) : null;
  const failed = error ? (
    <p role="alert" className="text-danger">
      {error.message}
    </p>
  ) : null;
  if (!cover)
    return (
      <div className="grid gap-1 text-sm" data-testid="cover-panel">
        <p className="text-muted">首圖：行銷沒有找到合適的圖片（或尚未找）。</p>
        {words}
        {status}
        {failed}
      </div>
    );
  const shown = cover.state === "active";
  return (
    <div className="flex flex-wrap items-start gap-3" data-testid="cover-panel">
      {shown ? (
        <img
          src={coverSrc(cover.url)}
          alt={cover.alt["zh-TW"] ?? cover.alt.en ?? ""}
          width={cover.width}
          height={cover.height}
          className="aspect-[1200/630] h-auto w-48 shrink-0 rounded border border-line object-cover"
        />
      ) : null}
      <div className="grid min-w-0 flex-1 gap-1 text-sm">
        <p className="text-muted">
          {shown ? (
            <>
              首圖・
              {cover.page_url ? (
                <a href={cover.page_url} target="_blank" rel="noopener noreferrer" className="underline">
                  {cover.credit}／{cover.library}
                </a>
              ) : (
                cover.credit
              )}
              ・{Math.round(cover.bytes / 1000)} KB
            </>
          ) : (
            "首圖已拿掉：文章不顯示圖片，行銷也不會再找。"
          )}
        </p>
        {shown && cover.alt["zh-TW"] ? <p className="break-words">{cover.alt["zh-TW"]}</p> : null}
        <p className="text-xs text-muted">搜尋：{cover.query}</p>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy || cover.others === 0}
            title={cover.others === 0 ? "同一次搜尋沒有其他圖片" : `同一次搜尋還有 ${cover.others} 張`}
            onClick={() => swap.mutate()}
            className="rounded-lg border border-line px-3 py-1 text-sm disabled:opacity-50"
          >
            {shown ? "換一張" : "放回一張"}
          </button>
          {shown ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => remove.mutate()}
              className="rounded-lg border border-line px-3 py-1 text-sm text-danger disabled:opacity-50"
            >
              拿掉
            </button>
          ) : null}
        </div>
        {words}
        {status}
        {failed}
      </div>
    </div>
  );
}

/** The person's words for the cover (D-233): 重找 searches the library with them at once, no model
 * call; 請行銷換圖 gives them to marketing, who may also generate one. */
function CoverWords({
  busy,
  canAsk,
  onSearch,
  onAsk,
}: {
  busy: boolean;
  canAsk: boolean;
  onSearch: (query: string) => void;
  onAsk: (words: string) => void;
}) {
  const [words, setWords] = useState("");
  const query = words.trim();
  const button = "rounded-lg border border-line px-3 py-1 text-sm disabled:opacity-50";
  return (
    <form
      className="flex flex-wrap gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (query) onSearch(query);
      }}
    >
      <input
        aria-label="用自己的話找首圖"
        value={words}
        maxLength={100}
        onChange={(event) => setWords(event.target.value)}
        placeholder="想要的圖：例如 晶圓廠、股市看板"
        className="min-w-0 flex-1 rounded-lg border border-line bg-transparent px-2 py-1 text-sm"
      />
      <button type="submit" disabled={busy || !query} title="直接用這些字搜尋圖庫" className={button}>
        重找
      </button>
      {canAsk ? (
        <button
          type="button"
          disabled={busy || !query}
          title="交給行銷照你的話找，圖庫沒有合適的會生成一張"
          onClick={() => onAsk(query)}
          className={button}
        >
          請行銷換圖
        </button>
      ) : null}
    </form>
  );
}

/** While marketing finds a new cover (D-233), the article is asked for again every few seconds:
 * what the card shows is still only what the API says (AC-S6). */
export const coverWatch = {
  refetchInterval: (query: { state: { data?: { cover_asked?: boolean } } }) =>
    query.state.data?.cover_asked ? 5000 : false,
} as const;
