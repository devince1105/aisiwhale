// An article's cover photo (D-142): 1200x630, credited to its photographer at the library it
// came from. Covers kept by the API itself (dev, without R2) have a path, not an address.
import { API_URL } from "@/config";

import type { PublicArticle } from "./api";
import { words, type Lang } from "./i18n";

export type Cover = NonNullable<PublicArticle["cover"]>;

/** Where the browser loads it from: the bucket's address as is, an API path on the API. */
export function coverSrc(url: string): string {
  return url.startsWith("/") ? `${API_URL}${url}` : url;
}

export function CoverFigure({ cover, lang }: { cover: Cover; lang: Lang }) {
  return (
    <figure className="-mx-4 mb-10 sm:mx-0" data-testid="article-cover">
      {/* a fixed-size WebP from our own storage: next/image would only resize it again */}
      <img
        src={coverSrc(cover.url)}
        alt={cover.alt}
        width={cover.width}
        height={cover.height}
        fetchPriority="high"
        className="aspect-[1200/630] h-auto w-full bg-surface object-cover sm:rounded-lg"
      />
      <figcaption className="mt-2 px-4 text-xs text-muted sm:px-0">
        {words(lang).photo}：
        <a href={cover.page_url} target="_blank" rel="noopener noreferrer nofollow" className="hover:text-ink hover:underline">
          {cover.credit}／{cover.library}
        </a>
      </figcaption>
    </figure>
  );
}
