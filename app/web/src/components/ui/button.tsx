import { LoaderCircle } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

/** `inverse` and `inverseGhost` sit on dark surfaces (home hero). `cn` does not merge, so never override colors by className. */
type Variant = "primary" | "secondary" | "ghost" | "danger" | "subtle" | "inverse" | "inverseGhost";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-brand-600 text-white shadow-sm hover:bg-brand-700 active:bg-brand-800 disabled:bg-ink-300 disabled:text-white",
  secondary:
    "bg-white text-ink-800 ring-1 ring-inset ring-ink-300 shadow-sm hover:bg-ink-50 hover:ring-ink-400 disabled:text-ink-400 disabled:ring-ink-200",
  ghost: "text-ink-700 hover:bg-ink-100 hover:text-ink-900 disabled:text-ink-400",
  subtle: "bg-soft text-navy hover:bg-ink-100 disabled:bg-ink-100 disabled:text-ink-400",
  danger: "text-critical-ink hover:bg-critical-wash disabled:text-ink-400",
  inverse: "bg-white font-semibold text-ink-950 shadow-sm hover:bg-soft active:bg-ink-100 disabled:bg-white/70 disabled:text-ink-600",
  inverseGhost: "text-ink-100 hover:bg-white/10 hover:text-white disabled:text-ink-400",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 gap-1.5 rounded-md px-2.5 text-sm",
  md: "h-10 gap-2 rounded-lg px-4 text-sm",
  lg: "h-12 gap-2 rounded-lg px-5 text-base",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({ variant = "primary", size = "md", loading = false, icon, className, children, disabled, type = "button", ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "inline-flex shrink-0 items-center justify-center font-medium whitespace-nowrap transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? <LoaderCircle aria-hidden className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}
