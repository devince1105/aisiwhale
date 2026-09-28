// A dropdown that closes when the reader clicks elsewhere or presses Escape: the calendar's
// (D-084), the language menu's and the reader's own (D-087).
import { useEffect, type RefObject } from "react";

export function useDismiss(box: RefObject<HTMLElement | null>, open: boolean, close: () => void): void {
  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) close();
    };
    const escape = (event: KeyboardEvent) => event.key === "Escape" && close();
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [box, open, close]);
}
