import type { Fact } from "@/lib/contract/schemas";

const MAX_VALUE_CHARS = 60;

/**
 * What the profile panel shows for a fact. A numeric answer given as a range carries `band`: its label
 * ("Moins de 1 mois") is what the investor chose, while `value` (0) is only the figure the code computes with.
 */
export function factValueText(fact: Pick<Fact, "value" | "band">): string {
  if (fact.band?.label) return fact.band.label;
  const { value } = fact;
  if (typeof value === "string") return value;
  const text = JSON.stringify(value);
  return text.length > MAX_VALUE_CHARS ? `${text.slice(0, MAX_VALUE_CHARS - 3)}…` : text;
}
