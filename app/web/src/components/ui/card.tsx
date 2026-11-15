import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

export function Card({ className, ...rest }: HTMLAttributes<HTMLElement>) {
  return <section className={cn("rounded-xl bg-surface shadow-card ring-1 ring-ink-200/80", className)} {...rest} />;
}

export function CardHeader({
  title,
  subtitle,
  icon,
  actions,
  level = 2,
  className,
  id,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  level?: 2 | 3;
  className?: string;
  id?: string;
}) {
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <header className={cn("flex items-start gap-3 border-b border-ink-150 px-5 py-4", className)}>
      {icon ? <span className="mt-0.5 text-navy">{icon}</span> : null}
      <div className="min-w-0 flex-1">
        <Heading id={id} className="text-[0.95rem] font-semibold tracking-tight text-ink-950">
          {title}
        </Heading>
        {subtitle ? <p className="mt-0.5 text-sm text-ink-500">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </header>
  );
}
