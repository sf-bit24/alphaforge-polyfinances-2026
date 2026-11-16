/**
 * Deterministic profile rules of the simulator ("calculé par le code"): weighted
 * completeness, knowledge level, risk tolerance and capacity, effective risk, and
 * the localized dimension summaries of `ProfileView`.
 */
import type {
  Completeness,
  Dimension,
  DimensionStatus,
  DimensionView,
  KnowledgeLevel,
  Locale,
  MissingField,
  ProfileDimensionKey,
  ProfileView,
  RiskDetail,
  RiskLevel,
} from "@/lib/contract/schemas";
import { KNOWLEDGE_LEVELS, PROFILE_DIMENSIONS, RISK_LEVELS } from "@/lib/contract/schemas";
import { optionLabel, questionByField, tr, type L } from "./questions";

export const THRESHOLD = 0.7;
export const CAP = 0.95;

/** A2's draft is journaled as a fact, but it is working data: the profile shown to the investor leaves it out. */
export const PORTFOLIO_DRAFT_FIELD = "context.portfolio_draft";

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

const TOTAL_WEIGHT = 10_000;

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

const valueOf = (values: FieldValues, field: string) => values.get(field)?.value;

const INVEST_FREQUENCY_POINTS: Record<string, number> = { never: 0, few: 1, yearly: 2, monthly: 3 };
const NEWS_FOLLOW_POINTS: Record<string, number> = { rarely: 0, monthly: 1, weekly: 2, daily: 3 };
const SELF_ASSESSMENT_LEVELS: Record<string, number> = { beginner: 0, intermediate: 1, advanced: 2 };

/** Observed experience on 0..2, from the 0..6 points of the two experience answers. */
function experienceLevel(points: number): number {
  if (points <= 1) return 0;
  return points <= 4 ? 1 : 2;
}

/** Knowledge level from the three knowledge answers, or the settings override. */
export function knowledgeLevel(values: FieldValues): { level: KnowledgeLevel | null; reason: string } {
  const override = values.get("knowledge.level");
  if (override && typeof override.value === "string") {
    return { level: override.value as KnowledgeLevel, reason: "settings" };
  }
  const frequency = valueOf(values, "knowledge.invest_frequency");
  const news = valueOf(values, "knowledge.news_follow");
  const selfAssessment = valueOf(values, "knowledge.self_assessment");
  if (typeof frequency !== "string" || typeof news !== "string" || typeof selfAssessment !== "string") {
    return { level: null, reason: "incomplete" };
  }
  const experience = (INVEST_FREQUENCY_POINTS[frequency] ?? 0) + (NEWS_FOLLOW_POINTS[news] ?? 0);
  const selfLevel = SELF_ASSESSMENT_LEVELS[selfAssessment] ?? 0;
  // The self-assessment weighs twice the observed experience.
  const level = Math.round((2 * selfLevel + experienceLevel(experience)) / 3);
  return {
    level: KNOWLEDGE_LEVELS[level] ?? "beginner",
    reason: `self=${selfAssessment}, experience=${experience}/6`,
  };
}

const riskAt = (index: number): RiskLevel => RISK_LEVELS[Math.max(0, Math.min(4, index - 1))] ?? "medium";

const DRAWDOWN_REACTION_LEVELS: Record<string, number> = { sell_all: 1, sell_some: 2, hold: 3, buy_more: 5 };

/** Risk tolerance on 1..5 from the declared reaction and the 1..10 scale. */
export function riskTolerance(values: FieldValues): number | null {
  const reaction = valueOf(values, "risk_tolerance.drawdown_reaction");
  const scale = valueOf(values, "risk_tolerance.risk_scale");
  const reactionLevel = typeof reaction === "string" ? (DRAWDOWN_REACTION_LEVELS[reaction] ?? null) : null;
  const scaleLevel = typeof scale === "number" ? Math.max(1, Math.min(5, Math.ceil(scale / 2))) : null;
  if (reactionLevel === null && scaleLevel === null) return null;
  if (reactionLevel === null) return scaleLevel;
  if (scaleLevel === null) return reactionLevel;
  // A declaration can overstate tolerance: the behavioural answer caps it at one level above.
  return Math.min(reactionLevel + 1, Math.round((reactionLevel + scaleLevel) / 2));
}

const HORIZON_CAPACITY: Record<string, number> = { lt3: 1, "3to10": 3, gt10: 5 };
const INCOME_STABILITY_CAPACITY: Record<string, number> = { very_stable: 5, stable: 4, variable: 2, none: 1 };
const UNLISTED_CAPACITY = 3;
/** A high-interest debt or a liquidity need holds the capacity at this level. */
const BURDENED_CAPACITY = 2;

function savingsShareCapacity(sharePct: number): number {
  if (sharePct <= 25) return 5;
  if (sharePct <= 50) return 4;
  return sharePct <= 75 ? 2 : 1;
}

function emergencyFundCapacity(months: number): number {
  if (months >= 6) return 5;
  return months >= 3 ? 3 : 1;
}

/** Situational factors of risk capacity: each gives a level on 1..5, or null while it is unknown. */
const CAPACITY_FACTORS: Array<{ field: string; level: (value: unknown) => number | null }> = [
  { field: "horizon.horizon_band", level: (value) => (typeof value === "string" ? (HORIZON_CAPACITY[value] ?? UNLISTED_CAPACITY) : null) },
  {
    field: "risk_capacity.income_stability",
    level: (value) => (typeof value === "string" ? (INCOME_STABILITY_CAPACITY[value] ?? UNLISTED_CAPACITY) : null),
  },
  { field: "risk_capacity.savings_share", level: (value) => (typeof value === "number" ? savingsShareCapacity(value) : null) },
  { field: "risk_capacity.emergency_fund", level: (value) => (typeof value === "number" ? emergencyFundCapacity(value) : null) },
  { field: "risk_capacity.high_interest_debt", level: (value) => (value === true ? BURDENED_CAPACITY : null) },
  { field: "constraints.liquidity_need", level: (value) => (value === true ? BURDENED_CAPACITY : null) },
];

/** Risk capacity on 1..5: the weakest of the known situational factors. */
export function riskCapacity(values: FieldValues): { level: number; limitedBy: string } | null {
  let weakest: { level: number; limitedBy: string } | null = null;
  for (const factor of CAPACITY_FACTORS) {
    const level = factor.level(valueOf(values, factor.field));
    if (level !== null && (weakest === null || level < weakest.level)) weakest = { level, limitedBy: factor.field };
  }
  return weakest;
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

export function isFieldKnown(values: FieldValues, field: string): boolean {
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
    if (isFieldKnown(values, def.field)) points += def.weight;
    else missing.push({ dimension: def.dimension, field: shortName(def.field), label: tr(def.label, locale), weight: def.weight });
  }
  const score = points / TOTAL_WEIGHT;
  missing.sort((left, right) => right.weight - left.weight);
  return {
    score,
    displayed: Math.min(score, CAP),
    threshold: THRESHOLD,
    cap: CAP,
    ready: score >= THRESHOLD,
    missing: missing.map(({ dimension, field, label }) => ({ dimension, field, label })),
  };
}

const LEVEL_WORDS: Record<Locale, string[]> = {
  fr: ["faible", "faible à moyenne", "moyenne", "moyenne à élevée", "élevée"],
  en: ["low", "low to medium", "medium", "medium to high", "high"],
};

const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** A label inside a sentence: in lower case, except the sigla (IA, AI, CELI), which keep their capitals. */
const inSentence = (label: string) =>
  label.replace(/\p{L}+/gu, (word) => (word.length > 1 && word === word.toUpperCase() ? word : word.toLowerCase()));

/** A 1..5 risk level in words, as the first part of a summary. */
const levelWords = (level: number, locale: Locale) => capitalize(LEVEL_WORDS[locale][level - 1] ?? "");

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

const KNOWLEDGE_LABELS: Record<KnowledgeLevel, L> = {
  beginner: { fr: "Débutant", en: "Beginner" },
  intermediate: { fr: "Intermédiaire", en: "Intermediate" },
  advanced: { fr: "Avancé", en: "Advanced" },
};

/** A confirmed portfolio as the profile keeps it: a count and a total (`context.existing_portfolio`). */
function isPositionsSummary(value: unknown): value is { positions: number; total_value_cad: number } {
  return typeof value === "object" && value !== null && "positions" in value && "total_value_cad" in value;
}

function numberLabel(field: string, value: number, locale: Locale): string {
  const fr = locale === "fr";
  const question = questionByField(field);
  if (question?.kind === "money") return formatMoney(value, locale);
  const number = value.toLocaleString(fr ? "fr-CA" : "en-CA");
  if (question?.kind === "percent") return fr ? `${number} %` : `${number}%`;
  if (question?.kind === "scale" && typeof question.max === "number") return fr ? `${number} sur ${question.max}` : `${number} out of ${question.max}`;
  return question?.unit ? `${number} ${tr(question.unit, locale)}` : number;
}

const FACT_WORDS = {
  yes: { fr: "Oui", en: "Yes" },
  no: { fr: "Non", en: "No" },
  none: { fr: "Aucun", en: "None" },
  noPortfolio: { fr: "Aucun portefeuille existant", en: "No existing portfolio" },
} satisfies Record<string, L>;

function stringLabel(field: string, value: string, locale: Locale): string {
  if (field === "knowledge.level" && value in KNOWLEDGE_LABELS) return tr(KNOWLEDGE_LABELS[value as KnowledgeLevel], locale);
  if (field === "context.existing_portfolio" && value === "none") return tr(FACT_WORDS.noPortfolio, locale);
  return optionLabel(field, value, locale) ?? value;
}

function positionsSummaryLabel({ positions, total_value_cad }: { positions: number; total_value_cad: number }, locale: Locale): string {
  return locale === "fr"
    ? `${positions} ${positions > 1 ? "positions" : "position"}, ${formatMoney(total_value_cad, locale)}`
    : `${positions} ${positions === 1 ? "position" : "positions"}, ${formatMoney(total_value_cad, locale)}`;
}

/**
 * The value of a fact as the investor reads it, in the language of the view (`Fact.label`, like `fact_label` of the
 * real runtime): the option or options chosen, « Oui » or « Non », a number with its unit, never a code or JSON.
 */
export function factLabel(field: string, value: unknown, locale: Locale): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return listLabels(field, value, locale) ?? tr(FACT_WORDS.none, locale);
  if (typeof value === "boolean") return tr(value ? FACT_WORDS.yes : FACT_WORDS.no, locale);
  if (typeof value === "number") return numberLabel(field, value, locale);
  if (typeof value === "string") return stringLabel(field, value, locale);
  return isPositionsSummary(value) ? positionsSummaryLabel(value, locale) : "—";
}

const MAX_PURPOSE_CHARS = 60;

function objectiveParts(values: FieldValues, locale: Locale): string[] {
  const fr = locale === "fr";
  const parts: string[] = [];
  const goal = optionLabel("objective.goal", valueOf(values, "objective.goal"), locale);
  if (goal) parts.push(goal);
  const amount = valueOf(values, "objective.amount");
  if (typeof amount === "number") parts.push(formatMoney(amount, locale));
  const income = valueOf(values, "objective.income_need");
  if (typeof income === "number") parts.push(fr ? `revenu visé ${formatMoney(income, locale)}/an` : `target income ${formatMoney(income, locale)}/yr`);
  const purpose = valueOf(values, "objective.purpose");
  if (typeof purpose === "string") parts.push(purpose.length > MAX_PURPOSE_CHARS ? `${purpose.slice(0, MAX_PURPOSE_CHARS - 3)}…` : purpose);
  return parts;
}

function horizonParts(values: FieldValues, locale: Locale): string[] {
  const parts: string[] = [];
  const band = optionLabel("horizon.horizon_band", valueOf(values, "horizon.horizon_band"), locale);
  if (band) parts.push(band);
  const pattern = optionLabel("horizon.withdrawal_pattern", valueOf(values, "horizon.withdrawal_pattern"), locale);
  if (pattern) parts.push(inSentence(pattern));
  return parts;
}

function riskToleranceParts(values: FieldValues, locale: Locale): string[] {
  const level = riskTolerance(values);
  if (level === null) return [];
  const scale = valueOf(values, "risk_tolerance.risk_scale");
  return typeof scale === "number" ? [levelWords(level, locale), `${scale}/10`] : [levelWords(level, locale)];
}

function riskCapacityParts(values: FieldValues, locale: Locale): string[] {
  const capacity = riskCapacity(values);
  if (capacity === null) return [];
  const limit = inSentence(fieldLabel(capacity.limitedBy, locale));
  return [levelWords(capacity.level, locale), locale === "fr" ? `limitée par : ${limit}` : `limited by: ${limit}`];
}

function constraintsParts(values: FieldValues, locale: Locale): string[] {
  const fr = locale === "fr";
  const parts: string[] = [];
  const accounts = listLabels("constraints.accounts", valueOf(values, "constraints.accounts"), locale);
  if (accounts) parts.push(accounts);
  const liquidity = valueOf(values, "constraints.liquidity_need");
  if (liquidity === true) parts.push(fr ? "liquidité requise" : "liquidity required");
  if (liquidity === false) parts.push(fr ? "pas de besoin de liquidité" : "no liquidity need");
  return parts;
}

/** The sectors excluded, without the "none" and "other" choices, which name no sector. */
function exclusionsPart(exclusions: unknown[], locale: Locale): string {
  const fr = locale === "fr";
  const named = exclusions.filter((item) => item !== "none" && item !== "other");
  const labels = listLabels("preferences.exclusions", named, locale);
  if (!labels) return fr ? "Aucune exclusion" : "No exclusion";
  return fr ? `Exclut : ${inSentence(labels)}` : `Excludes: ${inSentence(labels)}`;
}

function preferencesParts(values: FieldValues, locale: Locale): string[] {
  const parts: string[] = [];
  const exclusions = valueOf(values, "preferences.exclusions");
  if (Array.isArray(exclusions)) parts.push(exclusionsPart(exclusions, locale));
  const other = valueOf(values, "preferences.exclusions_other");
  if (typeof other === "string") parts.push(other);
  const themes = valueOf(values, "preferences.themes");
  if (Array.isArray(themes)) {
    const labels = listLabels("preferences.themes", themes.filter((item) => item !== "none"), locale);
    if (labels) parts.push(locale === "fr" ? `intérêt : ${inSentence(labels)}` : `interest: ${inSentence(labels)}`);
  }
  return parts;
}

const SUMMARY_PARTS: Record<ProfileDimensionKey, (values: FieldValues, locale: Locale) => string[]> = {
  objective: objectiveParts,
  horizon: horizonParts,
  risk_tolerance: riskToleranceParts,
  risk_capacity: riskCapacityParts,
  constraints: constraintsParts,
  preferences: preferencesParts,
};

function summarize(dimension: ProfileDimensionKey, values: FieldValues, locale: Locale): string | null {
  const parts = SUMMARY_PARTS[dimension](values, locale);
  return parts.length > 0 ? parts.join(" · ") : null;
}

/** Values of a dimension's fields, by short name. */
function dimensionFields(values: FieldValues, dimension: Dimension): Record<string, unknown> {
  const fields: Record<string, unknown> = {};
  for (const [field, fact] of values) {
    if (field.startsWith(`${dimension}.`) && field !== PORTFOLIO_DRAFT_FIELD) fields[shortName(field)] = fact.value;
  }
  return fields;
}

function dimensionStatus(known: number, required: number): DimensionStatus {
  if (known === 0) return "missing";
  return known === required ? "known" : "partial";
}

export function dimensionViews(values: FieldValues, locale: Locale): ProfileView["dimensions"] {
  const views = {} as Record<ProfileDimensionKey, DimensionView>;
  for (const dimension of PROFILE_DIMENSIONS) {
    const required = REQUIRED_FIELDS.filter((def) => def.dimension === dimension);
    const known = required.filter((def) => isFieldKnown(values, def.field)).length;
    const fields = dimensionFields(values, dimension);
    views[dimension] = {
      status: dimensionStatus(known, required.length),
      summary: known === 0 && Object.keys(fields).length === 0 ? null : summarize(dimension, values, locale),
      fields,
    };
  }
  return { ...views, context: contextView(values, locale) };
}

/** The confirmed portfolio as the profile keeps it: a count and a total, not the positions. */
interface PortfolioSummary {
  positions: number;
  total_value_cad: number;
}

function isPortfolioSummary(value: unknown): value is PortfolioSummary {
  return typeof value === "object" && value !== null && "positions" in value && "total_value_cad" in value;
}

function contextSummary(values: FieldValues, locale: Locale): string | null {
  const fr = locale === "fr";
  const existing = valueOf(values, "context.existing_portfolio");
  if (existing === "none") return fr ? "Aucun portefeuille existant" : "No existing portfolio";
  if (isPortfolioSummary(existing)) {
    const { positions, total_value_cad } = existing;
    return fr
      ? `Portefeuille existant : ${positions} ${positions > 1 ? "positions" : "position"}, ${formatMoney(total_value_cad, locale)}`
      : `Existing portfolio: ${positions} ${positions === 1 ? "position" : "positions"}, ${formatMoney(total_value_cad, locale)}`;
  }
  if (valueOf(values, "context.has_portfolio") === true) return fr ? "Portefeuille existant à analyser" : "Existing portfolio to analyse";
  return null;
}

function contextStatus(values: FieldValues, fields: Record<string, unknown>): DimensionStatus {
  if (valueOf(values, "context.existing_portfolio") !== undefined) return "known";
  return Object.keys(fields).length > 0 ? "partial" : "missing";
}

/** The `context` dimension (existing portfolio), outside the five of the profile. */
function contextView(values: FieldValues, locale: Locale): DimensionView {
  const fields = dimensionFields(values, "context");
  return { status: contextStatus(values, fields), summary: contextSummary(values, locale), fields };
}
