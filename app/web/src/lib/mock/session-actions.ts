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
    title: fr ? "Base du client créée" : "Client base created",
    detail: base,
    outputs: { keys: [`${base}index.md`, `${base}profil.md`, `${base}journal.md`] },
    durationMs: 9,
  });
  trace.add({
    kind: "deterministic",
    actor: "questionnaire",
    title: fr ? "Première question choisie par les règles" : "First question picked by the rules",
    detail: fr
      ? `${record.pendingBase} : le niveau de connaissances vient en premier`
      : `${record.pendingBase}: knowledge level comes first`,
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
    title: locale === "fr" ? "Base du client retrouvée" : "Client base found",
    detail: `clients/${record.id}/`,
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
    title: locale === "fr" ? "État du client lu" : "Client state read",
    detail: `clients/${record.id}/profil.md`,
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

function changesDetail(changes: Record<string, unknown>, locale: Locale): string {
  const listed = Object.entries(changes).map(([key, value]) => `${key} = ${String(value)}`);
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
