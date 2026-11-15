/**
 * Drafts of answers while the investor types, their validation before sending
 * (the runtime validates again), and a readable rendering for the conversation.
 */
import type { AnswerValue, Locale, Question } from "@/lib/contract/schemas";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { formatMoney, formatNumber } from "@/lib/i18n/locale";

export type Draft = string | string[] | boolean | number | null;

export function emptyDraft(question: Question): Draft {
  switch (question.kind) {
    case "multi_choice":
      return [];
    case "boolean":
    case "single_choice":
    case "scale":
      return null;
    default:
      return "";
  }
}

export function isDraftEmpty(question: Question, draft: Draft): boolean {
  if (draft === null) return true;
  if (Array.isArray(draft)) return draft.length === 0;
  if (typeof draft === "string") return draft.trim() === "";
  return false;
}

/** Question ids are opaque (q_*, a1_<turn>_<n>, fb_<turn>_<n>...): keep only safe characters for DOM ids and names. */
export function questionDomId(id: string): string {
  return id.replace(/[^A-Za-z0-9_-]/g, "_");
}

/** Parse "12 500,50", "12,500.50" or "12500.5" into a number. */
export function parseNumberInput(raw: string): number | null {
  const compact = raw.replace(/[\s  $%]/g, "");
  if (compact === "") return null;
  let normalized = compact;
  if (/^\d{1,3}(,\d{3})+(\.\d+)?$/.test(compact)) normalized = compact.replace(/,/g, "");
  else normalized = compact.replace(",", ".");
  if (!/^-?\d+(\.\d+)?$/.test(normalized)) return null;
  const value = Number(normalized);
  return Number.isFinite(value) ? value : null;
}

export type DraftResult = { ok: true; value: AnswerValue } | { ok: false; error: string };

type QuestionTexts = Dictionary["question"];

const MAX_TEXT_ANSWER_CHARS = 2000;

/** Why a number is out of the question's bounds, or null; a percent is within 0 to 100 unless the question says otherwise. */
function boundsError(question: Question, value: number, texts: QuestionTexts, locale: Locale): string | null {
  const min = question.min ?? (question.kind === "percent" ? 0 : null);
  const max = question.max ?? (question.kind === "percent" ? 100 : null);
  if (min !== null && max !== null && (value < min || value > max)) return texts.between(formatNumber(min, locale), formatNumber(max, locale));
  if (min !== null && value < min) return texts.atLeast(formatNumber(min, locale));
  if (max !== null && value > max) return texts.atMost(formatNumber(max, locale));
  return null;
}

function withinBounds(question: Question, value: number, texts: QuestionTexts, locale: Locale): DraftResult {
  const error = boundsError(question, value, texts, locale);
  return error ? { ok: false, error } : { ok: true, value };
}

function scaleValue(question: Question, draft: Draft, texts: QuestionTexts, locale: Locale): DraftResult {
  if (typeof draft !== "number") return { ok: false, error: texts.choose };
  if (!Number.isInteger(draft)) return { ok: false, error: texts.integer };
  return withinBounds(question, draft, texts, locale);
}

function numberOfDraft(draft: Draft): number | null {
  if (typeof draft === "number") return draft;
  return typeof draft === "string" ? parseNumberInput(draft) : null;
}

/** Number, money or percent. */
function amountValue(question: Question, draft: Draft, texts: QuestionTexts, locale: Locale): DraftResult {
  const value = numberOfDraft(draft);
  if (value === null) return { ok: false, error: texts.enterNumber };
  if (question.kind === "money" && value < 0) return { ok: false, error: texts.atLeast("0") };
  return withinBounds(question, value, texts, locale);
}

function textValue(draft: Draft, texts: QuestionTexts): DraftResult {
  const text = typeof draft === "string" ? draft.trim() : "";
  return text.length >= 1 && text.length <= MAX_TEXT_ANSWER_CHARS ? { ok: true, value: text } : { ok: false, error: texts.textLength };
}

export function draftToValue(question: Question, draft: Draft, t: Dictionary, locale: Locale): DraftResult {
  const texts = t.question;
  switch (question.kind) {
    case "single_choice":
      return typeof draft === "string" && draft ? { ok: true, value: draft } : { ok: false, error: texts.choose };
    case "multi_choice":
      return Array.isArray(draft) && draft.length > 0 ? { ok: true, value: draft } : { ok: false, error: texts.chooseAtLeastOne };
    case "boolean":
      return typeof draft === "boolean" ? { ok: true, value: draft } : { ok: false, error: texts.choose };
    case "scale":
      return scaleValue(question, draft, texts, locale);
    case "number":
    case "money":
    case "percent":
      return amountValue(question, draft, texts, locale);
    case "text":
      return textValue(draft, texts);
  }
}

function optionLabel(question: Question, option: string): string {
  return question.options?.find((candidate) => candidate.value === option)?.label ?? option;
}

/** A number answer with its unit: money in its currency, a percent with its sign. */
function amountText(question: Question, value: number, locale: Locale): string {
  if (question.kind === "money") return formatMoney(value, locale, question.unit || "CAD");
  if (question.kind === "percent") return `${formatNumber(value, locale)}${locale === "fr" ? "\u00a0%" : "%"}`;
  return `${formatNumber(value, locale)}${question.unit ? ` ${question.unit}` : ""}`;
}

/** A readable version of an answer, for the conversation thread. */
export function displayAnswer(question: Question, value: AnswerValue, t: Dictionary, locale: Locale): string {
  switch (question.kind) {
    case "single_choice":
      return optionLabel(question, String(value));
    case "multi_choice":
      return Array.isArray(value) ? value.map((option) => optionLabel(question, option)).join(", ") : String(value);
    case "boolean":
      return value === true ? t.question.yes : t.question.no;
    case "money":
    case "percent":
    case "number":
      return typeof value === "number" ? amountText(question, value, locale) : String(value);
    case "scale":
      return question.max !== null && question.max !== undefined ? `${String(value)} / ${question.max}` : String(value);
    case "text":
      return String(value);
  }
}
