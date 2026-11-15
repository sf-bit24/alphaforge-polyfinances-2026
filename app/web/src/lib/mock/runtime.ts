/**
 * In-memory simulator of the `profile` runtime (CONTRACTS.md 3). It implements
 * every action, the stage machine, completeness, traces and SSE streaming, so the
 * interface can be developed and demoed without AWS.
 *
 * Each action is computed at once into an `Outcome`: the final response plus the
 * script of trace and delta events that led to it. JSON mode returns the response
 * after a short latency; stream mode replays the script with realistic delays.
 */
import { randomUUID } from "node:crypto";
import type { AgentRequest, PositionInput } from "@/lib/contract/requests";
import type {
  AnswerValue,
  ClientState,
  ErrorBody,
  KbItem,
  KnowledgeLevel,
  Locale,
  PortfolioView,
  Question,
  Source,
  Stage,
  StreamEvent,
  TraceKind,
  TraceStep,
} from "@/lib/contract/schemas";
import {
  composeA1Message,
  composeA2Message,
  extractFacts,
  screenMessage,
  type ExtractedFact,
} from "./agents";
import { MockCollector } from "./collect";
import { generalIndex, generalSeed, okfDocument, staleAfter, type StoredDoc } from "./documents";
import { computeExposures, extractPositions, fxRate, normalizeConfirmed, portfolioSources } from "./portfolio";
import {
  completeness,
  dimensionViews,
  effectiveRisk,
  fieldDef,
  formatPercent,
  isFieldKnown,
  knowledgeLevel,
  riskCapacity,
  riskDetail,
  riskTolerance,
  type FieldValues,
  type StoredFact,
} from "./profile";
import {
  A1_QUESTIONS,
  a1Question,
  baseQuestion,
  branchesTriggeredBy,
  nextBaseQuestion,
  renderQuestion,
  tr,
  validateAnswer,
  type L,
  type QuestionDef,
} from "./questions";
import { STARTER_SOURCES } from "./starter";

export const MOCK_RELEASE = "mock";
const MODEL_ID = "us.anthropic.claude-opus-5-5";
const MAX_A1_QUESTIONS = 3;

export type Envelope = { ok: true; release: string; [key: string]: unknown } | { ok: false; release: string; error: ErrorBody };

interface ScriptItem {
  event: StreamEvent;
  delayMs: number;
}

export interface Outcome {
  response: Envelope;
  script: ScriptItem[];
}

interface ClientRecord {
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
  pendingA1: Array<{ id: string; def: string }>;
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

type JournalEntry =
  | { at: string; kind: "answer"; provenance: string; field: string; value: unknown; question_id?: string; previous?: unknown }
  | { at: string; kind: "message"; provenance: string; text: string; locale: Locale }
  | { at: string; kind: "stage"; provenance: string; value: Stage; previous: Stage | null; note: string };

class MockError extends Error {
  constructor(
    readonly code: ErrorBody["code"],
    readonly text: L,
    readonly details: Record<string, unknown> = {},
  ) {
    super(text.en);
  }
}

/** Collects trace steps and stream events with a simulated clock. */
class Trace {
  readonly steps: TraceStep[] = [];
  readonly script: ScriptItem[] = [];
  private clock: number;

  constructor(start: number) {
    this.clock = start;
  }

  get now(): string {
    return new Date(this.clock).toISOString();
  }

  add(step: {
    kind: TraceKind;
    actor: string;
    title: string;
    detail?: string;
    inputs?: unknown;
    outputs?: unknown;
    sources?: Source[];
    duration: number;
  }): TraceStep {
    const full: TraceStep = {
      id: `st_${String(this.steps.length + 1).padStart(2, "0")}`,
      at: this.now,
      kind: step.kind,
      actor: step.actor,
      title: step.title,
      detail: step.detail ?? null,
      inputs: step.inputs ?? {},
      outputs: step.outputs ?? {},
      sources: step.sources ?? [],
      duration_ms: step.duration,
    };
    this.clock += step.duration;
    this.steps.push(full);
    this.script.push({ event: { type: "trace", step: full }, delayMs: Math.min(900, Math.max(60, step.duration)) });
    return full;
  }

  /**
   * One `delta` per agent message, carrying the whole message (CONTRACTS.md 3.4): the runtime passes it
   * through a `finish_turn` tool once the model has written it, so it arrives after `totalMs`.
   */
  message(text: string, totalMs: number): void {
    this.script.push({ event: { type: "delta", text }, delayMs: totalMs });
  }
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export interface MockRuntimeOptions {
  /** Multiplies every simulated delay; 0 in tests. */
  delayScale?: number;
  now?: () => number;
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
    const latency = Math.min(total * 0.6, 2_500) * this.delayScale;
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
      if (error instanceof MockError) {
        return {
          response: {
            ok: false,
            release: MOCK_RELEASE,
            error: { code: error.code, message: tr(error.text, locale), details: error.details },
          },
          script: trace.script,
        };
      }
      return {
        response: {
          ok: false,
          release: MOCK_RELEASE,
          error: { code: "internal", message: error instanceof Error ? error.message : String(error), details: {} },
        },
        script: trace.script,
      };
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
        return this.sessionStart(request.locale, request.client_id, trace);
      case "session.resume": {
        const record = this.client(request.client_id);
        trace.add({
          kind: "storage",
          actor: "store",
          title: (request.locale ?? record.locale) === "fr" ? "État du client lu" : "Client state read",
          detail: `clients/${record.id}/profil.md`,
          outputs: { stage: record.stage },
          duration: 4,
        });
        return this.state(record, trace, request.locale ?? record.locale);
      }
      case "base.answer":
        return this.baseAnswer(request.client_id, request.question_id, request.value, trace);
      case "portfolio.submit":
        return this.portfolioSubmit(request.client_id, request.text, request.files, trace);
      case "portfolio.confirm":
        return this.portfolioConfirm(request.client_id, request.positions, trace);
      case "portfolio.skip":
        return this.portfolioSkip(request.client_id, trace);
      case "followup.reply":
        return this.followupReply(request.client_id, request.answers ?? [], request.message, request.stop ?? false, trace);
      case "settings.update":
        return this.settingsUpdate(request.client_id, request.locale, request.knowledge_level, trace);
      case "profile.get": {
        const record = this.client(request.client_id);
        const state = this.state(record, trace, record.locale) as unknown as ClientState;
        state.profile.documents = [...record.docs.values()]
          .filter((doc) => doc.key.endsWith(".md"))
          .map((doc) => ({ key: doc.key, title: doc.title }));
        return state as unknown as Envelope;
      }
      case "kb.list":
        return { ok: true, release: MOCK_RELEASE, items: this.kbList(request.prefix, request.client_id) };
      case "kb.get":
        return { ok: true, release: MOCK_RELEASE, ...this.kbGet(request.key, request.client_id) };
    }
  }

  /* ----------------------------- sessions ------------------------------ */

  private sessionStart(locale: Locale, requestedId: string | undefined, trace: Trace): Envelope {
    const id = (requestedId ?? randomUUID()).toLowerCase();
    let record = this.clients.get(id);
    const fr = locale === "fr";
    if (!record) {
      record = {
        id,
        locale,
        stage: "base_questions",
        createdAt: trace.now,
        baseAnswers: {},
        entries: [],
        values: new Map(),
        pendingBase: null,
        pendingA1: [],
        askedCount: {},
        turn: 0,
        a1Turns: 0,
        lastA2Turn: 0,
        message: null,
        portfolio: null,
        docs: new Map(),
      };
      this.clients.set(id, record);
      const next = nextBaseQuestion(record.baseAnswers);
      record.pendingBase = next?.id ?? null;
      trace.add({
        kind: "storage",
        actor: "store",
        title: fr ? "Base du client créée" : "Client base created",
        detail: `clients/${id}/`,
        outputs: { keys: [`clients/${id}/index.md`, `clients/${id}/profil.md`, `clients/${id}/journal.md`] },
        duration: 9,
      });
      trace.add({
        kind: "deterministic",
        actor: "questionnaire",
        title: fr ? "Première question choisie par les règles" : "First question picked by the rules",
        detail: fr
          ? `${record.pendingBase} : le niveau de connaissances vient en premier`
          : `${record.pendingBase}: knowledge level comes first`,
        outputs: { next: record.pendingBase },
        duration: 2,
      });
      this.writeClientDocs(record, trace, "session.start");
    } else {
      record.locale = locale;
      trace.add({
        kind: "storage",
        actor: "store",
        title: fr ? "Base du client retrouvée" : "Client base found",
        detail: `clients/${id}/`,
        outputs: { stage: record.stage },
        duration: 5,
      });
    }
    return this.state(record, trace, locale);
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

  private requireStage(record: ClientRecord, allowed: Stage[], action: string): void {
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

  private setFact(record: ClientRecord, field: string, value: unknown, provenance: string, at: string, questionId?: string): StoredFact {
    const fact: StoredFact = { field, value, provenance, at };
    const previous = record.values.get(field);
    record.values.set(field, fact);
    record.entries.push({
      at,
      kind: "answer",
      provenance,
      field,
      value,
      ...(questionId ? { question_id: questionId } : {}),
      ...(previous ? { previous: previous.value } : {}),
    });
    return fact;
  }

  private setStage(record: ClientRecord, stage: Stage, provenance: string, at: string, note: string): void {
    if (record.stage === stage) return;
    record.entries.push({ at, kind: "stage", provenance, value: stage, previous: record.stage, note });
    record.stage = stage;
  }

  private level(record: ClientRecord): KnowledgeLevel | null {
    return knowledgeLevel(record.values).level;
  }

  /* --------------------------- base questions -------------------------- */

  private baseAnswer(clientId: string, questionId: string, value: AnswerValue, trace: Trace): Envelope {
    const record = this.client(clientId);
    const fr = record.locale === "fr";
    this.requireStage(record, ["base_questions"], "base.answer");
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
    const question = renderQuestion(def, record.locale, this.level(record));
    const checked = validateAnswer(question, value);
    if (!checked.ok) throw new MockError("invalid_answer", checked.reason, checked.details);

    const before = completeness(record.values, record.locale);
    trace.add({
      kind: "deterministic",
      actor: "questionnaire",
      title: fr ? "Réponse validée par les règles" : "Answer validated by the rules",
      detail: fr ? `${questionId} : ${def.kind}, valeur conforme` : `${questionId}: ${def.kind}, valid value`,
      inputs: { question_id: questionId, value: checked.value },
      outputs: { valid: true, field: def.field },
      duration: 2,
    });
    record.baseAnswers[questionId] = checked.value;
    const at = trace.now;
    this.setFact(record, def.field, checked.value, `base:${questionId}`, at, questionId);
    if (questionId === "q_has_portfolio" && checked.value === false) {
      this.setFact(record, "context.existing_portfolio", "none", `base:${questionId}`, at, questionId);
    }

    if (def.dimension === "knowledge" && questionId === "q_self_assessment") {
      const computed = knowledgeLevel(record.values);
      trace.add({
        kind: "deterministic",
        actor: "questionnaire",
        title: fr ? "Niveau de connaissances calculé par le code" : "Knowledge level computed by code",
        detail: fr
          ? `Auto-évaluation pondérée deux fois l'expérience observée (${computed.reason})`
          : `Self-assessment weighted twice the observed experience (${computed.reason})`,
        outputs: { knowledge_level: computed.level },
        duration: 1,
      });
    }

    const after = completeness(record.values, record.locale);
    trace.add({
      kind: "deterministic",
      actor: "completeness",
      title: fr ? "Complétude recalculée" : "Completeness recomputed",
      detail: `${formatPercent(before.score, record.locale)} → ${formatPercent(after.score, record.locale)}`,
      outputs: { score: after.score, displayed: after.displayed, ready: after.ready },
      duration: 1,
    });
    if (def.dimension === "risk_tolerance" || def.dimension === "risk_capacity" || def.field === "horizon.horizon_band") {
      const risk = effectiveRisk(record.values);
      if (risk) {
        trace.add({
          kind: "deterministic",
          actor: "completeness",
          title: fr ? "Risque effectif = min(tolérance, capacité)" : "Effective risk = min(tolerance, capacity)",
          detail: fr
            ? `tolérance ${riskTolerance(record.values)}/5, capacité ${riskCapacity(record.values)?.level}/5`
            : `tolerance ${riskTolerance(record.values)}/5, capacity ${riskCapacity(record.values)?.level}/5`,
          outputs: { effective_risk: risk, limited_by: riskCapacity(record.values)?.limitedBy ?? null },
          duration: 1,
        });
      }
    }

    const next = nextBaseQuestion(record.baseAnswers);
    const branches = branchesTriggeredBy(questionId, record.baseAnswers).map((branch) => ({
      question: branch.question,
      active: branch.active,
      rule: tr(branch.rule, record.locale),
    }));
    if (next) {
      record.pendingBase = next.id;
      trace.add({
        kind: "deterministic",
        actor: "questionnaire",
        title: fr ? "Question suivante choisie par les règles" : "Next question picked by the rules",
        detail: next.branch
          ? fr
            ? `${next.id} après ${questionId} (branche : ${tr(next.branch, record.locale)})`
            : `${next.id} after ${questionId} (branch: ${tr(next.branch, record.locale)})`
          : fr
            ? `${next.id} après ${questionId}`
            : `${next.id} after ${questionId}`,
        inputs: { question_id: questionId },
        outputs: { next: next.id, branches },
        duration: 2,
      });
    } else {
      record.pendingBase = null;
      const hasPortfolio = record.baseAnswers.q_has_portfolio === true;
      this.setStage(
        record,
        hasPortfolio ? "existing_portfolio" : "followups",
        `base:${questionId}`,
        trace.now,
        hasPortfolio ? "portefeuille existant = oui" : "portefeuille existant = non",
      );
      trace.add({
        kind: "deterministic",
        actor: "questionnaire",
        title: fr ? "Questions de base terminées" : "Base questions done",
        detail: hasPortfolio
          ? fr
            ? "Portefeuille existant = oui : étape existing_portfolio"
            : "Existing portfolio = yes: existing_portfolio stage"
          : fr
            ? "Portefeuille existant = non : étape followups (relances A1)"
            : "Existing portfolio = no: followups stage (A1 follow-ups)",
        outputs: { stage: record.stage },
        duration: 2,
      });
    }
    this.writeClientDocs(record, trace, "base.answer");
    return this.state(record, trace, record.locale);
  }

  /* ------------------------------ portfolio ---------------------------- */

  private portfolioSubmit(
    clientId: string,
    text: string | undefined,
    files: Array<{ name: string; media_type: string; data_base64: string }> | undefined,
    trace: Trace,
  ): Envelope {
    const record = this.client(clientId);
    const fr = record.locale === "fr";
    this.requireStage(record, ["existing_portfolio", "portfolio_review"], "portfolio.submit");
    record.turn += 1;
    const turn = record.turn;
    record.lastA2Turn = turn;

    const screening = screenMessage(text ?? "");
    trace.add({
      kind: "guardrail",
      actor: "guardrail",
      title: fr ? "Entrée vérifiée par le garde-fou" : "Input checked by the guardrail",
      detail:
        screening.masked > 0
          ? fr
            ? `${screening.masked} renseignement(s) personnel(s) masqué(s) avant l'analyse`
            : `${screening.masked} personal detail(s) masked before analysis`
          : fr
            ? "Aucun renseignement bancaire confidentiel détecté"
            : "No confidential banking detail detected",
      outputs: { masked: screening.masked, action: "NONE" },
      duration: 140,
    });
    trace.add({
      kind: "agent",
      actor: "A2",
      title: fr ? "A2 analyse le portefeuille fourni" : "A2 analyses the provided portfolio",
      detail: fr
        ? `${text?.trim() ? `${text.trim().length} caractères collés` : "aucun texte"}, ${files?.length ?? 0} fichier(s)`
        : `${text?.trim() ? `${text.trim().length} pasted characters` : "no text"}, ${files?.length ?? 0} file(s)`,
      inputs: {
        text_chars: text?.trim().length ?? 0,
        files: (files ?? []).map((file) => ({ name: file.name, media_type: file.media_type })),
      },
      duration: 220,
    });

    const extraction = extractPositions({ text: screening.text, files }, record.locale);
    for (const file of extraction.files) {
      trace.add({
        kind: "tool",
        actor: "A2",
        title: fr ? `Outil read_file : ${file.name}` : `Tool read_file: ${file.name}`,
        detail: file.readable
          ? fr
            ? `${file.lines} ligne(s) lues (${file.media_type})`
            : `${file.lines} line(s) read (${file.media_type})`
          : fr
            ? `Contenu binaire (${file.media_type}) : le simulateur ne le lit pas`
            : `Binary content (${file.media_type}): the simulator does not read it`,
        inputs: { name: file.name, media_type: file.media_type, bytes: file.bytes },
        outputs: { readable: file.readable, lines: file.lines },
        duration: 180,
      });
    }
    const resolved = extraction.positions.filter((position) => position.resolved);
    trace.add({
      kind: "tool",
      actor: "A2",
      title: fr ? "Outil resolve_securities : univers du jeu de départ" : "Tool resolve_securities: starter universe",
      detail: fr
        ? `${resolved.length} titre(s) reconnu(s), ${extraction.unresolved.length} élément(s) non résolu(s)`
        : `${resolved.length} security(ies) recognized, ${extraction.unresolved.length} unresolved item(s)`,
      inputs: { lines: extraction.lines },
      outputs: {
        resolved: resolved.map((position) => position.ticker),
        unresolved: extraction.unresolved.map((item) => item.raw),
      },
      sources: [STARTER_SOURCES.universe],
      duration: 260,
    });
    if (resolved.length > 0) {
      trace.add({
        kind: "tool",
        actor: "A2",
        title: fr ? "Outil get_prices : derniers cours de clôture" : "Tool get_prices: last closing prices",
        detail: fr ? "Cours du 2026-11-12, devise de cotation" : "Prices of 2026-11-12, listing currency",
        outputs: Object.fromEntries(resolved.map((position) => [position.ticker ?? position.id, position.price])),
        sources: [STARTER_SOURCES.prices],
        duration: 190,
      });
    }
    if (extraction.positions.some((position) => position.currency === "USD")) {
      trace.add({
        kind: "tool",
        actor: "A2",
        title: fr ? "Outil get_fx : USD/CAD" : "Tool get_fx: USD/CAD",
        detail: fr ? "1 USD = 1,4255 CAD le 2026-11-12" : "1 USD = 1.4255 CAD on 2026-11-12",
        outputs: { usdcad: 1.4255, date: "2026-11-12" },
        sources: [STARTER_SOURCES.fx],
        duration: 120,
      });
    }

    const exposures = computeExposures(extraction.positions, extraction.unresolved.filter((item) => !item.position_id).length);
    const level = this.level(record);
    const message = composeA2Message({
      level,
      positions: resolved.length,
      unresolved: extraction.unresolved.map((item) => item.raw),
      exposures,
      usesUsd: extraction.positions.some((position) => position.currency === "USD"),
    });
    trace.message(tr(message, record.locale), 1_400);
    trace.add({
      kind: "model",
      actor: "A2",
      title: fr ? "Modèle Bedrock : synthèse pour l'investisseur" : "Bedrock model: summary for the investor",
      detail: fr
        ? `Rédaction au niveau ${level ?? "beginner"}; le modèle ne calcule aucun chiffre`
        : `Written at ${level ?? "beginner"} level; the model computes no figure`,
      inputs: { model_id: MODEL_ID, simulated: true, knowledge_level: level },
      outputs: { message_chars: tr(message, record.locale).length },
      duration: 1_450,
    });
    trace.add({
      kind: "deterministic",
      actor: "A2",
      title: fr ? "Expositions calculées par le code" : "Exposures computed by code",
      detail: fr
        ? `Total ${exposures.total_value_cad.toLocaleString("fr-CA")} $ CA; signaux : ${exposures.flags.join(", ") || "aucun"}`
        : `Total CAD ${exposures.total_value_cad.toLocaleString("en-CA")}; flags: ${exposures.flags.join(", ") || "none"}`,
      outputs: { total_value_cad: exposures.total_value_cad, flags: exposures.flags },
      sources: portfolioSources(extraction.positions),
      duration: 4,
    });

    record.portfolio = {
      positions: extraction.positions,
      unresolved: extraction.unresolved,
      fx: fxRate(),
      exposures,
      status: "draft",
      sources: portfolioSources(extraction.positions),
    };
    record.message = message;
    this.setStage(record, "portfolio_review", `a2:${turn}`, trace.now, "positions proposées par A2");
    this.setFact(
      record,
      "context.portfolio_draft",
      { positions: extraction.positions.length, total_value_cad: exposures.total_value_cad },
      `a2:${turn}`,
      trace.now,
    );
    this.writeClientDocs(record, trace, "portfolio.submit");
    return this.state(record, trace, record.locale);
  }

  private portfolioConfirm(clientId: string, positions: PositionInput[], trace: Trace): Envelope {
    const record = this.client(clientId);
    const fr = record.locale === "fr";
    this.requireStage(record, ["portfolio_review"], "portfolio.confirm");
    const normalized = positions.map((position) => normalizeConfirmed(position, record.locale));
    trace.add({
      kind: "deterministic",
      actor: "A2",
      title: fr ? "Positions corrigées relues par le code" : "Corrected positions re-read by code",
      detail: fr
        ? `${normalized.length} ${normalized.length > 1 ? "positions" : "position"}, ${normalized.filter((position) => !position.resolved).length} hors du jeu de départ`
        : `${normalized.length} ${normalized.length === 1 ? "position" : "positions"}, ${normalized.filter((position) => !position.resolved).length} outside the starter universe`,
      inputs: { positions: positions.length },
      outputs: { tickers: normalized.map((position) => position.ticker) },
      sources: [STARTER_SOURCES.universe, STARTER_SOURCES.prices],
      duration: 6,
    });
    const exposures = computeExposures(normalized);
    trace.add({
      kind: "deterministic",
      actor: "A2",
      title: fr ? "Expositions calculées par le code" : "Exposures computed by code",
      detail: fr
        ? `Par classe d'actifs, devise, marché et secteur; total ${exposures.total_value_cad.toLocaleString("fr-CA")} $ CA`
        : `By asset class, currency, market and sector; total CAD ${exposures.total_value_cad.toLocaleString("en-CA")}`,
      outputs: { by_asset_class: exposures.by_asset_class, flags: exposures.flags },
      sources: portfolioSources(normalized),
      duration: 5,
    });
    record.portfolio = {
      positions: normalized,
      unresolved: normalized
        .filter((position) => !(typeof position.value_cad === "number" && position.value_cad > 0))
        .map((position) => ({
          raw: position.raw ?? position.ticker ?? position.id,
          reason: fr ? "position sans valeur : ni cours ni valeur déclarée" : "position without a value: no price and no declared value",
          position_id: position.id,
        })),
      fx: fxRate(),
      exposures,
      status: "confirmed",
      sources: portfolioSources(normalized),
    };
    this.setFact(
      record,
      "context.existing_portfolio",
      { positions: normalized.length, total_value_cad: exposures.total_value_cad, flags: exposures.flags },
      `a2:${Math.max(1, record.lastA2Turn)}`,
      trace.now,
    );
    this.setStage(record, "followups", `a2:${Math.max(1, record.lastA2Turn)}`, trace.now, "positions confirmées");
    record.message = null;
    record.pendingA1 = [];
    const at = trace.now;
    const key = `clients/${record.id}/portefeuille-existant.md`;
    record.docs.set(key, this.portfolioDoc(record, at));
    trace.add({
      kind: "storage",
      actor: "store",
      title: fr ? "Portefeuille existant écrit" : "Existing portfolio written",
      detail: key,
      outputs: { key },
      duration: 11,
    });
    this.writeClientDocs(record, trace, "portfolio.confirm");
    return this.state(record, trace, record.locale);
  }

  private portfolioSkip(clientId: string, trace: Trace): Envelope {
    const record = this.client(clientId);
    const fr = record.locale === "fr";
    this.requireStage(record, ["existing_portfolio"], "portfolio.skip");
    this.setStage(record, "followups", "base:q_has_portfolio", trace.now, "portefeuille passé");
    record.message = null;
    trace.add({
      kind: "deterministic",
      actor: "questionnaire",
      title: fr ? "Portefeuille existant passé" : "Existing portfolio skipped",
      detail: fr ? "Étape followups sans portefeuille : le champ reste manquant" : "Followups stage without a portfolio: the field stays missing",
      outputs: { stage: "followups" },
      duration: 1,
    });
    this.writeClientDocs(record, trace, "portfolio.skip");
    return this.state(record, trace, record.locale);
  }

  /* ------------------------------ follow-ups --------------------------- */

  private followupReply(
    clientId: string,
    answers: Array<{ question_id: string; value: AnswerValue }>,
    message: string | undefined,
    stop: boolean,
    trace: Trace,
  ): Envelope {
    const record = this.client(clientId);
    const locale = record.locale;
    const fr = locale === "fr";
    this.requireStage(record, ["followups", "complete"], "followup.reply");

    // Validate every answer before anything is written.
    const level = this.level(record);
    const accepted: Array<{ def: QuestionDef; value: AnswerValue; questionId: string }> = [];
    for (const answer of answers) {
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
      const checked = validateAnswer(renderQuestion(def, locale, level), answer.value);
      if (!checked.ok) throw new MockError("invalid_answer", checked.reason, checked.details);
      accepted.push({ def, value: checked.value, questionId: answer.question_id });
    }

    const text = message?.trim() ?? "";
    const screening = text ? screenMessage(text) : null;
    if (screening?.transactionRequest) {
      trace.add({
        kind: "guardrail",
        actor: "guardrail",
        title: fr ? "Demande de transaction bloquée" : "Transaction request blocked",
        detail: fr ? "Sujet interdit par le cadre responsable : aucune transaction réelle" : "Denied topic under the responsible framework: no real transaction",
        inputs: { message_chars: text.length },
        outputs: { action: "BLOCKED", policy: "no-real-transaction" },
        duration: 150,
      });
      throw new MockError(
        "guardrail_blocked",
        {
          fr: "AlphaForge AI est une simulation : il ne passe aucun ordre et n'exécute aucune transaction. Reformulez votre message sur votre profil.",
          en: "AlphaForge AI is a simulation: it places no order and executes no transaction. Please rephrase your message about your profile.",
        },
        { policy: "no-real-transaction" },
      );
    }
    const currentValues = new Map([...record.values].map(([key, fact]) => [key, fact.value]));
    const extracted: ExtractedFact[] = screening ? extractFacts(screening.text, currentValues) : [];
    const wasComplete = record.stage === "complete";

    // `stop` is accepted only from the threshold, counting this turn's answers.
    if (stop) {
      const preview: FieldValues = new Map(record.values);
      for (const { def, value } of accepted) preview.set(def.field, { field: def.field, value, provenance: "preview", at: trace.now });
      for (const fact of extracted) preview.set(fact.field, { field: fact.field, value: fact.value, provenance: "preview", at: trace.now });
      const projected = completeness(preview, locale);
      if (!projected.ready) {
        throw new MockError(
          "conflict",
          {
            fr: `Vous pourrez vous arrêter dès ${formatPercent(projected.threshold, locale)} de complétude (actuellement ${formatPercent(projected.score, locale)}).`,
            en: `You can stop from ${formatPercent(projected.threshold, locale)} completeness (currently ${formatPercent(projected.score, locale)}).`,
          },
          { score: projected.score, threshold: projected.threshold },
        );
      }
    }

    record.turn += 1;
    const turn = record.turn;
    const provenance = `a1:${turn}`;
    const firstTurn = record.a1Turns === 0;
    record.a1Turns += 1;
    const before = completeness(record.values, locale);

    if (screening) {
      trace.add({
        kind: "guardrail",
        actor: "guardrail",
        title: screening.adviceRequest
          ? fr
            ? "Demande de conseil personnalisé détectée"
            : "Personalized advice request detected"
          : fr
            ? "Message vérifié par le garde-fou"
            : "Message checked by the guardrail",
        detail: screening.adviceRequest
          ? fr
            ? "A1 répond dans le cadre responsable : information générale, aucune recommandation d'achat ou de vente"
            : "A1 answers within the responsible framework: general information, no buy or sell recommendation"
          : screening.masked > 0
            ? fr
              ? `${screening.masked} renseignement(s) personnel(s) masqué(s)`
              : `${screening.masked} personal detail(s) masked`
            : fr
              ? "Aucun sujet interdit, aucun renseignement personnel"
              : "No denied topic, no personal detail",
        inputs: { message_chars: text.length },
        outputs: { masked: screening.masked, advice_request: screening.adviceRequest, action: screening.adviceRequest ? "INTERVENED" : "NONE" },
        duration: 160,
      });
    }
    trace.add({
      kind: "agent",
      actor: "A1",
      title: fr ? "A1 lit le profil et la réponse de l'investisseur" : "A1 reads the profile and the investor's reply",
      detail: fr
        ? `${accepted.length} réponse(s) structurée(s)${text ? ", un message libre" : ""}${stop ? ", demande d'arrêt" : ""}`
        : `${accepted.length} structured answer(s)${text ? ", one free-text message" : ""}${stop ? ", stop request" : ""}`,
      inputs: { answers: accepted.map(({ questionId }) => questionId), message: Boolean(text), stop, turn },
      duration: 210,
    });
    if (screening?.offTopic) {
      trace.add({
        kind: "agent",
        actor: "A1",
        title: fr ? "Message hors sujet : A1 recentre l'échange" : "Off-topic message: A1 refocuses",
        detail: fr ? "A1 ne s'écarte pas du profil d'investisseur" : "A1 does not stray from the investor profile",
        duration: 40,
      });
    }

    if (screening) {
      // Written only once the input guardrail has passed (a blocked message throws above).
      record.entries.push({ at: trace.now, kind: "message", provenance, text: screening.text, locale });
    }

    const written: Array<{ field: string; value: unknown; provenance: string }> = [];
    const notes: L[] = [];
    for (const { def, value, questionId } of accepted) {
      this.setFact(record, def.field, value, provenance, trace.now, questionId);
      written.push({ field: def.field, value, provenance });
    }
    for (const fact of extracted) {
      this.setFact(record, fact.field, fact.value, provenance, trace.now);
      written.push({ field: fact.field, value: fact.value, provenance });
      notes.push(fact.note);
    }
    if (written.length > 0) {
      trace.add({
        kind: "tool",
        actor: "A1",
        title: fr ? `Outil update-KB : ${written.length} fait(s) enregistré(s)` : `Tool update-KB: ${written.length} fact(s) saved`,
        detail: written.map((fact) => fact.field).join(", "),
        inputs: { provenance },
        outputs: { facts: written },
        duration: 120,
      });
    }

    const after = completeness(record.values, locale);
    trace.add({
      kind: "deterministic",
      actor: "completeness",
      title: fr ? "Complétude recalculée par le code" : "Completeness recomputed by code",
      detail: `${formatPercent(before.score, locale)} → ${formatPercent(after.score, locale)} (${fr ? "seuil" : "threshold"} ${formatPercent(after.threshold, locale)}, ${fr ? "plafond" : "cap"} ${formatPercent(after.cap, locale)})`,
      outputs: { score: after.score, displayed: after.displayed, ready: after.ready, missing: after.missing.map((item) => item.field) },
      duration: 2,
    });

    // A1 picks its next follow-ups among the missing fields, heaviest first.
    for (const { def } of record.pendingA1) record.askedCount[def] = (record.askedCount[def] ?? 0) + 1;
    const candidates = A1_QUESTIONS.filter((def) => !isFieldKnown(record.values, def.field) && (record.askedCount[def.id] ?? 0) < 2).sort(
      (a, b) => (fieldDef(b.field)?.weight ?? 0) - (fieldDef(a.field)?.weight ?? 0),
    );
    const nextQuestions = stop ? [] : candidates.slice(0, MAX_A1_QUESTIONS);
    const nextPending = nextQuestions.map((def, index) => ({ id: `a1_${turn}_${index + 1}`, def: def.id }));
    // From `complete`, a reply reopens the follow-ups (CONTRACTS.md 3.1); A1 closes them again later.
    const complete = stop || (!wasComplete && nextQuestions.length === 0 && after.ready);
    trace.add({
      kind: "tool",
      actor: "A1",
      title: fr ? "Outil check_completed" : "Tool check_completed",
      detail: complete
        ? stop
          ? fr
            ? "L'investisseur s'arrête au-dessus du seuil"
            : "The investor stops above the threshold"
          : fr
            ? "Plus de relance utile : profil complet"
            : "No useful follow-up left: profile complete"
        : fr
          ? `${nextQuestions.length} relance(s) utile(s) sur ${after.missing.length} champ(s) manquant(s)`
          : `${nextQuestions.length} useful follow-up(s) for ${after.missing.length} missing field(s)`,
      outputs: { complete, ready: after.ready, next: nextPending.map((item) => item.id) },
      duration: 30,
    });

    const reply = composeA1Message({
      level,
      notes,
      score: after.score,
      displayed: after.displayed,
      ready: after.ready,
      questions: nextQuestions,
      missingLabels: nextQuestions.map((def) => fieldDef(def.field)?.label ?? { fr: def.field, en: def.field }),
      adviceRequest: screening?.adviceRequest ?? false,
      offTopic: screening?.offTopic ?? false,
      outcome: stop ? "stopped" : complete ? "complete" : nextQuestions.length === 0 ? "idle" : "ask",
      firstTurn,
    });
    trace.message(tr(reply, locale), 1_600);
    trace.add({
      kind: "model",
      actor: "A1",
      title: fr ? "Modèle Bedrock : relance rédigée" : "Bedrock model: follow-up written",
      detail: fr
        ? `${nextQuestions.length} question(s) formulée(s) au niveau ${level ?? "beginner"}, sans s'écarter du profil`
        : `${nextQuestions.length} question(s) phrased at ${level ?? "beginner"} level, staying on the profile`,
      inputs: { model_id: MODEL_ID, simulated: true, knowledge_level: level, missing: after.missing.slice(0, 5).map((item) => item.field) },
      outputs: { questions: nextPending.map((item) => item.id), message_chars: tr(reply, locale).length },
      duration: 1_650,
    });
    trace.add({
      kind: "guardrail",
      actor: "guardrail",
      title: fr ? "Réponse vérifiée par le garde-fou" : "Reply checked by the guardrail",
      detail: fr ? "Aucun conseil personnalisé, aucune transaction" : "No personalized advice, no transaction",
      outputs: { action: "NONE" },
      duration: 130,
    });

    record.pendingA1 = nextPending;
    this.setStage(
      record,
      complete ? "complete" : "followups",
      provenance,
      trace.now,
      stop ? "arrêt demandé par l'investisseur" : complete ? "A1 juge le profil complet" : "relances d'A1",
    );
    record.message = reply;
    this.writeClientDocs(record, trace, "followup.reply");
    return this.state(record, trace, locale);
  }

  /* ------------------------------- settings ---------------------------- */

  private settingsUpdate(clientId: string, locale: Locale | undefined, level: KnowledgeLevel | undefined, trace: Trace): Envelope {
    const record = this.client(clientId);
    const changes: Record<string, unknown> = {};
    if (locale && locale !== record.locale) {
      record.locale = locale;
      changes.locale = locale;
    }
    const fr = record.locale === "fr";
    if (level && level !== this.level(record)) {
      this.setFact(record, "knowledge.level", level, "settings", trace.now);
      changes.knowledge_level = level;
    }
    trace.add({
      kind: "deterministic",
      actor: "questionnaire",
      title: fr ? "Réglages mis à jour" : "Settings updated",
      detail: Object.keys(changes).length
        ? Object.entries(changes)
            .map(([key, value]) => `${key} = ${String(value)}`)
            .join(", ")
        : fr
          ? "Aucun changement"
          : "No change",
      inputs: { locale: locale ?? null, knowledge_level: level ?? null },
      outputs: changes,
      duration: 2,
    });
    if (Object.keys(changes).length > 0) this.writeClientDocs(record, trace, "settings.update");
    return this.state(record, trace, record.locale);
  }

  /* ----------------------------- knowledge base ------------------------ */

  private kbList(prefix: string, clientId: string | undefined): KbItem[] {
    if (prefix === "general/") {
      return [...this.general.values()]
        .sort((a, b) => a.key.localeCompare(b.key))
        .map((doc) => ({ key: doc.key, title: doc.title, type: doc.type, description: doc.description, updated_at: doc.updated_at }));
    }
    const record = this.client(clientId ?? prefix.split("/")[1] ?? "");
    if (!prefix.startsWith(`clients/${record.id}/`)) {
      throw new MockError("not_found", { fr: "Préfixe inconnu.", en: "Unknown prefix." }, { prefix });
    }
    return [...record.docs.values()]
      .sort((a, b) => a.key.localeCompare(b.key))
      .map((doc) => ({ key: doc.key, title: doc.title, type: doc.type, description: doc.description, updated_at: doc.updated_at }));
  }

  private kbGet(key: string, clientId: string | undefined): { key: string; content: string } {
    if (key.startsWith("general/")) {
      const doc = this.general.get(key);
      if (!doc) throw new MockError("not_found", { fr: "Document introuvable.", en: "Document not found." }, { key });
      return { key, content: doc.content };
    }
    const owner = key.split("/")[1] ?? "";
    if (!clientId || clientId.toLowerCase() !== owner.toLowerCase()) {
      throw new MockError("not_found", { fr: "Document introuvable.", en: "Document not found." }, { key });
    }
    const doc = this.client(owner).docs.get(key);
    if (!doc) throw new MockError("not_found", { fr: "Document introuvable.", en: "Document not found." }, { key });
    return { key, content: doc.content };
  }

  /* ------------------------------ rendering ---------------------------- */

  private state(record: ClientRecord, trace: Trace, locale: Locale): Envelope {
    const level = this.level(record);
    let questions: Question[] = [];
    if (record.stage === "base_questions" && record.pendingBase) {
      const def = baseQuestion(record.pendingBase);
      if (def) questions = [renderQuestion(def, locale, level)];
    } else if (record.stage === "followups") {
      questions = record.pendingA1.flatMap(({ id, def }) => {
        const found = a1Question(def);
        return found ? [{ ...renderQuestion(found, locale, level), id }] : [];
      });
    }
    const state: ClientState = {
      ok: true,
      release: MOCK_RELEASE,
      client_id: record.id,
      locale,
      stage: record.stage,
      message: record.message ? tr(record.message, locale) : null,
      questions,
      profile: {
        knowledge_level: level,
        effective_risk: effectiveRisk(record.values),
        risk: riskDetail(record.values),
        dimensions: dimensionViews(record.values, locale),
        facts: [...record.values.values()]
          .filter((fact) => fact.field !== "context.portfolio_draft")
          .sort((a, b) => a.at.localeCompare(b.at))
          .map((fact) => ({ ...fact })),
      },
      completeness: completeness(record.values, locale),
      portfolio: record.portfolio,
      trace: trace.steps,
    };
    return state as unknown as Envelope;
  }

  private writeClientDocs(record: ClientRecord, trace: Trace, action: string): void {
    const fr = record.locale === "fr";
    const at = trace.now;
    const base = `clients/${record.id}/`;
    record.docs.set(`${base}profil.md`, this.profileDoc(record, at));
    record.docs.set(`${base}journal.md`, this.journalDoc(record, at));
    const stamp = at.replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
    const traceKey = `${base}traces/${stamp}-${action}.json`;
    const keys = [`${base}profil.md`, `${base}journal.md`, traceKey];
    trace.add({
      kind: "storage",
      actor: "store",
      title: fr ? "Base du client mise à jour" : "Client base updated",
      detail: fr ? `profil.md, journal.md et la trace de ${action}` : `profil.md, journal.md and the ${action} trace`,
      outputs: { keys },
      duration: 12,
    });
    record.docs.set(traceKey, {
      key: traceKey,
      title: fr ? `Trace : ${action}` : `Trace: ${action}`,
      type: "Trace",
      description: fr ? `${trace.steps.length} étapes` : `${trace.steps.length} steps`,
      updated_at: at,
      content: JSON.stringify({ action, at, steps: trace.steps }, null, 2),
    });
    record.docs.set(`${base}index.md`, this.indexDoc(record, at));
  }

  private profileSources(record: ClientRecord): Source[] {
    const seen = new Set<string>();
    const sources: Source[] = [];
    for (const fact of record.entries) {
      if (seen.has(fact.provenance)) continue;
      seen.add(fact.provenance);
      const [kind, ref] = fact.provenance.split(":");
      const title =
        kind === "base"
          ? `Réponse à ${ref}`
          : kind === "a1"
            ? `Relance A1, tour ${ref}`
            : kind === "a2"
              ? `Analyse A2, tour ${ref}`
              : "Réglages de l'investisseur";
      sources.push({ id: fact.provenance.replace(":", "-"), title, resource: fact.provenance, retrieved_at: fact.at });
    }
    return sources;
  }

  private profileDoc(record: ClientRecord, at: string): StoredDoc {
    const locale = record.locale;
    const fr = locale === "fr";
    const result = completeness(record.values, locale);
    const dims = dimensionViews(record.values, locale);
    const level = this.level(record);
    const statusWord = (status: string) =>
      fr ? ({ known: "connue", partial: "partielle", missing: "manquante" }[status] ?? status) : status;
    const rows = Object.entries(dims)
      .map(([key, view]) => `| ${key} | ${statusWord(view.status)} | ${view.summary ?? "—"} |`)
      .join("\n");
    const facts = [...record.values.values()]
      .map((fact) => `| ${fact.field} | ${JSON.stringify(fact.value)} | ${fact.provenance} | ${fact.at} |`)
      .join("\n");
    const body = `# ${fr ? "Profil investisseur" : "Investor profile"}

${fr ? "Complétude" : "Completeness"} : **${formatPercent(result.displayed, locale)}** (${fr ? "seuil" : "threshold"} ${formatPercent(result.threshold, locale)}, ${fr ? "plafond" : "cap"} ${formatPercent(result.cap, locale)}). ${fr ? "Niveau de connaissances" : "Knowledge level"} : ${level ?? "—"}. ${fr ? "Risque effectif" : "Effective risk"} : ${effectiveRisk(record.values) ?? "—"}.

| Dimension | ${fr ? "Statut" : "Status"} | ${fr ? "Résumé" : "Summary"} |
| --- | --- | --- |
${rows}

## ${fr ? "Faits et provenance" : "Facts and provenance"}

| ${fr ? "Champ" : "Field"} | ${fr ? "Valeur" : "Value"} | Provenance | Date |
| --- | --- | --- | --- |
${facts || "| — | — | — | — |"}

## ${fr ? "Ce qui manque" : "Missing"}

${result.missing.map((item) => `- ${item.label} (${item.dimension})`).join("\n") || (fr ? "- Rien" : "- Nothing")}`;
    return okfDocument(
      `clients/${record.id}/profil.md`,
      {
        type: "Investor Profile",
        title: fr ? "Profil investisseur" : "Investor profile",
        description: fr
          ? "Profil en cinq dimensions, niveau de connaissances et complétude."
          : "Five-dimension profile, knowledge level and completeness.",
        tags: ["profil-investisseur"],
        status: record.stage === "complete" ? "stable" : "draft",
        owners: ["alphaforge-a1"],
        sensitivity: "client",
        generated: { by: record.a1Turns > 0 ? "agent:A1" : "code:questionnaire", at },
        stale_after: staleAfter(at),
        sources: this.profileSources(record),
        data: {
          stage: record.stage,
          knowledge_level: level,
          effective_risk: effectiveRisk(record.values),
          completeness: { score: result.score, displayed: result.displayed },
          dimensions: Object.fromEntries(Object.entries(dims).map(([key, view]) => [key, view.fields])),
        },
      },
      body,
    );
  }

  private journalDoc(record: ClientRecord, at: string): StoredDoc {
    const fr = record.locale === "fr";
    const lines = record.entries.map((entry) => {
      const head = `- \`${entry.at}\` · **${entry.provenance}** ·`;
      if (entry.kind === "answer") {
        const previous = "previous" in entry ? ` (${fr ? "avant" : "was"} ${JSON.stringify(entry.previous)})` : "";
        return `${head} ${entry.field} = ${JSON.stringify(entry.value)}${previous}`;
      }
      if (entry.kind === "message") return `${head} ${fr ? "message" : "message"} : « ${entry.text} »`;
      return `${head} ${fr ? "étape" : "stage"} ${entry.previous ?? "—"} → ${entry.value} (${entry.note})`;
    });
    return okfDocument(
      `clients/${record.id}/journal.md`,
      {
        type: "Profile Journal",
        title: fr ? "Journal du profil" : "Profile journal",
        description: fr ? "Chaque réponse, avec sa provenance et sa date." : "Every answer, with its provenance and date.",
        tags: ["profil-investisseur"],
        status: "draft",
        owners: ["alphaforge-a1"],
        sensitivity: "client",
        generated: { by: "code:store", at },
        stale_after: staleAfter(at),
        sources: this.profileSources(record),
        data: { entries: record.entries },
      },
      `# ${fr ? "Journal du profil" : "Profile journal"}\n\n${lines.join("\n") || (fr ? "Aucune réponse pour l'instant." : "No answer yet.")}`,
    );
  }

  private portfolioDoc(record: ClientRecord, at: string): StoredDoc {
    const fr = record.locale === "fr";
    const portfolio = record.portfolio;
    const rows = (portfolio?.positions ?? [])
      .map(
        (position) =>
          `| ${position.ticker ?? "—"} | ${position.name ?? "—"} | ${position.quantity ?? "—"} | ${position.currency ?? "—"} | ${position.account_type ?? "—"} | ${position.value_cad ?? "—"} |`,
      )
      .join("\n");
    const exposures = portfolio?.exposures;
    const shares = (record_: Record<string, number> | undefined) =>
      Object.entries(record_ ?? {})
        .map(([name, share]) => `${name} ${formatPercent(share, record.locale)}`)
        .join(", ");
    return okfDocument(
      `clients/${record.id}/portefeuille-existant.md`,
      {
        type: "Existing Portfolio",
        title: fr ? "Portefeuille existant" : "Existing portfolio",
        description: fr
          ? "Positions confirmées par l'investisseur et expositions calculées par le code."
          : "Positions confirmed by the investor and exposures computed by code.",
        tags: ["construction-portefeuille", "profil-investisseur"],
        status: "stable",
        owners: ["alphaforge-a2"],
        sensitivity: "client",
        generated: { by: "agent:A2", at },
        stale_after: staleAfter(at, 1),
        sources: portfolio?.sources ?? [],
        data: { positions: portfolio?.positions ?? [], exposures: exposures ?? null },
      },
      `# ${fr ? "Portefeuille existant" : "Existing portfolio"}

| Ticker | ${fr ? "Nom" : "Name"} | ${fr ? "Quantité" : "Quantity"} | ${fr ? "Devise" : "Currency"} | ${fr ? "Compte" : "Account"} | ${fr ? "Valeur (CAD)" : "Value (CAD)"} |
| --- | --- | --- | --- | --- | --- |
${rows || "| — | — | — | — | — | — |"}

- ${fr ? "Valeur totale" : "Total value"} : ${exposures?.total_value_cad ?? 0} CAD
- ${fr ? "Classes d'actifs" : "Asset classes"} : ${shares(exposures?.by_asset_class)}
- ${fr ? "Devises" : "Currencies"} : ${shares(exposures?.by_currency)}
- ${fr ? "Marchés" : "Markets"} : ${shares(exposures?.by_market)}
- ${fr ? "Secteurs" : "Sectors"} : ${shares(exposures?.by_sector)}
- ${fr ? "Signaux" : "Flags"} : ${exposures?.flags.join(", ") || "—"}`,
    );
  }

  private indexDoc(record: ClientRecord, at: string): StoredDoc {
    const fr = record.locale === "fr";
    const docs = [...record.docs.values()].filter((doc) => doc.key.endsWith(".md") && !doc.key.endsWith("/index.md"));
    const traces = [...record.docs.keys()].filter((key) => key.includes("/traces/")).length;
    return okfDocument(
      `clients/${record.id}/index.md`,
      {
        type: "Index",
        title: fr ? "Base du client" : "Client base",
        description: fr ? "Documents OKF propres à cet investisseur." : "OKF documents of this investor.",
        tags: ["index"],
        status: "draft",
        owners: ["alphaforge-a1"],
        sensitivity: "client",
        generated: { by: "code:store", at },
        stale_after: staleAfter(at),
        sources: [],
        data: { documents: docs.length, traces },
      },
      `# ${fr ? "Base du client" : "Client base"}

${docs.map((doc) => `- [${doc.title}](${doc.key.split("/").pop()}) : ${doc.description}`).join("\n")}
- ${fr ? `${traces} trace(s) d'exécution dans` : `${traces} execution trace(s) in`} \`traces/\``,
    );
  }
}

const globalForMock = globalThis as unknown as { __alphaforgeMock?: MockRuntime };

/** One simulator per server process, kept across hot reloads in development. */
export function getMockRuntime(): MockRuntime {
  globalForMock.__alphaforgeMock ??= new MockRuntime();
  return globalForMock.__alphaforgeMock;
}
