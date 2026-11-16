/**
 * In-memory simulator of the `profile` runtime (CONTRACTS.md 3). It implements
 * every action, the stage machine, completeness, traces and SSE streaming, so the
 * interface can be developed and demoed without AWS.
 *
 * Each action is computed at once into an `Outcome`: the final response plus the
 * script of trace and delta events that led to it. JSON mode returns the response
 * after a short latency; stream mode replays the script with realistic delays.
 *
 * This module holds the clients and the general base and routes each request; the
 * actions themselves live in the `*-actions` modules.
 */
import { randomUUID } from "node:crypto";
import type { AgentRequest } from "@/lib/contract/requests";
import type { ClientState, KbItem, Locale, StreamEvent } from "@/lib/contract/schemas";
import { answerBaseQuestion } from "./base-actions";
import { newClientRecord, type ClientRecord } from "./client-record";
import { profileState } from "./client-state";
import { MockCollector } from "./collect";
import { generalIndex, generalSeed, type StoredDoc } from "./documents";
import { errorEnvelope, MOCK_RELEASE, MockError, type Envelope } from "./envelope";
import { replyToFollowups } from "./followup-actions";
import { kbItemsWithRelations } from "./kb-relations";
import { confirmPortfolio, skipPortfolio, submitPortfolio } from "./portfolio-actions";
import { openSession, reopenSession, resumeSession, updateSettings } from "./session-actions";
import { Trace, type ScriptItem } from "./trace";

export interface Outcome {
  response: Envelope;
  script: ScriptItem[];
}

export interface MockRuntimeOptions {
  /** Multiplies every simulated delay; 0 in tests. */
  delayScale?: number;
  now?: () => number;
}

type SessionStartRequest = Extract<AgentRequest, { action: "session.start" }>;
/** Requests that always name the client they act on. */
type ClientRequest = Extract<AgentRequest, { client_id: string }>;

/** Share of the scripted delays a non-streamed call waits, and its ceiling. */
const JSON_LATENCY_SHARE = 0.6;
const MAX_JSON_LATENCY_MS = 2_500;

const sleep = (durationMs: number) => new Promise<void>((resolve) => setTimeout(resolve, durationMs));

/** Run an action on the record of its client. */
function actOnClient(record: ClientRecord, request: ClientRequest, trace: Trace): Envelope {
  switch (request.action) {
    case "session.resume":
      return resumeSession(record, request, trace);
    case "base.answer":
      return answerBaseQuestion(record, request, trace);
    case "portfolio.submit":
      return submitPortfolio(record, request, trace);
    case "portfolio.confirm":
      return confirmPortfolio(record, request, trace);
    case "portfolio.skip":
      return skipPortfolio(record, trace);
    case "followup.reply":
      return replyToFollowups(record, request, trace);
    case "settings.update":
      return updateSettings(record, request, trace);
    case "profile.get":
      return profileState(record, trace);
  }
}

function kbItems(docs: Iterable<StoredDoc>): KbItem[] {
  return kbItemsWithRelations([...docs]);
}

function documentNotFound(key: string): MockError {
  return new MockError("not_found", { fr: "Document introuvable.", en: "Document not found." }, { key });
}

export class MockRuntime {
  private readonly clients = new Map<string, ClientRecord>();
  private readonly general = new Map<string, StoredDoc>();
  readonly collector: MockCollector;
  private readonly delayScale: number;
  private readonly now: () => number;

  constructor(options: MockRuntimeOptions = {}) {
    this.delayScale = options.delayScale ?? 1;
    this.now = options.now ?? (() => Date.now());
    for (const doc of generalSeed()) this.general.set(doc.key, doc);
    this.collector = new MockCollector((docs) => {
      for (const doc of docs) this.general.set(doc.key, doc);
      const index = generalIndex([...this.general.values()]);
      this.general.set(index.key, index);
    }, this.now);
  }

  /** Non-streamed call: the final JSON response. */
  async handle(request: AgentRequest): Promise<Envelope> {
    const outcome = this.run(request);
    const total = outcome.script.reduce((sum, item) => sum + item.delayMs, 0);
    const latency = Math.min(total * JSON_LATENCY_SHARE, MAX_JSON_LATENCY_MS) * this.delayScale;
    if (latency > 0) await sleep(latency);
    return outcome.response;
  }

  /** Streamed call (`stream: true`): trace and delta events, then one result or error. */
  async *stream(request: AgentRequest): AsyncGenerator<StreamEvent> {
    const outcome = this.run(request);
    for (const item of outcome.script) {
      if (this.delayScale > 0) await sleep(item.delayMs * this.delayScale);
      yield item.event;
    }
    if (outcome.response.ok) {
      yield { type: "result", result: outcome.response as unknown as ClientState };
    } else {
      yield { type: "error", error: outcome.response.error };
    }
  }

  /** Compute an action: mutate the state and return the response and its event script. */
  run(request: AgentRequest): Outcome {
    const trace = new Trace(this.now());
    const locale = this.localeOf(request);
    try {
      const response = this.dispatch(request, trace);
      return { response, script: trace.script };
    } catch (error) {
      return { response: errorEnvelope(error, locale), script: trace.script };
    }
  }

  private localeOf(request: AgentRequest): Locale {
    if ("locale" in request && request.locale) return request.locale;
    if ("client_id" in request && request.client_id) return this.clients.get(request.client_id)?.locale ?? "fr";
    return "fr";
  }

  private dispatch(request: AgentRequest, trace: Trace): Envelope {
    switch (request.action) {
      case "health":
        return { ok: true, release: MOCK_RELEASE, role: "profile", env: "mock" };
      case "session.start":
        return this.startSession(request, trace);
      case "kb.list":
        return { ok: true, release: MOCK_RELEASE, items: this.kbList(request.prefix, request.client_id) };
      case "kb.get":
        return { ok: true, release: MOCK_RELEASE, ...this.kbGet(request.key, request.client_id) };
      default:
        return actOnClient(this.client(request.client_id), request, trace);
    }
  }

  private startSession(request: SessionStartRequest, trace: Trace): Envelope {
    const id = (request.client_id ?? randomUUID()).toLowerCase();
    const known = this.clients.get(id);
    if (known) return reopenSession(known, request.locale, trace);
    const record = newClientRecord(id, request.locale, trace.now);
    this.clients.set(id, record);
    return openSession(record, trace);
  }

  /** « Supprimer mon compte », simulated: the client and its documents are forgotten. Its document count, or null if unknown. */
  forgetClient(id: string): number | null {
    const record = this.clients.get(id.toLowerCase());
    if (!record) return null;
    this.clients.delete(record.id);
    return record.docs.size;
  }

  private client(id: string): ClientRecord {
    const record = this.clients.get(id.toLowerCase());
    if (!record) {
      throw new MockError(
        "not_found",
        {
          fr: "Aucune base pour ce client. Le simulateur garde ses données en mémoire : elles disparaissent quand le serveur redémarre.",
          en: "No base for this client. The simulator keeps its data in memory: it is lost when the server restarts.",
        },
        { client_id: id },
      );
    }
    return record;
  }

  private kbList(prefix: string, clientId: string | undefined): KbItem[] {
    if (prefix === "general/") return kbItems(this.general.values());
    const record = this.client(clientId ?? prefix.split("/")[1] ?? "");
    if (!prefix.startsWith(`clients/${record.id}/`)) {
      throw new MockError("not_found", { fr: "Préfixe inconnu.", en: "Unknown prefix." }, { prefix });
    }
    return kbItems(record.docs.values());
  }

  private kbGet(key: string, clientId: string | undefined): { key: string; content: string } {
    const doc = key.startsWith("general/") ? this.general.get(key) : this.clientDoc(key, clientId);
    if (!doc) throw documentNotFound(key);
    return { key, content: doc.content };
  }

  /** A `clients/<id>/...` document, served only to the client it belongs to. */
  private clientDoc(key: string, clientId: string | undefined): StoredDoc | undefined {
    const owner = key.split("/")[1] ?? "";
    if (!clientId || clientId.toLowerCase() !== owner.toLowerCase()) throw documentNotFound(key);
    return this.client(owner).docs.get(key);
  }
}

const globalForMock = globalThis as unknown as { __alphaforgeMock?: MockRuntime };

/** One simulator per server process, kept across hot reloads in development. */
export function getMockRuntime(): MockRuntime {
  globalForMock.__alphaforgeMock ??= new MockRuntime();
  return globalForMock.__alphaforgeMock;
}
