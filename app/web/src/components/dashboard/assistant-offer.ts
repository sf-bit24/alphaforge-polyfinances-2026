/**
 * What Yan's composer says and offers around A1's follow-ups, as plain functions so they
 * are tested without a DOM (tests/issue-79-dashboard-copy.test.ts).
 */
import type { ClientState, Locale } from "@/lib/contract/schemas";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { formatPercent } from "@/lib/i18n/locale";

/**
 * The lines under the input: no transaction is placed, then, during the follow-ups, whether
 * they can be stopped yet. Each is a sentence of its own, shown on its own line, so the
 * threshold never reads as a condition on transactions.
 */
export function composeHints(t: Dictionary, locale: Locale, followups: boolean, completeness: ClientState["completeness"]): string[] {
  if (!followups) return [t.assistant.hint];
  const threshold = formatPercent(completeness.threshold, locale);
  // `displayed`, the value of the profile pill and of the completeness tile.
  const stop = completeness.ready ? t.followups.stopHintReady(threshold) : t.followups.stopHintLocked(threshold, formatPercent(completeness.displayed, locale));
  return [t.assistant.hint, stop];
}
