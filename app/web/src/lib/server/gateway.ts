import "server-only";
import { randomUUID } from "node:crypto";
import { PortfolioBuildRequest } from "@/lib/contract/portfolio";
import { AGENT_ACTIONS, AgentRequest, CollectRequest, MAX_BODY_BYTES, UPLOAD_LIMITS } from "@/lib/contract/requests";
import { HealthResponse, type GatewayHealth, type Locale } from "@/lib/contract/schemas";
import { mockPortfolioBuild } from "@/lib/mock/decisions";
import { getMockRuntime } from "@/lib/mock/runtime";
import {
  describeExecution,
  invokeAws,
  invokePortfolioAws,
  listExecutions,
  resolveProfileRuntime,
  startExecution,
  stateMachineInfo,
} from "./aws";
import { bindAgentBody, bindPortfolioBody, identityOf, requireAdmin, type Identity } from "./auth/guard";
import { ConfigError, getConfig, profileRuntimeName, type AgentMode, type GatewayConfig } from "./config";
import { GatewayError, jsonResponse, localeOf, statusOfEnvelope, toGatewayError } from "./errors";
import { withHeartbeat } from "./heartbeat";
import { invokeLocal } from "./local";
import { sseResponse, sseStreamOf, type Upstream } from "./upstream";

export function configOrThrow(): GatewayConfig {
  try {
    return getConfig();
  } catch (error) {
    if (error instanceof ConfigError) {
      throw new GatewayError(
        "internal",
        {
          fr: `Configuration invalide dans app/web/.env.local : ${error.issues.map((issue) => issue.variable).join(", ")}`,
          en: `Invalid configuration in app/web/.env.local: ${error.issues.map((issue) => issue.variable).join(", ")}`,
        },
        500,
        { issues: error.issues },
      );
    }
    throw error;
  }
}

function errorResponse(error: unknown, locale: Locale): Response {
  const gatewayError = toGatewayError(error);
  return jsonResponse(gatewayError.status, gatewayError.envelope(locale));
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * Read and validate a contract request; throws a GatewayError on any violation. In cognito mode the
 * client_id comes from the caller's session, never from the body (CONTRACTS.md 7.1).
 */
export async function readAgentRequest(request: Request, identity: Identity = { mode: "off" }): Promise<AgentRequest> {
  const length = Number(request.headers.get("content-length") ?? "0");
  if (length > MAX_BODY_BYTES) {
    throw new GatewayError(
      "bad_request",
      {
        fr: `Requête trop volumineuse : ${UPLOAD_LIMITS.maxFiles} fichiers de 10 Mo au plus.`,
        en: `Request too large: at most ${UPLOAD_LIMITS.maxFiles} files of 10 MB.`,
      },
      413,
      { limit_bytes: MAX_BODY_BYTES, content_length: length },
    );
  }
  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    throw new GatewayError("bad_request", { fr: "Corps JSON invalide.", en: "Invalid JSON body." }, 400);
  }
  return validateAgentRequest(bindAgentBody(raw, identity));
}

export function validateAgentRequest(raw: unknown): AgentRequest {
  if (!isRecord(raw) || typeof raw.action !== "string") {
    throw new GatewayError("bad_request", { fr: "Le champ action est requis.", en: "The action field is required." }, 400);
  }
  if (!(AGENT_ACTIONS as readonly string[]).includes(raw.action)) {
    throw new GatewayError(
      "unknown_action",
      { fr: `Action inconnue : ${raw.action}`, en: `Unknown action: ${raw.action}` },
      400,
      { action: raw.action, allowed: AGENT_ACTIONS },
    );
  }
  if (Array.isArray(raw.files) && raw.files.length > UPLOAD_LIMITS.maxFiles) {
    throw new GatewayError(
      "bad_request",
      { fr: `Au plus ${UPLOAD_LIMITS.maxFiles} fichiers.`, en: `At most ${UPLOAD_LIMITS.maxFiles} files.` },
      400,
      { limit: UPLOAD_LIMITS.maxFiles, received: raw.files.length },
    );
  }
  const parsed = AgentRequest.safeParse(raw);
  if (!parsed.success) {
    const issues = parsed.error.issues.slice(0, 10).map((issue) => ({ path: issue.path.join("."), message: issue.message }));
    const tooLarge = issues.some((issue) => /limit is/.test(issue.message));
    throw new GatewayError(
      "bad_request",
      tooLarge
        ? { fr: "Un fichier dépasse 10 Mo.", en: "A file exceeds 10 MB." }
        : { fr: `Requête ${raw.action} invalide.`, en: `Invalid ${raw.action} request.` },
      400,
      { action: raw.action, issues },
    );
  }
  const valid = parsed.data;
  // The gateway names a new client itself, so the AgentCore session is the client from the first call.
  if (valid.action === "session.start" && !valid.client_id) return { ...valid, client_id: randomUUID() };
  return valid;
}

function wantsStream(request: AgentRequest): boolean {
  return (request.action === "portfolio.submit" || request.action === "followup.reply") && request.stream === true;
}

async function callRuntime(config: GatewayConfig, request: AgentRequest, stream: boolean, signal: AbortSignal): Promise<Upstream> {
  switch (config.AGENT_MODE) {
    case "mock": {
      const runtime = getMockRuntime();
      if (stream) return { kind: "stream", body: sseStreamOf(runtime.stream(request)) };
      const body = await runtime.handle(request);
      return { kind: "json", status: 200, body };
    }
    case "local":
      return invokeLocal(config.LOCAL_AGENT_URL, request, { stream, signal });
    case "aws":
      return invokeAws(config, request, stream, signal);
  }
}

/** `POST /api/agent`: validate, call the configured runtime, pass JSON or SSE through. */
export async function handleAgent(request: Request): Promise<Response> {
  const locale = localeOf(request);
  try {
    const identity = identityOf(request);
    const config = configOrThrow();
    const agentRequest = await readAgentRequest(request, identity);
    const upstream = await callRuntime(config, agentRequest, wantsStream(agentRequest), request.signal);
    if (upstream.kind === "stream") return sseResponse(upstream.body);
    if (!isRecord(upstream.body) || typeof upstream.body.ok !== "boolean") {
      throw new GatewayError(
        "internal",
        { fr: "Réponse du runtime hors contrat (enveloppe absente).", en: "Runtime response outside the contract (no envelope)." },
        502,
        { upstream_status: upstream.status, body: JSON.stringify(upstream.body).slice(0, 500) },
      );
    }
    return jsonResponse(statusOfEnvelope(upstream.body, upstream.status), upstream.body);
  } catch (error) {
    return errorResponse(error, locale);
  }
}

/* ------------------------------------------------------------------ */
/* Portfolio runtime (CONTRACTS.md 12)                                 */
/* ------------------------------------------------------------------ */

/** A build request is a few fields: anything larger is not one. */
const MAX_PORTFOLIO_BODY_BYTES = 16 * 1024;
/** A build in `llm` mode makes several model calls (A3, four lenses, two rounds). */
const PORTFOLIO_TIMEOUT_MS = 600_000;

export function validatePortfolioRequest(raw: unknown): PortfolioBuildRequest {
  if (!isRecord(raw)) {
    throw new GatewayError("bad_request", { fr: "Le corps doit être un objet JSON.", en: "The body must be a JSON object." }, 400);
  }
  if (raw.action !== undefined && raw.action !== "build") {
    throw new GatewayError(
      "unknown_action",
      { fr: `Action inconnue : ${String(raw.action)}`, en: `Unknown action: ${String(raw.action)}` },
      400,
      { action: raw.action, allowed: ["build"] },
    );
  }
  const parsed = PortfolioBuildRequest.safeParse(raw);
  if (!parsed.success) {
    throw new GatewayError("bad_request", { fr: "Requête build invalide.", en: "Invalid build request." }, 400, {
      action: "build",
      issues: parsed.error.issues.slice(0, 10).map((issue) => ({ path: issue.path.join("."), message: issue.message })),
    });
  }
  return parsed.data;
}

async function callPortfolio(config: GatewayConfig, request: PortfolioBuildRequest, locale: Locale, signal: AbortSignal): Promise<Upstream> {
  switch (config.AGENT_MODE) {
    case "mock":
      return { kind: "json", status: 200, body: mockPortfolioBuild(request, request.locale ?? locale) };
    case "local":
      return invokeLocal(config.LOCAL_PORTFOLIO_URL, request, { stream: false, signal, role: "portfolio", timeoutMs: PORTFOLIO_TIMEOUT_MS });
    case "aws":
      return invokePortfolioAws(config, request, signal);
  }
}

/** The runtime's envelope as the gateway's JSON answer, or a 502 if there is none. */
async function portfolioAnswer(config: GatewayConfig, build: PortfolioBuildRequest, locale: Locale, signal: AbortSignal): Promise<Response> {
  const upstream = await callPortfolio(config, build, locale, signal);
  if (upstream.kind === "stream" || !isRecord(upstream.body) || typeof upstream.body.ok !== "boolean") {
    throw new GatewayError(
      "internal",
      { fr: "Réponse du runtime portfolio hors contrat (enveloppe absente).", en: "Portfolio runtime response outside the contract (no envelope)." },
      502,
      upstream.kind === "json" ? { upstream_status: upstream.status, body: JSON.stringify(upstream.body).slice(0, 500) } : { kind: "stream" },
    );
  }
  return jsonResponse(statusOfEnvelope(upstream.body, upstream.status), upstream.body);
}

/**
 * `POST /api/portfolio`: validate a `build` request, call the `portfolio` runtime of the configured mode
 * (fixtures of the engine in `mock`), pass the JSON envelope through. The browser validates the Decision.
 * A build longer than `HEARTBEAT_AFTER_MS` (the `llm` mode, about 2 min) is answered by `withHeartbeat`:
 * CloudFront cuts an origin silent for 60 s (`infrastructure/infra/web.tf`).
 */
export async function handlePortfolio(request: Request): Promise<Response> {
  const locale = localeOf(request);
  try {
    const identity = identityOf(request);
    const config = configOrThrow();
    const length = Number(request.headers.get("content-length") ?? "0");
    if (length > MAX_PORTFOLIO_BODY_BYTES) {
      throw new GatewayError("bad_request", { fr: "Requête trop volumineuse.", en: "Request too large." }, 413, {
        limit_bytes: MAX_PORTFOLIO_BODY_BYTES,
        content_length: length,
      });
    }
    let raw: unknown;
    try {
      raw = await request.json();
    } catch {
      throw new GatewayError("bad_request", { fr: "Corps JSON invalide.", en: "Invalid JSON body." }, 400);
    }
    const build = validatePortfolioRequest(bindPortfolioBody(raw, identity));
    return await withHeartbeat(portfolioAnswer(config, build, locale, request.signal), {
      fallback: (error) => errorResponse(error, locale),
      signal: request.signal,
    });
  } catch (error) {
    return errorResponse(error, locale);
  }
}

/** The runtime's own `health` answer, checked against the contract. */
async function runtimeHealth(config: GatewayConfig, signal: AbortSignal): Promise<HealthResponse> {
  const upstream = await callRuntime(config, { action: "health" }, false, signal);
  if (upstream.kind !== "json") throw new GatewayError("internal", { fr: "Réponse inattendue.", en: "Unexpected response." }, 502);
  const parsed = HealthResponse.safeParse(upstream.body);
  if (!parsed.success) {
    throw new GatewayError(
      "internal",
      { fr: "Réponse health hors contrat.", en: "Health response outside the contract." },
      502,
      { body: JSON.stringify(upstream.body).slice(0, 300) },
    );
  }
  return parsed.data;
}

/** The health route always answers 200: a failure is reported in the body. */
function unhealthy(mode: AgentMode, runtime: GatewayHealth["runtime"], error: unknown, locale: Locale): Response {
  const gatewayError = toGatewayError(error);
  return jsonResponse(200, { ok: false, mode, agent: null, runtime, error: gatewayError.envelope(locale).error } satisfies GatewayHealth);
}

/** `GET /api/health`: gateway mode plus the runtime's own `health` answer. */
export async function handleHealth(request: Request): Promise<Response> {
  const locale = localeOf(request);
  let config: GatewayConfig;
  try {
    config = configOrThrow();
  } catch (error) {
    return unhealthy("mock", null, error, locale);
  }
  let runtime: GatewayHealth["runtime"] =
    config.AGENT_MODE === "aws" ? { name: profileRuntimeName(config), arn: null, status: null } : null;
  try {
    if (config.AGENT_MODE === "aws") {
      const info = await resolveProfileRuntime(config);
      runtime = { name: info.name, arn: info.arn, status: info.status };
    }
    const agent = await runtimeHealth(config, request.signal);
    return jsonResponse(200, { ok: true, mode: config.AGENT_MODE, agent, runtime, error: null } satisfies GatewayHealth);
  } catch (error) {
    return unhealthy(config.AGENT_MODE, runtime, error, locale);
  }
}

function collectUnavailable(): GatewayError {
  return new GatewayError(
    "bad_request",
    {
      fr: "La collecte passe par Step Functions : elle est simulée en mode mock et réelle en mode aws, mais indisponible en mode local.",
      en: "Collection runs on Step Functions: it is simulated in mock mode and real in aws mode, but unavailable in local mode.",
    },
    501,
    { mode: "local", available_in: ["mock", "aws"] },
  );
}

const EXECUTION_ARN = /^arn:aws[a-z-]*:states:[a-z0-9-]+:\d{12}:execution:[A-Za-z0-9_-]{1,80}:[A-Za-z0-9_-]{1,80}$/;

/** The simulator's executions, in mock mode. */
function mockCollection(executionArn: string | null): Response {
  const collector = getMockRuntime().collector;
  if (executionArn) {
    const execution = collector.describe(executionArn);
    if (!execution) throw new GatewayError("not_found", { fr: "Exécution introuvable.", en: "Execution not found." }, 404);
    return jsonResponse(200, { ok: true, execution });
  }
  return jsonResponse(200, { ok: true, state_machine: collector.stateMachine, executions: collector.list() });
}

/** The executions of the Step Functions machine, in aws mode. */
async function awsCollection(config: GatewayConfig, executionArn: string | null): Promise<Response> {
  if (executionArn) return jsonResponse(200, { ok: true, execution: await describeExecution(config, executionArn) });
  const [stateMachine, executions] = await Promise.all([stateMachineInfo(config), listExecutions(config)]);
  return jsonResponse(200, { ok: true, state_machine: stateMachine, executions });
}

/** `GET /api/collect`: recent executions, or one execution with `?execution_arn=` (any signed-in account). */
export async function handleCollectGet(request: Request): Promise<Response> {
  const locale = localeOf(request);
  try {
    identityOf(request);
    const config = configOrThrow();
    const executionArn = new URL(request.url).searchParams.get("execution_arn");
    if (executionArn !== null && !EXECUTION_ARN.test(executionArn)) {
      throw new GatewayError("bad_request", { fr: "ARN d'exécution invalide.", en: "Invalid execution ARN." }, 400);
    }
    if (config.AGENT_MODE === "local") throw collectUnavailable();
    if (config.AGENT_MODE === "mock") return mockCollection(executionArn);
    return await awsCollection(config, executionArn);
  } catch (error) {
    return errorResponse(error, locale);
  }
}

/** Read and validate the body of `POST /api/collect`; an empty body asks for a default run. */
async function readCollectRequest(request: Request): Promise<CollectRequest> {
  let raw: unknown = {};
  const text = await request.text();
  if (text.trim() !== "") {
    try {
      raw = JSON.parse(text);
    } catch {
      throw new GatewayError("bad_request", { fr: "Corps JSON invalide.", en: "Invalid JSON body." }, 400);
    }
  }
  const parsed = CollectRequest.safeParse(raw);
  if (!parsed.success) {
    throw new GatewayError("bad_request", { fr: "Paramètres de collecte invalides.", en: "Invalid collection parameters." }, 400, {
      issues: parsed.error.issues.map((issue) => ({ path: issue.path.join("."), message: issue.message })),
    });
  }
  const input = parsed.data;
  if (input.since && input.since > new Date().toISOString().slice(0, 10)) {
    throw new GatewayError("bad_request", { fr: "La date de début est dans le futur.", en: "The start date is in the future." }, 400);
  }
  return input;
}

/**
 * `POST /api/collect`: start a collection run (no name, no run_id: Step Functions uses a UUID).
 * In cognito mode, members of the `admin` group only.
 */
export async function handleCollectPost(request: Request): Promise<Response> {
  const locale = localeOf(request);
  try {
    requireAdmin(identityOf(request));
    const config = configOrThrow();
    const input = await readCollectRequest(request);
    if (config.AGENT_MODE === "local") throw collectUnavailable();
    const execution =
      config.AGENT_MODE === "mock" ? getMockRuntime().collector.start(input) : await startExecution(config, input);
    return jsonResponse(200, { ok: true, execution });
  } catch (error) {
    return errorResponse(error, locale);
  }
}
