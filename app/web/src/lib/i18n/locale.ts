import type { Locale } from "@/lib/contract/schemas";

export const LOCALE_COOKIE = "af_locale";
export const DEFAULT_LOCALE: Locale = "fr";

export function parseLocale(value: string | undefined | null): Locale {
  return value === "en" ? "en" : DEFAULT_LOCALE;
}

const intlLocale = (locale: Locale) => (locale === "fr" ? "fr-CA" : "en-CA");

export function formatPercent(share: number, locale: Locale, digits = 0): string {
  return new Intl.NumberFormat(intlLocale(locale), {
    style: "percent",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(share);
}

/** A change with its sign, minus as U+2212 like the drafts: "+1,2 %", "−9,8 %". */
export function formatSignedPercent(share: number, locale: Locale, digits = 1): string {
  return `${share >= 0 ? "+" : "−"}${formatPercent(Math.abs(share), locale, digits)}`;
}

/** Money with a U+2212 minus for losses: "−39 200 $". */
export function formatSignedMoney(value: number, locale: Locale, currency = "CAD", digits = 0): string {
  return `${value < 0 ? "−" : ""}${formatMoney(Math.abs(value), locale, currency, digits)}`;
}

export function formatMoney(value: number, locale: Locale, currency = "CAD", digits = 0): string {
  try {
    return new Intl.NumberFormat(intlLocale(locale), {
      style: "currency",
      currency,
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(value);
  } catch {
    return `${formatNumber(value, locale, digits)} ${currency}`;
  }
}

export function formatNumber(value: number, locale: Locale, maxDigits = 2): string {
  return new Intl.NumberFormat(intlLocale(locale), { maximumFractionDigits: maxDigits }).format(value);
}

export function formatDateTime(iso: string, locale: Locale): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(intlLocale(locale), { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function formatDate(iso: string, locale: Locale): string {
  const date = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T12:00:00Z`) : new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(intlLocale(locale), { dateStyle: "medium" }).format(date);
}

export function formatTime(iso: string, locale: Locale): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  // A clock time, 21:34:58 (fr-CA would otherwise write « 21 h 34 min 58 s », which reads like a duration).
  const parts = new Intl.DateTimeFormat(intlLocale(locale), { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? "00";
  return `${part("hour")}:${part("minute")}:${part("second")}`;
}

export function formatDuration(ms: number, locale: Locale): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${formatNumber(seconds, locale, 1)} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes} min ${rest} s`;
}

/** Typographic apostrophes in text written by the runtime or the agents: l'argent → l’argent. */
export function curly(text: string): string {
  return text.replace(/(?<=\p{L})'(?=\p{L})/gu, "’");
}
