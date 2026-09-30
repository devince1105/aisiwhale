// The article's cover where a person decides (D-142): the photo marketing chose, whose it is, and
// 換一張 (the next photo from the same search, no model call) or 拿掉 (none; marketing picks no
// other). On a published article the site changes with it.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import type { Schemas } from "@/api/client";
import { removeCover, swapCover } from "@/api/queries";
import { coverSrc } from "@/features/site/Cover";

export type CoverView = Schemas["CoverView"];

export function CoverPanel({ articleId, cover }: { articleId: string; cover: CoverView | null | undefined }) {
  const queryClient = useQueryClient();
  const onSettled = () => queryClient.invalidateQueries({ queryKey: ["newsroom", "article", articleId] });
  const swap = useMutation({ mutationFn: () => swapCover(articleId), onSettled });
  const remove = useMutation({ mutationFn: () => removeCover(articleId), onSettled });
  const busy = swap.isPending || remove.isPending;
  const error = swap.error ?? remove.error;
  if (!cover) return <p className="text-sm text-muted">首圖：行銷沒有找到合適的圖片（或尚未找）。</p>;
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
        {error ? (
          <p role="alert" className="text-danger">
            {error.message}
          </p>
        ) : null}
      </div>
    </div>
  );
}
