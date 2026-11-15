/**
 * Questions of the simulator: the rules that order the deterministic base questions (with a
 * few branches), the rendering of a catalog entry as a contract `Question`, and the validation
 * of an answer by kind. The catalogs themselves are in `base-questions.ts` and `a1-questions.ts`.
 */
import type {
  AnswerValue,
  Dimension,
  KnowledgeLevel,
  Locale,
  Question,
  QuestionKind,
} from "@/lib/contract/schemas";
import { A1_QUESTIONS } from "./a1-questions";
import { BASE_QUESTIONS } from "./base-questions";

export interface L {
  fr: string;
  en: string;
}

export const tr = (text: L, locale: Locale): string => text[locale];

export interface OptionDef {
  value: string;
  label: L;
}

export interface QuestionDef {
  id: string;
  source: "deterministic" | "a1";
  dimension: Dimension;
  kind: QuestionKind;
  /** Profile field written by the answer, `<dimension>.<name>`. */
  field: string;
  prompt: L;
  help?: L | { beginner: L; other: L };
  options?: OptionDef[];
  min?: number;
  max?: number;
  unit?: L;
  required?: boolean;
}

/** Branches of the questionnaire: a question listed here is asked only if its rule holds. */
const BRANCHES: Record<string, { trigger: string; when: (answers: Record<string, AnswerValue>) => boolean; why: L }> = {
  q_income_need: {
    trigger: "q_goal",
    when: (answers) => answers.q_goal === "income",
    why: { fr: "objectif = revenu régulier", en: "goal = regular income" },
  },
  q_liquidity: {
    trigger: "q_horizon",
    when: (answers) => answers.q_horizon === "lt3",
    why: { fr: "horizon de moins de 3 ans", en: "horizon under 3 years" },
  },
  q_exclusions_other: {
    trigger: "q_exclusions",
    when: (answers) => Array.isArray(answers.q_exclusions) && answers.q_exclusions.includes("other"),
    why: { fr: "exclusion « Autre » cochée", en: "\"Other\" exclusion selected" },
  },
};

const BASE_BY_ID = new Map(BASE_QUESTIONS.map((question) => [question.id, question]));

export function baseQuestion(id: string): QuestionDef | undefined {
  return BASE_BY_ID.get(id);
}

/** Next base question by the rules, or null when the questionnaire is done. */
export function nextBaseQuestion(answers: Record<string, AnswerValue>): {
  id: string;
  branch: L | null;
} | null {
  for (const question of BASE_QUESTIONS) {
    if (question.id in answers) continue;
    const branch = BRANCHES[question.id];
    if (branch && !branch.when(answers)) continue;
    return { id: question.id, branch: branch?.why ?? null };
  }
  return null;
}

/** Branch rules decided by the answer to `questionId`, for the trace. */
export function branchesTriggeredBy(
  questionId: string,
  answers: Record<string, AnswerValue>,
): Array<{ question: string; active: boolean; rule: L }> {
  return Object.entries(BRANCHES)
    .filter(([, branch]) => branch.trigger === questionId)
    .map(([id, branch]) => ({ question: id, active: branch.when(answers), rule: branch.why }));
}

const A1_BY_ID = new Map(A1_QUESTIONS.map((question) => [question.id, question]));

export function a1Question(id: string): QuestionDef | undefined {
  return A1_BY_ID.get(id);
}

export function questionByField(field: string): QuestionDef | undefined {
  return [...BASE_QUESTIONS, ...A1_QUESTIONS].find((question) => question.field === field);
}

const PERCENT_RANGE = { min: 0, max: 100 };

/** The help text, in its beginner version when there are two and the level is beginner or unknown. */
function renderHelp(def: QuestionDef, locale: Locale, level: KnowledgeLevel | null): string | null {
  if (!def.help) return null;
  if (!("beginner" in def.help)) return tr(def.help, locale);
  return tr(level === "beginner" || level === null ? def.help.beginner : def.help.other, locale);
}

function renderUnit(def: QuestionDef, locale: Locale): string | null {
  if (def.unit) return tr(def.unit, locale);
  return def.kind === "money" ? "CAD" : null;
}

/** Render a catalog entry as a contract `Question` in the given locale and level. */
export function renderQuestion(def: QuestionDef, locale: Locale, level: KnowledgeLevel | null): Question {
  const defaultRange = def.kind === "percent" ? PERCENT_RANGE : { min: null, max: null };
  return {
    id: def.id,
    source: def.source,
    dimension: def.dimension,
    kind: def.kind,
    prompt: tr(def.prompt, locale),
    help: renderHelp(def, locale, level),
    options: def.options ? def.options.map((option) => ({ value: option.value, label: tr(option.label, locale) })) : null,
    min: def.min ?? defaultRange.min,
    max: def.max ?? defaultRange.max,
    unit: renderUnit(def, locale),
    required: def.required ?? true,
    // Short name, as in the CONTRACTS.md 3.3 example (`horizon_band`).
    field: def.field.slice(def.field.indexOf(".") + 1),
  };
}

/** Label of an option value, for summaries. */
export function optionLabel(field: string, value: unknown, locale: Locale): string | null {
  const def = questionByField(field);
  const option = def?.options?.find((candidate) => candidate.value === value);
  return option ? tr(option.label, locale) : null;
}

export type ValidationResult = { ok: true; value: AnswerValue } | { ok: false; reason: L; details: Record<string, unknown> };

interface Range {
  min: number | null;
  max: number | null;
}

const MAX_TEXT_LENGTH = 2000;

function invalid(question: Question, reason: L, details: Record<string, unknown> = {}): ValidationResult {
  return { ok: false, reason, details: { question_id: question.id, kind: question.kind, ...details } };
}

const allowedValues = (question: Question): string[] => question.options?.map((option) => option.value) ?? [];

const rangeOf = (question: Question): Range => ({ min: question.min ?? null, max: question.max ?? null });

function isInRange(value: number, { min, max }: Range): boolean {
  return (min === null || value >= min) && (max === null || value <= max);
}

function validateSingleChoice(question: Question, value: unknown): ValidationResult {
  const allowed = allowedValues(question);
  if (typeof value !== "string" || !allowed.includes(value)) {
    return invalid(question, { fr: "Choisissez une des options proposées.", en: "Choose one of the options." }, { allowed });
  }
  return { ok: true, value };
}

/** A list of known options, without duplicates; a required question needs at least one. */
function validateMultiChoice(question: Question, value: unknown): ValidationResult {
  const allowed = allowedValues(question);
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    return invalid(question, { fr: "Une liste d'options est attendue.", en: "A list of options is expected." }, { allowed });
  }
  const unique = [...new Set(value as string[])];
  const unknown = unique.filter((item) => !allowed.includes(item));
  if (unknown.length > 0) {
    return invalid(question, { fr: "Certaines options sont inconnues.", en: "Some options are unknown." }, { allowed, unknown });
  }
  if (question.required && unique.length === 0) {
    return invalid(question, { fr: "Cochez au moins une option.", en: "Select at least one option." }, { allowed });
  }
  return { ok: true, value: unique };
}

function validateBoolean(question: Question, value: unknown): ValidationResult {
  if (typeof value !== "boolean") return invalid(question, { fr: "Répondez par oui ou par non.", en: "Answer yes or no." });
  return { ok: true, value };
}

/** `number` and `money`: a finite number within the bounds; an amount of money is never negative. */
function validateNumber(question: Question, value: unknown): ValidationResult {
  const range = rangeOf(question);
  if (typeof value !== "number" || !Number.isFinite(value) || !isInRange(value, range) || (question.kind === "money" && value < 0)) {
    return invalid(question, { fr: "Entrez un nombre dans les bornes permises.", en: "Enter a number within the allowed range." }, { ...range });
  }
  return { ok: true, value };
}

function validatePercent(question: Question, value: unknown): ValidationResult {
  if (typeof value !== "number" || !Number.isFinite(value) || !isInRange(value, PERCENT_RANGE)) {
    return invalid(question, { fr: "Entrez un pourcentage de 0 à 100.", en: "Enter a percentage from 0 to 100." }, { ...PERCENT_RANGE });
  }
  return { ok: true, value };
}

function validateScale(question: Question, value: unknown): ValidationResult {
  const range = rangeOf(question);
  if (typeof value !== "number" || !Number.isInteger(value) || !isInRange(value, range)) {
    return invalid(question, { fr: "Choisissez un entier de l'échelle.", en: "Choose a whole number on the scale." }, { ...range });
  }
  return { ok: true, value };
}

/** The text is kept trimmed. */
function validateText(question: Question, value: unknown): ValidationResult {
  if (typeof value !== "string") return invalid(question, { fr: "Un texte est attendu.", en: "Text is expected." });
  const text = value.trim();
  if (text.length < 1 || text.length > MAX_TEXT_LENGTH) {
    return invalid(
      question,
      { fr: "Le texte doit compter de 1 à 2 000 caractères.", en: "Text must be 1 to 2,000 characters long." },
      { min: 1, max: MAX_TEXT_LENGTH },
    );
  }
  return { ok: true, value: text };
}

const VALIDATORS: Record<QuestionKind, (question: Question, value: unknown) => ValidationResult> = {
  single_choice: validateSingleChoice,
  multi_choice: validateMultiChoice,
  boolean: validateBoolean,
  number: validateNumber,
  money: validateNumber,
  percent: validatePercent,
  scale: validateScale,
  text: validateText,
};

/** Validate a value against a question, by kind (CONTRACTS.md 3.3). */
export function validateAnswer(question: Question, value: unknown): ValidationResult {
  return VALIDATORS[question.kind](question, value);
}
