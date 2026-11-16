"use client";

import { EXPLANATION_SECTIONS, type Decision, type ExplanationSection, type PortfolioBuildResponse, type Statement } from "@/lib/contract/portfolio";
import { curly, formatDateTime, formatDate } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { requestFacts } from "@/lib/portfolio/decision";
import { groundingLine } from "@/lib/portfolio/grounding";
import { cn } from "@/components/ui/cn";
import { Positions, StylePanel } from "./allocation-panels";
import d from "./base.module.css";
import { FactChip, FactChips, LabelBadge, useDecisionLookup } from "./facts";
import { Constraints, Debate } from "./judge-panels";
import p from "./portfolio.module.css";
import { Ranking } from "./ranking-table";

const KIND_TONE = { proposition: d.ok, refus_encadre: d.stop, position_attente: d.wait, incomplet: d.wait, protection: d.wait } as const;

/** The language the engine writes its texts in (facts, statements, checks, trace): French only for now. */
const ENGINE_LOCALE = "fr";

/** In another language than the engine's, says that the decision's own texts stay in French. */
function EngineLanguageNote() {
  const { t, locale } = useI18n();
  if (locale === ENGINE_LOCALE) return null;
  return (
    <p className={p.engineNote} role="note">
      {t.portfolioView.engineLanguage}
    </p>
  );
}

/** The investor's precise request, when there is one: its weight, its framing and the Judge's checks of it. */
function RequestCheck({ decision }: { decision: Decision }) {
  const { t } = useI18n();
  const v = t.portfolioView;
  const { facts } = useDecisionLookup();
  const req = requestFacts(decision, facts);
  if (!req.weight && req.checks.length === 0) return null;
  return (
    <div className={p.request}>
      <div className={p.chips}>
        {req.weight ? <FactChip id={req.weight.fact_id} /> : null}
        {req.method ? <FactChip id={req.method.fact_id} /> : null}
      </div>
      {req.checks.map((event) => (
        <p key={event.trace_id}>
          <b>{v.constraints.requestCheck}</b>
          {v.colon}
          {event.output_summary ?? v.trace.status[event.status]}
        </p>
      ))}
    </div>
  );
}

/** Date, mode, ids and release of the decision, with its X-Ray trace and audit link when there are. */
function SummaryMeta({ response, fixture }: { response: PortfolioBuildResponse; fixture: boolean }) {
  const { t, locale } = useI18n();
  const v = t.portfolioView;
  return (
    <dl className={p.meta}>
      <dt>{v.meta.asOf}</dt>
      <dd>{formatDate(response.as_of, locale)}</dd>
      <dt>{v.meta.mode}</dt>
      <dd>{v.modes[response.mode]}</dd>
      <dt>{v.meta.created}</dt>
      <dd>{formatDateTime(response.decision.created_utc, locale)}</dd>
      <dt>{v.meta.decision}</dt>
      <dd className={p.mono}>{response.decision.decision_id}</dd>
      <dt>{v.meta.release}</dt>
      <dd>
        <span className={p.mono}>{response.release}</span>
        {fixture ? <span className={p.sub} style={{ display: "block" }}>{v.meta.fixture}</span> : null}
      </dd>
      {response.xray_trace_id ? (
        <>
          <dt>{v.meta.xray}</dt>
          <dd className={p.mono} title={v.meta.xrayHelp}>
            {response.xray_trace_id}
          </dd>
        </>
      ) : null}
      {response.audit ? (
        <>
          <dt>{v.meta.audit}</dt>
          {"error" in response.audit ? (
            <dd>{v.meta.auditFailed}</dd>
          ) : (
            <dd title={`${v.meta.auditHelp} — ${response.audit.s3_key}`}>
              <span className={p.mono}>{v.meta.auditLink(response.audit.seq, response.audit.record_hash.slice(0, 12))}</span>
            </dd>
          )}
        </>
      ) : null}
    </dl>
  );
}

function Summary({ response, fixture }: { response: PortfolioBuildResponse; fixture: boolean }) {
  const { t } = useI18n();
  const v = t.portfolioView;
  const decision = response.decision;
  return (
    <section className={cn(d.tile, d.tWide)} aria-label={v.meta.decision}>
      <div className={p.summary}>
        <div>
          <div className={p.kindRow}>
            <span className={cn(d.chip, KIND_TONE[decision.kind])}>{v.kinds[decision.kind]}</span>
            <FactChip id="level" />
          </div>
          <p className={p.kindText}>{v.kindText[decision.kind]}</p>
          <EngineLanguageNote />
          <RequestCheck decision={decision} />
        </div>
        <SummaryMeta response={response} fixture={fixture} />
      </div>
    </section>
  );
}

/** One of the four questions of the explanation, with its statements and the facts each one cites. */
function ExplanationQuestion({ section, statements }: { section: ExplanationSection; statements: Statement[] }) {
  const { t } = useI18n();
  const v = t.portfolioView.explanation;
  return (
    <div>
      <h3>{v.sections[section]}</h3>
      {statements.length === 0 ? (
        <p className={p.empty}>{v.empty}</p>
      ) : (
        <ul className={p.statements}>
          {statements.map((statement, index) => (
            <li key={`${section}-${index}`} className={p.statement}>
              <div className={p.statementHead}>
                <LabelBadge label={statement.label} />
                <p>{curly(statement.text_fr)}</p>
              </div>
              <FactChips ids={statement.fact_ids} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** The outcome of the Bedrock Guardrails contextual grounding check, when a guardrail ran. */
function GroundingNote({ grounding }: { grounding: PortfolioBuildResponse["grounding"] }) {
  const { t, locale } = useI18n();
  const line = grounding ? groundingLine(grounding, t.portfolioView.grounding, locale) : null;
  if (!line) return null;
  return (
    <p className={cn(d.cap, p.block)}>
      {t.portfolioView.grounding.title} · {line}
    </p>
  );
}

function ExplanationPanel({ response }: { response: PortfolioBuildResponse }) {
  const { t } = useI18n();
  const v = t.portfolioView.explanation;
  const explanation = response.decision.explanation;
  return (
    <section className={cn(d.tile, d.tWide)} aria-labelledby="pf-why">
      <header>
        <h2 id="pf-why">{v.title}</h2>
      </header>
      <p className={p.kindText} style={{ marginTop: -6, marginBottom: 16 }}>
        {v.lead}
      </p>
      <div className={p.why}>
        {EXPLANATION_SECTIONS.map((section) => (
          <ExplanationQuestion key={section} section={section} statements={explanation[section]} />
        ))}
      </div>
      {response.explanation_report.length > 0 ? (
        <details className={p.block}>
          <summary className={d.cap}>{t.portfolioView.report}</summary>
          <ul className={p.notes}>
            {response.explanation_report.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
        </details>
      ) : null}
      <GroundingNote grounding={response.grounding} />
    </section>
  );
}

function Counterfactuals({ response }: { response: PortfolioBuildResponse }) {
  const { t } = useI18n();
  const v = t.portfolioView.counterfactuals;
  const items = response.decision.counterfactuals;
  return (
    <section className={cn(d.tile, p.half)} aria-labelledby="pf-cf">
      <header>
        <h2 id="pf-cf">{v.title}</h2>
      </header>
      <p className={p.sub} style={{ marginTop: -8, marginBottom: 12 }}>
        {v.lead}
      </p>
      {items.length === 0 ? (
        <p className={p.empty}>{v.none}</p>
      ) : (
        <ul className={p.list}>
          {items.map((item, index) => (
            <li key={index}>
              <p>{curly(item.change_fr)}</p>
              <FactChips ids={item.result_fact_ids} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Trace({ response }: { response: PortfolioBuildResponse }) {
  const { t, locale } = useI18n();
  const v = t.portfolioView.trace;
  const { open } = useDecisionLookup();
  const events = response.decision.trace;
  return (
    <section className={cn(d.tile, d.tWide)} aria-label={v.title}>
      <details className={p.trace}>
        <summary>
          <span>{v.title}</span>
          <span>{v.count(events.length)}</span>
        </summary>
        <ol className={p.traceList}>
          {events.map((event, index) => (
            <li key={event.trace_id} className={event.parent_id ? p.traceChild : undefined}>
              <span className={p.n}>{index + 1}</span>
              <span>
                <b>{event.agent}</b>
                {event.tool ? <span className={p.mono}> · {event.tool}</span> : null}
                {event.output_summary ? <span className={p.sub}> · {event.output_summary}</span> : null}
                {event.status !== "ok" ? <span className={cn(d.chip, d.stop)} style={{ marginLeft: 6 }}>{v.status[event.status] ?? event.status}</span> : null}
                <span className={cn(p.sub, p.mono)} style={{ display: "block" }}>
                  {formatDateTime(event.started_utc, locale)}
                </span>
              </span>
              {event.fact_ids.length > 0 ? (
                <button type="button" className={p.linkBtn} aria-haspopup="dialog" onClick={() => open(event.fact_ids, `${event.agent}${event.tool ? ` · ${event.tool}` : ""}`)}>
                  {v.facts(event.fact_ids.length)}
                </button>
              ) : (
                <span />
              )}
            </li>
          ))}
        </ol>
      </details>
    </section>
  );
}

/** The whole decision, as the backend computed it. */
export function DecisionView({ response, fixture }: { response: PortfolioBuildResponse; fixture: boolean }) {
  return (
    <div className={d.grid}>
      <Summary response={response} fixture={fixture} />
      <Positions positions={response.decision.positions} />
      <StylePanel response={response} />
      <ExplanationPanel response={response} />
      <Counterfactuals response={response} />
      <Debate response={response} />
      <Constraints checks={response.decision.constraints} />
      <Ranking response={response} />
      <Trace response={response} />
    </div>
  );
}
