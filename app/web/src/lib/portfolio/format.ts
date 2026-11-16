/**
 * Display formats of the finance engine's numbers, ported from `fmt` in
 * app/agents/src/alphaforge/finance/debate/facts.py, so a fact chip shows exactly the string that the
 * engine wrote (and checked) in its explanation: « 12,3 % », « 31 300 $ », « 4,2 mois ».
 *
 * Pure display: these helpers only format a value the backend gave. They never derive a weight, a risk
 * or any other financial quantity.
 */
import type { DecisionFact } from "@/lib/contract/portfolio";

/**
 * Python's `format(value, ".{digits}f")`: the exact decimal value of the double, ties to even.
 * `Number.prototype.toFixed` also works on the exact value but breaks ties upward: 2.25 gives "2.3"
 * where Python writes "2.2" (a sector cap of 0.0225 is « 2,2 % » in the engine's text).
 */
export function pythonFixed(value: number, digits: number): string {
  if (!Number.isFinite(value)) return String(value);
  const negative = value < 0 || Object.is(value, -0);
  const abs = Math.abs(value);
  let out = abs.toFixed(digits);
  // An exact tie at `digits` is a binary fraction with digits + 1 decimals ending in 5, so 25 more
  // decimals of the exact expansion are enough to tell it from a value merely close to the tie.
  const exact = abs.toFixed(Math.min(digits + 25, 100));
  const dot = exact.indexOf(".");
  const dropped = exact.slice(dot + 1 + digits);
  if (dropped.startsWith("5") && /^0*$/.test(dropped.slice(1))) {
    const kept = exact.slice(0, digits === 0 ? dot : dot + 1 + digits);
    const last = Number(kept.at(-1));
    if (last % 2 === 0) out = kept; // round half to even: keep the even digit (toFixed went up)
  }
  return negative ? `-${out}` : out;
}

function groupThousands(integer: string): string {
  const sign = integer.startsWith("-") ? "-" : "";
  const digits = sign ? integer.slice(1) : integer;
  return sign + digits.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

/**
 * Exact port of `facts.fmt(value, unit)`: « n.d. » for no value, text as is, `%` for a fraction
 * (×100, one decimal), `CAD` with a space thousands separator and no decimal, durations with one
 * decimal, other decimals with three. JSON cannot tell 1.0 from 1: an integral number is written as
 * an integer (Python would write « 1,000 » for a float 1.0 of unit « ratio »).
 */
export function formatEngineValue(value: number | string | null | undefined, unit: string): string {
  if (value === null || value === undefined) return "n.d.";
  if (typeof value === "string") return value;
  if (unit === "%") return `${pythonFixed(value * 100, 1).replace(".", ",")} %`;
  if (unit === "CAD") return `${groupThousands(pythonFixed(value, 0))} $`;
  if (unit === "mois" || unit === "années" || unit === "ans") return `${pythonFixed(value, 1).replace(".", ",")} ${unit}`;
  if (!Number.isInteger(value)) return pythonFixed(value, 3).replace(".", ",");
  return String(value);
}

/**
 * Units of the Judge and the optimizer that hold a fraction of the portfolio without saying `%`
 * (`fmt` would write « 0,815 »): shown as a percentage, the same convention as `%`.
 */
export const FRACTION_UNITS: ReadonlySet<string> = new Set(["%", "part du portefeuille", "poids", "perte (fraction)", "volatilité annualisée"]);

/**
 * Units of a whole duration (`WHOLE_UNITS` in finance/debate/explain.py): `fmt` writes the number alone (« 12 »)
 * and the engine's sentence adds the word (« 12 mois »). A chip has no sentence around it, so it adds the word
 * itself: « 12 mois », « 5 ans », « 1 an ». The word follows the French rule (below 2, singular).
 */
const WHOLE_DURATION_WORDS: Readonly<Record<string, (count: number) => string>> = {
  "nombre de mois": () => "mois",
  "nombre d'années": (count) => (Math.abs(count) >= 2 ? "ans" : "an"),
};

/** A fact as displayed on a chip or in a table cell. */
export function formatFact(fact: Pick<DecisionFact, "value" | "unit">): string {
  if (typeof fact.value === "number" && FRACTION_UNITS.has(fact.unit)) return formatEngineValue(fact.value, "%");
  const word = Object.hasOwn(WHOLE_DURATION_WORDS, fact.unit) ? WHOLE_DURATION_WORDS[fact.unit] : undefined;
  if (typeof fact.value === "number" && word) {
    // Whole by construction; a fractional value would keep one decimal, as « mois » and « ans ».
    const digits = Number.isInteger(fact.value) ? 0 : 1;
    return `${pythonFixed(fact.value, digits).replace(".", ",")} ${word(fact.value)}`;
  }
  return formatEngineValue(fact.value, fact.unit);
}

/** A weight of `positions[]` (a fraction from 0 to 1): « 48,0 % ». */
export function formatWeight(weight: number): string {
  return formatEngineValue(weight, "%");
}

/** A limit of a constraint check, in the unit of the fact that measures it (a fraction when unknown). */
export function formatLimit(limit: number | null | undefined, unit: string | undefined): string {
  if (limit === null || limit === undefined) return "—";
  return formatFact({ value: limit, unit: unit ?? "%" });
}

/** An amount the interface sends (a demo request), in the engine's convention: « 50 000 $ ». */
export function formatCad(amount: number): string {
  return formatEngineValue(amount, "CAD");
}

/**
 * A number of the same text, in the engine's normalized form (`explain._norm`): spaces dropped,
 * comma as the decimal point, no sign. Used by the tests that compare this port with the engine.
 */
export function normalizeNumber(text: string): string {
  return text.replace(/[\u0020\u00a0\u202f]/g, "").replaceAll(",", ".").replace(/^-/, "");
}
