/**
 * Display of the engine's `allocation` (where the money goes): the share and the dollar amount of a row,
 * and the name of an asset class or a currency in the interface language.
 *
 * Pure display: every weight and every amount comes from the engine. Nothing here sums, splits or
 * multiplies a number. In French the strings are the engine's own (`formatWeight`, `formatCad`), so they
 * read exactly like the fact chips; in English the locale formatters write them the English way.
 */
import type { Allocation, AllocationBucket } from "@/lib/contract/portfolio";
import type { Locale } from "@/lib/contract/schemas";
import { formatMoney, formatPercent } from "@/lib/i18n/locale";
import { formatCad, formatWeight } from "./format";

/** A share of the portfolio given by the engine: « 48,0 % » / "48.0%". */
export function allocationShare(weight: number, locale: Locale): string {
  return locale === "fr" ? formatWeight(weight) : formatPercent(weight, locale, 1);
}

/** An amount in dollars given by the engine: « 31 300 $ » / "$31,300"; null when the engine gave none. */
export function allocationAmount(amount: number | null | undefined, locale: Locale): string | null {
  if (amount === null || amount === undefined) return null;
  return locale === "fr" ? formatCad(amount) : formatMoney(amount, locale, "CAD");
}

/** The name of a row: the interface's own name for a known key, else the engine's French label. */
export function bucketLabel(bucket: Pick<AllocationBucket, "key" | "label_fr">, names: Readonly<Record<string, string>>): string {
  const own = Object.hasOwn(names, bucket.key) ? names[bucket.key] : undefined;
  return own ?? (bucket.label_fr || bucket.key);
}

/** The engine's amount of each position, by asset id (a lookup, not a computation). */
export function positionAmounts(allocation: Allocation | null | undefined): ReadonlyMap<string, number | null> {
  return new Map((allocation?.positions ?? []).map((position) => [position.asset_id, position.amount_cad ?? null]));
}
