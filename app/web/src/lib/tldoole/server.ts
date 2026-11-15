import "server-only";
import { BedrockAgentCoreClient, InvokeAgentRuntimeCommand } from "@aws-sdk/client-bedrock-agentcore";
import { BedrockAgentCoreControlClient, ListAgentRuntimesCommand } from "@aws-sdk/client-bedrock-agentcore-control";
import { getConfig, type GatewayConfig } from "@/lib/server/config";
import { mockTldoole } from "./mock";
import type { TldooleRequest } from "./types";

/**
 * Server-side gateway to the `tldoole` runtime (CONTRACTS.md 8), with the AWS credentials of the
 * workstation, never from the browser. Same modes as the profile gateway (AGENT_MODE):
 * `mock` (in-memory), `local` (LOCAL_TLDOOLE_URL, default http://localhost:8081/invocations),
 * `aws` (InvokeAgentRuntime on `<ALPHAFORGE_PREFIX>_tldoole`, found by name).
 */

export interface TldooleUpstream {
  status: number;
  body: unknown;
}

interface Cache {
  agentCore: Map<string, BedrockAgentCoreClient>;
  control: Map<string, BedrockAgentCoreControlClient>;
  runtimes: Map<string, Promise<string>>;
}

const globalForTldoole = globalThis as unknown as { __alphaforgeTldoole?: Cache };
const cache: Cache = (globalForTldoole.__alphaforgeTldoole ??= { agentCore: new Map(), control: new Map(), runtimes: new Map() });

function agentCore(region: string): BedrockAgentCoreClient {
  let current = cache.agentCore.get(region);
  if (!current) cache.agentCore.set(region, (current = new BedrockAgentCoreClient({ region })));
  return current;
}

function control(region: string): BedrockAgentCoreControlClient {
  let current = cache.control.get(region);
  if (!current) cache.control.set(region, (current = new BedrockAgentCoreControlClient({ region })));
  return current;
}

export function tldooleRuntimeName(config: GatewayConfig): string {
  return `${config.ALPHAFORGE_PREFIX}_tldoole`;
}

async function resolveRuntime(config: GatewayConfig): Promise<string> {
  const name = tldooleRuntimeName(config);
  const key = `${config.AWS_REGION}:${name}`;
  let pending = cache.runtimes.get(key);
  if (!pending) {
    pending = (async () => {
      let nextToken: string | undefined;
      do {
        const page = await control(config.AWS_REGION).send(new ListAgentRuntimesCommand({ maxResults: 100, nextToken }));
        const match = page.agentRuntimes?.find((runtime) => runtime.agentRuntimeName === name);
        if (match?.agentRuntimeArn) return match.agentRuntimeArn;
        nextToken = page.nextToken;
      } while (nextToken);
      throw new Error(`No AgentCore runtime named ${name} in ${config.AWS_REGION}`);
    })();
    cache.runtimes.set(key, pending);
    pending.catch(() => cache.runtimes.delete(key));
  }
  return pending;
}

function failure(status: number, message: string, details: Record<string, unknown> = {}): TldooleUpstream {
  return { status, body: { ok: false, release: null, error: { code: "internal", message, details } } };
}

export async function invokeTldoole(request: TldooleRequest, signal: AbortSignal): Promise<TldooleUpstream> {
  const config = getConfig();
  if (config.AGENT_MODE === "mock") return mockTldoole(request);

  if (config.AGENT_MODE === "local") {
    const url = process.env.LOCAL_TLDOOLE_URL?.trim() || "http://localhost:8081/invocations";
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json", accept: "application/json" },
        body: JSON.stringify(request),
        signal,
      });
      return { status: response.status, body: await response.json() };
    } catch (error) {
      if (signal.aborted) throw error;
      return failure(502, `Runtime tldoole local injoignable (${url}).`, { mode: "local", url });
    }
  }

  try {
    const arn = await resolveRuntime(config);
    const output = await agentCore(config.AWS_REGION).send(
      new InvokeAgentRuntimeCommand({
        agentRuntimeArn: arn,
        qualifier: "DEFAULT",
        // Une session par investisseur pour l'interface (33 caractères au moins).
        runtimeSessionId: `${request.client_id}-feed`,
        contentType: "application/json",
        accept: "application/json",
        payload: new TextEncoder().encode(JSON.stringify(request)),
      }),
      { abortSignal: signal },
    );
    const text = (await output.response?.transformToString()) ?? "";
    return { status: output.statusCode ?? 200, body: JSON.parse(text) };
  } catch (error) {
    if (signal.aborted) throw error;
    const name = error instanceof Error ? error.name : "Error";
    const message = error instanceof Error ? error.message : String(error);
    if (name === "ResourceNotFoundException") cache.runtimes.clear();
    return failure(502, `Échec de l'appel au runtime tldoole (${name}) : ${message}`, { mode: "aws", aws_error: name });
  }
}
