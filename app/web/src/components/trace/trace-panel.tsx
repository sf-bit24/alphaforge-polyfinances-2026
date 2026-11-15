"use client";

import { Activity, Bot, ChevronDown, Cog, Database, ShieldCheck, Sparkles, Trash2, Wrench } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { Source, TraceKind, TraceStep } from "@/lib/contract/schemas";
import { TRACE_KINDS } from "@/lib/contract/schemas";
import type { TraceRun } from "@/lib/client/session-store";
import { useSession } from "@/lib/client/session";
import { formatDate, formatDateTime, formatDuration, formatTime } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/components/ui/cn";
import { JsonView } from "@/components/ui/json-view";
import { Spinner } from "@/components/ui/spinner";

/** Categorical slots 1 to 6 in fixed order; icons sit in white or near-black by fill luminance. */
export const KIND_STYLE: Record<TraceKind, { color: string; icon: ReactNode; ink: string }> = {
  deterministic: { color: "var(--color-kind-deterministic)", icon: <Cog aria-hidden className="size-3.5" />, ink: "text-white" },
  agent: { color: "var(--color-kind-agent)", icon: <Bot aria-hidden className="size-3.5" />, ink: "text-white" },
  model: { color: "var(--color-kind-model)", icon: <Sparkles aria-hidden className="size-3.5" />, ink: "text-ink-950" },
  tool: { color: "var(--color-kind-tool)", icon: <Wrench aria-hidden className="size-3.5" />, ink: "text-ink-950" },
  storage: { color: "var(--color-kind-storage)", icon: <Database aria-hidden className="size-3.5" />, ink: "text-ink-950" },
  guardrail: { color: "var(--color-kind-guardrail)", icon: <ShieldCheck aria-hidden className="size-3.5" />, ink: "text-white" },
};

function isEmpty(value: unknown): boolean {
  if (value === undefined || value === null) return true;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value as object).length === 0;
  return false;
}

export function SourceLine({ source }: { source: Source }) {
  const { t, locale } = useI18n();
  const dates = [
    source.observed_at ? `${t.sourcesBlock.observed} ${formatDate(source.observed_at, locale)}` : null,
    source.published_at ? `${t.sourcesBlock.published} ${formatDate(source.published_at, locale)}` : null,
    source.retrieved_at ? `${t.sourcesBlock.retrieved} ${formatDate(source.retrieved_at, locale)}` : null,
  ].filter(Boolean);
  return (
    <li className="text-xs leading-snug text-ink-700">
      <span className="font-medium text-ink-900">{source.title}</span>
      <span className="ml-1.5 font-mono text-[0.68rem] break-all text-ink-500">{source.resource}</span>
      {dates.length ? <span className="block text-[0.68rem] text-ink-500">{dates.join(" · ")}</span> : null}
    </li>
  );
}

function StepItem({ step, last }: { step: TraceStep; last: boolean }) {
  const { t, locale } = useI18n();
  const style = KIND_STYLE[step.kind];
  const hasIo = !isEmpty(step.inputs) || !isEmpty(step.outputs);
  return (
    <li className="animate-fade-in relative pb-4 pl-9 last:pb-1">
      {!last ? <span aria-hidden className="absolute top-7 bottom-0 left-[11px] w-px bg-ink-150" /> : null}
      <span
        aria-hidden
        className={cn("absolute top-0 left-0 flex size-6 items-center justify-center rounded-full ring-2 ring-white", style.ink)}
        style={{ backgroundColor: style.color }}
      >
        {style.icon}
      </span>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.7rem] text-ink-500">
        <span className="font-semibold text-ink-700">{t.trace.kinds[step.kind]}</span>
        <span className="rounded bg-ink-100 px-1.5 py-px font-mono font-medium text-ink-800">{step.actor}</span>
        {typeof step.duration_ms === "number" ? <span className="tabular-nums">{formatDuration(step.duration_ms, locale)}</span> : null}
        <time dateTime={step.at} title={formatDateTime(step.at, locale)} className="ml-auto tabular-nums">
          {formatTime(step.at, locale)}
        </time>
      </div>
      <p className="mt-1 text-sm leading-snug font-medium text-ink-950">{step.title}</p>
      {step.detail ? <p className="mt-0.5 text-[0.8rem] leading-snug break-words text-ink-600">{step.detail}</p> : null}
      {step.sources.length > 0 ? (
        <div className="mt-2 rounded-md bg-soft px-2.5 py-1.5 ring-1 ring-line">
          <p className="text-[0.65rem] font-semibold tracking-wide text-navy uppercase">{t.trace.sources}</p>
          <ul className="mt-0.5 space-y-1">
            {step.sources.map((source) => (
              <SourceLine key={source.id} source={source} />
            ))}
          </ul>
        </div>
      ) : null}
      {hasIo ? (
        <details className="group/io mt-1.5">
          <summary className="inline-flex items-center gap-1 rounded text-[0.75rem] font-medium text-navy hover:underline focus-visible:outline-2 focus-visible:outline-focus">
            <ChevronDown aria-hidden className="size-3.5 transition-transform group-open/io:rotate-180" />
            {t.trace.io}
          </summary>
          <div className="mt-1.5 space-y-2">
            {!isEmpty(step.inputs) ? (
              <div>
                <p className="mb-1 text-[0.65rem] font-semibold tracking-wide text-ink-500 uppercase">{t.trace.inputs}</p>
                <JsonView value={step.inputs} maxHeight="max-h-48" />
              </div>
            ) : null}
            {!isEmpty(step.outputs) ? (
              <div>
                <p className="mb-1 text-[0.65rem] font-semibold tracking-wide text-ink-500 uppercase">{t.trace.outputs}</p>
                <JsonView value={step.outputs} maxHeight="max-h-48" />
              </div>
            ) : null}
          </div>
        </details>
      ) : null}
    </li>
  );
}

function RunCard({ run, hidden, defaultOpen, live }: { run: TraceRun; hidden: Set<TraceKind>; defaultOpen: boolean; live: boolean }) {
  const { t, locale } = useI18n();
  const steps = run.steps.filter((step) => !hidden.has(step.kind));
  const hiddenCount = run.steps.length - steps.length;
  const counts = TRACE_KINDS.map((kind) => ({ kind, count: run.steps.filter((step) => step.kind === kind).length })).filter(
    (entry) => entry.count > 0,
  );
  return (
    <li>
      <details open={defaultOpen} className={cn("group/run rounded-lg ring-1", live ? "bg-soft/60 ring-line-2" : "bg-white ring-ink-150")}>
        <summary className="flex items-start gap-2 rounded-lg px-3 py-2.5 focus-visible:outline-2 focus-visible:outline-focus">
          <div className="min-w-0 flex-1">
            <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-ink-950">
              {t.trace.actions[run.action] ?? run.action}
              {live ? (
                <Badge tone="brand" icon={<span className="size-1.5 animate-pulse-dot rounded-full bg-navy" />}>
                  {t.common.live}
                </Badge>
              ) : null}
              {run.status === "error" && run.error ? (
                <Badge tone="critical" className="font-mono">
                  {run.error.code}
                </Badge>
              ) : null}
            </p>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[0.7rem] text-ink-500">
              <span className="font-mono">{run.action}</span>
              <span>·</span>
              <time dateTime={run.startedAt}>{formatTime(run.startedAt, locale)}</time>
              {run.durationMs !== null ? (
                <>
                  <span>·</span>
                  <span className="tabular-nums">{formatDuration(run.durationMs, locale)}</span>
                </>
              ) : null}
              <span>·</span>
              <span>{t.trace.steps(run.steps.length)}</span>
              {run.streamed ? <span className="text-navy">· {t.trace.streamed}</span> : null}
            </p>
            {counts.length > 0 ? (
              <p aria-hidden className="mt-1.5 flex h-1.5 gap-0.5 overflow-hidden rounded-full">
                {counts.map((entry) => (
                  <span key={entry.kind} style={{ flexGrow: entry.count, backgroundColor: KIND_STYLE[entry.kind].color }} />
                ))}
              </p>
            ) : null}
          </div>
          <ChevronDown aria-hidden className="mt-0.5 size-4 shrink-0 text-ink-400 transition-transform group-open/run:rotate-180" />
        </summary>
        <div className="border-t border-ink-150 px-3 pt-3 pb-2">
          {run.status === "running" && run.steps.length === 0 ? <Spinner label={t.trace.running} className="mb-2" /> : null}
          {run.status === "error" && run.error ? <p className="mb-3 text-[0.8rem] text-critical-ink">{run.error.message}</p> : null}
          <ol aria-label={t.trace.steps(steps.length)}>
            {steps.map((step, index) => (
              <StepItem key={`${run.id}-${step.id}-${index}`} step={step} last={index === steps.length - 1} />
            ))}
          </ol>
          {hiddenCount > 0 ? <p className="mt-1 text-[0.7rem] text-ink-500">{t.trace.hiddenSteps(hiddenCount)}</p> : null}
        </div>
      </details>
    </li>
  );
}

/** Every request's TraceSteps, newest first, live while a request streams. */
export function TracePanel({ className }: { className?: string }) {
  const { t } = useI18n();
  const session = useSession();
  const [hidden, setHidden] = useState<Set<TraceKind>>(() => new Set());
  const toggle = (kind: TraceKind) =>
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  const live = session.liveRun;
  const latestLive = live?.steps[live.steps.length - 1];

  return (
    <section aria-labelledby="trace-title" className={cn("rounded-xl bg-surface shadow-card ring-1 ring-ink-200/80", className)}>
      <header className="flex items-start gap-2 border-b border-ink-150 px-4 py-3.5">
        <Activity aria-hidden className="mt-0.5 size-4 text-navy" />
        <div className="min-w-0 flex-1">
          <h2 id="trace-title" className="text-[0.95rem] font-semibold tracking-tight text-ink-950">
            {t.trace.title}
          </h2>
          <p className="mt-0.5 text-xs leading-snug text-ink-500">{t.trace.subtitle}</p>
        </div>
        {session.runs.length > 0 ? (
          <Button size="sm" variant="ghost" onClick={session.clearRuns} aria-label={t.trace.clear} title={t.trace.clear}>
            <Trash2 aria-hidden className="size-4" />
          </Button>
        ) : null}
      </header>
      <div className="border-b border-ink-150 px-4 py-2.5">
        <div role="group" aria-label={t.trace.filter} className="flex flex-wrap gap-1.5">
          {TRACE_KINDS.map((kind) => {
            const on = !hidden.has(kind);
            return (
              <button
                key={kind}
                type="button"
                aria-pressed={on}
                onClick={() => toggle(kind)}
                title={t.trace.kindHelp[kind]}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[0.7rem] font-medium ring-1 transition focus-visible:outline-2 focus-visible:outline-focus",
                  on ? "bg-white text-ink-800 ring-ink-200" : "bg-ink-50 text-ink-400 line-through ring-ink-150",
                )}
              >
                <span aria-hidden className="size-2 rounded-full" style={{ backgroundColor: on ? KIND_STYLE[kind].color : "var(--color-ink-300)" }} />
                {t.trace.kinds[kind]}
              </button>
            );
          })}
        </div>
        <details className="mt-2">
          <summary className="text-[0.7rem] font-medium text-ink-500 hover:text-ink-800">{t.trace.legend}</summary>
          <dl className="mt-2 space-y-1.5">
            {TRACE_KINDS.map((kind) => (
              <div key={kind} className="flex items-start gap-2 text-xs">
                <span
                  aria-hidden
                  className={cn("mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full [&>svg]:size-2.5", KIND_STYLE[kind].ink)}
                  style={{ backgroundColor: KIND_STYLE[kind].color }}
                >
                  {KIND_STYLE[kind].icon}
                </span>
                <dt className="font-semibold text-ink-800">{t.trace.kinds[kind]}</dt>
                <dd className="text-ink-600">{t.trace.kindHelp[kind]}</dd>
              </div>
            ))}
          </dl>
        </details>
      </div>
      <div className="px-3 py-3">
        <p className="sr-only" aria-live="polite">
          {latestLive ? `${latestLive.actor} : ${latestLive.title}` : ""}
        </p>
        {!live && session.runs.length === 0 ? (
          <p className="px-1 py-6 text-center text-sm text-ink-500">{t.trace.empty}</p>
        ) : (
          <ol className="space-y-2">
            {live ? <RunCard key={live.id} run={live} hidden={hidden} defaultOpen live /> : null}
            {session.runs.map((run, index) => (
              <RunCard key={run.id} run={run} hidden={hidden} defaultOpen={!live && index === 0} live={false} />
            ))}
          </ol>
        )}
      </div>
      <p className="border-t border-ink-150 px-4 py-3 text-[0.7rem] leading-snug text-ink-500">{t.trace.footnote}</p>
    </section>
  );
}
