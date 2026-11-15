"use client";

import type { GatewayHealth } from "@/lib/contract/schemas";
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

/** Which backend the gateway talks to (simulator, local runtime, AWS AgentCore), and whether it answers. */
export function ModeChip({ className }: { className?: string }) {
  const { locale, t } = useI18n();
  const { status, health } = useHealth(locale);
  const label = health ? t.mode[health.mode] : t.mode.checking;
  const tone = healthTone({ status, health });
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
