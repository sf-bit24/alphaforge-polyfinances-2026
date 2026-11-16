/**
 * What the session store remembers of past requests: the trace run of each one and the A1
 * conversation, with the pure helpers that build them. Kept in localStorage by session-storage.
 */
import type { ClientState, Question, Stage, TraceStep } from "@/lib/contract/schemas";

export interface TraceRun {
  id: string;
  action: string;
  startedAt: string;
  durationMs: number | null;
  status: "running" | "ok" | "error";
  streamed: boolean;
  steps: TraceStep[];
  error: { code: string; message: string } | null;
}

export interface AnsweredItem {
  question_id: string;
  prompt: string;
  display: string;
}

export type ConversationEntry =
  | { id: string; role: "agent"; at: string; message: string | null; questions: Question[]; stage: Stage; runId?: string }
  | { id: string; role: "user"; at: string; answers: AnsweredItem[]; message: string | null; stop: boolean };

export const MAX_RUNS = 40;

export function uid(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function newRun(action: string, { streamed }: { streamed: boolean }): TraceRun {
  return { id: uid(), action, startedAt: new Date().toISOString(), durationMs: null, status: "running", streamed, steps: [], error: null };
}

/** Newest first, at most MAX_RUNS. */
export function withNewRun(runs: TraceRun[], run: TraceRun): TraceRun[] {
  return [run, ...runs].slice(0, MAX_RUNS);
}

/** A1's message and questions in a ClientState, as a conversation entry. */
export function agentEntryOf(state: ClientState): Extract<ConversationEntry, { role: "agent" }> {
  return { id: uid(), role: "agent", at: new Date().toISOString(), message: state.message, questions: state.questions, stage: state.stage };
}

/** `message` is null after a deterministic transition: A1 then has nothing to show. */
export function agentSpoke(state: ClientState): boolean {
  return Boolean(state.message) || state.questions.length > 0;
}

/** The runtime is past what the page showed: another stage, or questions the page has never seen. */
export function movedOn(shown: ClientState | null, fresh: ClientState): boolean {
  if (!shown) return false;
  if (shown.stage !== fresh.stage) return true;
  const ids = new Set(shown.questions.map((question) => question.id));
  return fresh.questions.some((question) => !ids.has(question.id));
}
