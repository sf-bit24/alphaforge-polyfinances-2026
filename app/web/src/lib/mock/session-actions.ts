/**
 * Session actions of the simulator (CONTRACTS.md 3.2): opening a client base or finding it
 * again, resuming it, and changing its settings.
 */
import type { AgentRequest } from "@/lib/contract/requests";
import type { Locale } from "@/lib/contract/schemas";
import { writeClientDocs } from "./client-docs";
import { knowledgeLevelOf, setFact, type ClientRecord } from "./client-record";
import { clientState } from "./client-state";
import type { Envelope } from "./envelope";
import type { Trace } from "./trace";

type SessionResumeRequest = Extract<AgentRequest, { action: "session.resume" }>;
type SettingsUpdateRequest = Extract<AgentRequest, { action: "settings.update" }>;

/** `session.start` for a new client: its base is created and the rules pick the first question. */
export function openSession(record: ClientRecord, trace: Trace): Envelope {
  const fr = record.locale === "fr";
  const base = `clients/${record.id}/`;
  trace.add({
    kind: "storage",
    actor: "store",
    title: fr ? "Votre profil est créé" : "Your profile is created",
    detail: fr ? "Vos réponses y seront enregistrées au fur et à mesure" : "Your answers will be saved there as you go",
    outputs: { keys: [`${base}index.md`, `${base}profil.md`, `${base}journal.md`] },
    durationMs: 9,
  });
  trace.add({
    kind: "deterministic",
    actor: "questionnaire",
    title: fr ? "Première question choisie selon des règles fixes" : "First question picked with fixed rules",
    detail: fr ? "Votre niveau de connaissances vient en premier" : "Your knowledge level comes first",
    outputs: { next: record.pendingBase },
    durationMs: 2,
  });
  writeClientDocs(record, trace, "session.start");
  return clientState(record, trace, record.locale);
}

/** `session.start` with the id of a known client: the session goes on, in the requested language. */
export function reopenSession(record: ClientRecord, locale: Locale, trace: Trace): Envelope {
  record.locale = locale;
  trace.add({
    kind: "storage",
    actor: "store",
    title: locale === "fr" ? "Votre profil est retrouvé" : "Your profile is found",
    detail: locale === "fr" ? "On reprend là où vous en étiez" : "We pick up where you left off",
    outputs: { stage: record.stage },
    durationMs: 5,
  });
  return clientState(record, trace, locale);
}

/** `session.resume`: the state as it is, rendered in the requested language when there is one. */
export function resumeSession(record: ClientRecord, request: SessionResumeRequest, trace: Trace): Envelope {
  const locale = request.locale ?? record.locale;
  trace.add({
    kind: "storage",
    actor: "store",
    title: locale === "fr" ? "Votre profil est lu" : "Your profile is read",
    detail: locale === "fr" ? "Vos réponses enregistrées sont reprises" : "Your saved answers are loaded",
    outputs: { stage: record.stage },
    durationMs: 4,
  });
  return clientState(record, trace, locale);
}

/** Apply the requested settings and return those that changed, under their contract names. */
function applySettings(record: ClientRecord, request: SettingsUpdateRequest, at: string): Record<string, unknown> {
  const changes: Record<string, unknown> = {};
  if (request.locale && request.locale !== record.locale) {
    record.locale = request.locale;
    changes.locale = request.locale;
  }
  const level = request.knowledge_level;
  if (level && level !== knowledgeLevelOf(record)) {
    setFact(record, { field: "knowledge.level", value: level, provenance: "settings", at });
    changes.knowledge_level = level;
  }
  return changes;
}

/** A changed setting in words: « Langue : anglais », "Knowledge level: advanced". */
const SETTING_WORDS: Record<string, { name: Record<Locale, string>; values: Record<string, Record<Locale, string>> }> = {
  locale: {
    name: { fr: "Langue", en: "Language" },
    values: { fr: { fr: "français", en: "French" }, en: { fr: "anglais", en: "English" } },
  },
  knowledge_level: {
    name: { fr: "Niveau de connaissances", en: "Knowledge level" },
    values: {
      beginner: { fr: "débutant", en: "beginner" },
      intermediate: { fr: "intermédiaire", en: "intermediate" },
      advanced: { fr: "avancé", en: "advanced" },
    },
  },
};

function changesDetail(changes: Record<string, unknown>, locale: Locale): string {
  const listed = Object.entries(changes).map(([key, value]) => {
    const words = SETTING_WORDS[key];
    if (!words) return String(value);
    return `${words.name[locale]}${locale === "fr" ? " : " : ": "}${words.values[String(value)]?.[locale] ?? String(value)}`;
  });
  if (listed.length > 0) return listed.join(", ");
  return locale === "fr" ? "Aucun changement" : "No change";
}

/** `settings.update`: language and knowledge level; the documents are rewritten only on a change. */
export function updateSettings(record: ClientRecord, request: SettingsUpdateRequest, trace: Trace): Envelope {
  const changes = applySettings(record, request, trace.now);
  trace.add({
    kind: "deterministic",
    actor: "questionnaire",
    title: record.locale === "fr" ? "Réglages mis à jour" : "Settings updated",
    detail: changesDetail(changes, record.locale),
    inputs: { locale: request.locale ?? null, knowledge_level: request.knowledge_level ?? null },
    outputs: changes,
    durationMs: 2,
  });
  if (Object.keys(changes).length > 0) writeClientDocs(record, trace, "settings.update");
  return clientState(record, trace, record.locale);
}
