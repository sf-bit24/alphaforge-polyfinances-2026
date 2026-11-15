/**
 * `followup.reply` of the simulator (CONTRACTS.md 3.2): the fake A1 reads the investor's answers
 * and free text, stores the facts, lets the code recompute completeness, then picks its next
 * follow-ups among the missing fields and writes its reply.
 */
import type { AgentRequest } from "@/lib/contract/requests";
import type { AnswerValue, Completeness, KnowledgeLevel, Locale } from "@/lib/contract/schemas";
import {
  composeA1Message,
  extractFacts,
  MODEL_ID,
  screenMessage,
  type A1MessageInput,
  type ExtractedFact,
  type Screening,
} from "./agents";
import { A1_QUESTIONS } from "./a1-questions";
import { writeClientDocs } from "./client-docs";
import { knowledgeLevelOf, requireStage, setFact, setStage, type ClientRecord, type PendingFollowup } from "./client-record";
import { clientState } from "./client-state";
import { MockError, type Envelope } from "./envelope";
import { completeness, fieldDef, formatPercent, isFieldKnown, type FieldValues } from "./profile";
import { a1Question, renderQuestion, tr, validateAnswer, type L, type QuestionDef } from "./questions";
import type { Trace, TraceStepInput } from "./trace";

type FollowupReplyRequest = Extract<AgentRequest, { action: "followup.reply" }>;

const MAX_A1_QUESTIONS = 3;
/** A1 does not insist: a follow-up left unanswered twice is not asked again. */
const MAX_TIMES_ASKED = 2;
const REPLY_DELAY_MS = 1_600;
const NO_TRANSACTION_POLICY = "no-real-transaction";

interface AcceptedAnswer {
  def: QuestionDef;
  value: AnswerValue;
  questionId: string;
}

/** What the investor sent in one turn, validated and screened before anything is written. */
interface TurnInput {
  accepted: AcceptedAnswer[];
  text: string;
  screening: Screening | null;
  extracted: ExtractedFact[];
  stop: boolean;
}

/** One A1 turn: its number, shared with A2, and what was true when it started. */
interface Turn {
  number: number;
  provenance: string;
  isFirst: boolean;
  wasComplete: boolean;
  locale: Locale;
  level: KnowledgeLevel | null;
}

type TurnOutcome = A1MessageInput["outcome"];

/** What A1 decides at the end of a turn: its next follow-ups, or why it asks none. */
interface Decision {
  questions: QuestionDef[];
  pending: PendingFollowup[];
  outcome: TurnOutcome;
}

interface WrittenFact {
  field: string;
  value: unknown;
  provenance: string;
}

/** Every answer must match a pending follow-up and be valid for its kind. */
function acceptAnswers(record: ClientRecord, answers: NonNullable<FollowupReplyRequest["answers"]>): AcceptedAnswer[] {
  const level = knowledgeLevelOf(record);
  return answers.map((answer) => {
    const pending = record.pendingA1.find((item) => item.id === answer.question_id);
    if (!pending) {
      throw new MockError(
        "invalid_answer",
        {
          fr: `La question ${answer.question_id} n'est pas une relance en attente.`,
          en: `Question ${answer.question_id} is not a pending follow-up.`,
        },
        { question_id: answer.question_id, pending: record.pendingA1.map((item) => item.id) },
      );
    }
    const def = a1Question(pending.def);
    if (!def) throw new MockError("invalid_answer", { fr: "Question inconnue.", en: "Unknown question." }, { question_id: answer.question_id });
    const checked = validateAnswer(renderQuestion(def, record.locale, level), answer.value);
    if (!checked.ok) throw new MockError("invalid_answer", checked.reason, checked.details);
    return { def, value: checked.value, questionId: answer.question_id };
  });
}

/** A request to trade is a denied topic: the refusal is traced, and the message is never journaled. */
function refuseTransactionRequest(text: string, locale: Locale, trace: Trace): never {
  const fr = locale === "fr";
  trace.add({
    kind: "guardrail",
    actor: "guardrail",
    title: fr ? "Demande de transaction bloquée" : "Transaction request blocked",
    detail: fr ? "Sujet interdit par le cadre responsable : aucune transaction réelle" : "Denied topic under the responsible framework: no real transaction",
    inputs: { message_chars: text.length },
    outputs: { action: "BLOCKED", policy: NO_TRANSACTION_POLICY },
    durationMs: 150,
  });
  throw new MockError(
    "guardrail_blocked",
    {
      fr: "AlphaForge AI est une simulation : il ne passe aucun ordre et n'exécute aucune transaction. Reformulez votre message sur votre profil.",
      en: "AlphaForge AI is a simulation: it places no order and executes no transaction. Please rephrase your message about your profile.",
    },
    { policy: NO_TRANSACTION_POLICY },
  );
}

/** `stop` is accepted only from the threshold, counting this turn's answers. */
function requireStopAllowed(record: ClientRecord, input: TurnInput, at: string): void {
  const locale = record.locale;
  const preview: FieldValues = new Map(record.values);
  for (const { def, value } of input.accepted) preview.set(def.field, { field: def.field, value, provenance: "preview", at });
  for (const fact of input.extracted) preview.set(fact.field, { field: fact.field, value: fact.value, provenance: "preview", at });
  const projected = completeness(preview, locale);
  if (projected.ready) return;
  throw new MockError(
    "conflict",
    {
      fr: `Vous pourrez vous arrêter dès ${formatPercent(projected.threshold, locale)} de complétude (actuellement ${formatPercent(projected.score, locale)}).`,
      en: `You can stop from ${formatPercent(projected.threshold, locale)} completeness (currently ${formatPercent(projected.score, locale)}).`,
    },
    { score: projected.score, threshold: projected.threshold },
  );
}

/** Validate every answer and screen the message before anything is written. */
function readTurn(record: ClientRecord, request: FollowupReplyRequest, trace: Trace): TurnInput {
  const accepted = acceptAnswers(record, request.answers ?? []);
  const text = request.message?.trim() ?? "";
  const screening = text ? screenMessage(text, record.locale) : null;
  if (screening?.transactionRequest) refuseTransactionRequest(text, record.locale, trace);
  const currentValues = new Map([...record.values].map(([key, fact]) => [key, fact.value]));
  const extracted = screening ? extractFacts(screening.text, currentValues) : [];
  const input: TurnInput = { accepted, text, screening, extracted, stop: request.stop ?? false };
  if (input.stop) requireStopAllowed(record, input, trace.now);
  return input;
}

function openTurn(record: ClientRecord): Turn {
  record.turn += 1;
  const turn: Turn = {
    number: record.turn,
    provenance: `a1:${record.turn}`,
    isFirst: record.a1Turns === 0,
    wasComplete: record.stage === "complete",
    locale: record.locale,
    level: knowledgeLevelOf(record),
  };
  record.a1Turns += 1;
  return turn;
}

function messageGuardrailDetail(screening: Screening): L {
  if (screening.adviceRequest) {
    return {
      fr: "A1 répond dans le cadre responsable : information générale, aucune recommandation d'achat ou de vente",
      en: "A1 answers within the responsible framework: general information, no buy or sell recommendation",
    };
  }
  if (screening.masked > 0) {
    return { fr: `${screening.masked} renseignement(s) personnel(s) masqué(s)`, en: `${screening.masked} personal detail(s) masked` };
  }
  return { fr: "Aucun sujet interdit, aucun renseignement personnel", en: "No denied topic, no personal detail" };
}

function messageGuardrailStep(screening: Screening, text: string, locale: Locale): TraceStepInput {
  const title: L = screening.adviceRequest
    ? { fr: "Demande de conseil personnalisé détectée", en: "Personalized advice request detected" }
    : { fr: "Message vérifié par le garde-fou", en: "Message checked by the guardrail" };
  return {
    kind: "guardrail",
    actor: "guardrail",
    title: tr(title, locale),
    detail: tr(messageGuardrailDetail(screening), locale),
    inputs: { message_chars: text.length },
    outputs: { masked: screening.masked, advice_request: screening.adviceRequest, action: screening.adviceRequest ? "INTERVENED" : "NONE" },
    durationMs: 160,
  };
}

function readingStep(turn: Turn, { accepted, text, stop }: TurnInput): TraceStepInput {
  const fr = turn.locale === "fr";
  return {
    kind: "agent",
    actor: "A1",
    title: fr ? "A1 lit le profil et la réponse de l'investisseur" : "A1 reads the profile and the investor's reply",
    detail: fr
      ? `${accepted.length} réponse(s) structurée(s)${text ? ", un message libre" : ""}${stop ? ", demande d'arrêt" : ""}`
      : `${accepted.length} structured answer(s)${text ? ", one free-text message" : ""}${stop ? ", stop request" : ""}`,
    inputs: { answers: accepted.map(({ questionId }) => questionId), message: Boolean(text), stop, turn: turn.number },
    durationMs: 210,
  };
}

function offTopicStep(locale: Locale): TraceStepInput {
  const fr = locale === "fr";
  return {
    kind: "agent",
    actor: "A1",
    title: fr ? "Message hors sujet : A1 recentre l'échange" : "Off-topic message: A1 refocuses",
    detail: fr ? "A1 ne s'écarte pas du profil d'investisseur" : "A1 does not stray from the investor profile",
    durationMs: 40,
  };
}

/** What A1 does with the turn before it writes anything: guardrail on the message, reading, refocusing. */
function readingSteps(turn: Turn, input: TurnInput): TraceStepInput[] {
  const steps: TraceStepInput[] = [];
  if (input.screening) steps.push(messageGuardrailStep(input.screening, input.text, turn.locale));
  steps.push(readingStep(turn, input));
  if (input.screening?.offTopic) steps.push(offTopicStep(turn.locale));
  return steps;
}

/** Journal the message, then store the answers and the facts read in the free text, under the turn's provenance. */
function writeTurn(record: ClientRecord, turn: Turn, input: TurnInput, at: string): WrittenFact[] {
  const { provenance } = turn;
  if (input.screening) {
    // Written only once the input guardrail has passed (a blocked message throws above).
    record.entries.push({ at, kind: "message", provenance, text: input.screening.text, locale: turn.locale });
  }
  const written: WrittenFact[] = [];
  for (const { def, value, questionId } of input.accepted) {
    setFact(record, { field: def.field, value, provenance, at }, questionId);
    written.push({ field: def.field, value, provenance });
  }
  for (const fact of input.extracted) {
    setFact(record, { field: fact.field, value: fact.value, provenance, at });
    written.push({ field: fact.field, value: fact.value, provenance });
  }
  return written;
}

function updateKbStep(turn: Turn, written: WrittenFact[]): TraceStepInput {
  return {
    kind: "tool",
    actor: "A1",
    title: turn.locale === "fr" ? `Outil update-KB : ${written.length} fait(s) enregistré(s)` : `Tool update-KB: ${written.length} fact(s) saved`,
    detail: written.map((fact) => fact.field).join(", "),
    inputs: { provenance: turn.provenance },
    outputs: { facts: written },
    durationMs: 120,
  };
}

function completenessStep(before: Completeness, after: Completeness, locale: Locale): TraceStepInput {
  const fr = locale === "fr";
  const percent = (share: number) => formatPercent(share, locale);
  return {
    kind: "deterministic",
    actor: "completeness",
    title: fr ? "Complétude recalculée par le code" : "Completeness recomputed by code",
    detail: `${percent(before.score)} → ${percent(after.score)} (${fr ? "seuil" : "threshold"} ${percent(after.threshold)}, ${fr ? "plafond" : "cap"} ${percent(after.cap)})`,
    outputs: { score: after.score, displayed: after.displayed, ready: after.ready, missing: after.missing.map((item) => item.field) },
    durationMs: 2,
  };
}

/** The follow-ups that were pending during this turn have been asked once more. */
function countPendingAsAsked(record: ClientRecord): void {
  for (const { def } of record.pendingA1) record.askedCount[def] = (record.askedCount[def] ?? 0) + 1;
}

/** A1 picks its next follow-ups among the missing fields, heaviest first. */
function nextFollowups(record: ClientRecord): QuestionDef[] {
  const weight = (def: QuestionDef) => fieldDef(def.field)?.weight ?? 0;
  return A1_QUESTIONS.filter((def) => !isFieldKnown(record.values, def.field) && (record.askedCount[def.id] ?? 0) < MAX_TIMES_ASKED)
    .sort((left, right) => weight(right) - weight(left))
    .slice(0, MAX_A1_QUESTIONS);
}

function turnOutcome(turn: Turn, input: TurnInput, questions: QuestionDef[], after: Completeness): TurnOutcome {
  if (input.stop) return "stopped";
  // From `complete`, a reply reopens the follow-ups (CONTRACTS.md 3.1); A1 closes them again later.
  if (!turn.wasComplete && questions.length === 0 && after.ready) return "complete";
  return questions.length === 0 ? "idle" : "ask";
}

function decideFollowups(record: ClientRecord, turn: Turn, input: TurnInput, after: Completeness): Decision {
  const questions = input.stop ? [] : nextFollowups(record);
  const pending = questions.map((def, index) => ({ id: `a1_${turn.number}_${index + 1}`, def: def.id }));
  return { questions, pending, outcome: turnOutcome(turn, input, questions, after) };
}

const closesProfile = (outcome: TurnOutcome) => outcome === "stopped" || outcome === "complete";

function checkCompletedDetail({ questions, outcome }: Decision, after: Completeness): L {
  if (outcome === "stopped") return { fr: "L'investisseur s'arrête au-dessus du seuil", en: "The investor stops above the threshold" };
  if (outcome === "complete") return { fr: "Plus de relance utile : profil complet", en: "No useful follow-up left: profile complete" };
  return {
    fr: `${questions.length} relance(s) utile(s) sur ${after.missing.length} champ(s) manquant(s)`,
    en: `${questions.length} useful follow-up(s) for ${after.missing.length} missing field(s)`,
  };
}

function checkCompletedStep(decision: Decision, after: Completeness, locale: Locale): TraceStepInput {
  return {
    kind: "tool",
    actor: "A1",
    title: locale === "fr" ? "Outil check_completed" : "Tool check_completed",
    detail: tr(checkCompletedDetail(decision, after), locale),
    outputs: { complete: closesProfile(decision.outcome), ready: after.ready, next: decision.pending.map((item) => item.id) },
    durationMs: 30,
  };
}

function replyInput(turn: Turn, input: TurnInput, decision: Decision, after: Completeness): A1MessageInput {
  return {
    level: turn.level,
    notes: input.extracted.map((fact) => fact.note),
    score: after.score,
    displayed: after.displayed,
    ready: after.ready,
    questions: decision.questions,
    missingLabels: decision.questions.map((def) => fieldDef(def.field)?.label ?? { fr: def.field, en: def.field }),
    adviceRequest: input.screening?.adviceRequest ?? false,
    offTopic: input.screening?.offTopic ?? false,
    outcome: decision.outcome,
    firstTurn: turn.isFirst,
  };
}

function replyModelStep(turn: Turn, decision: Decision, after: Completeness, replyText: string): TraceStepInput {
  const { level } = turn;
  const count = decision.questions.length;
  return {
    kind: "model",
    actor: "A1",
    title: turn.locale === "fr" ? "Modèle Bedrock : relance rédigée" : "Bedrock model: follow-up written",
    detail:
      turn.locale === "fr"
        ? `${count} question(s) formulée(s) au niveau ${level ?? "beginner"}, sans s'écarter du profil`
        : `${count} question(s) phrased at ${level ?? "beginner"} level, staying on the profile`,
    inputs: { model_id: MODEL_ID, simulated: true, knowledge_level: level, missing: after.missing.slice(0, 5).map((item) => item.field) },
    outputs: { questions: decision.pending.map((item) => item.id), message_chars: replyText.length },
    durationMs: 1_650,
  };
}

function replyGuardrailStep(locale: Locale): TraceStepInput {
  const fr = locale === "fr";
  return {
    kind: "guardrail",
    actor: "guardrail",
    title: fr ? "Réponse vérifiée par le garde-fou" : "Reply checked by the guardrail",
    detail: fr ? "Aucun conseil personnalisé, aucune transaction" : "No personalized advice, no transaction",
    outputs: { action: "NONE" },
    durationMs: 130,
  };
}

/** Journal notes of the stage change that ends a turn. */
const STAGE_NOTES: Record<TurnOutcome, string> = {
  stopped: "arrêt demandé par l'investisseur",
  complete: "A1 juge le profil complet",
  idle: "relances d'A1",
  ask: "relances d'A1",
};

export function replyToFollowups(record: ClientRecord, request: FollowupReplyRequest, trace: Trace): Envelope {
  const locale = record.locale;
  requireStage(record, ["followups", "complete"], "followup.reply");
  const input = readTurn(record, request, trace);
  const turn = openTurn(record);
  const before = completeness(record.values, locale);

  for (const step of readingSteps(turn, input)) trace.add(step);
  const written = writeTurn(record, turn, input, trace.now);
  if (written.length > 0) trace.add(updateKbStep(turn, written));
  const after = completeness(record.values, locale);
  trace.add(completenessStep(before, after, locale));

  countPendingAsAsked(record);
  const decision = decideFollowups(record, turn, input, after);
  trace.add(checkCompletedStep(decision, after, locale));
  const reply = composeA1Message(replyInput(turn, input, decision, after));
  trace.message(tr(reply, locale), REPLY_DELAY_MS);
  trace.add(replyModelStep(turn, decision, after, tr(reply, locale)));
  trace.add(replyGuardrailStep(locale));

  record.pendingA1 = decision.pending;
  setStage(record, closesProfile(decision.outcome) ? "complete" : "followups", {
    provenance: turn.provenance,
    at: trace.now,
    note: STAGE_NOTES[decision.outcome],
  });
  record.message = reply;
  writeClientDocs(record, trace, "followup.reply");
  return clientState(record, trace, locale);
}
