/**
 * Browser-side calls to the local gateway. Every response is validated with the
 * contract's zod schemas; streamed responses are read event by event.
 */
import type { z } from "zod";
import { DeleteAccountResponse } from "@/lib/contract/auth";
import { PortfolioBuildResponse, type PortfolioBuildRequestInput } from "@/lib/contract/portfolio";
import type { AgentRequestInput, CollectRequest } from "@/lib/contract/requests";
import {
  ClientState,
  ErrorEnvelope,
  ExecutionDetailResponse,
  ExecutionListResponse,
  ExecutionStartResponse,
  GatewayHealth,
  KbGetResponse,
  KbListResponse,
  type Locale,
  type TraceStep,
} from "@/lib/contract/schemas";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { readAgentEvents, type DecodedEvent } from "@/lib/sse";
import { track } from "./activity";

export class ApiError extends Error {
  // eslint-disable-next-line max-params -- frozen public signature: callers build ApiError positionally.
  constructor(
    readonly code: string,
    message: string,
    readonly details?: unknown,
    readonly release?: string | null,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/** Anything a call threw, as an ApiError: an abort becomes `aborted`, any other failure `internal`. */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (isAbort(error)) return new ApiError("aborted", "Aborted");
  return new ApiError("internal", error instanceof Error ? error.message : String(error));
}

export interface CallOptions {
  locale: Locale;
  signal?: AbortSignal;
  messages: { network: string; invalidResponse: string; noResult: string };
}

/** The texts of a failed call, in the interface language. */
export function callMessages(t: Dictionary): CallOptions["messages"] {
  return { network: t.errors.network, invalidResponse: t.errors.invalidResponse, noResult: t.errors.noResult };
}

function issuesOf(error: z.ZodError) {
  return error.issues.slice(0, 8).map((issue) => ({ path: issue.path.join(".") || "(root)", message: issue.message }));
}

/** Throw the error envelope if it is one, else validate the success shape. */
export function parseEnvelope<T>(json: unknown, schema: z.ZodType<T>, options: Pick<CallOptions, "messages">, status?: number): T {
  const failure = ErrorEnvelope.safeParse(json);
  if (failure.success) {
    const { error, release } = failure.data;
    throw new ApiError(error.code, error.message, error.details, release, status);
  }
  const parsed = schema.safeParse(json);
  if (!parsed.success) {
    throw new ApiError("invalid_response", options.messages.invalidResponse, { issues: issuesOf(parsed.error) }, null, status);
  }
  return parsed.data;
}

async function send(path: string, init: RequestInit, options: CallOptions): Promise<Response> {
  try {
    return await fetch(path, {
      ...init,
      headers: { "content-type": "application/json", "x-alphaforge-locale": options.locale, ...init.headers },
      signal: options.signal,
      cache: "no-store",
    });
  } catch (error) {
    if (isAbort(error)) throw error;
    throw new ApiError("network_error", options.messages.network, { cause: String(error) });
  }
}

async function readJson(response: Response, options: CallOptions): Promise<unknown> {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch {
    throw new ApiError("invalid_response", options.messages.invalidResponse, { status: response.status, body: text.slice(0, 300) });
  }
}

export function callAgent<T>(request: AgentRequestInput, schema: z.ZodType<T>, options: CallOptions): Promise<T> {
  return track(
    (async () => {
      const response = await send("/api/agent", { method: "POST", body: JSON.stringify(request) }, options);
      return parseEnvelope(await readJson(response, options), schema, options, response.status);
    })(),
  );
}

export interface StreamHandlers {
  onTrace: (step: TraceStep) => void;
  onDelta: (text: string) => void;
}

/** An event outside the contract is skipped, unless it claims to be the result or an error: then the call fails. */
function skipOutsideContract(decoded: Extract<DecodedEvent, { ok: false }>, options: CallOptions): void {
  let type: unknown = null;
  try {
    type = (JSON.parse(decoded.raw) as { type?: unknown }).type;
  } catch {
    // not JSON at all
  }
  if (type === "result" || type === "error") {
    throw new ApiError("invalid_response", options.messages.invalidResponse, { reason: decoded.reason });
  }
  console.warn("Ignored a stream event outside the contract:", decoded.reason);
}

/** Pass trace and delta events to the handlers as they arrive; the last `result` event is the answer. */
async function readStreamedState(body: ReadableStream<Uint8Array>, handlers: StreamHandlers, options: CallOptions): Promise<ClientState> {
  let result: ClientState | null = null;
  for await (const decoded of readAgentEvents(body, options.signal)) {
    if (!decoded.ok) {
      skipOutsideContract(decoded, options);
      continue;
    }
    const event = decoded.event;
    if (event.type === "trace") handlers.onTrace(event.step);
    else if (event.type === "delta") handlers.onDelta(event.text);
    else if (event.type === "error") throw new ApiError(event.error.code, event.error.message, event.error.details);
    else result = event.result;
  }
  if (!result) throw new ApiError("invalid_response", options.messages.noResult);
  return result;
}

/** `stream: true` call: trace and delta events as they arrive, then the final ClientState. Busy until the stream ends. */
export function callAgentStream(request: AgentRequestInput, handlers: StreamHandlers, options: CallOptions): Promise<ClientState> {
  return track(streamAgent(request, handlers, options));
}

async function streamAgent(request: AgentRequestInput, handlers: StreamHandlers, options: CallOptions): Promise<ClientState> {
  const response = await send(
    "/api/agent",
    { method: "POST", body: JSON.stringify({ ...request, stream: true }), headers: { accept: "text/event-stream, application/json" } },
    options,
  );
  const type = response.headers.get("content-type") ?? "";
  if (!type.includes("text/event-stream") || !response.body) {
    // The runtime may answer in JSON even when asked to stream.
    return parseEnvelope(await readJson(response, options), ClientState, options, response.status);
  }
  return readStreamedState(response.body, handlers, options);
}

export function getHealth(options: CallOptions): Promise<GatewayHealth> {
  return track(
    (async () => {
      const response = await send("/api/health", { method: "GET" }, options);
      const parsed = GatewayHealth.safeParse(await readJson(response, options));
      if (!parsed.success) throw new ApiError("invalid_response", options.messages.invalidResponse, { issues: issuesOf(parsed.error) });
      return parsed.data;
    })(),
  );
}

export async function listKb(prefix: string, clientId: string | null, options: CallOptions) {
  return callAgent(
    { action: "kb.list", prefix, ...(clientId && prefix.startsWith("clients/") ? { client_id: clientId } : {}) },
    KbListResponse,
    options,
  );
}

export async function getKbDocument(key: string, clientId: string | null, options: CallOptions) {
  return callAgent(
    { action: "kb.get", key, ...(clientId && key.startsWith("clients/") ? { client_id: clientId } : {}) },
    KbGetResponse,
    options,
  );
}

export async function listExecutions(options: CallOptions) {
  const response = await send("/api/collect", { method: "GET" }, options);
  return parseEnvelope(await readJson(response, options), ExecutionListResponse, options, response.status);
}

export async function describeExecution(executionArn: string, options: CallOptions) {
  const response = await send(`/api/collect?execution_arn=${encodeURIComponent(executionArn)}`, { method: "GET" }, options);
  return parseEnvelope(await readJson(response, options), ExecutionDetailResponse, options, response.status);
}

export function startCollection(input: CollectRequest, options: CallOptions) {
  return track(
    (async () => {
      const response = await send("/api/collect", { method: "POST", body: JSON.stringify(input) }, options);
      return parseEnvelope(await readJson(response, options), ExecutionStartResponse, options, response.status);
    })(),
  );
}

/** `build` on the `portfolio` runtime (CONTRACTS.md 12); the Decision is validated before it reaches the screen. */
export function buildPortfolio(input: Omit<PortfolioBuildRequestInput, "action">, options: CallOptions): Promise<PortfolioBuildResponse> {
  return track(
    (async () => {
      const response = await send("/api/portfolio", { method: "POST", body: JSON.stringify({ action: "build", ...input }) }, options);
      return parseEnvelope(await readJson(response, options), PortfolioBuildResponse, options, response.status);
    })(),
  );
}

/** « Supprimer mon compte » (CONTRACTS.md 7.1): the server deletes the account's data, then its sign-in account. */
export function deleteAccount(confirmation: string, options: CallOptions): Promise<DeleteAccountResponse> {
  return track(
    (async () => {
      const response = await send("/api/auth/delete-account", { method: "POST", body: JSON.stringify({ confirmation }) }, options);
      return parseEnvelope(await readJson(response, options), DeleteAccountResponse, options, response.status);
    })(),
  );
}
