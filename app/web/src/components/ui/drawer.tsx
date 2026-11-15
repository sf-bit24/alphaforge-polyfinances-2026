"use client";

import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "./cn";

function DrawerBar({ label, closeLabel, onClose }: { label: string; closeLabel: string; onClose: () => void }) {
  return (
    <div className="flex items-center justify-end gap-3 border-b border-line px-5 py-2">
      {/* The panel inside has its own visible title; the dialog is named by aria-label. */}
      <p className="sr-only">{label}</p>
      <button
        type="button"
        onClick={onClose}
        className="rounded-md p-1.5 text-ink-500 hover:bg-ink-100 hover:text-ink-950"
        aria-label={closeLabel}
      >
        <X aria-hidden className="size-5" />
      </button>
    </div>
  );
}

/**
 * A panel sliding in from the right, on the native modal <dialog> (focus trap, Escape,
 * backdrop). The trace and the full profile open in it, so no sidebar is permanent.
 */
export function Drawer({
  open,
  onClose,
  label,
  children,
  className,
}: {
  open: boolean;
  onClose: () => void;
  label: string;
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const { t } = useI18n();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
      aria-label={label}
      className={cn(
        "fixed inset-y-0 right-0 left-auto m-0 h-dvh max-h-dvh w-[min(30rem,100vw)] max-w-none overflow-hidden border-l border-line bg-white p-0 text-ink-950 shadow-lift open:animate-drawer-in",
        className,
      )}
    >
      {open ? (
        <div className="flex h-full flex-col">
          <DrawerBar label={label} closeLabel={t.common.close} onClose={onClose} />
          <div className="min-h-0 flex-1 overflow-y-auto bg-page p-4">{children}</div>
        </div>
      ) : null}
    </dialog>
  );
}
