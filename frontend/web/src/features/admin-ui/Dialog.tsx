"use client";

// The back office's modal surfaces (AD-01), on the browser's own <dialog>: shown with showModal()
// it sits above everything, keeps focus inside, makes the page behind inert and closes on Esc —
// nothing for a library to add. Each is rendered only while open, so a closed one is not in the
// page at all (and a test environment without showModal still sees what is open).
import { useEffect, useRef, useState, type ReactNode } from "react";

import { Button } from "./Button";
import { Icon } from "./icons";

function Modal({
  onClose,
  label,
  className,
  children,
}: {
  onClose: () => void;
  label: string;
  className: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    // Esc: the browser fires cancel; the parent decides, so the dialog stays until it is unmounted
    const cancel = (event: Event) => {
      event.preventDefault();
      close.current();
    };
    dialog.addEventListener("cancel", cancel);
    return () => {
      dialog.removeEventListener("cancel", cancel);
      if (dialog.open && typeof dialog.close === "function") dialog.close();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      aria-label={label}
      // a click on the backdrop lands on the dialog itself, not on its content
      onClick={(event) => {
        if (event.target === event.currentTarget) close.current();
      }}
      className={`bg-surface text-ink backdrop:bg-black/40 ${className}`}
    >
      {children}
    </dialog>
  );
}

export interface ConfirmDialogProps {
  title: string;
  /** What will happen, and what cannot be undone. */
  children?: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  tone?: "danger" | "primary";
  /** Ask for a reason before the confirm button works (it is passed to ``onConfirm``). */
  reason?: { placeholder: string; maxLength?: number };
  busy?: boolean;
  error?: string | null;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}

/** Asks before an action that is hard to take back. Render it while asking; ``onCancel`` (also Esc
 * or a click outside) is where the caller stops rendering it. */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  cancelLabel = "取消",
  tone = "danger",
  reason,
  busy = false,
  error = null,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const [said, setSaid] = useState("");
  const ready = !busy && (!reason || said.trim() !== "");
  return (
    <Modal onClose={onCancel} label={title} className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-xl border border-line p-0 shadow-xl">
      <form
        className="grid gap-3 p-5"
        onSubmit={(event) => {
          event.preventDefault();
          if (ready) onConfirm(said.trim());
        }}
      >
        <h2 className="text-base font-semibold">{title}</h2>
        {children ? <div className="text-sm text-muted">{children}</div> : null}
        {reason ? (
          <input
            autoFocus
            required
            maxLength={reason.maxLength}
            value={said}
            onChange={(event) => setSaid(event.target.value)}
            placeholder={reason.placeholder}
            aria-label={reason.placeholder}
            className="rounded-md border border-line bg-canvas px-3 py-1.5 text-sm"
          />
        ) : null}
        {error ? (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        ) : null}
        <div className="mt-1 flex justify-end gap-2">
          <Button variant="subtle" onClick={onCancel} autoFocus={!reason}>
            {cancelLabel}
          </Button>
          <Button type="submit" variant={tone === "danger" ? "danger" : "primary"} disabled={!ready}>
            {confirmLabel}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/** A panel that slides over the page from one side. Render it while open. */
export function Drawer({
  title,
  side = "right",
  onClose,
  children,
}: {
  title: string;
  side?: "left" | "right";
  onClose: () => void;
  children: ReactNode;
}) {
  const edge = side === "left" ? "mr-auto border-r" : "ml-auto border-l";
  return (
    <Modal
      onClose={onClose}
      label={title}
      className={`${edge} my-0 h-dvh max-h-dvh w-[min(22rem,calc(100vw-3rem))] border-line p-0 shadow-xl`}
    >
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          <Button variant="subtle" size="sm" onClick={onClose} aria-label="關閉">
            <Icon name="close" className="size-4" />
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </Modal>
  );
}
