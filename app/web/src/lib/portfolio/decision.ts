/**
 * Read-only selectors over a finance `Decision`: they find the facts a view needs by their fact_id
 * (`strat.*`, `request.*`) and group them. Nothing is computed: every number on screen is the value of
 * a fact produced by the engine, a position weight, or a constraint limit.
 */
import type { Decision, DecisionFact, DecisionTraceEvent, StrategySummary } from "@/lib/contract/portfolio";

export type FactIndex = ReadonlyMap<string, DecisionFact>;
export type TraceIndex = ReadonlyMap<string, DecisionTraceEvent>;

export function indexFacts(decision: Decision): FactIndex {
  return new Map(decision.facts.map((fact) => [fact.fact_id, fact]));
}

export function indexTrace(decision: Decision): TraceIndex {
  return new Map(decision.trace.map((event) => [event.trace_id, event]));
}

/** Facts whose id starts with `prefix`, with the rest of the id (e.g. a ticker or a sector tag). */
export function factsWithPrefix(facts: FactIndex, prefix: string): Array<{ key: string; fact: DecisionFact }> {
  const out: Array<{ key: string; fact: DecisionFact }> = [];
  for (const [id, fact] of facts) if (id.startsWith(prefix)) out.push({ key: id.slice(prefix.length), fact });
  return out;
}

/* ------------------------------------------------------------------ */
/* Style and equity band (strategy/select.py, debate/pipeline.py)       */
/* ------------------------------------------------------------------ */

export interface StyleBand {
  /** `strat.e_min`: equity share floor of the level. */
  eMin?: DecisionFact;
  /** `strat.e_cap`: equity share cap (dollar rule). */
  eCap?: DecisionFact;
  /** `strat.band_target`: target placed by step 0, before the debate. */
  target?: DecisionFact;
  /** `strat.final.band_target`: target after the lenses lowered it, when they did. */
  finalTarget?: DecisionFact;
  /** `strat.pi`: position aimed at in the band (0 = floor, 1 = cap). */
  pi?: DecisionFact;
}

export function styleBand(facts: FactIndex): StyleBand {
  return {
    eMin: facts.get("strat.e_min"),
    eCap: facts.get("strat.e_cap"),
    target: facts.get("strat.band_target"),
    finalTarget: facts.get("strat.final.band_target"),
    pi: facts.get("strat.pi"),
  };
}

/** A share in [0, 1] of a `%` fact, for the geometry of the band bar only; `null` otherwise. */
export function bandPosition(fact: DecisionFact | undefined): number | null {
  if (!fact || typeof fact.value !== "number" || fact.unit !== "%") return null;
  return fact.value >= 0 && fact.value <= 1 ? fact.value : null;
}

export interface StyleNotes {
  style?: DecisionFact;
  fromLevel?: DecisionFact;
  preference?: DecisionFact;
  /** Refused or capped preferences, contradictions, behaviour flags, fallback steps, notes, error. */
  notes: DecisionFact[];
  sectorCaps: Array<{ tag: string; fact: DecisionFact }>;
  k?: DecisionFact;
  nCandidates?: DecisionFact;
  applied?: DecisionFact;
  riskCost?: DecisionFact;
  baseRisk?: DecisionFact;
}

const NOTE_PREFIXES = [
  "strat.preference_refused.",
  "strat.contradiction.",
  "strat.flag.",
  "strat.fallback.",
  "strat.note.",
  "strat.final.removed.",
];

export function styleNotes(facts: FactIndex): StyleNotes {
  const notes = NOTE_PREFIXES.flatMap((prefix) => factsWithPrefix(facts, prefix).map(({ fact }) => fact));
  const error = facts.get("strat.error");
  if (error) notes.push(error);
  return {
    style: facts.get("strat.style"),
    fromLevel: facts.get("strat.style_from_level"),
    preference: facts.get("strat.preference"),
    notes,
    sectorCaps: factsWithPrefix(facts, "strat.sector_cap.").map(({ key, fact }) => ({ tag: key, fact })),
    k: facts.get("strat.K"),
    nCandidates: facts.get("strat.n_candidates"),
    applied: facts.get("strat.applied"),
    riskCost: facts.get("strat.risk_cost"),
    baseRisk: facts.get("strat.base_risk"),
  };
}

/**
 * Why step 0 kept no single stock, as the engine wrote it: the `processing` of the first source of
 * `strat.K` (« niveau N0 : aucun titre individuel », « preferences.approach = fonds indiciels : FNB seulement »...).
 * Shown as is; null when the fact or its text is missing.
 */
export function shortlistReason(facts: FactIndex): { fact: DecisionFact; reason: string } | null {
  const fact = facts.get("strat.K");
  const reason = fact?.sources[0]?.processing?.trim();
  return fact && reason ? { fact, reason } : null;
}

/* ------------------------------------------------------------------ */
/* Ranking of single stocks                                            */
/* ------------------------------------------------------------------ */

/** Indicators of `strategy.select.FEATURE_UNITS`, in display order; momentum is a sensitivity only. */
export const RANKING_FEATURES = ["vol", "beta", "corr_core", "mdd_long", "dividend_yield", "liquidity_cad", "momentum"] as const;
export type RankingFeature = (typeof RANKING_FEATURES)[number];

export interface RankingRow {
  ticker: string;
  rank?: DecisionFact;
  score?: DecisionFact;
  features: Partial<Record<RankingFeature, DecisionFact>>;
  /** `strat.sens.mom.rank.<T>`: rank by momentum alone, shown as a sensitivity. */
  momentumRank?: DecisionFact;
  /** `strat.ineligible.<T>`: why the stock was set aside. */
  ineligible?: DecisionFact;
  /** In `strategy.shortlist` (kept as a satellite). */
  shortlisted: boolean;
  /** Satellite floor: the final one when the debate changed it (`strat.final.floor.<T>`). */
  floor?: DecisionFact;
}

const FEATURE_SUFFIX = new RegExp(`^(.+)\\.(${RANKING_FEATURES.join("|")})$`);

/**
 * One row per single stock the engine ranked, ordered by the engine's rank (`strat.rank.<T>`). Tickers
 * contain dots (ENB.TO): a feature id is split on its known feature name, never on the first dot.
 */
export function rankingRows(facts: FactIndex, strategy: StrategySummary | null): RankingRow[] {
  const rows = new Map<string, RankingRow>();
  const row = (ticker: string): RankingRow => {
    let current = rows.get(ticker);
    if (!current) {
      current = { ticker, features: {}, shortlisted: strategy?.shortlist.includes(ticker) ?? false };
      rows.set(ticker, current);
    }
    return current;
  };
  for (const { key, fact } of factsWithPrefix(facts, "strat.rank.")) row(key).rank = fact;
  for (const { key, fact } of factsWithPrefix(facts, "strat.score.")) row(key).score = fact;
  for (const { key, fact } of factsWithPrefix(facts, "strat.feat.")) {
    const match = FEATURE_SUFFIX.exec(key);
    if (match?.[1] && match[2]) row(match[1]).features[match[2] as RankingFeature] = fact;
  }
  for (const { key, fact } of factsWithPrefix(facts, "strat.sens.mom.rank.")) row(key).momentumRank = fact;
  for (const { key, fact } of factsWithPrefix(facts, "strat.ineligible.")) row(key).ineligible = fact;
  for (const current of rows.values()) current.floor = facts.get(`strat.final.floor.${current.ticker}`) ?? facts.get(`strat.floor.${current.ticker}`);
  const rankOf = (item: RankingRow) => (typeof item.rank?.value === "number" ? item.rank.value : Number.POSITIVE_INFINITY);
  return [...rows.values()].sort((a, b) => rankOf(a) - rankOf(b) || a.ticker.localeCompare(b.ticker));
}

/** All facts of one ranking row, for its detail panel. */
export function rowFacts(row: RankingRow): DecisionFact[] {
  return [row.rank, row.score, ...RANKING_FEATURES.map((feature) => row.features[feature]), row.momentumRank, row.ineligible, row.floor].filter(
    (fact): fact is DecisionFact => fact !== undefined,
  );
}

/* ------------------------------------------------------------------ */
/* Investor request and Judge                                          */
/* ------------------------------------------------------------------ */

export interface RequestFacts {
  weight?: DecisionFact;
  method?: DecisionFact;
  /** Judge checks of the request as asked, with their observable outcome (« refusée ; 4 violations bloquantes »). */
  checks: DecisionTraceEvent[];
}

export function requestFacts(decision: Decision, facts: FactIndex): RequestFacts {
  return {
    weight: facts.get("request.weight"),
    method: facts.get("request.framed_method"),
    checks: decision.trace.filter((event) => event.agent === "judge" && event.trace_id.endsWith(":demande")),
  };
}

/**
 * A check's provenance as the investor reads it: each part of `derived_from` (« level ; dollar_rule.l_star »,
 * split on « ; ») named by `labels`, a part the table does not know kept as the engine wrote it.
 */
export function derivedFromLabel(raw: string, labels: Readonly<Record<string, string>>): string {
  return raw
    .split(";")
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
    .map((part) => (Object.hasOwn(labels, part) ? labels[part] : part))
    .join(", ");
}

/** The unit of the fact that measures a constraint, to format its limit the same way. */
export function constraintUnit(facts: FactIndex, valueFactId: string | null | undefined): string | undefined {
  return valueFactId ? facts.get(valueFactId)?.unit : undefined;
}
