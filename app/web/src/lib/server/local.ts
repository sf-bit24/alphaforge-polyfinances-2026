import "server-only";
import type { PortfolioBuildRequest } from "@/lib/contract/portfolio";
import type { AgentRequest } from "@/lib/contract/requests";
import { GatewayError } from "./errors";
import type { Upstream } from "./upstream";

const TIMEOUT_MS = 180_000;

/** How to start each local runtime, for the error message when it does not answer. */
const START = {
  profile: "cd app/agents && AGENT_ROLE=profile ALPHAFORGE_STORE=local uv run python main.py",
  portfolio: "cd app/agents && AGENT_ROLE=portfolio PORT=8081 ALPHAFORGE_STORE=local uv run --group finance python main.py",
} as const;

interface LocalOptions {
  role?: keyof typeof START;
  timeoutMs?: number;
}

/** `local` mode: POST the request to the Python runtime started on this machine. */
export async function invokeLocal(
  url: string,
  request: AgentRequest | PortfolioBuildRequest,
  stream: boolean,
  signal: AbortSignal,
  { role = "profile", timeoutMs = TIMEOUT_MS }: LocalOptions = {},
): Promise<Upstream> {
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
      signal: AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)]),
    });
  } catch (error) {
    if (signal.aborted) throw error;
    const reason = error instanceof Error ? (error.cause instanceof Error ? error.cause.message : error.message) : String(error);
    throw new GatewayError(
      "internal",
      {
        fr: `Runtime local injoignable à ${url} (${reason}). Lancez-le : ${START[role]}. Il n'écoute que sur 127.0.0.1 : évitez localhost dans ${role === "profile" ? "LOCAL_AGENT_URL" : "LOCAL_PORTFOLIO_URL"}.`,
        en: `Local runtime unreachable at ${url} (${reason}). Start it: ${START[role]}. It listens on 127.0.0.1 only: avoid localhost in ${role === "profile" ? "LOCAL_AGENT_URL" : "LOCAL_PORTFOLIO_URL"}.`,
      },
      502,
      { mode: "local", url, role },
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
