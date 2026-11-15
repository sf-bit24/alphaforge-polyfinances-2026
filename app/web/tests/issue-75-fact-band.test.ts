/**
 * #75 : a numeric answer given as a range keeps its range in ProfileView.facts (optional `band`), and the
 * profile panel shows the range ("Moins de 1 mois"), not the figure the code computes with (0).
 */
import { describe, expect, it } from "vitest";
import { Fact, ProfileView } from "@/lib/contract/schemas";
import { factValueText } from "@/lib/fact-value";

const AT = "2026-11-15T21:39:16Z";
const LT1 = { option: "lt1", label: "Moins de 1 mois", min: 0, max: 1 };

describe("Fact.band", () => {
  it("keeps the range of a numeric answer", () => {
    const fact = Fact.parse({ field: "risk_capacity.emergency_fund", value: 0, provenance: "base:q_emergency_fund", at: AT, band: LT1 });
    expect(fact.value).toBe(0);
    expect(fact.band).toEqual(LT1);
  });

  it("accepts open bounds (« 12 mois ou plus », « Je ne sais pas »)", () => {
    const open = Fact.parse({ field: "context.amount_cad", value: 10000, provenance: "base:q_amount", at: AT, band: { option: "unknown", label: "Je ne sais pas (10 000 $ retenus)", min: null, max: null } });
    expect(open.band?.label).toBe("Je ne sais pas (10 000 $ retenus)");
  });

  it("stays optional: a fact without a band is unchanged", () => {
    const fact = Fact.parse({ field: "horizon.horizon_band", value: "gt10", provenance: "base:q_horizon", at: AT });
    expect(fact.band).toBeUndefined();
  });

  it("drops a malformed band instead of failing the whole profile", () => {
    const view = ProfileView.parse({
      knowledge_level: null,
      effective_risk: null,
      dimensions: Object.fromEntries(
        ["objective", "horizon", "risk_tolerance", "risk_capacity", "constraints", "preferences"].map((key) => [key, { status: "missing", summary: null, fields: {} }]),
      ),
      facts: [{ field: "risk_capacity.emergency_fund", value: 0, provenance: "base:q_emergency_fund", at: AT, band: { label: "", min: "x" } }],
    });
    expect(view.facts).toHaveLength(1);
    expect(view.facts[0]?.value).toBe(0);
    expect(view.facts[0]?.band).toBeUndefined();
  });
});

describe("factValueText", () => {
  it("shows the chosen range, not the cautious figure", () => {
    expect(factValueText({ value: 0, band: LT1 })).toBe("Moins de 1 mois");
    expect(factValueText({ value: 0, band: { ...LT1, label: "Less than 1 month" } })).toBe("Less than 1 month");
  });

  it("falls back to the value when there is no band", () => {
    expect(factValueText({ value: 0 })).toBe("0");
    expect(factValueText({ value: "gt10" })).toBe("gt10");
    expect(factValueText({ value: ["tfsa", "rrsp"] })).toBe('["tfsa","rrsp"]');
    const long = factValueText({ value: Array.from({ length: 30 }, (_, index) => `option_${index}`) });
    expect(long).toHaveLength(58);
    expect(long.endsWith("…")).toBe(true);
  });
});
