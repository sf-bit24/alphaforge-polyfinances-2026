/**
 * What the simulator keeps for one client: answers, journal, pending questions, turn counters,
 * portfolio and OKF documents. Facts and stage changes go through here, so that the journal
 * (CONTRACTS.md 5) records each of them.
 */
import type { AnswerValue, KnowledgeLevel, Locale, PortfolioView, Stage } from "@/lib/contract/schemas";
import type { StoredDoc } from "./documents";
import { MockError } from "./envelope";
import { knowledgeLevel, type FieldValues, type StoredFact } from "./profile";
import { nextBaseQuestion, type L } from "./questions";

export interface ClientRecord {
  id: string;
  locale: Locale;
  stage: Stage;
  createdAt: string;
  baseAnswers: Record<string, AnswerValue>;
  /** journal.md `data.entries[]`, append-only (CONTRACTS.md 5). */
  entries: JournalEntry[];
  values: FieldValues;
  pendingBase: string | null;
  /** A1's pending follow-ups: opaque id `a1_<turn>_<n>` (CONTRACTS.md 3.3) and the question it renders. */
  pendingA1: PendingFollowup[];
  /** Times each A1 question was asked, by question definition. */
  askedCount: Record<string, number>;
  /** Turn number shared by A1 and A2 in the session: an A1 turn after A2's first is `a1:2`. */
  turn: number;
  a1Turns: number;
  lastA2Turn: number;
  message: L | null;
  portfolio: PortfolioView | null;
  docs: Map<string, StoredDoc>;
}

export interface PendingFollowup {
  id: string;
  def: string;
}

export type JournalEntry =
  | { at: string; kind: "answer"; provenance: string; field: string; value: unknown; question_id?: string; previous?: unknown }
  | { at: string; kind: "message"; provenance: string; text: string; locale: Locale }
  | { at: string; kind: "stage"; provenance: string; value: Stage; previous: Stage | null; note: string };

/** A client at the first base question, with nothing known yet. */
export function newClientRecord(id: string, locale: Locale, createdAt: string): ClientRecord {
  return {
    id,
    locale,
    stage: "base_questions",
    createdAt,
    baseAnswers: {},
    entries: [],
    values: new Map(),
    pendingBase: nextBaseQuestion({})?.id ?? null,
    pendingA1: [],
    askedCount: {},
    turn: 0,
    a1Turns: 0,
    lastA2Turn: 0,
    message: null,
    portfolio: null,
    docs: new Map(),
  };
}

export function knowledgeLevelOf(record: ClientRecord): KnowledgeLevel | null {
  return knowledgeLevel(record.values).level;
}

export function requireStage(record: ClientRecord, allowed: Stage[], action: string): void {
  if (!allowed.includes(record.stage)) {
    throw new MockError(
      "conflict",
      {
        fr: `L'action ${action} n'est pas possible à l'étape ${record.stage}.`,
        en: `Action ${action} is not possible at stage ${record.stage}.`,
      },
      { stage: record.stage, allowed },
    );
  }
}

/** Store the latest value of a field and journal it, with the value it replaces. */
export function setFact(record: ClientRecord, { field, value, provenance, at }: StoredFact, questionId?: string): void {
  const previous = record.values.get(field);
  record.values.set(field, { field, value, provenance, at });
  record.entries.push({
    at,
    kind: "answer",
    provenance,
    field,
    value,
    ...(questionId ? { question_id: questionId } : {}),
    ...(previous ? { previous: previous.value } : {}),
  });
}

/** Who moves the client to another stage, when and why, as the journal keeps it. */
export interface StageChange {
  provenance: string;
  at: string;
  note: string;
}

export function setStage(record: ClientRecord, stage: Stage, { provenance, at, note }: StageChange): void {
  if (record.stage === stage) return;
  record.entries.push({ at, kind: "stage", provenance, value: stage, previous: record.stage, note });
  record.stage = stage;
}
