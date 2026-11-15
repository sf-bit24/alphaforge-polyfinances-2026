import "server-only";
import type { AgentRequest } from "@/lib/contract/requests";
import { GatewayError } from "./errors";
import type { Upstream } from "./upstream";

const TIMEOUT_MS = 180_000;

/** Why fetch failed: Node's fetch puts the network error (ECONNREFUSED...) in `cause`. */
function failureReason(error: unknown): string {
  if (!(error instanceof Error)) return String(error);
  return error.cause instanceof Error ? error.cause.message : error.message;
}

/** `local` mode: POST the request to the Python runtime started on this machine. */
export async function invokeLocal(url: string, request: AgentRequest, stream: boolean, signal: AbortSignal): Promise<Upstream> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        accept: stream ? "text/event-stream, application/json" : "application/json",
      },
      body: JSON.stringify(request),
      cache: "no-store",
      signal: AbortSignal.any([signal, AbortSignal.timeout(TIMEOUT_MS)]),
    });
  } catch (error) {
    if (signal.aborted) throw error;
    const reason = failureReason(error);
    throw new GatewayError(
      "internal",
      {
        fr: `Runtime local injoignable à ${url} (${reason}). Lancez-le : cd app/agents && AGENT_ROLE=profile ALPHAFORGE_STORE=local uv run python main.py. Il n'écoute que sur 127.0.0.1 : évitez localhost dans LOCAL_AGENT_URL.`,
        en: `Local runtime unreachable at ${url} (${reason}). Start it: cd app/agents && AGENT_ROLE=profile ALPHAFORGE_STORE=local uv run python main.py. It listens on 127.0.0.1 only: avoid localhost in LOCAL_AGENT_URL.`,
      },
      502,
      { mode: "local", url },
    );
  }

  const type = response.headers.get("content-type") ?? "";
  if (stream && type.includes("text/event-stream") && response.body) {
    return { kind: "stream", body: response.body };
  }
  const text = await response.text();
  try {
    return { kind: "json", status: response.status, body: JSON.parse(text) };
  } catch {
    throw new GatewayError(
      "internal",
      {
        fr: `Le runtime local a répondu HTTP ${response.status} sans JSON.`,
        en: `The local runtime answered HTTP ${response.status} without JSON.`,
      },
      502,
      { mode: "local", upstream_status: response.status, body: text.slice(0, 500) },
    );
  }
}
