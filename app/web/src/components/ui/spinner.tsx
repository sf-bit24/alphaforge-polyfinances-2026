import { LoaderCircle } from "lucide-react";
import { cn } from "./cn";

export function Spinner({ label, className }: { label?: string; className?: string }) {
  return (
    <span role="status" className={cn("inline-flex items-center gap-2 text-sm text-ink-500", className)}>
      <LoaderCircle aria-hidden className="size-4 animate-spin text-navy" />
      {label ? <span>{label}</span> : <span className="sr-only">…</span>}
    </span>
  );
}
