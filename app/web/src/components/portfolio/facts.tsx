"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import type { DecisionFact, FactLabel, FactSource } from "@/lib/contract/portfolio";
import { formatDateTime, formatDate } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import type { FactIndex, TraceIndex } from "@/lib/portfolio/decision";
import { formatFact } from "@/lib/portfolio/format";
import { cn } from "@/components/ui/cn";
import p from "./portfolio.module.css";

/** Facts and trace of the decision on screen, and the opener of the fact panel. */
export interface DecisionLookup {
  facts: FactIndex;
  trace: TraceIndex;
  open: (factIds: readonly string[], title?: string) => void;
}

const DecisionContext = createContext<DecisionLookup | null>(null);
export const DecisionProvider = DecisionContext.Provider;

export function useDecisionLookup(): DecisionLookup {
  const value = useContext(DecisionContext);
  if (!value) throw new Error("useDecisionLookup must be used inside DecisionProvider");
  return value;
}

const LABEL_CLASS: Record<FactLabel, string | undefined> = { FAIT: p.labelFait, HYPOTHESE: p.labelHyp, FICTION: p.labelFic };

/** FAIT / HYPOTHÈSE / FICTION, with what the label means on hover. */
export function LabelBadge({ label }: { label: FactLabel }) {
  const { t } = useI18n();
  return (
    <span className={cn(p.label, LABEL_CLASS[label])} title={t.portfolioView.labelHelp[label]}>
      {t.portfolioView.labels[label]}
    </span>
  );
}

/** One fact: its label and its value as the engine formats it; opens the fact panel. */
export function FactChip({ id, compact = false }: { id: string; compact?: boolean }) {
  const { t } = useI18n();
  const { facts, open } = useDecisionLookup();
  const fact = facts.get(id);
  if (!fact) return <span className={cn(p.fact, p.mono)}>{id}</span>;
  const value = formatFact(fact);
  return (
    <button
      type="button"
      className={cn(p.fact, fact.status !== "FAIT" && p.factHyp)}
      onClick={() => open([id])}
      aria-haspopup="dialog"
      aria-label={`${t.portfolioView.fact.open(fact.label_fr)} (${value}, ${t.portfolioView.labels[fact.status]})`}
      title={`${fact.label_fr} : ${value} · ${t.portfolioView.labels[fact.status]}`}
    >
      <span aria-hidden className={cn(p.dot, fact.status === "HYPOTHESE" && p.dotHyp, fact.status === "FICTION" && p.dotFic)} />
      {compact ? null : <span className={p.factLabel}>{fact.label_fr}</span>}
      <span className={p.factValue}>{value}</span>
    </button>
  );
}

/** The facts a statement or a counterfactual cites; long lists fold after `limit` chips. */
export function FactChips({ ids, limit = 6 }: { ids: readonly string[]; limit?: number }) {
  const { t } = useI18n();
  const [all, setAll] = useState(false);
  if (ids.length === 0) return null;
  const shown = all ? ids : ids.slice(0, limit);
  const hidden = ids.length - shown.length;
  return (
    <div className={p.chips}>
      {shown.map((id) => (
        <FactChip key={id} id={id} />
      ))}
      {hidden > 0 ? (
        <button type="button" className={p.more} onClick={() => setAll(true)} aria-expanded={false}>
          {t.portfolioView.explanation.more(hidden)}
        </button>
      ) : null}
      {all && ids.length > limit ? (
        <button type="button" className={p.more} onClick={() => setAll(false)} aria-expanded>
          {t.portfolioView.explanation.less}
        </button>
      ) : null}
    </div>
  );
}

/** A term of a definition list and its value. */
function Entry({ term, mono = false, children }: { term: string; mono?: boolean; children: ReactNode }) {
  return (
    <>
      <dt>{term}</dt>
      <dd className={mono ? p.mono : undefined}>{children}</dd>
    </>
  );
}

/** Where a fact comes from: dataset, processing, link, licence, retrieval time and checksum. */
function SourceEntries({ source }: { source: FactSource }) {
  const { t, locale } = useI18n();
  const f = t.portfolioView.fact;
  return (
    <dl className={p.kv}>
      <Entry term={f.dataset} mono>
        {source.dataset}
      </Entry>
      {source.processing ? <Entry term={f.processing}>{source.processing}</Entry> : null}
      {source.url ? (
        <Entry term={f.url}>
          <a href={source.url} target="_blank" rel="noreferrer noopener">
            {source.url}
          </a>
        </Entry>
      ) : null}
      {source.licence ? <Entry term={f.licence}>{source.licence}</Entry> : null}
      {source.retrieved_utc ? <Entry term={f.retrieved}>{formatDateTime(source.retrieved_utc, locale)}</Entry> : null}
      {source.sha256 ? (
        <Entry term={f.sha} mono>
          {source.sha256}
        </Entry>
      ) : null}
    </dl>
  );
}

/** The step of the trace that produced a fact: agent, tool, outcome, summary, model and time. */
function TraceStep({ traceId }: { traceId: string }) {
  const { t, locale } = useI18n();
  const { trace } = useDecisionLookup();
  const f = t.portfolioView.fact;
  const event = trace.get(traceId);
  return (
    <div className={p.subCard}>
      <h4>{f.trace}</h4>
      <dl className={p.kv}>
        <Entry term={f.id} mono>
          {traceId}
        </Entry>
        {event ? (
          <>
            <Entry term={f.agent}>{event.agent}</Entry>
            {event.tool ? (
              <Entry term={f.tool} mono>
                {event.tool}
              </Entry>
            ) : null}
            <Entry term={t.portfolioView.constraints.state}>{t.portfolioView.trace.status[event.status] ?? event.status}</Entry>
            {event.output_summary ? <Entry term={f.summary}>{event.output_summary}</Entry> : null}
            {event.model_id ? (
              <Entry term={f.model} mono>
                {event.model_id}
              </Entry>
            ) : null}
            <Entry term={t.portfolioView.meta.created}>{formatDateTime(event.started_utc, locale)}</Entry>
          </>
        ) : null}
      </dl>
    </div>
  );
}

function FactCard({ fact }: { fact: DecisionFact }) {
  const { t, locale } = useI18n();
  const f = t.portfolioView.fact;
  return (
    <article className={p.factCard}>
      <div className={p.statementHead}>
        <h3 style={{ flex: 1 }}>{fact.label_fr}</h3>
        <LabelBadge label={fact.status} />
      </div>
      <p className={p.factBig}>{formatFact(fact)}</p>
      <dl className={p.kv}>
        <Entry term={f.id} mono>
          {fact.fact_id}
        </Entry>
        <Entry term={f.unit}>
          {fact.unit}
          {fact.currency ? ` (${fact.currency})` : ""}
        </Entry>
        {fact.as_of ? <Entry term={f.asOf}>{formatDate(fact.as_of, locale)}</Entry> : null}
        {fact.published ? <Entry term={f.published}>{formatDate(fact.published, locale)}</Entry> : null}
      </dl>
      <div className={p.subCard}>
        <h4>{f.sources}</h4>
        {fact.sources.map((source, index) => (
          <SourceEntries key={`${source.dataset}-${index}`} source={source} />
        ))}
      </div>
      <TraceStep traceId={fact.trace_id} />
    </article>
  );
}

/** Content of the fact panel: one card per fact, with its sources and the trace step behind it. */
export function FactPanel({ ids, title }: { ids: readonly string[]; title: string }) {
  const { t } = useI18n();
  const { facts } = useDecisionLookup();
  return (
    <div>
      <h2 className={p.drawerTitle}>{title}</h2>
      {ids.map((id) => {
        const fact = facts.get(id);
        return fact ? (
          <FactCard key={id} fact={fact} />
        ) : (
          <p key={id} className={p.empty}>
            <span className={p.mono}>{id}</span> : {t.portfolioView.fact.missing}
          </p>
        );
      })}
    </div>
  );
}
