/**
 * The client's own knowledge base, simulated (CONTRACTS.md 5, `clients/<id>/kb.json`): created at the first action,
 * active from the next one, then every Markdown document of the base is indexed. Traces and JSON are never indexed.
 */
import type { ClientKb, ClientKbStatus } from "@/lib/contract/schemas";
import type { ClientRecord } from "./client-record";
import type { Trace } from "./trace";

export interface MockClientKb {
  status: ClientKbStatus;
  knowledgeBaseId: string | null;
  /** Keys indexed so far, with the `updated_at` of the version that was sent. */
  indexed: Map<string, string>;
}

export function newMockClientKb(): MockClientKb {
  return { status: "creating", knowledgeBaseId: null, indexed: new Map() };
}

/** Markdown documents of the base that the index holds (no trace, no JSON). */
function indexable(record: ClientRecord): Array<{ key: string; updated_at: string }> {
  return [...record.docs.values()].filter((doc) => doc.key.endsWith(".md") && !doc.key.includes("/traces/"));
}

interface KbStep {
  title: { fr: string; en: string };
  detail: string;
  outputs: unknown;
}

function storageStep(trace: Trace, record: ClientRecord, step: KbStep) {
  const title = record.locale === "fr" ? step.title.fr : step.title.en;
  trace.add({ kind: "storage", actor: "store", title, detail: step.detail, outputs: step.outputs, durationMs: 40 });
}

/** Reconciliation at the end of an action: one creation step, then the activation, then each new version sent. */
export function reconcileClientKb(record: ClientRecord, trace: Trace): ClientKb {
  const kb = record.kb;
  const docs = indexable(record);
  if (kb.knowledgeBaseId === null) {
    kb.knowledgeBaseId = `MOCK${record.id.replace(/-/g, "").slice(0, 6).toUpperCase()}`;
    storageStep(trace, record, {
      title: { fr: "Knowledge Base du client créée", en: "Client knowledge base created" },
      detail: kb.knowledgeBaseId,
      outputs: { knowledge_base_id: kb.knowledgeBaseId, index: `client-${record.id}`, status: "CREATING" },
    });
  } else if (kb.status === "creating") {
    kb.status = "active";
    storageStep(trace, record, {
      title: { fr: "Knowledge Base du client active", en: "Client knowledge base active" },
      detail: kb.knowledgeBaseId,
      outputs: { pending: docs.length },
    });
  }
  const changed = docs.filter((doc) => kb.indexed.get(doc.key) !== doc.updated_at);
  if (kb.status === "active" && changed.length > 0) {
    for (const doc of changed) kb.indexed.set(doc.key, doc.updated_at);
    storageStep(trace, record, {
      title: { fr: "Documents indexés dans la Knowledge Base du client", en: "Documents indexed in the client knowledge base" },
      detail: kb.knowledgeBaseId,
      outputs: { ingested: changed.map((doc) => doc.key), deleted: [], pending: [] },
    });
  }
  const pending = kb.status === "active" ? 0 : changed.length;
  return { status: kb.status, knowledge_base_id: kb.knowledgeBaseId, documents: kb.indexed.size, pending };
}
