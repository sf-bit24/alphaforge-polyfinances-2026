/**
 * Deterministic profile rules of the simulator ("calculé par le code"): weighted
 * completeness, knowledge level, risk tolerance and capacity, effective risk, and
 * the localized dimension summaries of `ProfileView`.
 */
import type {
  Completeness,
  Dimension,
  DimensionView,
  KnowledgeLevel,
  Locale,
  MissingField,
  ProfileDimensionKey,
  ProfileView,
  RiskDetail,
  RiskLevel,
} from "@/lib/contract/schemas";
import { PROFILE_DIMENSIONS, RISK_LEVELS } from "@/lib/contract/schemas";
import { optionLabel, tr, type L } from "./questions";

export const THRESHOLD = 0.7;
export const CAP = 0.95;

export interface StoredFact {
  field: string;
  value: unknown;
  provenance: string;
  at: string;
}

/** Latest value per field. */
export type FieldValues = Map<string, StoredFact>;

interface FieldDef {
  field: string;
  dimension: Dimension;
  /** Weight in basis points; the weights of required fields sum to 10 000. */
  weight: number;
  label: L;
}

export const REQUIRED_FIELDS: FieldDef[] = [
  { field: "knowledge.level", dimension: "knowledge", weight: 500, label: { fr: "Niveau de connaissances", en: "Knowledge level" } },
  { field: "objective.goal", dimension: "objective", weight: 1000, label: { fr: "Objectif principal", en: "Main goal" } },
  { field: "objective.amount", dimension: "objective", weight: 500, label: { fr: "Montant à placer", en: "Amount to invest" } },
  { field: "objective.purpose", dimension: "objective", weight: 600, label: { fr: "Finalité de l'argent", en: "Purpose of the money" } },
  { field: "horizon.horizon_band", dimension: "horizon", weight: 1000, label: { fr: "Horizon de placement", en: "Investment horizon" } },
  { field: "horizon.withdrawal_pattern", dimension: "horizon", weight: 600, label: { fr: "Profil de retrait", en: "Withdrawal pattern" } },
  { field: "risk_tolerance.drawdown_reaction", dimension: "risk_tolerance", weight: 800, label: { fr: "Réaction à une baisse", en: "Reaction to a decline" } },
  { field: "risk_tolerance.risk_scale", dimension: "risk_tolerance", weight: 400, label: { fr: "Variations acceptées", en: "Accepted fluctuations" } },
  { field: "risk_capacity.income_stability", dimension: "risk_capacity", weight: 600, label: { fr: "Stabilité des revenus", en: "Income stability" } },
  { field: "risk_capacity.savings_share", dimension: "risk_capacity", weight: 400, label: { fr: "Part de l'épargne", en: "Share of savings" } },
  { field: "risk_capacity.emergency_fund", dimension: "risk_capacity", weight: 800, label: { fr: "Fonds d'urgence", en: "Emergency fund" } },
  { field: "risk_capacity.high_interest_debt", dimension: "risk_capacity", weight: 500, label: { fr: "Dettes à taux élevé", en: "High-interest debt" } },
  { field: "constraints.accounts", dimension: "constraints", weight: 500, label: { fr: "Comptes possibles", en: "Eligible accounts" } },
  { field: "constraints.liquidity_need", dimension: "constraints", weight: 500, label: { fr: "Besoin de liquidité", en: "Liquidity need" } },
  { field: "preferences.exclusions", dimension: "preferences", weight: 500, label: { fr: "Exclusions", en: "Exclusions" } },
  { field: "preferences.themes", dimension: "preferences", weight: 400, label: { fr: "Thèmes d'intérêt", en: "Themes of interest" } },
  { field: "context.existing_portfolio", dimension: "context", weight: 400, label: { fr: "Portefeuille existant", en: "Existing portfolio" } },
];

export function fieldDef(field: string): FieldDef | undefined {
  return REQUIRED_FIELDS.find((def) => def.field === field);
}

export function fieldLabel(field: string, locale: Locale): string {
  const def = fieldDef(field);
  return def ? tr(def.label, locale) : field;
}

const shortName = (field: string) => field.slice(field.indexOf(".") + 1);

/** Knowledge level from the three knowledge answers, or the settings override. */
export function knowledgeLevel(values: FieldValues): { level: KnowledgeLevel | null; reason: string } {
  const override = values.get("knowledge.level");
  if (override && typeof override.value === "string") {
    return { level: override.value as KnowledgeLevel, reason: "settings" };
  }
  const frequency = values.get("knowledge.invest_frequency")?.value;
  const news = values.get("knowledge.news_follow")?.value;
  const self = values.get("knowledge.self_assessment")?.value;
  if (typeof frequency !== "string" || typeof news !== "string" || typeof self !== "string") {
    return { level: null, reason: "incomplete" };
  }
  const frequencyPoints = { never: 0, few: 1, yearly: 2, monthly: 3 }[frequency] ?? 0;
  const newsPoints = { rarely: 0, monthly: 1, weekly: 2, daily: 3 }[news] ?? 0;
  const experience = frequencyPoints + newsPoints;
  const experienceLevel = experience <= 1 ? 0 : experience <= 4 ? 1 : 2;
  const selfLevel = { beginner: 0, intermediate: 1, advanced: 2 }[self] ?? 0;
  // The self-assessment weighs twice the observed experience.
  const level = Math.round((2 * selfLevel + experienceLevel) / 3);
  const levels: KnowledgeLevel[] = ["beginner", "intermediate", "advanced"];
  return {
    level: levels[level] ?? "beginner",
    reason: `self=${self}, experience=${experience}/6`,
  };
}

const riskAt = (index: number): RiskLevel => RISK_LEVELS[Math.max(0, Math.min(4, index - 1))] ?? "medium";

/** Risk tolerance on 1..5 from the declared reaction and the 1..10 scale. */
export function riskTolerance(values: FieldValues): number | null {
  const reaction = values.get("risk_tolerance.drawdown_reaction")?.value;
  const scale = values.get("risk_tolerance.risk_scale")?.value;
  const reactionLevel =
    typeof reaction === "string" ? ({ sell_all: 1, sell_some: 2, hold: 3, buy_more: 5 }[reaction] ?? null) : null;
  const scaleLevel = typeof scale === "number" ? Math.max(1, Math.min(5, Math.ceil(scale / 2))) : null;
  if (reactionLevel === null && scaleLevel === null) return null;
  if (reactionLevel === null) return scaleLevel;
  if (scaleLevel === null) return reactionLevel;
  // A declaration can overstate tolerance: the behavioural answer caps it at one level above.
  return Math.min(reactionLevel + 1, Math.round((reactionLevel + scaleLevel) / 2));
}

/** Risk capacity on 1..5: the weakest of the known situational factors. */
export function riskCapacity(values: FieldValues): { level: number; limitedBy: string } | null {
  const factors: Array<[string, number]> = [];
  const horizon = values.get("horizon.horizon_band")?.value;
  if (typeof horizon === "string") factors.push(["horizon.horizon_band", { lt3: 1, "3to10": 3, gt10: 5 }[horizon] ?? 3]);
  const income = values.get("risk_capacity.income_stability")?.value;
  if (typeof income === "string") {
    factors.push(["risk_capacity.income_stability", { very_stable: 5, stable: 4, variable: 2, none: 1 }[income] ?? 3]);
  }
  const share = values.get("risk_capacity.savings_share")?.value;
  if (typeof share === "number") {
    factors.push(["risk_capacity.savings_share", share <= 25 ? 5 : share <= 50 ? 4 : share <= 75 ? 2 : 1]);
  }
  const fund = values.get("risk_capacity.emergency_fund")?.value;
  if (typeof fund === "number") factors.push(["risk_capacity.emergency_fund", fund >= 6 ? 5 : fund >= 3 ? 3 : 1]);
  const debt = values.get("risk_capacity.high_interest_debt")?.value;
  if (debt === true) factors.push(["risk_capacity.high_interest_debt", 2]);
  const liquidity = values.get("constraints.liquidity_need")?.value;
  if (liquidity === true) factors.push(["constraints.liquidity_need", 2]);
  if (factors.length === 0) return null;
  const weakest = factors.reduce((low, factor) => (factor[1] < low[1] ? factor : low));
  return { level: weakest[1], limitedBy: weakest[0] };
}

export function effectiveRisk(values: FieldValues): RiskLevel | null {
  const tolerance = riskTolerance(values);
  const capacity = riskCapacity(values);
  if (tolerance === null || capacity === null) return null;
  return riskAt(Math.min(tolerance, capacity.level));
}

/** `ProfileView.risk`: the three levels behind `effective_risk`. */
export function riskDetail(values: FieldValues): RiskDetail {
  const tolerance = riskTolerance(values);
  const capacity = riskCapacity(values);
  return {
    tolerance: tolerance === null ? null : riskAt(tolerance),
    capacity: capacity === null ? null : riskAt(capacity.level),
    effective: effectiveRisk(values),
  };
}

function isKnown(values: FieldValues, field: string): boolean {
  if (field === "knowledge.level") return knowledgeLevel(values).level !== null;
  const fact = values.get(field);
  if (!fact) return false;
  if (Array.isArray(fact.value)) return true;
  return fact.value !== null && fact.value !== undefined && fact.value !== "";
}

export function completeness(values: FieldValues, locale: Locale): Completeness {
  let points = 0;
  const missing: Array<MissingField & { weight: number }> = [];
  for (const def of REQUIRED_FIELDS) {
    if (isKnown(values, def.field)) points += def.weight;
    else missing.push({ dimension: def.dimension, field: shortName(def.field), label: tr(def.label, locale), weight: def.weight });
  }
  const score = points / 10_000;
  missing.sort((a, b) => b.weight - a.weight);
  return {
    score,
    displayed: Math.min(score, CAP),
    threshold: THRESHOLD,
    cap: CAP,
    ready: score >= THRESHOLD,
    missing: missing.map(({ dimension, field, label }) => ({ dimension, field, label })),
  };
}

export function isFieldKnown(values: FieldValues, field: string): boolean {
  return isKnown(values, field);
}

const LEVEL_WORDS: Record<Locale, string[]> = {
  fr: ["faible", "faible à moyenne", "moyenne", "moyenne à élevée", "élevée"],
  en: ["low", "low to medium", "medium", "medium to high", "high"],
};

const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export function formatMoney(value: number, locale: Locale, currency = "CAD"): string {
  return new Intl.NumberFormat(locale === "fr" ? "fr-CA" : "en-CA", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatPercent(share: number, locale: Locale): string {
  return new Intl.NumberFormat(locale === "fr" ? "fr-CA" : "en-CA", {
    style: "percent",
    maximumFractionDigits: 0,
  }).format(share);
}

function listLabels(field: string, value: unknown, locale: Locale): string | null {
  if (!Array.isArray(value)) return null;
  const labels = value.map((item) => optionLabel(field, item, locale) ?? String(item));
  return labels.length > 0 ? labels.join(", ") : null;
}

function summarize(dimension: ProfileDimensionKey, values: FieldValues, locale: Locale): string | null {
  const get = (field: string) => values.get(field)?.value;
  const parts: string[] = [];
  const fr = locale === "fr";
  switch (dimension) {
    case "objective": {
      const goal = optionLabel("objective.goal", get("objective.goal"), locale);
      if (goal) parts.push(goal);
      const amount = get("objective.amount");
      if (typeof amount === "number") parts.push(formatMoney(amount, locale));
      const income = get("objective.income_need");
      if (typeof income === "number") parts.push(fr ? `revenu visé ${formatMoney(income, locale)}/an` : `target income ${formatMoney(income, locale)}/yr`);
      const purpose = get("objective.purpose");
      if (typeof purpose === "string") parts.push(purpose.length > 60 ? `${purpose.slice(0, 57)}…` : purpose);
      break;
    }
    case "horizon": {
      const band = optionLabel("horizon.horizon_band", get("horizon.horizon_band"), locale);
      if (band) parts.push(band);
      const pattern = optionLabel("horizon.withdrawal_pattern", get("horizon.withdrawal_pattern"), locale);
      if (pattern) parts.push(pattern.toLowerCase());
      break;
    }
    case "risk_tolerance": {
      const level = riskTolerance(values);
      if (level === null) break;
      parts.push(capitalize(LEVEL_WORDS[locale][level - 1] ?? ""));
      const scale = get("risk_tolerance.risk_scale");
      if (typeof scale === "number") parts.push(`${scale}/10`);
      break;
    }
    case "risk_capacity": {
      const capacity = riskCapacity(values);
      if (capacity === null) break;
      const limit = fieldLabel(capacity.limitedBy, locale).toLowerCase();
      parts.push(capitalize(LEVEL_WORDS[locale][capacity.level - 1] ?? ""));
      parts.push(fr ? `limitée par : ${limit}` : `limited by: ${limit}`);
      break;
    }
    case "constraints": {
      const accounts = listLabels("constraints.accounts", get("constraints.accounts"), locale);
      if (accounts) parts.push(accounts);
      const liquidity = get("constraints.liquidity_need");
      if (liquidity === true) parts.push(fr ? "liquidité requise" : "liquidity required");
      if (liquidity === false) parts.push(fr ? "pas de besoin de liquidité" : "no liquidity need");
      break;
    }
    case "preferences": {
      const exclusions = get("preferences.exclusions");
      if (Array.isArray(exclusions)) {
        const kept = exclusions.filter((item) => item !== "none" && item !== "other");
        const labels = listLabels("preferences.exclusions", kept, locale);
        parts.push(labels ? (fr ? `Exclut : ${labels.toLowerCase()}` : `Excludes: ${labels.toLowerCase()}`) : fr ? "Aucune exclusion" : "No exclusion");
      }
      const other = get("preferences.exclusions_other");
      if (typeof other === "string") parts.push(other);
      const themes = get("preferences.themes");
      if (Array.isArray(themes)) {
        const kept = themes.filter((item) => item !== "none");
        const labels = listLabels("preferences.themes", kept, locale);
        if (labels) parts.push(fr ? `intérêt : ${labels.toLowerCase()}` : `interest: ${labels.toLowerCase()}`);
      }
      break;
    }
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

export function dimensionViews(values: FieldValues, locale: Locale): ProfileView["dimensions"] {
  const views = {} as Record<ProfileDimensionKey, DimensionView>;
  for (const dimension of PROFILE_DIMENSIONS) {
    const required = REQUIRED_FIELDS.filter((def) => def.dimension === dimension);
    const known = required.filter((def) => isKnown(values, def.field)).length;
    const fields: Record<string, unknown> = {};
    for (const [field, fact] of values) {
      if (field.startsWith(`${dimension}.`)) fields[shortName(field)] = fact.value;
    }
    views[dimension] = {
      status: known === 0 ? "missing" : known === required.length ? "known" : "partial",
      summary: known === 0 && Object.keys(fields).length === 0 ? null : summarize(dimension, values, locale),
      fields,
    };
  }
  return { ...views, context: contextView(values, locale) };
}

/** The `context` dimension (existing portfolio), outside the five of the profile. */
function contextView(values: FieldValues, locale: Locale): DimensionView {
  const fr = locale === "fr";
  const fields: Record<string, unknown> = {};
  for (const [field, fact] of values) {
    if (field.startsWith("context.") && field !== "context.portfolio_draft") fields[shortName(field)] = fact.value;
  }
  const existing = values.get("context.existing_portfolio")?.value;
  let summary: string | null = null;
  if (existing === "none") summary = fr ? "Aucun portefeuille existant" : "No existing portfolio";
  else if (existing && typeof existing === "object" && "positions" in existing && "total_value_cad" in existing) {
    const { positions, total_value_cad } = existing as { positions: number; total_value_cad: number };
    summary = fr
      ? `Portefeuille existant : ${positions} position(s), ${formatMoney(total_value_cad, locale)}`
      : `Existing portfolio: ${positions} position(s), ${formatMoney(total_value_cad, locale)}`;
  } else if (values.get("context.has_portfolio")?.value === true) {
    summary = fr ? "Portefeuille existant à analyser" : "Existing portfolio to analyse";
  }
  return {
    status: existing !== undefined ? "known" : Object.keys(fields).length > 0 ? "partial" : "missing",
    summary,
    fields,
  };
}
