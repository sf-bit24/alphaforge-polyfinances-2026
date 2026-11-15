"use client";

import { CircleCheck, TriangleAlert } from "lucide-react";
import type { CollectorOutcome, RunOutcome } from "@/lib/contract/collect";
import type { ExecutionDetail, ExecutionSummary } from "@/lib/contract/schemas";
import { callMessages, describeExecution } from "@/lib/client/api";
import { useAsync } from "@/lib/client/use-async";
import { formatNumber } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { ErrorNotice } from "@/components/ui/error-notice";
import { JsonView } from "@/components/ui/json-view";
import { Spinner } from "@/components/ui/spinner";

/** A4 or A5 status from the run output: a failed collector does not fail the run. */
export function CollectorBadge({ outcome }: { outcome: CollectorOutcome | null | undefined }) {
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

function FailureNote({ error, cause }: Pick<ExecutionDetail, "error" | "cause">) {
  const { t } = useI18n();
  return (
    <div className="rounded-lg bg-critical-wash px-3 py-2 ring-1 ring-critical/25">
      {error ? (
        <p>
          <span className="font-semibold text-critical-ink">{t.collect.error} : </span>
          <span className="font-mono">{error}</span>
        </p>
      ) : null}
      {cause ? (
        <p className="mt-1 text-ink-700">
          <span className="font-semibold">{t.collect.cause} : </span>
          {cause}
        </p>
      ) : null}
    </div>
  );
}

function CollectorCards({ outcome }: { outcome: RunOutcome }) {
  const { t } = useI18n();
  return (
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
  );
}

/** Documents A6 wrote (each opens in the reader) and those it rejected, with the reason. */
function CuratedDocuments({ curated, onOpenDoc }: { curated: NonNullable<RunOutcome["curated"]>; onOpenDoc: (key: string) => void }) {
  const { t } = useI18n();
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div>
        <p className="mb-1.5 text-xs font-semibold tracking-wide text-ink-600 uppercase">
          {t.collect.writtenDocs} ({curated.written.length})
        </p>
        <ul className="space-y-1">
          {curated.written.map((key) => (
            <li key={key}>
              <button
                type="button"
                onClick={() => onOpenDoc(key)}
                className="rounded text-left font-mono text-xs break-all text-navy underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-focus"
              >
                {key}
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <p className="mb-1.5 text-xs font-semibold tracking-wide text-ink-600 uppercase">
          {t.collect.rejectedDocs} ({curated.rejected.length})
        </p>
        <ul className="space-y-1.5">
          {curated.rejected.map((item) => (
            <li key={item.key} className="text-xs">
              <span className="block font-mono break-all text-ink-600">{item.key}</span>
              <span className="text-ink-800">{item.reason}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function RunOutcomeView({ outcome, onOpenDoc }: { outcome: RunOutcome; onOpenDoc: (key: string) => void }) {
  const { t } = useI18n();
  return (
    <>
      <CollectorCards outcome={outcome} />
      <p className="text-xs text-ink-500">{t.collect.collectorNote}</p>
      {outcome.curated ? <CuratedDocuments curated={outcome.curated} onOpenDoc={onOpenDoc} /> : null}
    </>
  );
}

function InputOutput({ input, output }: Pick<ExecutionDetail, "input" | "output">) {
  const { t } = useI18n();
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <div>
        <p className="mb-1 text-xs font-semibold tracking-wide text-ink-600 uppercase">{t.collect.input}</p>
        <JsonView value={input ?? {}} maxHeight="max-h-40" />
      </div>
      {output ? (
        <div>
          <p className="mb-1 text-xs font-semibold tracking-wide text-ink-600 uppercase">{t.collect.output}</p>
          <JsonView value={output} maxHeight="max-h-40" />
        </div>
      ) : null}
    </div>
  );
}

export function ExecutionDetails({ execution, onOpenDoc }: { execution: ExecutionSummary; onOpenDoc: (key: string) => void }) {
  const { t, locale } = useI18n();
  const finished = execution.status !== "RUNNING";
  const { data, error, loading } = useAsync(`${execution.execution_arn}|${execution.status}`, (signal) =>
    describeExecution(execution.execution_arn, { locale, signal, messages: callMessages(t) }),
  );
  if (loading) return <Spinner label={t.common.loading} />;
  if (error) return <ErrorNotice error={error} compact />;
  const detail = data?.execution;
  if (!detail) return null;
  return (
    <div className="space-y-4 text-sm">
      {!finished ? <p className="text-ink-500">{t.collect.pending}</p> : null}
      {detail.error || detail.cause ? <FailureNote error={detail.error} cause={detail.cause} /> : null}
      {detail.outcome ? <RunOutcomeView outcome={detail.outcome} onOpenDoc={onOpenDoc} /> : null}
      <InputOutput input={detail.input} output={detail.output} />
    </div>
  );
}
