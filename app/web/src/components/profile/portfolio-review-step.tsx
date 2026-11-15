"use client";

import { Bot, CircleCheck, CirclePlus, ListPlus } from "lucide-react";
import { useState } from "react";
import type { PositionInput } from "@/lib/contract/requests";
import type { PortfolioView, UnresolvedItem } from "@/lib/contract/schemas";
import { useSession } from "@/lib/client/session";
import { useI18n } from "@/lib/i18n/provider";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Markdown } from "@/components/ui/markdown";
import { ExposuresView, FxNote } from "./exposures";
import { blankPosition, confirmProblem, PositionsTable, reviewIndex, rowOf, toInput, type Row } from "./review-rows";

function LooseUnresolved({ items, confirming, onAdd }: { items: UnresolvedItem[]; confirming: boolean; onAdd: (raw: string) => void }) {
  const { t } = useI18n();
  return (
    <div className="border-t border-ink-150 px-5 py-4">
      <h3 className="text-sm font-semibold text-ink-900">{t.review.unresolvedTitle}</h3>
      <ul className="mt-2 space-y-2">
        {items.map((item, index) => (
          <li key={`${item.raw}-${index}`} className="flex flex-wrap items-center gap-3 rounded-lg bg-warning-wash px-3 py-2 text-sm ring-1 ring-warning/40">
            <span className="font-mono text-ink-900">{item.raw}</span>
            <span className="flex-1 text-xs text-ink-600">{item.reason}</span>
            <Button size="sm" variant="ghost" onClick={() => onAdd(item.raw)} icon={<ListPlus aria-hidden className="size-4" />} disabled={confirming}>
              {t.review.addAsRow}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ReviewFooter({ problem, confirming, onConfirm }: { problem: string | null; confirming: boolean; onConfirm: () => void }) {
  const { t } = useI18n();
  const session = useSession();
  return (
    <footer className="space-y-3 border-t border-ink-150 px-5 py-4">
      {problem ? (
        <p role="alert" className="text-sm font-medium text-critical-ink">
          {problem}
        </p>
      ) : null}
      {session.error && session.errorAction === "portfolio.confirm" ? (
        <ErrorNotice error={session.error} onRetry={session.retry} onDismiss={session.dismissError} />
      ) : null}
      <div className="flex justify-end">
        <Button size="lg" onClick={onConfirm} loading={confirming} icon={<CircleCheck aria-hidden className="size-4" />}>
          {confirming ? t.review.confirming : t.review.confirm}
        </Button>
      </div>
    </footer>
  );
}

function AgentMessage({ message }: { message: string }) {
  const { t } = useI18n();
  return (
    <Card>
      <div className="flex gap-3 px-5 py-4">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-kind-agent text-white">
          <Bot aria-hidden className="size-4" />
        </span>
        <div className="min-w-0">
          <p className="text-xs font-semibold text-ink-600">A2 · {t.stages.portfolio_review}</p>
          <Markdown className="mt-1">{message}</Markdown>
        </div>
      </div>
    </Card>
  );
}

/** Exposures of A2's reading; once the investor edits a row they are stale until confirmed. */
function ReviewExposures({ portfolio, stale }: { portfolio: PortfolioView; stale: boolean }) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader title={t.exposures.title} subtitle={stale ? t.review.staleNote : t.exposures.computedByCode} />
      <div className="px-5 py-5">
        <ExposuresView exposures={portfolio.exposures} positions={portfolio.positions} sources={portfolio.sources} fx={portfolio.fx} stale={stale} />
      </div>
    </Card>
  );
}

/** The rows under correction, the problem that blocks confirming them, and the edits. */
function useReviewRows(portfolio: PortfolioView) {
  const [rows, setRows] = useState<Row[]>(() => portfolio.positions.map(rowOf));
  const [problem, setProblem] = useState<string | null>(null);
  const [counter, setCounter] = useState(1);

  const update = (key: string, patch: Partial<Row>) =>
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch, edited: true } : row)));

  const addRow = (raw: string | null = null) => {
    const id = `u${counter}`;
    setCounter(counter + 1);
    setRows((current) => [...current, { ...rowOf(blankPosition(id, raw)), edited: true }]);
  };

  const removeRow = (key: string) => setRows((current) => current.filter((candidate) => candidate.key !== key));

  return { rows, problem, setProblem, update, addRow, removeRow };
}

/** `portfolio_review`: the investor corrects A2's positions, then confirms (`onConfirm` lets the journey walk on). */
export function PortfolioReviewStep({
  portfolio,
  message,
  onConfirm,
}: {
  portfolio: PortfolioView;
  message: string | null;
  onConfirm?: (positions: PositionInput[]) => Promise<boolean>;
}) {
  const { t } = useI18n();
  const session = useSession();
  const { rows, problem, setProblem, update, addRow, removeRow } = useReviewRows(portfolio);
  const confirming = session.pending === "portfolio.confirm";
  const edited = rows.some((row) => row.edited) || rows.length !== portfolio.positions.length;
  const review = reviewIndex(portfolio);

  const confirm = () => {
    const blocking = confirmProblem(rows, review.rowIds, t);
    setProblem(blocking);
    if (blocking) return;
    void (onConfirm ?? session.confirmPortfolio)(rows.map(toInput));
  };

  return (
    <div className="animate-fade-in space-y-5">
      {message ? <AgentMessage message={message} /> : null}
      <Card>
        <CardHeader title={t.review.title} subtitle={t.review.intro} />
        <PositionsTable rows={rows} review={review} confirming={confirming} onChange={update} onDelete={removeRow} />
        <div className="flex flex-wrap items-center gap-3 px-5 py-3">
          <Button variant="secondary" size="sm" onClick={() => addRow()} icon={<CirclePlus aria-hidden className="size-4" />} disabled={confirming}>
            {t.review.addRow}
          </Button>
          <FxNote fx={portfolio.fx} className="ml-auto" />
        </div>
        {review.looseUnresolved.length > 0 ? (
          <LooseUnresolved items={review.looseUnresolved} confirming={confirming} onAdd={addRow} />
        ) : null}
        <ReviewFooter problem={problem} confirming={confirming} onConfirm={confirm} />
      </Card>
      <ReviewExposures portfolio={portfolio} stale={edited} />
    </div>
  );
}
