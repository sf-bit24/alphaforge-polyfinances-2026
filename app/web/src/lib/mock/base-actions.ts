/**
 * `base.answer` of the simulator (CONTRACTS.md 3.2): the deterministic questionnaire validates
 * the answer and stores it, the code recomputes what depends on it, and the rules pick the next
 * question or end the base questions.
 */
import type { AgentRequest } from "@/lib/contract/requests";
import type { AnswerValue, Completeness, Locale } from "@/lib/contract/schemas";
import { writeClientDocs } from "./client-docs";
import { knowledgeLevelOf, requireStage, setFact, setStage, type ClientRecord } from "./client-record";
import { clientState } from "./client-state";
import { MockError, type Envelope } from "./envelope";
import { completeness, effectiveRisk, formatPercent, knowledgeLevel, riskCapacity, riskTolerance, type FieldValues } from "./profile";
import {
  baseQuestion,
  branchesTriggeredBy,
  nextBaseQuestion,
  renderQuestion,
  tr,
  validateAnswer,
  type L,
  type QuestionDef,
} from "./questions";
import type { Trace, TraceStepInput } from "./trace";

type BaseAnswerRequest = Extract<AgentRequest, { action: "base.answer" }>;
type NextQuestion = NonNullable<ReturnType<typeof nextBaseQuestion>>;

const LAST_KNOWLEDGE_QUESTION = "q_self_assessment";
const HAS_PORTFOLIO_QUESTION = "q_has_portfolio";

interface CheckedAnswer {
  def: QuestionDef;
  value: AnswerValue;
}

/** The answer must be for the pending question, and valid for its kind. */
function checkAnswer(record: ClientRecord, request: BaseAnswerRequest): CheckedAnswer {
  const questionId = request.question_id;
  if (record.pendingBase !== questionId) {
    throw new MockError(
      "conflict",
      {
        fr: `La question attendue est ${record.pendingBase}, pas ${questionId}.`,
        en: `The expected question is ${record.pendingBase}, not ${questionId}.`,
      },
      { expected: record.pendingBase, received: questionId },
    );
  }
  const def = baseQuestion(questionId);
  if (!def) throw new MockError("not_found", { fr: "Question inconnue.", en: "Unknown question." }, { question_id: questionId });
  const checked = validateAnswer(renderQuestion(def, record.locale, knowledgeLevelOf(record)), request.value);
  if (!checked.ok) throw new MockError("invalid_answer", checked.reason, checked.details);
  return { def, value: checked.value };
}

function validatedStep({ def, value }: CheckedAnswer, locale: Locale): TraceStepInput {
  const fr = locale === "fr";
  return {
    kind: "deterministic",
    actor: "questionnaire",
    title: fr ? "Réponse validée par les règles" : "Answer validated by the rules",
    detail: fr ? `${def.id} : ${def.kind}, valeur conforme` : `${def.id}: ${def.kind}, valid value`,
    inputs: { question_id: def.id, value },
    outputs: { valid: true, field: def.field },
    durationMs: 2,
  };
}

/** Store the answer as a fact; "no portfolio" also settles the existing portfolio field. */
function storeAnswer(record: ClientRecord, { def, value }: CheckedAnswer, at: string): void {
  const provenance = `base:${def.id}`;
  record.baseAnswers[def.id] = value;
  setFact(record, { field: def.field, value, provenance, at }, def.id);
  if (def.id === HAS_PORTFOLIO_QUESTION && value === false) {
    setFact(record, { field: "context.existing_portfolio", value: "none", provenance, at }, def.id);
  }
}

function knowledgeLevelStep(values: FieldValues, locale: Locale): TraceStepInput {
  const computed = knowledgeLevel(values);
  return {
    kind: "deterministic",
    actor: "questionnaire",
    title: locale === "fr" ? "Niveau de connaissances calculé par le code" : "Knowledge level computed by code",
    detail:
      locale === "fr"
        ? `Auto-évaluation pondérée deux fois l'expérience observée (${computed.reason})`
        : `Self-assessment weighted twice the observed experience (${computed.reason})`,
    outputs: { knowledge_level: computed.level },
    durationMs: 1,
  };
}

function completenessStep(before: Completeness, after: Completeness, locale: Locale): TraceStepInput {
  return {
    kind: "deterministic",
    actor: "completeness",
    title: locale === "fr" ? "Complétude recalculée" : "Completeness recomputed",
    detail: `${formatPercent(before.score, locale)} → ${formatPercent(after.score, locale)}`,
    outputs: { score: after.score, displayed: after.displayed, ready: after.ready },
    durationMs: 1,
  };
}

function feedsEffectiveRisk(def: QuestionDef): boolean {
  return def.dimension === "risk_tolerance" || def.dimension === "risk_capacity" || def.field === "horizon.horizon_band";
}

/** The effective risk once both tolerance and capacity are known, or null before that. */
function effectiveRiskStep(values: FieldValues, locale: Locale): TraceStepInput | null {
  const risk = effectiveRisk(values);
  if (!risk) return null;
  const tolerance = riskTolerance(values);
  const capacity = riskCapacity(values);
  return {
    kind: "deterministic",
    actor: "completeness",
    title: locale === "fr" ? "Risque effectif = min(tolérance, capacité)" : "Effective risk = min(tolerance, capacity)",
    detail:
      locale === "fr"
        ? `tolérance ${tolerance}/5, capacité ${capacity?.level}/5`
        : `tolerance ${tolerance}/5, capacity ${capacity?.level}/5`,
    outputs: { effective_risk: risk, limited_by: capacity?.limitedBy ?? null },
    durationMs: 1,
  };
}

/** What the code recomputes after an answer: knowledge level, completeness, effective risk. */
function recomputedSteps(record: ClientRecord, def: QuestionDef, before: Completeness): TraceStepInput[] {
  const { values, locale } = record;
  const steps: TraceStepInput[] = [];
  if (def.dimension === "knowledge" && def.id === LAST_KNOWLEDGE_QUESTION) steps.push(knowledgeLevelStep(values, locale));
  steps.push(completenessStep(before, completeness(values, locale), locale));
  const riskStep = feedsEffectiveRisk(def) ? effectiveRiskStep(values, locale) : null;
  if (riskStep) steps.push(riskStep);
  return steps;
}

function nextQuestionDetail(next: NextQuestion, answeredId: string, locale: Locale): L {
  if (!next.branch) return { fr: `${next.id} après ${answeredId}`, en: `${next.id} after ${answeredId}` };
  const branch = tr(next.branch, locale);
  return {
    fr: `${next.id} après ${answeredId} (branche : ${branch})`,
    en: `${next.id} after ${answeredId} (branch: ${branch})`,
  };
}

function nextQuestionStep(record: ClientRecord, answeredId: string, next: NextQuestion): TraceStepInput {
  const locale = record.locale;
  const branches = branchesTriggeredBy(answeredId, record.baseAnswers).map((branch) => ({
    question: branch.question,
    active: branch.active,
    rule: tr(branch.rule, locale),
  }));
  return {
    kind: "deterministic",
    actor: "questionnaire",
    title: locale === "fr" ? "Question suivante choisie par les règles" : "Next question picked by the rules",
    detail: tr(nextQuestionDetail(next, answeredId, locale), locale),
    inputs: { question_id: answeredId },
    outputs: { next: next.id, branches },
    durationMs: 2,
  };
}

const hasPortfolio = (record: ClientRecord) => record.baseAnswers[HAS_PORTFOLIO_QUESTION] === true;

function questionnaireDoneStep(record: ClientRecord): TraceStepInput {
  const detail: L = hasPortfolio(record)
    ? { fr: "Portefeuille existant = oui : étape existing_portfolio", en: "Existing portfolio = yes: existing_portfolio stage" }
    : {
        fr: "Portefeuille existant = non : étape followups (relances A1)",
        en: "Existing portfolio = no: followups stage (A1 follow-ups)",
      };
  return {
    kind: "deterministic",
    actor: "questionnaire",
    title: record.locale === "fr" ? "Questions de base terminées" : "Base questions done",
    detail: tr(detail, record.locale),
    outputs: { stage: record.stage },
    durationMs: 2,
  };
}

/** Ask the next question by the rules; after the last one, go to the existing portfolio or to A1's follow-ups. */
function advanceQuestionnaire(record: ClientRecord, answeredId: string, trace: Trace): void {
  const next = nextBaseQuestion(record.baseAnswers);
  record.pendingBase = next?.id ?? null;
  if (next) {
    trace.add(nextQuestionStep(record, answeredId, next));
    return;
  }
  setStage(record, hasPortfolio(record) ? "existing_portfolio" : "followups", {
    provenance: `base:${answeredId}`,
    at: trace.now,
    note: hasPortfolio(record) ? "portefeuille existant = oui" : "portefeuille existant = non",
  });
  trace.add(questionnaireDoneStep(record));
}

export function answerBaseQuestion(record: ClientRecord, request: BaseAnswerRequest, trace: Trace): Envelope {
  requireStage(record, ["base_questions"], "base.answer");
  const answer = checkAnswer(record, request);
  const before = completeness(record.values, record.locale);
  trace.add(validatedStep(answer, record.locale));
  storeAnswer(record, answer, trace.now);
  for (const step of recomputedSteps(record, answer.def, before)) trace.add(step);
  advanceQuestionnaire(record, answer.def.id, trace);
  writeClientDocs(record, trace, "base.answer");
  return clientState(record, trace, record.locale);
}
