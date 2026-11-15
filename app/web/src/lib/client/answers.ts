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

/** Parse "12 500,50", "12,500.50" or "12500.5" into a number. */
/** Question ids are opaque (q_*, a1_<turn>_<n>, fb_<turn>_<n>...): keep only safe characters for DOM ids and names. */
export function questionDomId(id: string): string {
  return id.replace(/[^A-Za-z0-9_-]/g, "_");
}

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

export function draftToValue(question: Question, draft: Draft, t: Dictionary, locale: Locale): DraftResult {
  const q = t.question;
  const min = question.min ?? (question.kind === "percent" ? 0 : null);
  const max = question.max ?? (question.kind === "percent" ? 100 : null);
  const bounds = (value: number): string | null => {
    if (min !== null && max !== null && (value < min || value > max)) return q.between(formatNumber(min, locale), formatNumber(max, locale));
    if (min !== null && value < min) return q.atLeast(formatNumber(min, locale));
    if (max !== null && value > max) return q.atMost(formatNumber(max, locale));
    return null;
  };
  switch (question.kind) {
    case "single_choice":
      return typeof draft === "string" && draft ? { ok: true, value: draft } : { ok: false, error: q.choose };
    case "multi_choice":
      return Array.isArray(draft) && draft.length > 0 ? { ok: true, value: draft } : { ok: false, error: q.chooseAtLeastOne };
    case "boolean":
      return typeof draft === "boolean" ? { ok: true, value: draft } : { ok: false, error: q.choose };
    case "scale": {
      if (typeof draft !== "number") return { ok: false, error: q.choose };
      if (!Number.isInteger(draft)) return { ok: false, error: q.integer };
      const error = bounds(draft);
      return error ? { ok: false, error } : { ok: true, value: draft };
    }
    case "number":
    case "money":
    case "percent": {
      const value = typeof draft === "number" ? draft : typeof draft === "string" ? parseNumberInput(draft) : null;
      if (value === null) return { ok: false, error: q.enterNumber };
      if (question.kind === "money" && value < 0) return { ok: false, error: q.atLeast("0") };
      const error = bounds(value);
      return error ? { ok: false, error } : { ok: true, value };
    }
    case "text": {
      const text = typeof draft === "string" ? draft.trim() : "";
      return text.length >= 1 && text.length <= 2000 ? { ok: true, value: text } : { ok: false, error: q.textLength };
    }
  }
}

/** A readable version of an answer, for the conversation thread. */
export function displayAnswer(question: Question, value: AnswerValue, t: Dictionary, locale: Locale): string {
  const label = (option: string) => question.options?.find((candidate) => candidate.value === option)?.label ?? option;
  switch (question.kind) {
    case "single_choice":
      return label(String(value));
    case "multi_choice":
      return Array.isArray(value) ? value.map(label).join(", ") : String(value);
    case "boolean":
      return value === true ? t.question.yes : t.question.no;
    case "money":
      return typeof value === "number" ? formatMoney(value, locale, question.unit || "CAD") : String(value);
    case "percent":
      return typeof value === "number" ? `${formatNumber(value, locale)}${locale === "fr" ? "\u00a0%" : "%"}` : String(value);
    case "scale":
      return question.max !== null && question.max !== undefined ? `${String(value)} / ${question.max}` : String(value);
    case "number":
      return typeof value === "number" ? `${formatNumber(value, locale)}${question.unit ? ` ${question.unit}` : ""}` : String(value);
    case "text":
      return String(value);
  }
}
