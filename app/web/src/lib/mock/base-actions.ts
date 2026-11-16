/**
 * `base.answer` of the simulator (CONTRACTS.md 3.2): the deterministic questionnaire validates
 * the answer and stores it, the code recomputes what depends on it, and the rules pick the next
 * question or end the base questions.
 */
import type { AgentRequest } from "@/lib/contract/requests";
import type { AnswerValue, Completeness, KnowledgeLevel, Locale } from "@/lib/contract/schemas";
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
        fr: "Cette question a déjà reçu une réponse. Rechargez la page pour voir la question en cours.",
        en: "This question has already been answered. Reload the page to see the current question.",
      },
      { expected: record.pendingBase, received: questionId },
    );
  }
  const def = baseQuestion(questionId);
  if (!def) {
    throw new MockError(
      "not_found",
      { fr: "Nous ne retrouvons pas cette question. Rechargez la page pour continuer.", en: "We cannot find this question. Reload the page to continue." },
      { question_id: questionId },
    );
  }
  const checked = validateAnswer(renderQuestion(def, record.locale, knowledgeLevelOf(record)), request.value);
  if (!checked.ok) throw new MockError("invalid_answer", checked.reason, checked.details);
  return { def, value: checked.value };
}

function validatedStep({ def, value }: CheckedAnswer, locale: Locale): TraceStepInput {
  const fr = locale === "fr";
  return {
    kind: "deterministic",
    actor: "questionnaire",
    title: fr ? "Réponse vérifiée" : "Answer checked",
    detail: fr ? `Réponse valide à la question « ${tr(def.prompt, locale)} »` : `Valid answer to the question "${tr(def.prompt, locale)}"`,
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

const TO_DETERMINE: L = { fr: "à déterminer", en: "to be determined" };

const KNOWLEDGE_WORDS: Record<KnowledgeLevel, L> = {
  beginner: { fr: "débutant", en: "beginner" },
  intermediate: { fr: "intermédiaire", en: "intermediate" },
  advanced: { fr: "avancé", en: "advanced" },
};

function knowledgeLevelStep(values: FieldValues, locale: Locale): TraceStepInput {
  const computed = knowledgeLevel(values);
  const level = tr(computed.level ? KNOWLEDGE_WORDS[computed.level] : TO_DETERMINE, locale);
  return {
    kind: "deterministic",
    actor: "questionnaire",
    title: locale === "fr" ? "Niveau de connaissances calculé selon des règles fixes" : "Knowledge level computed with fixed rules",
    detail:
      locale === "fr"
        ? `Votre propre évaluation compte deux fois plus que votre expérience : niveau ${level}`
        : `Your own assessment counts twice as much as your experience: ${level} level`,
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
    title:
      locale === "fr"
        ? "Risque retenu : le plus prudent de votre tolérance et de votre capacité"
        : "Risk retained: the more cautious of your tolerance and your capacity",
    detail:
      locale === "fr"
        ? `Tolérance ${tolerance} sur 5, capacité ${capacity?.level} sur 5`
        : `Tolerance ${tolerance} out of 5, capacity ${capacity?.level} out of 5`,
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

function nextQuestionDetail(next: NextQuestion, locale: Locale): L {
  const def = baseQuestion(next.id);
  const prompt = def ? tr(def.prompt, locale) : "";
  if (!next.branch) return { fr: `« ${prompt} »`, en: `"${prompt}"` };
  const branch = tr(next.branch, locale);
  return {
    fr: `« ${prompt} », posée parce que ${branch}`,
    en: `"${prompt}", asked because ${branch}`,
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
    title: locale === "fr" ? "Question suivante choisie selon des règles fixes" : "Next question picked with fixed rules",
    detail: tr(nextQuestionDetail(next, locale), locale),
    inputs: { question_id: answeredId },
    outputs: { next: next.id, branches },
    durationMs: 2,
  };
}

const hasPortfolio = (record: ClientRecord) => record.baseAnswers[HAS_PORTFOLIO_QUESTION] === true;

function questionnaireDoneStep(record: ClientRecord): TraceStepInput {
  const detail: L = hasPortfolio(record)
    ? { fr: "Vous avez un portefeuille existant : Yan va le lire avec vous", en: "You have an existing portfolio: Yan will read it with you" }
    : {
        fr: "Pas de portefeuille existant : Yan passe à ses questions de suivi",
        en: "No existing portfolio: Yan moves on to its follow-up questions",
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
    note: hasPortfolio(record) ? "vous avez un portefeuille existant" : "pas de portefeuille existant",
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
