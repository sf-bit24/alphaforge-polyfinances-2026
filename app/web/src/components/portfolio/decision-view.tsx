"use client";

import { useState, type CSSProperties } from "react";
import {
  EXPLANATION_SECTIONS,
  type ConstraintCheck,
  type DecisionFact,
  type DecisionPosition,
  type LensVerdict,
  type PortfolioBuildResponse,
} from "@/lib/contract/portfolio";
import { curly, formatDateTime, formatDate } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import {
  RANKING_FEATURES,
  bandPosition,
  constraintUnit,
  rankingRows,
  requestFacts,
  rowFacts,
  styleBand,
  styleNotes,
  type FactIndex,
} from "@/lib/portfolio/decision";
import { formatFact, formatLimit, formatWeight } from "@/lib/portfolio/format";
import d from "@/components/details/details.module.css";
import { cn } from "@/components/ui/cn";
import { FactChip, FactChips, LabelBadge, useDecisionLookup } from "./facts";
import p from "./portfolio.module.css";

/** A CSS custom property set from a backend share, for geometry only. */
const share = (name: string, value: number): CSSProperties => ({ [name]: String(value) }) as CSSProperties;

const KIND_TONE = { proposition: d.ok, refus_encadre: d.stop, position_attente: d.wait, incomplet: d.wait, protection: d.wait } as const;

function Summary({ response, fixture }: { response: PortfolioBuildResponse; fixture: boolean }) {
  const { t, locale } = useI18n();
  const v = t.portfolioView;
  const { facts } = useDecisionLookup();
  const decision = response.decision;
  const req = requestFacts(decision, facts);
  return (
    <section className={cn(d.tile, d.tWide)} aria-label={v.meta.decision}>
      <div className={p.summary}>
        <div>
          <div className={p.kindRow}>
            <span className={cn(d.chip, KIND_TONE[decision.kind])}>{v.kinds[decision.kind]}</span>
            <FactChip id="level" />
          </div>
          <p className={p.kindText}>{v.kindText[decision.kind]}</p>
          {req.weight || req.checks.length > 0 ? (
            <div className={p.request}>
              <div className={p.chips}>
                {req.weight ? <FactChip id={req.weight.fact_id} /> : null}
                {req.method ? <FactChip id={req.method.fact_id} /> : null}
              </div>
              {req.checks.map((event) => (
                <p key={event.trace_id}>
                  <b>{v.constraints.requestCheck}</b> : {event.output_summary ?? v.trace.status[event.status]}
                </p>
              ))}
            </div>
          ) : null}
        </div>
        <dl className={p.meta}>
          <dt>{v.meta.asOf}</dt>
          <dd>{formatDate(response.as_of, locale)}</dd>
          <dt>{v.meta.mode}</dt>
          <dd>{v.modes[response.mode]}</dd>
          <dt>{v.meta.created}</dt>
          <dd>{formatDateTime(decision.created_utc, locale)}</dd>
          <dt>{v.meta.decision}</dt>
          <dd className={p.mono}>{decision.decision_id}</dd>
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
      </div>
    </section>
  );
}

function roleClass(role: DecisionPosition["role"], index: number): string | undefined {
  if (role === "satellite") return p.sat;
  if (role === "coeur") return index % 2 === 1 ? p.coreAlt : "";
  return p.other;
}

function Positions({ positions }: { positions: DecisionPosition[] }) {
  const { t } = useI18n();
  const v = t.portfolioView.positions;
  const roleLabel = (role: DecisionPosition["role"]) => (role === "coeur" ? v.core : role === "satellite" ? v.satellite : (role ?? "—"));
  return (
    <section className={cn(d.tile, p.half)} aria-labelledby="pf-positions">
      <header>
        <h2 id="pf-positions">{v.title}</h2>
        <span className={d.cap} style={{ margin: 0 }}>
          {v.count(positions.length)}
        </span>
      </header>
      {positions.length === 0 ? (
        <p className={p.empty}>{v.none}</p>
      ) : (
        <>
          <div className={p.alloc} role="img" aria-label={v.barAria(positions.map((pos) => `${pos.asset_id} ${formatWeight(pos.weight)} (${roleLabel(pos.role)})`).join(", "))}>
            {positions.map((pos, index) => (
              <span key={pos.asset_id} className={roleClass(pos.role, index)} style={share("--w", pos.weight)} title={`${pos.asset_id} · ${formatWeight(pos.weight)} · ${roleLabel(pos.role)}`} />
            ))}
          </div>
          <div className={p.legend} aria-hidden>
            <span>
              <i className={p.swatch} />
              {v.core}
            </span>
            <span>
              <i className={cn(p.swatch, p.swatchSat)} />
              {v.satellite}
            </span>
          </div>
          <div className={d.tableWrap}>
            <table className={d.table} style={{ minWidth: 480 }}>
              <caption className="sr-only">{v.title}</caption>
              <thead>
                <tr>
                  <th scope="col">{v.asset}</th>
                  <th scope="col">{v.role}</th>
                  <th scope="col" className={d.n}>
                    {v.weight}
                  </th>
                  <th scope="col">{v.facts}</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => (
                  <tr key={pos.asset_id} className={pos.role === "satellite" ? p.rowSat : undefined}>
                    <td>
                      <span className={d.ticker}>{pos.asset_id}</span>
                    </td>
                    <td>
                      <span className={cn(d.chip, pos.role === "satellite" ? d.stop : d.navy)}>{roleLabel(pos.role)}</span>
                    </td>
                    <td className={cn(d.n, p.num)}>{formatWeight(pos.weight)}</td>
                    <td>
                      <FactChips ids={pos.rationale_fact_ids} limit={2} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function BandBar({ facts }: { facts: FactIndex }) {
  const { t } = useI18n();
  const v = t.portfolioView.style;
  const band = styleBand(facts);
  const min = bandPosition(band.eMin);
  const cap = bandPosition(band.eCap);
  const target = bandPosition(band.target);
  const final = bandPosition(band.finalTarget);
  if (!band.eMin || !band.eCap || min === null || cap === null) return null;
  const shown = band.finalTarget ?? band.target;
  return (
    <div className={p.block}>
      <h3>{v.band}</h3>
      <div
        className={p.band}
        role="img"
        aria-label={v.bandAria(formatFact(band.eMin), formatFact(band.eCap), shown ? formatFact(shown) : "—")}
        style={{ ...share("--min", min), ...share("--cap", cap) }}
      >
        <span className={p.track} />
        <span className={p.zone} />
        {target !== null ? <span className={cn(p.mark, final !== null && p.markBefore)} style={share("--at", target)} /> : null}
        {final !== null ? <span className={cn(p.mark, p.markFinal)} style={share("--at", final)} /> : null}
      </div>
      <div className={p.scale} aria-hidden>
        <span>0 %</span>
        <span>100 %</span>
      </div>
      <ul className={p.bandKeys}>
        <li>
          <i className={p.keyZone} aria-hidden />
          <span>
            {v.min} – {v.cap}
          </span>
          <FactChip id="strat.e_min" compact />
          <FactChip id="strat.e_cap" compact />
        </li>
        {band.target ? (
          <li>
            <i className={p.keyMark} aria-hidden />
            <span>{v.target}</span>
            <FactChip id={band.target.fact_id} compact />
          </li>
        ) : (
          <li className={p.sub}>{v.noTarget}</li>
        )}
        {band.finalTarget ? (
          <li>
            <i className={cn(p.keyMark, p.keyMarkFinal)} aria-hidden />
            <span>{v.finalTarget}</span>
            <FactChip id={band.finalTarget.fact_id} compact />
          </li>
        ) : null}
        {band.pi ? (
          <li>
            <FactChip id={band.pi.fact_id} />
          </li>
        ) : null}
      </ul>
    </div>
  );
}

function StylePanel({ response }: { response: PortfolioBuildResponse }) {
  const { t } = useI18n();
  const v = t.portfolioView.style;
  const { facts } = useDecisionLookup();
  const strategy = response.strategy;
  const notes = styleNotes(facts);
  return (
    <section className={cn(d.tile, p.half)} aria-labelledby="pf-style">
      <header>
        <h2 id="pf-style">{v.title}</h2>
        {strategy ? (
          <span className={d.cap} style={{ margin: 0 }}>
            strategy.yaml@{strategy.version}
          </span>
        ) : null}
      </header>
      {!strategy ? (
        <p className={p.empty}>{v.off}</p>
      ) : (
        <>
          <div className={p.styleHead}>
            <span className={cn(d.chip, d.navy, p.styleBadge)}>{v.badge(v.styles[strategy.style])}</span>
            <span className={p.sub}>{v.fromLevel(v.styles[strategy.from_level])}</span>
          </div>
          <div className={cn(p.chips, p.block)} style={{ marginTop: 10 }}>
            {notes.style ? <FactChip id={notes.style.fact_id} /> : null}
            {notes.preference ? <FactChip id={notes.preference.fact_id} /> : null}
            {notes.applied ? <FactChip id={notes.applied.fact_id} /> : null}
            {notes.k ? <FactChip id={notes.k.fact_id} /> : null}
          </div>
          <BandBar facts={facts} />
          <div className={p.block}>
            <h3>{v.shortlist}</h3>
            {strategy.shortlist.length === 0 ? (
              <p className={p.sub}>{v.noShortlist}</p>
            ) : (
              <div className={p.chips}>
                {strategy.shortlist.flatMap((ticker) => {
                  // The final floor when the debate lowered it, else the floor of step 0; then its amount in dollars.
                  const floor = facts.has(`strat.final.floor.${ticker}`) ? `strat.final.floor.${ticker}` : `strat.floor.${ticker}`;
                  return [floor, `strat.floor_cad.${ticker}`].filter((id) => facts.has(id)).map((id) => <FactChip key={id} id={id} />);
                })}
              </div>
            )}
          </div>
          {notes.sectorCaps.length > 0 ? (
            <div className={p.block}>
              <h3>{v.sectorCaps}</h3>
              <div className={p.chips}>
                {notes.sectorCaps.map(({ fact }) => (
                  <FactChip key={fact.fact_id} id={fact.fact_id} />
                ))}
              </div>
            </div>
          ) : null}
          {notes.riskCost || notes.baseRisk ? (
            <div className={p.block}>
              <h3>{v.riskCost}</h3>
              <div className={p.chips}>
                {notes.riskCost ? <FactChip id={notes.riskCost.fact_id} /> : null}
                {notes.baseRisk ? <FactChip id={notes.baseRisk.fact_id} /> : null}
              </div>
            </div>
          ) : null}
          {notes.notes.length > 0 ? (
            <div className={p.block}>
              <h3>{v.notes}</h3>
              <div className={p.chips}>
                {notes.notes.map((fact) => (
                  <FactChip key={fact.fact_id} id={fact.fact_id} />
                ))}
              </div>
            </div>
          ) : null}
        </>
      )}
    </section>
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
          <div key={section}>
            <h3>{v.sections[section]}</h3>
            {explanation[section].length === 0 ? (
              <p className={p.empty}>{v.empty}</p>
            ) : (
              <ul className={p.statements}>
                {explanation[section].map((statement, index) => (
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
      {response.grounding?.action ? (
        <p className={cn(d.cap, p.block)}>
          {t.portfolioView.grounding.title} · {t.portfolioView.grounding.action(response.grounding.action)}
        </p>
      ) : null}
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

const VERDICT_TONE: Record<LensVerdict, string | undefined> = { soutien: d.ok, objection_maintenue: d.wait, objection_satisfaite: d.navy };

function Debate({ response }: { response: PortfolioBuildResponse }) {
  const { t } = useI18n();
  const v = t.portfolioView.debate;
  const { facts } = useDecisionLookup();
  const last = response.rounds.at(-1);
  const amendments = response.rounds.flatMap((round) => round.amendments);
  if (!last) return null;
  return (
    <section className={cn(d.tile, p.half)} aria-labelledby="pf-debate">
      <header>
        <h2 id="pf-debate">{v.title}</h2>
      </header>
      <p className={p.sub} style={{ marginTop: -8, marginBottom: 12 }}>
        {v.lead}
      </p>
      <ul className={p.lenses}>
        {Object.entries(last.verdicts).map(([lens, verdict]) => (
          <li key={lens}>
            <b>{v.lenses[lens] ?? lens}</b>
            <span className={p.chips}>
              <span className={cn(d.chip, VERDICT_TONE[verdict])}>{v.verdicts[verdict]}</span>
              {facts.has(`emphasis.${lens}`) ? <FactChip id={`emphasis.${lens}`} compact /> : null}
            </span>
          </li>
        ))}
      </ul>
      <div className={p.block}>
        <h3>{v.amendments}</h3>
        {amendments.length === 0 ? (
          <p className={p.sub}>{v.noAmendment}</p>
        ) : (
          <ul className={p.list}>
            {amendments.map((item, index) => (
              <li key={index}>
                <p>
                  <b>{v.lenses[item.lens] ?? item.lens}</b> · {item.status === "applique" ? v.applied : v.rejected} · {curly(item.amendment.reason_fr)}
                </p>
                <p className={p.sub}>{curly(item.why_fr)}</p>
                <FactChips ids={item.amendment.evidence_fact_ids.filter((id) => facts.has(id))} limit={3} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function ConstraintRow({ check, facts }: { check: ConstraintCheck; facts: FactIndex }) {
  const { t } = useI18n();
  const v = t.portfolioView.constraints;
  return (
    <tr className={check.violated ? p.rowViolated : undefined}>
      <td>
        {check.description_fr}
        <span className={p.rule}>{check.rule_id}</span>
      </td>
      <td>{check.derived_from}</td>
      <td className={cn(d.n, p.num)}>{formatLimit(check.limit, constraintUnit(facts, check.value_fact_id))}</td>
      <td>{check.value_fact_id ? <FactChip id={check.value_fact_id} compact /> : "—"}</td>
      <td>
        <span className={p.flags}>
          {check.violated ? <span className={cn(d.chip, d.stop)}>{v.violated}</span> : <span className={cn(d.chip, d.ok)}>{v.respected}</span>}
          {check.active ? <span className={cn(d.chip, d.navy)}>{v.active}</span> : null}
          <span className={cn(d.chip, check.blocking ? d.navy : d.wait)}>{check.blocking ? v.blocking : v.indicative}</span>
        </span>
      </td>
    </tr>
  );
}

function Constraints({ checks }: { checks: ConstraintCheck[] }) {
  const { t } = useI18n();
  const v = t.portfolioView.constraints;
  const { facts } = useDecisionLookup();
  const [all, setAll] = useState(false);
  const notable = checks.filter((check) => check.active || check.violated);
  const rows = all || notable.length === 0 ? checks : notable;
  return (
    <section className={cn(d.tile, d.tWide)} aria-labelledby="pf-judge">
      <header>
        <h2 id="pf-judge">{v.title}</h2>
        <span className={d.cap} style={{ margin: 0 }}>
          {v.summary(checks.length, checks.filter((check) => check.active).length, checks.filter((check) => check.violated).length)}
        </span>
      </header>
      <p className={p.sub} style={{ marginTop: -8, marginBottom: 12 }}>
        {v.lead}
      </p>
      {checks.length === 0 ? (
        <p className={p.empty}>{v.none}</p>
      ) : (
        <>
          <div className={d.tableWrap}>
            <table className={cn(d.table, p.cTable)}>
              <caption className="sr-only">{v.title}</caption>
              <thead>
                <tr>
                  <th scope="col">{v.rule}</th>
                  <th scope="col">{v.derived}</th>
                  <th scope="col" className={d.n}>
                    {v.limit}
                  </th>
                  <th scope="col">{v.value}</th>
                  <th scope="col">{v.state}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((check) => (
                  <ConstraintRow key={check.rule_id} check={check} facts={facts} />
                ))}
              </tbody>
            </table>
          </div>
          {notable.length > 0 && notable.length < checks.length ? (
            <p className={p.tableFoot}>
              <button type="button" className={p.linkBtn} onClick={() => setAll(!all)} aria-expanded={all}>
                {all ? v.showLess : v.showAll(checks.length)}
              </button>
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}

function cell(fact: DecisionFact | undefined, className?: string) {
  return <td className={cn(d.n, p.num, className)}>{fact ? formatFact(fact) : "—"}</td>;
}

const RANKING_PREVIEW = 10;

function Ranking({ response }: { response: PortfolioBuildResponse }) {
  const { t } = useI18n();
  const v = t.portfolioView.ranking;
  const { facts, open } = useDecisionLookup();
  const [all, setAll] = useState(false);
  const rows = rankingRows(facts, response.strategy);
  if (rows.length === 0) return null;
  const shown = all ? rows : rows.slice(0, RANKING_PREVIEW);
  const scored = RANKING_FEATURES.filter((feature) => feature !== "momentum");
  return (
    <section className={cn(d.tile, d.tWide)} aria-labelledby="pf-rank">
      <header>
        <h2 id="pf-rank">{v.title}</h2>
        {facts.has("strat.n_candidates") ? <FactChip id="strat.n_candidates" /> : null}
      </header>
      <p className={p.sub} style={{ marginTop: -8, marginBottom: 4 }}>
        {v.lead}
      </p>
      <p className={p.sub} style={{ marginBottom: 12 }}>
        {v.momentumNote}
      </p>
      <div className={d.tableWrap}>
        <table className={cn(d.table, p.rTable)}>
          <caption className="sr-only">{v.title}</caption>
          <thead>
            <tr>
              <th scope="col" className={d.n}>
                {v.rank}
              </th>
              <th scope="col">{v.ticker}</th>
              <th scope="col">{v.status}</th>
              <th scope="col" className={d.n}>
                {v.score}
              </th>
              {scored.map((feature) => (
                <th key={feature} scope="col" className={d.n}>
                  {v.features[feature]}
                </th>
              ))}
              <th scope="col" className={d.n}>
                {v.momentum}
                <span className={p.thSub}>{v.sensitivity}</span>
              </th>
              <th scope="col" className={d.n}>
                {v.momentumRank}
                <span className={p.thSub}>{v.sensitivity}</span>
              </th>
              <th scope="col">
                <span className="sr-only">{v.facts}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.ticker} className={row.shortlisted ? p.rowKept : undefined}>
                {cell(row.rank)}
                <th scope="row">{row.ticker}</th>
                <td>
                  {row.shortlisted ? (
                    <span className={cn(d.chip, d.stop)}>{v.kept}</span>
                  ) : row.ineligible ? (
                    <>
                      <span className={cn(d.chip, d.wait)}>{v.setAside}</span>
                      <span className={p.reason}>{String(row.ineligible.value ?? "")}</span>
                    </>
                  ) : (
                    <span className={cn(d.chip, d.navy)}>{v.ranked}</span>
                  )}
                </td>
                {cell(row.score)}
                {scored.map((feature) => (
                  <td key={feature} className={cn(d.n, p.num)}>
                    {row.features[feature] ? formatFact(row.features[feature]) : "—"}
                  </td>
                ))}
                {cell(row.features.momentum, p.sens)}
                {cell(row.momentumRank, p.sens)}
                <td>
                  <button type="button" className={p.linkBtn} aria-haspopup="dialog" aria-label={v.factsAria(row.ticker)} onClick={() => open(rowFacts(row).map((fact) => fact.fact_id), t.portfolioView.fact.rowPanel(row.ticker))}>
                    {v.facts}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > RANKING_PREVIEW ? (
        <p className={p.tableFoot}>
          <button type="button" className={p.linkBtn} onClick={() => setAll(!all)} aria-expanded={all}>
            {all ? v.showLess : v.showAll(rows.length)}
          </button>
        </p>
      ) : null}
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
