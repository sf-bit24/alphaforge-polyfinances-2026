import type { Fact } from "@/lib/contract/schemas";

const MAX_VALUE_CHARS = 60;

function plain(item: unknown): string {
  if (item === null || item === undefined) return "—";
  if (typeof item === "object") return JSON.stringify(item);
  return String(item);
}

/**
 * What the profile panel shows for a fact, in this order:
 * - `band.label`, the range chosen for a numeric answer ("Moins de 1 mois"), while `value` (0) is only the
 *   figure the code computes with;
 * - `label`, the value as the investor reads it, written by the runtime in the language of the view
 *   ("Plutôt stables", "CELI, REER", "Oui");
 * - otherwise the value itself, from an older runtime or the mock: a code stays as it is and a list of codes is
 *   joined with commas ("tfsa, rrsp"), never shown as JSON.
 */
export function factValueText(fact: Pick<Fact, "value" | "band" | "label">): string {
  if (fact.band?.label) return fact.band.label;
  if (fact.label) return fact.label;
  const { value } = fact;
  if (typeof value === "string") return value;
  const text = Array.isArray(value) ? value.map(plain).join(", ") || "—" : plain(value);
  return text.length > MAX_VALUE_CHARS ? `${text.slice(0, MAX_VALUE_CHARS - 3)}…` : text;
}
