"use client";

// A row opened beside its list (AD-07): ?peek=<id> on the address, so a link or a reload shows
// it and the browser's back closes it. A peek opened here goes back when closed; one that came
// with the address is taken off it instead, so closing never leaves the page.
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useRef } from "react";

export function usePeek(): { peek: string | null; open: (id: string) => void; close: () => void } {
  const params = useSearchParams() ?? new URLSearchParams();
  const pathname = usePathname() ?? "";
  const router = useRouter();
  const pushed = useRef(false);
  const search = params.toString();
  const href = useCallback(
    (id: string | null) => {
      const next = new URLSearchParams(search);
      if (id) next.set("peek", id);
      else next.delete("peek");
      const query = next.toString();
      return query ? `${pathname}?${query}` : pathname;
    },
    [pathname, search],
  );
  return {
    peek: params.get("peek"),
    open: (id) => {
      pushed.current = true;
      router.push(href(id), { scroll: false });
    },
    close: () => {
      if (pushed.current) {
        pushed.current = false;
        router.back();
      } else {
        router.replace(href(null), { scroll: false });
      }
    },
  };
}

/** A link that opens the row's peek on a plain click, and the full page otherwise (a new tab,
 * a copied address). */
export function peekClick(open: ((id: string) => void) | undefined, id: string) {
  return (event: React.MouseEvent<HTMLAnchorElement>) => {
    if (!open || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault();
    open(id);
  };
}
