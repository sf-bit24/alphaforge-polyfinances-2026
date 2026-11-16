/**
 * Line shown under the explanation about the Bedrock Guardrails grounding check (`grounding_check` in the
 * engine), in the client's words (« Vérification des faits »): the count of statements checked and of those
 * that rest little on the cited facts. The scores and the threshold stay in the decision, for the team.
 */
import type { Grounding } from "@/lib/contract/portfolio";
import type { PortfolioStrings } from "@/lib/i18n/portfolio";

export function groundingLine(grounding: Grounding, v: PortfolioStrings["grounding"]): string | null {
  if (!grounding.action) return null;
  if (grounding.action === "ERROR") return v.failed;
  // An older response, or one without a count per statement: its overall outcome, in words (never the raw code).
  if (grounding.method !== "per_statement" || grounding.checked == null) return v.actions[grounding.action] ?? v.actions.other ?? null;
  const main = grounding.below ? v.below(grounding.below, grounding.checked) : v.passed(grounding.checked);
  return grounding.errors ? `${main} · ${v.errors(grounding.errors)}` : main;
}
