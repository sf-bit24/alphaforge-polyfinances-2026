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

/** Where A1's follow-ups stand when Yan's assistant renders. */
export interface FollowupsStatus {
  /** Stage `followups`. */
  followups: boolean;
  /** A1's reply is being written. */
  replying: boolean;
  /** A1 has spoken already: in the journey since #72, or here. */
  started: boolean;
  /** A1's questions waiting for an answer. */
  questionCount: number;
}

/**
 * Whether « Ask me your follow-up questions » is offered. In the intro, while follow-ups are
 * waiting: not asked yet, being written, or asked and not answered (Yan asks them in the
 * journey now). Under the thread, only before A1 has asked anything: its questions show in
 * the thread afterwards.
 */
export function offersFollowups(where: "intro" | "thread", { followups, replying, started, questionCount }: FollowupsStatus): boolean {
  if (!followups) return false;
  if (!started) return where === "intro" || !replying;
  return where === "intro" && (replying || questionCount > 0);
}

/** The intro's heading and lead: during the follow-ups, the lead offers Yan's questions only when their chip is there. */
export function introCopy(t: Dictionary, followups: boolean, followupsOffered: boolean): { heading: string; lead: string } {
  if (!followups) return { heading: t.assistant.introComplete, lead: t.assistant.leadComplete };
  return { heading: t.assistant.introFollowups, lead: followupsOffered ? t.assistant.leadFollowups : t.assistant.leadFollowupsWrite };
}

/** The follow-ups' status from the thread's view, A1's conversation so far and its open questions. */
export function followupsStatus(view: { followups: boolean; replying: boolean }, conversationLength: number, questionCount: number): FollowupsStatus {
  return { followups: view.followups, replying: view.replying, started: conversationLength > 0, questionCount };
}
