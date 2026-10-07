"use client";

// A short word after something happened (AD-08, deferred from AD-01 until something used it):
// bottom right, read out by a screen reader, gone after a few seconds or when closed. The timer
// only takes the message away; what it says is what the caller learned.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { Icon } from "./icons";

type Tone = "ok" | "danger";
interface Toast {
  id: number;
  text: string;
  tone: Tone;
}

const ToastContext = createContext<(text: string, tone?: Tone) => void>(() => undefined);
const SHOWN_MS = 6000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const show = useCallback((text: string, tone: Tone = "ok") => {
    setToasts((now) => [...now.slice(-2), { id: Date.now() + Math.random(), text, tone }]);
  }, []);
  const dismiss = (id: number) => setToasts((now) => now.filter((t) => t.id !== id));
  return (
    <ToastContext.Provider value={show}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed right-4 bottom-4 z-50 grid w-[min(24rem,calc(100vw-2rem))] gap-2 print:hidden">
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onDismiss={() => dismiss(toast.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, SHOWN_MS);
    return () => clearTimeout(timer);
  }, [onDismiss]);
  return (
    <div
      role={toast.tone === "danger" ? "alert" : "status"}
      className={`pointer-events-auto flex items-start gap-2 rounded-lg border px-3 py-2 text-sm shadow-lg ${
        toast.tone === "danger" ? "border-danger-line bg-danger-soft text-danger" : "border-line bg-surface text-ink"
      }`}
    >
      <span className="grow">{toast.text}</span>
      <button type="button" onClick={onDismiss} aria-label="關閉通知" className="rounded p-0.5 opacity-70 hover:opacity-100">
        <Icon name="close" className="size-4" />
      </button>
    </div>
  );
}

/** ``toast("已下架")``, ``toast("沒有下架：…", "danger")``. */
export function useToast(): (text: string, tone?: Tone) => void {
  return useContext(ToastContext);
}
