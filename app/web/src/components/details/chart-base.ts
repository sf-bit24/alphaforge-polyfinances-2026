import type { Locale } from "@/lib/contract/schemas";

export const NAVY = "#0B2341";
export const RED = "#E41C23";
export const SLATE = "#8D9BAD";

/** Dates of the sample are UTC midnights. */
export function formatDay(at: number, locale: Locale, options: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" }): string {
  return new Intl.DateTimeFormat(locale === "fr" ? "fr-CA" : "en-CA", { timeZone: "UTC", ...options }).format(new Date(at));
}
