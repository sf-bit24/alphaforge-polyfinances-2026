/**
 * Suite of #75: the "Facts" list of the profile panel shows the label of each value ("Plutôt stables",
 * "CELI, REER", "Non"), not its code (very_stable, ["tfsa","rrsp"], false). `label` is optional in both
 * directions: an older runtime sends none, an older web strips it, and a malformed one is dropped.
 */
import { describe, expect, it } from "vitest";
import { Fact } from "@/lib/contract/schemas";
import { factValueText } from "@/lib/fact-value";

const AT = "2026-11-15T21:39:16Z";
const fact = (value: unknown, extra: Record<string, unknown> = {}) =>
  Fact.parse({ field: "constraints.account_types", value, provenance: "base:q_accounts", at: AT, ...extra });

describe("Fact.label", () => {
  it("keeps the label written by the runtime, and the value unchanged", () => {
    const parsed = fact(["tfsa", "rrsp"], { label: "CELI, REER" });
    expect(parsed.value).toEqual(["tfsa", "rrsp"]);
    expect(parsed.label).toBe("CELI, REER");
  });

  it("stays optional (older runtime) and drops a malformed label without failing the fact", () => {
    expect(fact(["tfsa"]).label).toBeUndefined();
    expect(fact(["tfsa"], { label: 12 }).label).toBeUndefined();
    expect(fact(["tfsa"], { label: "" }).label).toBeUndefined();
    expect(fact(["tfsa"], { label: ["CELI"] }).value).toEqual(["tfsa"]);
  });
});

describe("factValueText with labels", () => {
  it("shows the label of the chosen options, in the language the runtime used", () => {
    expect(factValueText(fact(["tfsa", "rrsp"], { label: "CELI, REER" }))).toBe("CELI, REER");
    expect(factValueText(fact(["tfsa", "rrsp"], { label: "TFSA, RRSP" }))).toBe("TFSA, RRSP");
    expect(factValueText({ value: "very_stable", label: "Plutôt stables" })).toBe("Plutôt stables");
    expect(factValueText({ value: "3to10", label: "De 3 à 10 ans" })).toBe("De 3 à 10 ans");
    expect(factValueText({ value: false, label: "Non" })).toBe("Non");
  });

  it("prefers the range of a numeric answer", () => {
    const band = { option: "lt1", label: "Moins de 1 mois", min: 0, max: 1 };
    expect(factValueText({ value: 0, band, label: "Moins de 1 mois" })).toBe("Moins de 1 mois");
    expect(factValueText({ value: 0, band })).toBe("Moins de 1 mois");
  });

  it("without a label, keeps a code as it is and never shows a list as JSON", () => {
    expect(factValueText({ value: "held" })).toBe("held");
    expect(factValueText({ value: ["tfsa"] })).toBe("tfsa");
    expect(factValueText({ value: ["tfsa", "rrsp"] })).toBe("tfsa, rrsp");
    expect(factValueText({ value: [] })).toBe("—");
    expect(factValueText({ value: false })).toBe("false");
    expect(factValueText({ value: null })).toBe("—");
    expect(factValueText(fact(["tfsa"], { label: 12 }))).toBe("tfsa");
  });
});
