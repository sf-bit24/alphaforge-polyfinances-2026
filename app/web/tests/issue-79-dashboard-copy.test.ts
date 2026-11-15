import { describe, expect, it } from "vitest";
import type { ClientState } from "@/lib/contract/schemas";
import { composeHints } from "@/components/dashboard/assistant-offer";
import { dictionaries } from "@/lib/i18n/dictionary";

const nbsp = (text: string) => text.replace(/[  ]/g, " ");

function completeness(score: number, threshold = 0.7, cap = 0.95): ClientState["completeness"] {
  return { score, displayed: Math.min(score, cap), threshold, cap, ready: score >= threshold, missing: [] };
}

describe("hint under Yan's input (#79)", () => {
  it("says only that no transaction is placed outside the follow-ups", () => {
    expect(composeHints(dictionaries.fr, "fr", false, completeness(0.66))).toEqual(["Aucune transaction n’est passée."]);
  });

  it("puts the stop condition in a sentence of its own, never read as a condition on transactions", () => {
    for (const locale of ["fr", "en"] as const) {
      const t = dictionaries[locale];
      const [transactions, stop, ...rest] = composeHints(t, locale, true, completeness(0.66));
      expect(rest).toEqual([]);
      expect(transactions).toBe(t.assistant.hint);
      expect(stop).not.toMatch(/^(Possible|Available)/);
      expect(nbsp(stop!)).toContain(locale === "fr" ? "70 %" : "70%");
      expect(nbsp(stop!)).toContain(locale === "fr" ? "66 %" : "66%");
    }
    expect(nbsp(composeHints(dictionaries.fr, "fr", true, completeness(0.66))[1]!)).toBe(
      "Vous pourrez arrêter les questions dès 70 % de complétude (actuellement 66 %).",
    );
    expect(composeHints(dictionaries.en, "en", true, completeness(0.66))[1]).toBe("You can stop the questions from 70% completeness (currently 66%).");
  });

  it("names the threshold of the contract, and says the questions can stop once it is reached", () => {
    const [, locked] = composeHints(dictionaries.en, "en", true, completeness(0.5, 0.6));
    expect(locked).toBe("You can stop the questions from 60% completeness (currently 50%).");
    const [, ready] = composeHints(dictionaries.fr, "fr", true, completeness(1));
    expect(nbsp(ready!)).toBe("Votre profil atteint le seuil de 70 % : vous pouvez arrêter les questions.");
  });
});
