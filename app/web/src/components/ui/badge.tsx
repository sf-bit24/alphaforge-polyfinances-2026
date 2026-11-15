import type { ReactNode } from "react";
import { cn } from "./cn";

type Tone = "neutral" | "brand" | "good" | "warning" | "critical" | "outline";

const TONES: Record<Tone, string> = {
  neutral: "bg-ink-100 text-ink-700",
  brand: "bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-100",
  good: "bg-good-wash text-good-ink",
  warning: "bg-warning-wash text-warning-ink",
  critical: "bg-critical-wash text-critical-ink",
  outline: "bg-white text-ink-700 ring-1 ring-inset ring-ink-200",
};

export function Badge({ tone = "neutral", icon, children, className, title }: { tone?: Tone; icon?: ReactNode; children: ReactNode; className?: string; title?: string }) {
  return (
    <span
      title={title}
      className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap", TONES[tone], className)}
    >
      {icon}
      {children}
    </span>
  );
}
