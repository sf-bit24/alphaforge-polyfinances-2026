"use client";

import { CircleAlert } from "lucide-react";
import type { GatewayHealth } from "@/lib/contract/schemas";
import { useOperator } from "@/lib/client/account";
import { useHealth } from "@/lib/client/health";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/components/ui/cn";

type HealthTone = "ok" | "failed" | "checking";

const DOT_CLASS: Record<HealthTone, string> = { ok: "bg-good", failed: "bg-critical", checking: "animate-pulse-dot bg-warning" };

function healthTone({ status, health }: ReturnType<typeof useHealth>): HealthTone {
  if (status === "ready" && health?.ok) return "ok";
  if (status === "error" || (status === "ready" && !health?.ok)) return "failed";
  return "checking";
}

function healthTitle(health: GatewayHealth, t: Dictionary): string {
  return [
    `${t.mode.label} : ${t.mode[health.mode]}`,
    health.agent ? `${t.mode.release} ${health.agent.release} · ${health.agent.env}` : null,
    health.runtime ? health.runtime.name : null,
    health.error ? `${health.error.code} : ${health.error.message}` : null,
  ]
    .filter(Boolean)
    .join("\n");
}

/** What a client sees when the service does not answer: a plain sentence, no backend, no code (LANGAGE.md). */
function ServiceDownChip({ className }: { className?: string }) {
  const { t } = useI18n();
  return (
    <span
      role="status"
      title={t.errors.hints.internal}
      className={cn("items-center gap-1.5 rounded-full border border-warning/40 bg-warning-wash px-2.5 py-1 text-xs font-medium text-warning-ink", className ?? "inline-flex")}
    >
      <CircleAlert aria-hidden className="size-3.5" />
      {t.errors.unavailable}
      <span className="sr-only">. {t.errors.hints.internal}</span>
    </span>
  );
}

/**
 * Team's view (`useOperator`): which backend the gateway talks to (simulator, local runtime, AWS AgentCore),
 * and whether it answers. A client sees nothing, or « Service indisponible » when the service does not answer.
 */
export function ModeChip({ className }: { className?: string }) {
  const { locale, t } = useI18n();
  const operator = useOperator();
  const { status, health } = useHealth(locale);
  const tone = healthTone({ status, health });
  if (!operator) return tone === "failed" ? <ServiceDownChip className={className} /> : null;
  const label = health ? t.mode[health.mode] : t.mode.checking;
  const title = health ? healthTitle(health, t) : t.mode.checking;
  return (
    <span
      title={title}
      className={cn("items-center gap-2 rounded-full border border-line bg-white px-2.5 py-1 text-xs text-ink-600", className ?? "inline-flex")}
    >
      <span aria-hidden className={cn("size-2 rounded-full", DOT_CLASS[tone])} />
      <span className="font-medium text-ink-950">{label}</span>
      {tone === "failed" ? <span className="sr-only">{t.mode.unreachable}</span> : null}
    </span>
  );
}
