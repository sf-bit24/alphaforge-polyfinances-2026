/**
 * Issue #78, after the review of #76's follow-up: a fact of a whole duration (units « nombre de mois » and
 * « nombre d'années », WHOLE_UNITS of finance/debate/explain.py) shows its word on a chip, without a decimal,
 * while `formatEngineValue` stays the exact port of `fmt` (« 12 »), so the number rule is unchanged.
 */
import { describe, expect, it } from "vitest";
import { formatEngineValue, formatFact } from "@/lib/portfolio/format";

describe("whole durations on a fact chip", () => {
  it("write the word of the unit, without a decimal", () => {
    expect(formatFact({ value: 12, unit: "nombre de mois" })).toBe("12 mois");
    expect(formatFact({ value: 1, unit: "nombre de mois" })).toBe("1 mois");
    expect(formatFact({ value: 5, unit: "nombre d'années" })).toBe("5 ans");
    expect(formatFact({ value: 1, unit: "nombre d'années" })).toBe("1 an");
    expect(formatFact({ value: 30, unit: "nombre d'années" })).toBe("30 ans");
  });

  it("keep one decimal for a fractional value, as the other durations", () => {
    expect(formatFact({ value: 5.5, unit: "nombre d'années" })).toBe("5,5 ans");
  });

  it("leave the engine's format and the other units as they were", () => {
    expect(formatEngineValue(12, "nombre de mois")).toBe("12");
    expect(formatFact({ value: 12, unit: "mois" })).toBe("12,0 mois");
    expect(formatFact({ value: 5, unit: "ans" })).toBe("5,0 ans");
    expect(formatFact({ value: 7.5, unit: "années" })).toBe("7,5 années");
    expect(formatFact({ value: 0.123, unit: "%" })).toBe("12,3 %");
    expect(formatFact({ value: 31300, unit: "CAD" })).toBe("31 300 $");
    expect(formatFact({ value: 12, unit: "titres" })).toBe("12");
    expect(formatFact({ value: "texte", unit: "nombre de mois" })).toBe("texte");
  });
});
