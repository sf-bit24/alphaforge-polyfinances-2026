"use client";

import { useState } from "react";
import type { DecisionFact, PortfolioBuildResponse } from "@/lib/contract/portfolio";
import { useI18n } from "@/lib/i18n/provider";
import { RANKING_FEATURES, rankingRows, rowFacts, type RankingRow } from "@/lib/portfolio/decision";
import { engineText } from "@/lib/portfolio/wording";
import { cn } from "@/components/ui/cn";
import d from "./base.module.css";
import { FactChip, factValue, useDecisionLookup } from "./facts";
import p from "./portfolio.module.css";

const RANKING_PREVIEW = 10;

/** The indicators that make the score; momentum is shown apart, as a sensitivity. */
const SCORED_FEATURES = RANKING_FEATURES.filter((feature) => feature !== "momentum");

function cell(fact: DecisionFact | undefined, className?: string) {
  return <td className={cn(d.n, p.num, className)}>{fact ? factValue(fact) : "—"}</td>;
}

function RankingHead() {
  const { t } = useI18n();
  const v = t.portfolioView.ranking;
  return (
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
        {SCORED_FEATURES.map((feature) => (
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
  );
}

/** Kept as a satellite, set aside (and why), or only ranked. */
function RankingStatus({ row }: { row: RankingRow }) {
  const { t } = useI18n();
  const v = t.portfolioView.ranking;
  if (row.shortlisted) return <span className={cn(d.chip, d.stop)}>{v.kept}</span>;
  if (row.ineligible) {
    return (
      <>
        <span className={cn(d.chip, d.wait)}>{v.setAside}</span>
        <span className={p.reason}>{engineText(String(row.ineligible.value ?? ""))}</span>
      </>
    );
  }
  return <span className={cn(d.chip, d.navy)}>{v.ranked}</span>;
}

function RankingLine({ row }: { row: RankingRow }) {
  const { t } = useI18n();
  const v = t.portfolioView.ranking;
  const { open } = useDecisionLookup();
  return (
    <tr className={row.shortlisted ? p.rowKept : undefined}>
      {cell(row.rank)}
      <th scope="row">{row.ticker}</th>
      <td>
        <RankingStatus row={row} />
      </td>
      {cell(row.score)}
      {SCORED_FEATURES.map((feature) => (
        <td key={feature} className={cn(d.n, p.num)}>
          {row.features[feature] ? factValue(row.features[feature]) : "—"}
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
  );
}

/** The single stocks the engine ranked, in its order: the first ones, all of them on demand. */
export function Ranking({ response }: { response: PortfolioBuildResponse }) {
  const { t } = useI18n();
  const v = t.portfolioView.ranking;
  const { facts } = useDecisionLookup();
  const [all, setAll] = useState(false);
  const rows = rankingRows(facts, response.strategy);
  if (rows.length === 0) return null;
  const shown = all ? rows : rows.slice(0, RANKING_PREVIEW);
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
          <RankingHead />
          <tbody>
            {shown.map((row) => (
              <RankingLine key={row.ticker} row={row} />
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
