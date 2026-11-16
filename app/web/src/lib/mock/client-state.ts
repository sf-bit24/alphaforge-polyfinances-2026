/** `ClientState` (CONTRACTS.md 3.2), rendered from a client record in the requested language. */
import type { ClientState, KnowledgeLevel, Locale, Question } from "@/lib/contract/schemas";
import { reconcileClientKb } from "./client-kb";
import { knowledgeLevelOf, type ClientRecord } from "./client-record";
import { MOCK_RELEASE, type Envelope } from "./envelope";
import { completeness, dimensionViews, effectiveRisk, factLabel, PORTFOLIO_DRAFT_FIELD, riskDetail } from "./profile";
import { a1Question, baseQuestion, renderQuestion, tr } from "./questions";
import type { Trace } from "./trace";

/** The pending base question, or A1's pending follow-ups under their opaque ids. */
function pendingQuestions(record: ClientRecord, locale: Locale, level: KnowledgeLevel | null): Question[] {
  if (record.stage === "base_questions" && record.pendingBase) {
    const def = baseQuestion(record.pendingBase);
    return def ? [renderQuestion(def, locale, level)] : [];
  }
  if (record.stage !== "followups") return [];
  return record.pendingA1.flatMap(({ id, def }) => {
    const found = a1Question(def);
    return found ? [{ ...renderQuestion(found, locale, level), id }] : [];
  });
}

export function clientState(record: ClientRecord, trace: Trace, locale: Locale): Envelope {
  // Once per action, like the runtime: the knowledge base of the client moves on and receives the new documents.
  const clientKb = reconcileClientKb(record, trace);
  const level = knowledgeLevelOf(record);
  const state: ClientState = {
    ok: true,
    release: MOCK_RELEASE,
    client_id: record.id,
    locale,
    stage: record.stage,
    message: record.message ? tr(record.message, locale) : null,
    questions: pendingQuestions(record, locale, level),
    profile: {
      knowledge_level: level,
      effective_risk: effectiveRisk(record.values),
      risk: riskDetail(record.values),
      dimensions: dimensionViews(record.values, locale),
      facts: [...record.values.values()]
        .filter((fact) => fact.field !== PORTFOLIO_DRAFT_FIELD)
        .sort((left, right) => left.at.localeCompare(right.at))
        .map((fact) => ({ ...fact, label: factLabel(fact.field, fact.value, locale) })),
    },
    completeness: completeness(record.values, locale),
    portfolio: record.portfolio,
    trace: trace.steps,
    client_kb: clientKb,
  };
  return state as unknown as Envelope;
}

/** `profile.get`: the state in the client's language, with the Markdown documents of its base. */
export function profileState(record: ClientRecord, trace: Trace): Envelope {
  const state = clientState(record, trace, record.locale) as unknown as ClientState;
  state.profile.documents = [...record.docs.values()]
    .filter((doc) => doc.key.endsWith(".md"))
    .map((doc) => ({ key: doc.key, title: doc.title }));
  return state as unknown as Envelope;
}
