"use client";

import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "./cn";

type HeaderProps = { title: ReactNode; subtitle?: ReactNode; closeLabel: string; onClose: () => void; busy: boolean };

function DialogHeader({ title, subtitle, closeLabel, onClose, busy }: HeaderProps) {
  return (
    <header className="flex items-start gap-3 border-b border-ink-150 px-6 py-4">
      <div className="min-w-0 flex-1">
        <h2 id="dialog-title" className="text-lg font-semibold tracking-tight text-ink-950">
          {title}
        </h2>
        {subtitle ? <p className="mt-0.5 truncate font-mono text-xs text-ink-500">{subtitle}</p> : null}
      </div>
      <button
        type="button"
        onClick={onClose}
        disabled={busy}
        className="rounded-md p-1.5 text-ink-500 hover:bg-ink-100 hover:text-ink-900 focus-visible:outline-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-40"
        aria-label={closeLabel}
      >
        <X aria-hidden className="size-5" />
      </button>
    </header>
  );
}

/** The native dialog, shown as a modal while `open`. */
function useModal(open: boolean) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return ref;
}

const WIDTHS = { lg: "w-[min(56rem,calc(100vw-2rem))]", md: "w-[min(34rem,calc(100vw-2rem))]" } as const;

/**
 * Modal built on the native <dialog>: focus trap, Escape and backdrop come for free. `busy` (an action under way)
 * keeps it open: Escape, the backdrop and the close button do nothing until it ends.
 */
export function Dialog({
  open,
  onClose,
  title,
  subtitle,
  children,
  className,
  size = "lg",
  busy = false,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  className?: string;
  size?: keyof typeof WIDTHS;
  busy?: boolean;
}) {
  const ref = useModal(open);
  const { t } = useI18n();

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onCancel={(event) => {
        if (busy) event.preventDefault();
      }}
      onClick={(event) => {
        if (event.target === ref.current && !busy) onClose();
      }}
      aria-labelledby="dialog-title"
      aria-busy={busy || undefined}
      className={cn(
        "m-auto max-h-[calc(100dvh-2rem)] overflow-hidden rounded-2xl bg-surface p-0 text-ink-900 shadow-lift",
        WIDTHS[size],
        className,
      )}
    >
      {open ? (
        <div className="flex max-h-[calc(100dvh-2rem)] flex-col">
          <DialogHeader title={title} subtitle={subtitle} closeLabel={t.common.close} onClose={onClose} busy={busy} />
          <div className="overflow-y-auto px-6 py-5">{children}</div>
        </div>
      ) : null}
    </dialog>
  );
}
