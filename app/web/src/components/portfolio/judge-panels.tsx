"use client";

import { useState } from "react";
import type { AppliedAmendment, ConstraintCheck, DebateRoundSummary, LensVerdict, PortfolioBuildResponse } from "@/lib/contract/portfolio";
import { curly } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { constraintUnit, derivedFromLabel, type FactIndex } from "@/lib/portfolio/decision";
import { formatLimit } from "@/lib/portfolio/format";
import { engineText } from "@/lib/portfolio/wording";
import { cn } from "@/components/ui/cn";
import d from "./base.module.css";
import { FactChip, FactChips, useDecisionLookup } from "./facts";
import p from "./portfolio.module.css";

/* ------------------------------------------------------------------ */
/* Debate of the lenses                                                 */
/* ------------------------------------------------------------------ */

const VERDICT_TONE: Record<LensVerdict, string | undefined> = { soutien: d.ok, objection_maintenue: d.wait, objection_satisfaite: d.navy };

/** The verdict of each lens in the last round, with the emphasis it put when the engine recorded one. */
function LensVerdicts({ round }: { round: DebateRoundSummary }) {
  const { t } = useI18n();
  const v = t.portfolioView.debate;
  const { facts } = useDecisionLookup();
  return (
    <ul className={p.lenses}>
      {Object.entries(round.verdicts).map(([lens, verdict]) => (
        <li key={lens}>
          <b>{v.lenses[lens] ?? lens}</b>
          <span className={p.chips}>
            <span className={cn(d.chip, VERDICT_TONE[verdict])}>{v.verdicts[verdict]}</span>
            {facts.has(`emphasis.${lens}`) ? <FactChip id={`emphasis.${lens}`} compact /> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** The amendments the lenses proposed over all rounds, applied or rejected by the code, with their evidence. */
function Amendments({ amendments }: { amendments: AppliedAmendment[] }) {
  const { t } = useI18n();
  const v = t.portfolioView.debate;
  const { facts } = useDecisionLookup();
  return (
    <div className={p.block}>
      <h3>{v.amendments}</h3>
      {amendments.length === 0 ? (
        <p className={p.sub}>{v.noAmendment}</p>
      ) : (
        <ul className={p.list}>
          {amendments.map((item, index) => (
            <li key={index}>
              <p>
                <b>{v.lenses[item.lens] ?? item.lens}</b> · {item.status === "applique" ? v.applied : v.rejected} · {curly(engineText(item.amendment.reason_fr))}
              </p>
              {/* Evidence the decision does not hold (a rule id instead of a fact id…) is not shown: the reason says it in words. */}
              <p className={p.sub}>{curly(engineText(item.why_fr))}</p>
              <FactChips ids={item.amendment.evidence_fact_ids.filter((id) => facts.has(id))} limit={3} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Debate({ response }: { response: PortfolioBuildResponse }) {
  const { t } = useI18n();
  const v = t.portfolioView.debate;
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
      <LensVerdicts round={last} />
      <Amendments amendments={amendments} />
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Judge                                                                */
/* ------------------------------------------------------------------ */

function ConstraintRow({ check, facts }: { check: ConstraintCheck; facts: FactIndex }) {
  const { t } = useI18n();
  const v = t.portfolioView.constraints;
  return (
    <tr className={check.violated ? p.rowViolated : undefined}>
      <td>{engineText(check.description_fr)}</td>
      <td>{engineText(derivedFromLabel(check.derived_from, v.derivedFrom))}</td>
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

function ConstraintTable({ rows }: { rows: ConstraintCheck[] }) {
  const { t } = useI18n();
  const v = t.portfolioView.constraints;
  const { facts } = useDecisionLookup();
  return (
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
  );
}

/** The Judge's checks: the active or violated ones first, all of them on demand. */
export function Constraints({ checks }: { checks: ConstraintCheck[] }) {
  const { t } = useI18n();
  const v = t.portfolioView.constraints;
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
          <ConstraintTable rows={rows} />
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
