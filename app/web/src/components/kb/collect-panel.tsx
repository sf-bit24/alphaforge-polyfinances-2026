"use client";

import { Ban, CircleAlert, CircleCheck, Hourglass, LoaderCircle, Play, RefreshCw, TriangleAlert } from "lucide-react";
import { useEffect, useEffectEvent, useId, useRef, useState, type ReactNode } from "react";
import type { CollectorOutcome } from "@/lib/contract/collect";
import type { ExecutionStatus, ExecutionSummary } from "@/lib/contract/schemas";
import { ApiError, describeExecution, listExecutions, startCollection } from "@/lib/client/api";
import { useHealth } from "@/lib/client/health";
import { useAsync } from "@/lib/client/use-async";
import { formatDateTime, formatDuration, formatNumber } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { JsonView } from "@/components/ui/json-view";
import { Spinner } from "@/components/ui/spinner";

const TICKER = /^[A-Za-z0-9.\-^=]{1,15}$/;

function sevenDaysAgo(): string {
  const date = new Date();
  date.setDate(date.getDate() - 7);
  return date.toISOString().slice(0, 10);
}

const STATUS_STYLE: Record<ExecutionStatus, { tone: "brand" | "good" | "critical" | "warning" | "neutral"; icon: ReactNode }> = {
  RUNNING: { tone: "brand", icon: <LoaderCircle aria-hidden className="size-3 animate-spin" /> },
  SUCCEEDED: { tone: "good", icon: <CircleCheck aria-hidden className="size-3" /> },
  FAILED: { tone: "critical", icon: <CircleAlert aria-hidden className="size-3" /> },
  TIMED_OUT: { tone: "warning", icon: <Hourglass aria-hidden className="size-3" /> },
  ABORTED: { tone: "neutral", icon: <Ban aria-hidden className="size-3" /> },
  PENDING_REDRIVE: { tone: "warning", icon: <Hourglass aria-hidden className="size-3" /> },
};

function StatusBadge({ status }: { status: ExecutionStatus }) {
  const { t } = useI18n();
  const style = STATUS_STYLE[status];
  return (
    <Badge tone={style.tone} icon={style.icon}>
      {t.collect.statuses[status]}
    </Badge>
  );
}

/** A4 or A5 status from the run output: a failed collector does not fail the run. */
function CollectorBadge({ outcome }: { outcome: CollectorOutcome | null | undefined }) {
  const { t, locale } = useI18n();
  if (!outcome) return <span className="text-ink-400">—</span>;
  if (outcome.status === "ok") {
    return (
      <Badge tone="good" icon={<CircleCheck aria-hidden className="size-3" />}>
        {t.collect.collectorOk(outcome.items === null ? "?" : formatNumber(outcome.items, locale))}
      </Badge>
    );
  }
  return (
    <Badge tone="critical" icon={<TriangleAlert aria-hidden className="size-3" />} title={outcome.error ?? undefined}>
      {t.collect.collectorError}
    </Badge>
  );
}

function ExecutionDetails({ execution, onOpenDoc }: { execution: ExecutionSummary; onOpenDoc: (key: string) => void }) {
  const { t, locale } = useI18n();
  const finished = execution.status !== "RUNNING";
  const { data, error, loading } = useAsync(`${execution.execution_arn}|${execution.status}`, (signal) =>
    describeExecution(execution.execution_arn, {
      locale,
      signal,
      messages: { network: t.errors.network, invalidResponse: t.errors.invalidResponse, noResult: t.errors.noResult },
    }),
  );
  if (loading) return <Spinner label={t.common.loading} />;
  if (error) return <ErrorNotice error={error} compact />;
  const detail = data?.execution;
  if (!detail) return null;
  const outcome = detail.outcome;
  return (
    <div className="space-y-4 text-sm">
      {!finished ? <p className="text-ink-500">{t.collect.pending}</p> : null}
      {detail.error || detail.cause ? (
        <div className="rounded-lg bg-critical-wash px-3 py-2 ring-1 ring-critical/25">
          {detail.error ? (
            <p>
              <span className="font-semibold text-critical-ink">{t.collect.error} : </span>
              <span className="font-mono">{detail.error}</span>
            </p>
          ) : null}
          {detail.cause ? (
            <p className="mt-1 text-ink-700">
              <span className="font-semibold">{t.collect.cause} : </span>
              {detail.cause}
            </p>
          ) : null}
        </div>
      ) : null}
      {outcome ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              { label: t.collect.columns.press, value: outcome.press },
              { label: t.collect.columns.data, value: outcome.data },
            ].map((collector) => (
              <div key={collector.label} className="rounded-lg bg-ink-50 px-3 py-2.5 ring-1 ring-ink-150">
                <p className="flex items-center justify-between gap-2 font-medium text-ink-900">
                  {collector.label}
                  <CollectorBadge outcome={collector.value} />
                </p>
                {collector.value?.error ? <p className="mt-1 text-xs text-critical-ink">{collector.value.error}</p> : null}
              </div>
            ))}
          </div>
          <p className="text-xs text-ink-500">{t.collect.collectorNote}</p>
          {outcome.curated ? (
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <p className="mb-1.5 text-xs font-semibold tracking-wide text-ink-600 uppercase">
                  {t.collect.writtenDocs} ({outcome.curated.written.length})
                </p>
                <ul className="space-y-1">
                  {outcome.curated.written.map((key) => (
                    <li key={key}>
                      <button
                        type="button"
                        onClick={() => onOpenDoc(key)}
                        className="rounded text-left font-mono text-xs break-all text-brand-700 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-brand-500"
                      >
                        {key}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="mb-1.5 text-xs font-semibold tracking-wide text-ink-600 uppercase">
                  {t.collect.rejectedDocs} ({outcome.curated.rejected.length})
                </p>
                <ul className="space-y-1.5">
                  {outcome.curated.rejected.map((item) => (
                    <li key={item.key} className="text-xs">
                      <span className="block font-mono break-all text-ink-600">{item.key}</span>
                      <span className="text-ink-800">{item.reason}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : null}
        </>
      ) : null}
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <p className="mb-1 text-xs font-semibold tracking-wide text-ink-600 uppercase">{t.collect.input}</p>
          <JsonView value={detail.input ?? {}} maxHeight="max-h-40" />
        </div>
        {detail.output ? (
          <div>
            <p className="mb-1 text-xs font-semibold tracking-wide text-ink-600 uppercase">{t.collect.output}</p>
            <JsonView value={detail.output} maxHeight="max-h-40" />
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** Start a collection run of the general base and follow recent executions. */
export function CollectPanel({ onWritten, onOpenDoc }: { onWritten: () => void; onOpenDoc: (key: string) => void }) {
  const { t, locale } = useI18n();
  const { health } = useHealth(locale);
  const sinceId = useId();
  const tickersId = useId();
  const [since, setSince] = useState(sevenDaysAgo);
  const [tickers, setTickers] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<ApiError | null>(null);
  const [startedName, setStartedName] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const local = health?.mode === "local";

  const options = (signal?: AbortSignal) => ({
    locale,
    signal,
    messages: { network: t.errors.network, invalidResponse: t.errors.invalidResponse, noResult: t.errors.noResult },
  });
  const { data, error, previous } = useAsync(local ? null : `executions|${tick}`, (signal) => listExecutions(options(signal)));
  const list = data ?? previous;
  const running = list?.executions.some((execution) => execution.status === "RUNNING") ?? false;

  // Poll while a run is in progress; when it ends, the general base has new documents.
  const notifyWritten = useEffectEvent(onWritten);
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && !running) notifyWritten();
    wasRunning.current = running;
    if (!running) return;
    const timer = window.setInterval(() => setTick((value) => value + 1), 3000);
    return () => window.clearInterval(timer);
  }, [running]);

  const tickerList = tickers
    .split(/[,\s]+/)
    .map((ticker) => ticker.trim())
    .filter(Boolean);
  const tickersInvalid = tickerList.some((ticker) => !TICKER.test(ticker));

  const start = async () => {
    if (tickersInvalid) return;
    setStarting(true);
    setStartError(null);
    try {
      const result = await startCollection(
        { ...(since ? { since } : {}), ...(tickerList.length ? { tickers: tickerList.map((ticker) => ticker.toUpperCase()) } : {}) },
        options(),
      );
      setStartedName(result.execution.name);
      setSelected(result.execution.execution_arn);
      setTick((value) => value + 1);
    } catch (caught) {
      setStartError(caught instanceof ApiError ? caught : new ApiError("internal", String(caught)));
    } finally {
      setStarting(false);
    }
  };

  return (
    <Card>
      <CardHeader
        title={t.collect.title}
        subtitle={t.collect.lead}
        actions={
          !local ? (
            <Button size="sm" variant="ghost" onClick={() => setTick((value) => value + 1)} aria-label={t.common.refresh} icon={<RefreshCw aria-hidden className="size-4" />} />
          ) : null
        }
      />
      {local ? (
        <p className="px-5 py-5 text-sm text-ink-600">{t.collect.unavailableLocal}</p>
      ) : (
        <>
          <div className="grid gap-4 border-b border-ink-150 px-5 py-4 md:grid-cols-[12rem_minmax(0,1fr)_auto] md:items-end">
            <div>
              <label htmlFor={sinceId} className="text-sm font-medium text-ink-900">
                {t.collect.since}
              </label>
              <input
                id={sinceId}
                type="date"
                value={since}
                max={new Date().toISOString().slice(0, 10)}
                onChange={(event) => setSince(event.target.value)}
                aria-describedby={`${sinceId}-help`}
                className="mt-1 block w-full rounded-lg border-0 bg-white px-3 py-2 text-sm ring-1 ring-ink-300 ring-inset focus:ring-2 focus:ring-brand-500 focus:outline-none"
              />
              <p id={`${sinceId}-help`} className="mt-1 text-xs text-ink-500">
                {t.collect.sinceHelp}
              </p>
            </div>
            <div>
              <label htmlFor={tickersId} className="text-sm font-medium text-ink-900">
                {t.collect.tickers}
              </label>
              <input
                id={tickersId}
                value={tickers}
                onChange={(event) => setTickers(event.target.value)}
                placeholder="RY.TO, AAPL, BTC-USD"
                aria-invalid={tickersInvalid || undefined}
                aria-describedby={`${tickersId}-help`}
                className="mt-1 block w-full rounded-lg border-0 bg-white px-3 py-2 font-mono text-sm uppercase ring-1 ring-ink-300 ring-inset placeholder:normal-case focus:ring-2 focus:ring-brand-500 focus:outline-none aria-[invalid=true]:ring-2 aria-[invalid=true]:ring-critical"
              />
              <p id={`${tickersId}-help`} className={cn("mt-1 text-xs", tickersInvalid ? "text-critical-ink" : "text-ink-500")}>
                {tickersInvalid ? t.collect.tickersInvalid : t.collect.tickersHelp}
              </p>
            </div>
            <Button onClick={() => void start()} loading={starting} disabled={tickersInvalid} icon={<Play aria-hidden className="size-4" />} className="md:mb-5">
              {starting ? t.collect.starting : t.collect.start}
            </Button>
          </div>
          {startError ? <ErrorNotice className="mx-5 mt-4" error={startError} onDismiss={() => setStartError(null)} /> : null}
          {startedName && !startError ? (
            <p role="status" className="mx-5 mt-4 rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-800 ring-1 ring-brand-100">
              {t.collect.started(startedName)}
            </p>
          ) : null}
          <div className="px-5 py-4">
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-sm font-semibold text-ink-900">{t.collect.recent}</h3>
              <p className="text-xs text-ink-500">
                {list ? t.collect.machine(list.state_machine.name) : null}
                {running ? ` · ${t.collect.autoRefresh}` : null}
              </p>
            </div>
            {error ? <ErrorNotice error={error} compact /> : null}
            {!list && !error ? <Spinner label={t.common.loading} /> : null}
            {list && list.executions.length === 0 ? <p className="text-sm text-ink-500">{t.collect.none}</p> : null}
            {list && list.executions.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-sm">
                  <thead>
                    <tr className="border-b border-ink-200 text-left text-xs text-ink-600">
                      {[
                        t.collect.columns.run,
                        t.collect.columns.status,
                        t.collect.columns.started,
                        t.collect.columns.duration,
                        t.collect.columns.press,
                        t.collect.columns.data,
                        t.collect.columns.written,
                        t.collect.columns.rejected,
                        t.collect.columns.ingestion,
                      ].map((label) => (
                        <th key={label} scope="col" className="py-2 pr-3 font-semibold whitespace-nowrap">
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {list.executions.map((execution) => {
                      const open = selected === execution.execution_arn;
                      const duration = execution.stop_date ? Date.parse(execution.stop_date) - Date.parse(execution.start_date) : null;
                      return (
                        <tr key={execution.execution_arn} className={cn("border-b border-ink-150 align-middle", open && "bg-brand-50/50")}>
                          <td className="py-2 pr-3">
                            <button
                              type="button"
                              onClick={() => setSelected(open ? null : execution.execution_arn)}
                              aria-expanded={open}
                              aria-label={t.collect.detailsOf(execution.name)}
                              title={execution.name}
                              className="rounded font-mono text-xs text-brand-700 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-brand-500"
                            >
                              {execution.name.slice(0, 13)}…
                            </button>
                          </td>
                          <td className="py-2 pr-3">
                            <StatusBadge status={execution.status} />
                          </td>
                          <td className="py-2 pr-3 whitespace-nowrap text-ink-700">{formatDateTime(execution.start_date, locale)}</td>
                          <td className="py-2 pr-3 whitespace-nowrap text-ink-700 tabular-nums">{duration !== null ? formatDuration(duration, locale) : "—"}</td>
                          <td className="py-2 pr-3">
                            <CollectorBadge outcome={execution.outcome?.press} />
                          </td>
                          <td className="py-2 pr-3">
                            <CollectorBadge outcome={execution.outcome?.data} />
                          </td>
                          <td className="py-2 pr-3 tabular-nums">{execution.outcome?.curated ? execution.outcome.curated.written.length : "—"}</td>
                          <td className="py-2 pr-3 tabular-nums">{execution.outcome?.curated ? execution.outcome.curated.rejected.length : "—"}</td>
                          <td className="py-2 font-mono text-xs">{execution.outcome?.ingestion?.status ?? "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : null}
            {selected && list ? (
              (() => {
                const execution = list.executions.find((candidate) => candidate.execution_arn === selected);
                return execution ? (
                  <div className="mt-4 rounded-xl bg-white p-4 ring-1 ring-ink-200">
                    <p className="mb-3 font-mono text-xs break-all text-ink-500">{execution.execution_arn}</p>
                    <ExecutionDetails execution={execution} onOpenDoc={onOpenDoc} />
                  </div>
                ) : null;
              })()
            ) : null}
          </div>
        </>
      )}
    </Card>
  );
}
