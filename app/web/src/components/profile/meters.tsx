"use client";

import { CircleCheck, Hourglass } from "lucide-react";
import type { Completeness, KnowledgeLevel, RiskLevel } from "@/lib/contract/schemas";
import { KNOWLEDGE_LEVELS, RISK_LEVELS } from "@/lib/contract/schemas";
import { formatPercent } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/components/ui/cn";

/**
 * Completeness as a meter: blue fill on a lighter blue track, the 70% threshold
 * as a tick, and the 95% cap zone that the fill never reaches.
 */
export function CompletenessMeter({ completeness, compact = false }: { completeness: Completeness; compact?: boolean }) {
  const { t, locale } = useI18n();
  const { displayed, threshold, cap, ready, score } = completeness;
  const pct = (value: number) => `${Math.max(0, Math.min(1, value)) * 100}%`;
  const gap = Math.max(0, threshold - score);
  return (
    <div>
      <div className="flex items-end justify-between gap-3">
        <p className="text-sm font-medium text-ink-600">{t.panel.completeness}</p>
        <p className={cn("font-semibold tracking-tight text-ink-950", compact ? "text-xl" : "text-[2rem] leading-none")}>
          {formatPercent(displayed, locale)}
        </p>
      </div>
      <div
        role="meter"
        aria-label={t.panel.completeness}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(displayed * 100)}
        aria-valuetext={`${formatPercent(displayed, locale)} · ${t.panel.threshold} · ${t.panel.cap}`}
        className="relative mt-3"
      >
        <div className="relative h-2.5 overflow-hidden rounded-full bg-soft">
          <div className="absolute inset-y-0 right-0 bg-ink-200" style={{ left: pct(cap) }} />
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-brand-500 transition-[width] duration-500 ease-out"
            style={{ width: pct(displayed) }}
          />
        </div>
        <span aria-hidden className="absolute -top-1 h-4.5 w-0.5 rounded bg-ink-800" style={{ left: `calc(${pct(threshold)} - 1px)` }} />
        <span aria-hidden className="absolute -top-1 h-4.5 w-px bg-ink-400" style={{ left: pct(cap) }} />
      </div>
      <div aria-hidden className="relative mt-1.5 h-4 text-[0.7rem] text-ink-500">
        <span className="absolute pr-1 font-medium whitespace-nowrap text-ink-700" style={{ right: `calc(100% - ${pct(threshold)})` }}>
          {t.panel.threshold}
        </span>
        <span className="absolute right-0 whitespace-nowrap">{t.panel.cap}</span>
      </div>
      <p className={cn("mt-2 flex items-center gap-1.5 text-sm font-medium", ready ? "text-good-ink" : "text-ink-600")}>
        {ready ? (
          <CircleCheck aria-hidden className="size-4 text-good" />
        ) : (
          <Hourglass aria-hidden className="size-4 text-ink-400" />
        )}
        {ready ? t.panel.ready : t.panel.notReady(formatPercent(gap, locale))}
      </p>
      {!compact ? <p className="mt-1 text-xs text-ink-500">{t.panel.completenessCaption}</p> : null}
    </div>
  );
}

/** An ordinal level as a segmented meter, with its label: the value is never colour-only. */
function SegmentedMeter({ label, value, steps, text }: { label: string; value: number | null; steps: number; text: string }) {
  return (
    <div>
      <p className="text-xs font-medium text-ink-500">{label}</p>
      <p className="mt-0.5 text-[0.95rem] font-semibold text-ink-950">{text}</p>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={1}
        aria-valuemax={steps}
        aria-valuenow={value ?? undefined}
        aria-valuetext={text}
        className="mt-2 flex gap-0.5"
      >
        {Array.from({ length: steps }, (_, index) => (
          <span
            key={index}
            className={cn(
              "h-1.5 flex-1 first:rounded-l-full last:rounded-r-full",
              value !== null && index < value ? "bg-navy" : "bg-ink-100",
            )}
          />
        ))}
      </div>
    </div>
  );
}

export function KnowledgeMeter({ level }: { level: KnowledgeLevel | null }) {
  const { t } = useI18n();
  const index = level ? KNOWLEDGE_LEVELS.indexOf(level) + 1 : null;
  return <SegmentedMeter label={t.panel.knowledge} value={index} steps={3} text={level ? t.knowledgeLevels[level] : t.panel.toDetermine} />;
}

export function RiskMeter({ level }: { level: RiskLevel | null }) {
  const { t } = useI18n();
  const index = level ? RISK_LEVELS.indexOf(level) + 1 : null;
  return <SegmentedMeter label={t.panel.risk} value={index} steps={5} text={level ? t.riskLevels[level] : t.panel.toDetermine} />;
}
