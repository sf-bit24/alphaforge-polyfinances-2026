"use client";

import { useHealth } from "@/lib/client/health";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/components/ui/cn";

/** Which backend the gateway talks to, and whether the runtime answers. */
export function ModeChip() {
  const { locale, t } = useI18n();
  const { status, health } = useHealth(locale);
  const label = health ? t.mode[health.mode] : t.mode.checking;
  const ok = status === "ready" && health?.ok;
  const failed = status === "error" || (status === "ready" && !health?.ok);
  const title = health
    ? [
        `${t.mode.label} : ${t.mode[health.mode]}`,
        health.agent ? `${t.mode.release} ${health.agent.release} · ${health.agent.env}` : null,
        health.runtime ? health.runtime.name : null,
        health.error ? `${health.error.code} : ${health.error.message}` : null,
      ]
        .filter(Boolean)
        .join("\n")
    : t.mode.checking;
  return (
    <span
      title={title}
      className="hidden items-center gap-2 rounded-full bg-white/8 px-2.5 py-1 text-xs text-ink-100 ring-1 ring-white/15 sm:inline-flex"
    >
      <span
        aria-hidden
        className={cn(
          "size-2 rounded-full",
          ok ? "bg-good" : failed ? "bg-critical" : "animate-pulse-dot bg-warning",
        )}
      />
      <span className="font-medium">{label}</span>
      {health?.agent ? <span className="font-mono text-[0.7rem] text-ink-300">{health.agent.release}</span> : null}
      {failed ? <span className="sr-only">{t.mode.unreachable}</span> : null}
    </span>
  );
}
