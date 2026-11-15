import type { AnswerValue, Question, QuestionKind } from "@/lib/contract/schemas";

/**
 * The sample profile behind « Passer les questions » (tests and demos): a balanced investor
 * of about 35, saving for retirement over more than ten years, without an existing portfolio.
 * The interface answers the base questions itself with `base.answer`, so the runtime builds a
 * real profile (completeness, risk, A1 follow-ups) in every mode; nothing is written around it.
 *
 * Keys are the base question ids of the Python runtime (`questionnaire.yaml`). A question
 * missing here (the mock simulator has its own questionnaire), or an answer the question no
 * longer accepts, falls back to `fallbackAnswer`.
 */
export const SAMPLE_ANSWERS: Readonly<Record<string, AnswerValue>> = {
  q_kn_invest_freq: "several_per_year",
  q_kn_news: "monthly",
  q_kn_products: ["savings_gic", "mutual_funds", "etf"],
  q_kn_quiz_diversification: "etf",
  q_kn_quiz_bond_rates: "falls",
  q_kn_self: "intermediate",
  q_goal: "retirement",
  q_horizon: "gt10",
  q_drop_reaction: "hold",
  q_risk_attitude: "moderate",
  q_sell_threshold: "20to30",
  q_emergency_fund: "3to6",
  q_income_stability: "stable",
  q_employment_sector: "healthcare",
  q_loss_impact: "some",
  q_liquidity: "none",
  q_accounts: ["tfsa", "rrsp"],
  q_currency: "cad_usd",
  q_esg: 2,
  q_interests: ["canadian_companies", "dividends"],
  q_hype_reaction: "wait",
  q_amount: "50k_150k",
  q_existing_portfolio: false,
};

/** Options that say nothing about the investor: avoided by the fallback, unless nothing else is offered. */
const NEUTRAL = ["none", "dont_know", "unknown"];

const clamp = (value: number, question: Question) =>
  Math.min(question.max ?? Number.POSITIVE_INFINITY, Math.max(question.min ?? Number.NEGATIVE_INFINITY, value));

const offeredValues = (question: Question) => new Set((question.options ?? []).map((option) => option.value));

/** The offered options that say something about the investor, or all of them if none does. */
function telling(question: Question) {
  const options = question.options ?? [];
  const real = options.filter((option) => !NEUTRAL.includes(option.value));
  return real.length ? real : options;
}

/** A valid, middle-of-the-road answer, per kind of question. */
const FALLBACKS: Record<QuestionKind, (question: Question) => AnswerValue> = {
  boolean: () => false,
  single_choice: (question) => {
    const pool = telling(question);
    return pool[Math.floor((pool.length - 1) / 2)]?.value ?? "";
  },
  multi_choice: (question) => {
    const none = (question.options ?? []).find((option) => option.value === "none");
    const pick = none ?? telling(question)[0];
    return pick ? [pick.value] : [];
  },
  scale: (question) => Math.round(((question.min ?? 1) + (question.max ?? 5)) / 2),
  money: (question) => clamp(50000, question),
  percent: (question) => clamp(10, question),
  number: (question) => clamp(10, question),
  text: () => "Aucune préférence particulière.",
};

const isBound = (value: AnswerValue, question: Question) => typeof value === "number" && value === clamp(value, question);

/** Whether a value is an answer the question accepts: right type, offered option, within bounds. */
const ACCEPTS: Record<QuestionKind, (question: Question, value: AnswerValue) => boolean> = {
  boolean: (_, value) => typeof value === "boolean",
  single_choice: (question, value) => {
    const offered = offeredValues(question);
    return typeof value === "string" && (offered.size === 0 || offered.has(value));
  },
  multi_choice: (question, value) => {
    const offered = offeredValues(question);
    return Array.isArray(value) && value.length > 0 && (offered.size === 0 || value.every((item) => offered.has(item)));
  },
  text: (_, value) => typeof value === "string" && value.trim().length > 0,
  scale: (question, value) => isBound(value, question),
  number: (question, value) => isBound(value, question),
  money: (question, value) => isBound(value, question),
  percent: (question, value) => isBound(value, question),
};

/** A valid, middle-of-the-road answer for a question the sample profile does not know. */
export function fallbackAnswer(question: Question): AnswerValue {
  return FALLBACKS[question.kind](question);
}

function accepts(question: Question, value: AnswerValue): boolean {
  return ACCEPTS[question.kind](question, value);
}

/** The sample profile's answer to a base question, or a valid fallback. */
export function sampleAnswer(question: Question): AnswerValue {
  const value = SAMPLE_ANSWERS[question.id];
  if (value !== undefined && accepts(question, value)) return value;
  if (Array.isArray(value) && question.kind === "multi_choice") {
    const offered = offeredValues(question);
    const kept = value.filter((item) => offered.has(item));
    if (kept.length) return kept;
  }
  return fallbackAnswer(question);
}
