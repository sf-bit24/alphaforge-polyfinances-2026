"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import type { DecisionFact, FactLabel, FactSource } from "@/lib/contract/portfolio";
import { formatDateTime, formatDate } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import type { FactIndex, TraceIndex } from "@/lib/portfolio/decision";
import { formatFact } from "@/lib/portfolio/format";
import { engineText, plainProcessing, sourceKind, stepTitle } from "@/lib/portfolio/wording";
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

/** A fact's value as a chip or a cell shows it: the engine's format, a text value in the client's words. */
export function factValue(fact: Pick<DecisionFact, "value" | "unit">): string {
  return engineText(formatFact(fact));
}

/** One fact: its label and its value as the engine formats it; opens the fact panel. A fact the decision lacks shows nothing. */
export function FactChip({ id, compact = false }: { id: string; compact?: boolean }) {
  const { t } = useI18n();
  const { facts, open } = useDecisionLookup();
  const fact = facts.get(id);
  if (!fact) return null;
  const value = factValue(fact);
  const label = engineText(fact.label_fr);
  return (
    <button
      type="button"
      className={cn(p.fact, fact.status !== "FAIT" && p.factHyp)}
      onClick={() => open([id])}
      aria-haspopup="dialog"
      aria-label={`${t.portfolioView.fact.open(label)} (${value}, ${t.portfolioView.labels[fact.status]})`}
      title={`${label}${t.portfolioView.colon}${value} · ${t.portfolioView.labels[fact.status]}`}
    >
      <span aria-hidden className={cn(p.dot, fact.status === "HYPOTHESE" && p.dotHyp, fact.status === "FICTION" && p.dotFic)} />
      {compact ? null : <span className={p.factLabel}>{label}</span>}
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
function Entry({ term, children }: { term: string; children: ReactNode }) {
  return (
    <>
      <dt>{term}</dt>
      <dd>{children}</dd>
    </>
  );
}

/** Where a fact comes from: the source by what it is (never its key), how it was computed, link, licence, date. */
function SourceEntries({ source }: { source: FactSource }) {
  const { t, locale } = useI18n();
  const f = t.portfolioView.fact;
  const processing = plainProcessing(source.processing);
  return (
    <dl className={p.kv}>
      <Entry term={f.dataset}>{f.sourceKinds[sourceKind(source.dataset)]}</Entry>
      {processing ? <Entry term={f.processing}>{processing}</Entry> : null}
      {source.url ? (
        <Entry term={f.url}>
          <a href={source.url} target="_blank" rel="noreferrer noopener">
            {source.url}
          </a>
        </Entry>
      ) : null}
      {source.licence ? <Entry term={f.licence}>{source.licence}</Entry> : null}
      {source.retrieved_utc ? <Entry term={f.retrieved}>{formatDateTime(source.retrieved_utc, locale)}</Entry> : null}
    </dl>
  );
}

/** The step of the simulator that produced a fact, by what it did, with its outcome when it wrote one. */
function TraceStep({ traceId }: { traceId: string }) {
  const { t } = useI18n();
  const { trace } = useDecisionLookup();
  const v = t.portfolioView;
  const event = trace.get(traceId);
  if (!event) return null;
  return (
    <div className={p.subCard}>
      <h4>{v.fact.trace}</h4>
      <p>{stepTitle(event, v)}</p>
      {event.output_summary || event.status !== "ok" ? (
        <dl className={p.kv}>
          <Entry term={v.fact.summary}>{event.output_summary ? engineText(event.output_summary) : (v.trace.status[event.status] ?? v.trace.status.erreur)}</Entry>
        </dl>
      ) : null}
    </div>
  );
}

function FactCard({ fact }: { fact: DecisionFact }) {
  const { t, locale } = useI18n();
  const f = t.portfolioView.fact;
  return (
    <article className={p.factCard}>
      <div className={p.statementHead}>
        <h3 style={{ flex: 1 }}>{engineText(fact.label_fr)}</h3>
        <LabelBadge label={fact.status} />
      </div>
      <p className={p.factBig}>{factValue(fact)}</p>
      {fact.as_of || fact.published ? (
        <dl className={p.kv}>
          {fact.as_of ? <Entry term={f.asOf}>{formatDate(fact.as_of, locale)}</Entry> : null}
          {fact.published ? <Entry term={f.published}>{formatDate(fact.published, locale)}</Entry> : null}
        </dl>
      ) : null}
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
            {t.portfolioView.fact.missing}
          </p>
        );
      })}
    </div>
  );
}
