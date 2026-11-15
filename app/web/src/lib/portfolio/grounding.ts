/**
 * Line shown under the explanation about the Bedrock Guardrails grounding check (`grounding_check` in the
 * engine). It formats what the engine reports; it never recomputes a score or a count.
 */
import type { Grounding } from "@/lib/contract/portfolio";
import type { Locale } from "@/lib/contract/schemas";
import { formatNumber } from "@/lib/i18n/locale";
import type { PortfolioStrings } from "@/lib/i18n/portfolio";

export function groundingLine(grounding: Grounding, v: PortfolioStrings["grounding"], locale: Locale): string | null {
  if (!grounding.action) return null;
  if (grounding.method !== "per_statement" || grounding.checked == null) return v.action(grounding.action);
  if (grounding.action === "ERROR") return v.failed;
  const threshold = grounding.threshold != null ? formatNumber(grounding.threshold, locale) : "—";
  const main =
    grounding.below
      ? v.below(grounding.below, grounding.checked, threshold)
      : v.passed(grounding.checked, grounding.min_score != null ? formatNumber(grounding.min_score, locale) : "—", threshold);
  return grounding.errors ? `${main} · ${v.errors(grounding.errors)}` : main;
}
