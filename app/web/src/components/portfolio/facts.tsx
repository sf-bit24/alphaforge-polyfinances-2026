"use client";

import { createContext, useContext, useState } from "react";
import type { DecisionFact, FactLabel } from "@/lib/contract/portfolio";
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

function FactCard({ fact }: { fact: DecisionFact }) {
  const { t, locale } = useI18n();
  const { trace } = useDecisionLookup();
  const f = t.portfolioView.fact;
  const event = trace.get(fact.trace_id);
  return (
    <article className={p.factCard}>
      <div className={p.statementHead}>
        <h3 style={{ flex: 1 }}>{fact.label_fr}</h3>
        <LabelBadge label={fact.status} />
      </div>
      <p className={p.factBig}>{formatFact(fact)}</p>
      <dl className={p.kv}>
        <dt>{f.id}</dt>
        <dd className={p.mono}>{fact.fact_id}</dd>
        <dt>{f.unit}</dt>
        <dd>{fact.unit}{fact.currency ? ` (${fact.currency})` : ""}</dd>
        {fact.as_of ? (
          <>
            <dt>{f.asOf}</dt>
            <dd>{formatDate(fact.as_of, locale)}</dd>
          </>
        ) : null}
        {fact.published ? (
          <>
            <dt>{f.published}</dt>
            <dd>{formatDate(fact.published, locale)}</dd>
          </>
        ) : null}
      </dl>
      <div className={p.subCard}>
        <h4>{f.sources}</h4>
        {fact.sources.map((source, index) => (
          <dl key={`${source.dataset}-${index}`} className={p.kv}>
            <dt>{f.dataset}</dt>
            <dd className={p.mono}>{source.dataset}</dd>
            {source.processing ? (
              <>
                <dt>{f.processing}</dt>
                <dd>{source.processing}</dd>
              </>
            ) : null}
            {source.url ? (
              <>
                <dt>{f.url}</dt>
                <dd>
                  <a href={source.url} target="_blank" rel="noreferrer noopener">
                    {source.url}
                  </a>
                </dd>
              </>
            ) : null}
            {source.licence ? (
              <>
                <dt>{f.licence}</dt>
                <dd>{source.licence}</dd>
              </>
            ) : null}
            {source.retrieved_utc ? (
              <>
                <dt>{f.retrieved}</dt>
                <dd>{formatDateTime(source.retrieved_utc, locale)}</dd>
              </>
            ) : null}
            {source.sha256 ? (
              <>
                <dt>{f.sha}</dt>
                <dd className={p.mono}>{source.sha256}</dd>
              </>
            ) : null}
          </dl>
        ))}
      </div>
      <div className={p.subCard}>
        <h4>{f.trace}</h4>
        <dl className={p.kv}>
          <dt>{f.id}</dt>
          <dd className={p.mono}>{fact.trace_id}</dd>
          {event ? (
            <>
              <dt>{f.agent}</dt>
              <dd>{event.agent}</dd>
              {event.tool ? (
                <>
                  <dt>{f.tool}</dt>
                  <dd className={p.mono}>{event.tool}</dd>
                </>
              ) : null}
              <dt>{t.portfolioView.constraints.state}</dt>
              <dd>{t.portfolioView.trace.status[event.status] ?? event.status}</dd>
              {event.output_summary ? (
                <>
                  <dt>{f.summary}</dt>
                  <dd>{event.output_summary}</dd>
                </>
              ) : null}
              {event.model_id ? (
                <>
                  <dt>{f.model}</dt>
                  <dd className={p.mono}>{event.model_id}</dd>
                </>
              ) : null}
              <dt>{t.portfolioView.meta.created}</dt>
              <dd>{formatDateTime(event.started_utc, locale)}</dd>
            </>
          ) : null}
        </dl>
      </div>
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
