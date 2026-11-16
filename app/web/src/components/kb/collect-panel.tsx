"use client";

import { Ban, CircleAlert, CircleCheck, Hourglass, LoaderCircle, Play, RefreshCw } from "lucide-react";
import { useEffect, useEffectEvent, useId, useRef, useState, type ReactNode } from "react";
import type { CollectRequest } from "@/lib/contract/requests";
import type { ExecutionStatus, ExecutionSummary } from "@/lib/contract/schemas";
import { useAccount } from "@/lib/client/account";
import { ApiError, callMessages, listExecutions, startCollection, type CallOptions } from "@/lib/client/api";
import { useHealth } from "@/lib/client/health";
import { useAsync } from "@/lib/client/use-async";
import { formatDateTime, formatDuration } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Spinner } from "@/components/ui/spinner";
import { CollectorBadge, ExecutionDetails } from "./execution-details";

const TICKER = /^[A-Za-z0-9.\-^=]{1,15}$/;
const POLL_INTERVAL_MS = 3000;
const COLUMNS = ["run", "status", "started", "duration", "press", "data", "written", "rejected", "ingestion"] as const;

function sevenDaysAgo(): string {
  const date = new Date();
  date.setDate(date.getDate() - 7);
  return date.toISOString().slice(0, 10);
}

/** Tickers typed in the field, separated by commas or spaces. */
function parseTickers(text: string): string[] {
  return text
    .split(/[,\s]+/)
    .map((ticker) => ticker.trim())
    .filter(Boolean);
}

function collectRequestOf(since: string, tickers: string[]): CollectRequest {
  return { ...(since ? { since } : {}), ...(tickers.length ? { tickers: tickers.map((ticker) => ticker.toUpperCase()) } : {}) };
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

/** Starting a run: the request in flight, its error, and the name of the run it started. */
function useCollectionStart() {
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<ApiError | null>(null);
  const [startedName, setStartedName] = useState<string | null>(null);

  const start = async (input: CollectRequest, options: CallOptions, onStarted: (execution: ExecutionSummary) => void) => {
    setStarting(true);
    setStartError(null);
    try {
      const result = await startCollection(input, options);
      setStartedName(result.execution.name);
      onStarted(result.execution);
    } catch (caught) {
      setStartError(caught instanceof ApiError ? caught : new ApiError("internal", String(caught)));
    } finally {
      setStarting(false);
    }
  };

  return { starting, startError, startedName, dismissError: () => setStartError(null), start };
}

/** Recent executions and the one opened below the table; the list reloads while a run is in progress. */
function useRecentExecutions(local: boolean, onWritten: () => void, options: (signal?: AbortSignal) => CallOptions) {
  const [tick, setTick] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
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
    const timer = window.setInterval(() => setTick((value) => value + 1), POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [running]);

  const refresh = () => setTick((value) => value + 1);
  return { list, error, running, selected, setSelected, refresh };
}

type RecentExecutionsState = ReturnType<typeof useRecentExecutions>;

function SinceField({ id, value, onChange }: { id: string; value: string; onChange: (value: string) => void }) {
  const { t } = useI18n();
  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium text-ink-900">
        {t.collect.since}
      </label>
      <input
        id={id}
        type="date"
        value={value}
        max={new Date().toISOString().slice(0, 10)}
        onChange={(event) => onChange(event.target.value)}
        aria-describedby={`${id}-help`}
        className="mt-1 block w-full rounded-lg border-0 bg-white px-3 py-2 text-sm ring-1 ring-ink-300 ring-inset focus:ring-2 focus:ring-navy focus:outline-none"
      />
      <p id={`${id}-help`} className="mt-1 text-xs text-ink-500">
        {t.collect.sinceHelp}
      </p>
    </div>
  );
}

function TickersField({ id, value, invalid, onChange }: { id: string; value: string; invalid: boolean; onChange: (value: string) => void }) {
  const { t } = useI18n();
  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium text-ink-900">
        {t.collect.tickers}
      </label>
      <input
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="RY.TO, AAPL, BTC-USD"
        aria-invalid={invalid || undefined}
        aria-describedby={`${id}-help`}
        className="mt-1 block w-full rounded-lg border-0 bg-white px-3 py-2 font-mono text-sm uppercase ring-1 ring-ink-300 ring-inset placeholder:normal-case focus:ring-2 focus:ring-navy focus:outline-none aria-[invalid=true]:ring-2 aria-[invalid=true]:ring-critical"
      />
      <p id={`${id}-help`} className={cn("mt-1 text-xs", invalid ? "text-critical-ink" : "text-ink-500")}>
        {invalid ? t.collect.tickersInvalid : t.collect.tickersHelp}
      </p>
    </div>
  );
}

interface CollectFormProps {
  ids: { since: string; tickers: string };
  since: string;
  tickers: string;
  tickersInvalid: boolean;
  starting: boolean;
  /** Sign-in on and the account is not in the `admin` group: the run cannot be started. */
  locked: boolean;
  onSinceChange: (value: string) => void;
  onTickersChange: (value: string) => void;
  onStart: () => void;
}

function CollectForm({ ids, since, tickers, tickersInvalid, starting, locked, onSinceChange, onTickersChange, onStart }: CollectFormProps) {
  const { t } = useI18n();
  return (
    <div className="grid gap-4 border-b border-ink-150 px-5 py-4 md:grid-cols-[12rem_minmax(0,1fr)_auto] md:items-end">
      <SinceField id={ids.since} value={since} onChange={onSinceChange} />
      <TickersField id={ids.tickers} value={tickers} invalid={tickersInvalid} onChange={onTickersChange} />
      <Button onClick={onStart} loading={starting} disabled={tickersInvalid || locked} icon={<Play aria-hidden className="size-4" />} className="md:mb-5">
        {starting ? t.collect.starting : t.collect.start}
      </Button>
      {locked ? <p className="text-xs text-ink-500 md:col-span-3">{t.auth.adminOnly}</p> : null}
    </div>
  );
}

function StartFeedback({ error, startedName, onDismiss }: { error: ApiError | null; startedName: string | null; onDismiss: () => void }) {
  const { t } = useI18n();
  return (
    <>
      {error ? <ErrorNotice className="mx-5 mt-4" error={error} onDismiss={onDismiss} /> : null}
      {startedName && !error ? (
        <p role="status" className="mx-5 mt-4 rounded-lg bg-soft px-3 py-2 text-sm text-navy ring-1 ring-line">
          {t.collect.started(startedName)}
        </p>
      ) : null}
    </>
  );
}

/** The state of the base update in words; a state without a label stays as is. */
function ingestionLabel(status: string | null | undefined, labels: Record<string, string>): string {
  return status ? (labels[status] ?? status) : "—";
}

function ExecutionRow({ execution, open, onSelect }: { execution: ExecutionSummary; open: boolean; onSelect: (arn: string | null) => void }) {
  const { t, locale } = useI18n();
  const duration = execution.stop_date ? Date.parse(execution.stop_date) - Date.parse(execution.start_date) : null;
  return (
    <tr className={cn("border-b border-ink-150 align-middle", open && "bg-soft")}>
      <td className="py-2 pr-3">
        <button
          type="button"
          onClick={() => onSelect(open ? null : execution.execution_arn)}
          aria-expanded={open}
          aria-label={t.collect.detailsOf(execution.name)}
          title={execution.name}
          className="rounded font-mono text-xs text-navy underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-focus"
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
      <td className="py-2 text-ink-700">{ingestionLabel(execution.outcome?.ingestion?.status, t.collect.ingestionStatuses)}</td>
    </tr>
  );
}

function ExecutionsTable({ executions, selected, onSelect }: { executions: ExecutionSummary[]; selected: string | null; onSelect: (arn: string | null) => void }) {
  const { t } = useI18n();
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] text-sm">
        <thead>
          <tr className="border-b border-ink-200 text-left text-xs text-ink-600">
            {COLUMNS.map((column) => t.collect.columns[column]).map((label) => (
              <th key={label} scope="col" className="py-2 pr-3 font-semibold whitespace-nowrap">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {executions.map((execution) => (
            <ExecutionRow key={execution.execution_arn} execution={execution} open={selected === execution.execution_arn} onSelect={onSelect} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecentExecutions({ executions, onOpenDoc }: { executions: RecentExecutionsState; onOpenDoc: (key: string) => void }) {
  const { t } = useI18n();
  const { list, error, running, selected, setSelected } = executions;
  const opened = selected && list ? list.executions.find((candidate) => candidate.execution_arn === selected) : undefined;
  return (
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
      {list && list.executions.length > 0 ? <ExecutionsTable executions={list.executions} selected={selected} onSelect={setSelected} /> : null}
      {opened ? (
        <div className="mt-4 rounded-xl bg-white p-4 ring-1 ring-ink-200">
          <p className="mb-3 font-mono text-xs break-all text-ink-500">{opened.execution_arn}</p>
          <ExecutionDetails execution={opened} onOpenDoc={onOpenDoc} />
        </div>
      ) : null}
    </div>
  );
}

function RefreshButton({ onRefresh }: { onRefresh: () => void }) {
  const { t } = useI18n();
  return <Button size="sm" variant="ghost" onClick={onRefresh} aria-label={t.common.refresh} icon={<RefreshCw aria-hidden className="size-4" />} />;
}

/** Start a collection run of the general base and follow recent executions. */
export function CollectPanel({ onWritten, onOpenDoc }: { onWritten: () => void; onOpenDoc: (key: string) => void }) {
  const { t, locale } = useI18n();
  const { health } = useHealth(locale);
  const sinceId = useId();
  const tickersId = useId();
  const [since, setSince] = useState(sevenDaysAgo);
  const [tickers, setTickers] = useState("");
  const starter = useCollectionStart();
  const local = health?.mode === "local";
  const account = useAccount();
  const locked = account.status === "signed_in" && !account.user.admin;
  const options = (signal?: AbortSignal) => ({ locale, signal, messages: callMessages(t) });
  const executions = useRecentExecutions(local, onWritten, options);
  const tickerList = parseTickers(tickers);
  const tickersInvalid = tickerList.some((ticker) => !TICKER.test(ticker));

  const start = () => {
    if (tickersInvalid) return;
    void starter.start(collectRequestOf(since, tickerList), options(), (execution) => {
      executions.setSelected(execution.execution_arn);
      executions.refresh();
    });
  };

  return (
    <Card>
      <CardHeader title={t.collect.title} subtitle={t.collect.lead} actions={!local ? <RefreshButton onRefresh={executions.refresh} /> : null} />
      {local ? (
        <p className="px-5 py-5 text-sm text-ink-600">{t.collect.unavailableLocal}</p>
      ) : (
        <>
          <CollectForm
            ids={{ since: sinceId, tickers: tickersId }}
            since={since}
            tickers={tickers}
            tickersInvalid={tickersInvalid}
            starting={starter.starting}
            locked={locked}
            onSinceChange={setSince}
            onTickersChange={setTickers}
            onStart={start}
          />
          <StartFeedback error={starter.startError} startedName={starter.startedName} onDismiss={starter.dismissError} />
          <RecentExecutions executions={executions} onOpenDoc={onOpenDoc} />
        </>
      )}
    </Card>
  );
}
