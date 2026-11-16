"use client";

import { Bot, Calculator, ChartLine, ChevronDown, ExternalLink, ListChecks, PenLine, Save, ShieldCheck, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import type { Source, TraceKind, TraceStep } from "@/lib/contract/schemas";
import type { TraceRun } from "@/lib/client/session-store";
import { useSession } from "@/lib/client/session";
import { formatDate, formatDateTime, formatTime } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/components/ui/cn";
import { Spinner } from "@/components/ui/spinner";

/** Categorical slots 1 to 6 in fixed order; icons sit in white or near-black by fill luminance. */
export const KIND_STYLE: Record<TraceKind, { color: string; icon: ReactNode; ink: string }> = {
  deterministic: { color: "var(--color-kind-deterministic)", icon: <Calculator aria-hidden className="size-3.5" />, ink: "text-white" },
  agent: { color: "var(--color-kind-agent)", icon: <Bot aria-hidden className="size-3.5" />, ink: "text-white" },
  model: { color: "var(--color-kind-model)", icon: <PenLine aria-hidden className="size-3.5" />, ink: "text-ink-950" },
  tool: { color: "var(--color-kind-tool)", icon: <ChartLine aria-hidden className="size-3.5" />, ink: "text-ink-950" },
  storage: { color: "var(--color-kind-storage)", icon: <Save aria-hidden className="size-3.5" />, ink: "text-ink-950" },
  guardrail: { color: "var(--color-kind-guardrail)", icon: <ShieldCheck aria-hidden className="size-3.5" />, ink: "text-white" },
};

/** A web page can be opened; any other resource is a key the investor has no use for. */
function webLink(resource: string): string | null {
  return /^https?:\/\//i.test(resource) ? resource : null;
}

/** A source as the investor reads it: its title and its dates, and a link when it is a web page. */
export function SourceLine({ source }: { source: Source }) {
  const { t, locale } = useI18n();
  const dates = [
    source.observed_at ? `${t.sourcesBlock.observed} ${formatDate(source.observed_at, locale)}` : null,
    source.published_at ? `${t.sourcesBlock.published} ${formatDate(source.published_at, locale)}` : null,
    source.retrieved_at ? `${t.sourcesBlock.retrieved} ${formatDate(source.retrieved_at, locale)}` : null,
  ].filter(Boolean);
  const link = webLink(source.resource);
  return (
    <li className="text-xs leading-snug text-ink-700">
      <span className="font-medium text-ink-900">{source.title}</span>
      {link ? (
        <a
          href={link}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-1.5 inline-flex items-center gap-0.5 text-[0.7rem] font-medium text-navy hover:underline focus-visible:outline-2 focus-visible:outline-focus"
        >
          {t.trace.viewSource}
          <ExternalLink aria-hidden className="size-3" />
        </a>
      ) : null}
      {dates.length ? <span className="block text-[0.68rem] text-ink-500">{dates.join(" · ")}</span> : null}
    </li>
  );
}

function StepSources({ sources }: { sources: Source[] }) {
  const { t } = useI18n();
  return (
    <div className="mt-2 rounded-md bg-soft px-2.5 py-1.5 ring-1 ring-line">
      <p className="text-[0.65rem] font-semibold tracking-wide text-navy uppercase">{t.trace.sources}</p>
      <ul className="mt-0.5 space-y-1">
        {sources.map((source) => (
          <SourceLine key={source.id} source={source} />
        ))}
      </ul>
    </div>
  );
}

function StepItem({ step, last }: { step: TraceStep; last: boolean }) {
  const { t } = useI18n();
  const style = KIND_STYLE[step.kind];
  return (
    <li className="animate-fade-in relative pb-4 pl-9 last:pb-1">
      {!last ? <span aria-hidden className="absolute top-7 bottom-0 left-[11px] w-px bg-ink-150" /> : null}
      <span
        aria-hidden
        className={cn("absolute top-0 left-0 flex size-6 items-center justify-center rounded-full ring-2 ring-white", style.ink)}
        style={{ backgroundColor: style.color }}
        title={t.trace.kinds[step.kind]}
      >
        {style.icon}
      </span>
      <p className="text-sm leading-snug font-medium text-ink-950">{step.title}</p>
      {step.detail ? <p className="mt-0.5 text-[0.8rem] leading-snug break-words text-ink-600">{step.detail}</p> : null}
      {step.sources.length > 0 ? <StepSources sources={step.sources} /> : null}
    </li>
  );
}

function RunSummary({ run, live }: { run: TraceRun; live: boolean }) {
  const { t, locale } = useI18n();
  return (
    <summary className="flex items-start gap-2 rounded-lg px-3 py-2.5 focus-visible:outline-2 focus-visible:outline-focus">
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-ink-950">
          {t.trace.actions[run.action] ?? t.trace.otherAction}
          {live ? (
            <Badge tone="brand" icon={<span className="size-1.5 animate-pulse-dot rounded-full bg-navy" />}>
              {t.common.live}
            </Badge>
          ) : null}
          {run.status === "error" ? <Badge tone="critical">{t.trace.failed}</Badge> : null}
        </p>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[0.7rem] text-ink-500">
          <time dateTime={run.startedAt} title={formatDateTime(run.startedAt, locale)}>
            {formatTime(run.startedAt, locale)}
          </time>
          <span>·</span>
          <span>{t.trace.steps(run.steps.length)}</span>
        </p>
      </div>
      <ChevronDown aria-hidden className="mt-0.5 size-4 shrink-0 text-ink-400 transition-transform group-open/run:rotate-180" />
    </summary>
  );
}

function RunCard({ run, defaultOpen, live }: { run: TraceRun; defaultOpen: boolean; live: boolean }) {
  const { t } = useI18n();
  return (
    <li>
      <details open={defaultOpen} className={cn("group/run rounded-lg ring-1", live ? "bg-soft/60 ring-line-2" : "bg-white ring-ink-150")}>
        <RunSummary run={run} live={live} />
        <div className="border-t border-ink-150 px-3 pt-3 pb-2">
          {run.status === "running" && run.steps.length === 0 ? <Spinner label={t.trace.running} className="mb-2" /> : null}
          {run.status === "error" ? <p className="mb-3 text-[0.8rem] text-critical-ink">{t.trace.failedText}</p> : null}
          <ol aria-label={t.trace.steps(run.steps.length)}>
            {run.steps.map((step, index) => (
              <StepItem key={`${run.id}-${step.id}-${index}`} step={step} last={index === run.steps.length - 1} />
            ))}
          </ol>
        </div>
      </details>
    </li>
  );
}

function TraceHeader({ canClear, onClear }: { canClear: boolean; onClear: () => void }) {
  const { t } = useI18n();
  return (
    <header className="flex items-start gap-2 border-b border-ink-150 px-4 py-3.5">
      <ListChecks aria-hidden className="mt-0.5 size-4 text-navy" />
      <div className="min-w-0 flex-1">
        <h2 id="trace-title" className="text-[0.95rem] font-semibold tracking-tight text-ink-950">
          {t.trace.title}
        </h2>
        <p className="mt-0.5 text-xs leading-snug text-ink-500">{t.trace.subtitle}</p>
      </div>
      {canClear ? (
        <Button size="sm" variant="ghost" onClick={onClear} aria-label={t.trace.clear} title={t.trace.clear}>
          <Trash2 aria-hidden className="size-4" />
        </Button>
      ) : null}
    </header>
  );
}

/** The live run first, then the stored runs, newest first; the newest is open. */
function RunList({ live, runs }: { live: TraceRun | null; runs: TraceRun[] }) {
  return (
    <ol className="space-y-2">
      {live ? <RunCard key={live.id} run={live} defaultOpen live /> : null}
      {runs.map((run, index) => (
        <RunCard key={run.id} run={run} defaultOpen={!live && index === 0} live={false} />
      ))}
    </ol>
  );
}

/** How Yan worked on each request, newest first, live while a request streams. */
export function TracePanel({ className }: { className?: string }) {
  const { t } = useI18n();
  const session = useSession();
  const live = session.liveRun;
  const latestLive = live?.steps[live.steps.length - 1];

  return (
    <section aria-labelledby="trace-title" className={cn("rounded-xl bg-surface shadow-card ring-1 ring-ink-200/80", className)}>
      <TraceHeader canClear={session.runs.length > 0} onClear={session.clearRuns} />
      <div className="px-3 py-3">
        <p className="sr-only" aria-live="polite">
          {latestLive ? latestLive.title : ""}
        </p>
        {!live && session.runs.length === 0 ? (
          <p className="px-1 py-6 text-center text-sm text-ink-500">{t.trace.empty}</p>
        ) : (
          <RunList live={live} runs={session.runs} />
        )}
      </div>
      <p className="border-t border-ink-150 px-4 py-3 text-[0.7rem] leading-snug text-ink-500">{t.trace.footnote}</p>
    </section>
  );
}
