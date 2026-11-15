import "server-only";
import { randomUUID } from "node:crypto";
import { BedrockAgentCoreClient, InvokeAgentRuntimeCommand } from "@aws-sdk/client-bedrock-agentcore";
import { BedrockAgentCoreControlClient, ListAgentRuntimesCommand } from "@aws-sdk/client-bedrock-agentcore-control";
import {
  DescribeExecutionCommand,
  ListExecutionsCommand,
  ListStateMachinesCommand,
  SFNClient,
  StartExecutionCommand,
} from "@aws-sdk/client-sfn";
import { parseJsonText, summarizeRunOutput } from "@/lib/contract/collect";
import type { PortfolioBuildRequest } from "@/lib/contract/portfolio";
import type { AgentRequest, CollectRequest } from "@/lib/contract/requests";
import type { ExecutionDetail, ExecutionStatus, ExecutionSummary } from "@/lib/contract/schemas";
import type { GatewayConfig } from "./config";
import { portfolioRuntimeName, profileRuntimeName } from "./config";
import { GatewayError } from "./errors";
import type { Upstream } from "./upstream";

interface RuntimeInfo {
  name: string;
  arn: string;
  status: string | null;
}

interface AwsCache {
  clients: Map<string, unknown>;
  runtimes: Map<string, Promise<RuntimeInfo>>;
  stateMachines: Map<string, Promise<string>>;
  /** Session for calls that concern no client (health, general base): one per server process. */
  technicalSession: string;
}

const globalForAws = globalThis as unknown as { __alphaforgeAws?: AwsCache };
const cache: AwsCache = (globalForAws.__alphaforgeAws ??= {
  clients: new Map(),
  runtimes: new Map(),
  stateMachines: new Map(),
  technicalSession: `alphaforge-web-${randomUUID()}`,
});

function client<T>(key: string, create: () => T): T {
  if (!cache.clients.has(key)) cache.clients.set(key, create());
  return cache.clients.get(key) as T;
}

const agentCore = (region: string) => client(`agentcore:${region}`, () => new BedrockAgentCoreClient({ region }));
const agentCoreControl = (region: string) =>
  client(`agentcore-control:${region}`, () => new BedrockAgentCoreControlClient({ region }));
const sfn = (region: string) => client(`sfn:${region}`, () => new SFNClient({ region }));

/** Translate an AWS SDK error into a readable gateway error. */
function awsError(error: unknown, operation: string): GatewayError {
  const name = error instanceof Error ? error.name : "Error";
  const message = error instanceof Error ? error.message : String(error);
  const status = (error as { $metadata?: { httpStatusCode?: number } }).$metadata?.httpStatusCode ?? null;
  const details = { mode: "aws", operation, aws_error: name, http_status: status };
  if (name === "CredentialsProviderError" || /credential/i.test(message)) {
    return new GatewayError(
      "internal",
      {
        fr: "Identifiants AWS introuvables pour le serveur Next.js : lancez `aws sso login` ou définissez AWS_PROFILE, puis redémarrez `npm run dev`.",
        en: "No AWS credentials for the Next.js server: run `aws sso login` or set AWS_PROFILE, then restart `npm run dev`.",
      },
      500,
      details,
    );
  }
  if (name === "AccessDeniedException" || name === "UnrecognizedClientException" || status === 403) {
    return new GatewayError(
      "internal",
      { fr: `Accès refusé par AWS pour ${operation} : ${message}`, en: `AWS denied ${operation}: ${message}` },
      502,
      details,
    );
  }
  return new GatewayError(
    "internal",
    { fr: `Échec de l'appel AWS ${operation} (${name}) : ${message}`, en: `AWS call ${operation} failed (${name}): ${message}` },
    502,
    details,
  );
}

/** ARN of a runtime, found once by name with `ListAgentRuntimes`. */
async function resolveRuntime(config: GatewayConfig, name: string, hint?: { fr: string; en: string }): Promise<RuntimeInfo> {
  const key = `${config.AWS_REGION}:${name}`;
  let pending = cache.runtimes.get(key);
  if (!pending) {
    pending = (async () => {
      let nextToken: string | undefined;
      do {
        let page;
        try {
          page = await agentCoreControl(config.AWS_REGION).send(new ListAgentRuntimesCommand({ maxResults: 100, nextToken }));
        } catch (error) {
          throw awsError(error, "ListAgentRuntimes");
        }
        const match = page.agentRuntimes?.find((runtime) => runtime.agentRuntimeName === name);
        if (match?.agentRuntimeArn) return { name, arn: match.agentRuntimeArn, status: match.status ?? null };
        nextToken = page.nextToken;
      } while (nextToken);
      throw new GatewayError(
        "internal",
        {
          fr: `Aucun runtime AgentCore nommé ${name} dans ${config.AWS_REGION} : vérifiez ALPHAFORGE_PREFIX et le déploiement Terraform.${hint ? ` ${hint.fr}` : ""}`,
          en: `No AgentCore runtime named ${name} in ${config.AWS_REGION}: check ALPHAFORGE_PREFIX and the Terraform deployment.${hint ? ` ${hint.en}` : ""}`,
        },
        502,
        { mode: "aws", runtime: name, region: config.AWS_REGION },
      );
    })();
    cache.runtimes.set(key, pending);
    pending.catch(() => cache.runtimes.delete(key));
  }
  return pending;
}

/** ARN of `<prefix>_profile`, found once by name with `ListAgentRuntimes`. */
export async function resolveProfileRuntime(config: GatewayConfig): Promise<RuntimeInfo> {
  return resolveRuntime(config, profileRuntimeName(config));
}

/** ARN of the optional `<prefix>_portfolio` (CONTRACTS.md 12), deployed only with `portfolio_enabled = true`. */
export async function resolvePortfolioRuntime(config: GatewayConfig): Promise<RuntimeInfo> {
  return resolveRuntime(config, portfolioRuntimeName(config), {
    fr: "Le runtime portfolio n'existe qu'avec portfolio_enabled = true.",
    en: "The portfolio runtime only exists with portfolio_enabled = true.",
  });
}

/** `runtimeSessionId`: the client_id for client actions, a stable technical session otherwise. */
export function sessionIdFor(request: AgentRequest): string {
  if ("client_id" in request && request.client_id) return request.client_id;
  return cache.technicalSession;
}

/**
 * `runtimeSessionId` of a portfolio build: the client_id, as for `profile`; for a FICTION demo persona,
 * a stable session per persona (AgentCore wants at least 33 characters).
 */
export function portfolioSessionId(request: PortfolioBuildRequest): string {
  if (request.client_id) return request.client_id;
  return `alphaforge-web-persona-${request.persona ?? "none"}-session`.padEnd(33, "0");
}

/** `aws` mode: InvokeAgentRuntime on the `profile` runtime, qualifier DEFAULT. */
export async function invokeAws(config: GatewayConfig, request: AgentRequest, stream: boolean, signal: AbortSignal): Promise<Upstream> {
  return invokeRuntime(config, await resolveProfileRuntime(config), sessionIdFor(request), request, stream, signal);
}

/** `aws` mode: `build` on the `portfolio` runtime (JSON only, no streaming in version 1). */
export async function invokePortfolioAws(config: GatewayConfig, request: PortfolioBuildRequest, signal: AbortSignal): Promise<Upstream> {
  return invokeRuntime(config, await resolvePortfolioRuntime(config), portfolioSessionId(request), request, false, signal);
}

async function invokeRuntime(
  config: GatewayConfig,
  runtime: RuntimeInfo,
  runtimeSessionId: string,
  payload: unknown,
  stream: boolean,
  signal: AbortSignal,
): Promise<Upstream> {
  let output;
  try {
    output = await agentCore(config.AWS_REGION).send(
      new InvokeAgentRuntimeCommand({
        agentRuntimeArn: runtime.arn,
        qualifier: "DEFAULT",
        runtimeSessionId,
        contentType: "application/json",
        accept: stream ? "text/event-stream" : "application/json",
        payload: new TextEncoder().encode(JSON.stringify(payload)),
      }),
      { abortSignal: signal },
    );
  } catch (error) {
    if (signal.aborted) throw error;
    if (error instanceof Error && error.name === "ResourceNotFoundException") cache.runtimes.clear();
    throw awsError(error, "InvokeAgentRuntime");
  }
  if (!output.response) {
    throw new GatewayError("internal", { fr: "Réponse vide d'AgentCore.", en: "Empty response from AgentCore." }, 502, {
      mode: "aws",
    });
  }
  const type = output.contentType ?? "";
  if (stream && type.includes("text/event-stream")) {
    return { kind: "stream", body: output.response.transformToWebStream() as ReadableStream<Uint8Array> };
  }
  const text = await output.response.transformToString();
  try {
    return { kind: "json", status: output.statusCode ?? 200, body: JSON.parse(text) };
  } catch {
    throw new GatewayError(
      "internal",
      { fr: "AgentCore a répondu sans JSON.", en: "AgentCore answered without JSON." },
      502,
      { mode: "aws", content_type: type, body: text.slice(0, 500) },
    );
  }
}

/* ----------------------------- Step Functions ----------------------------- */

async function resolveStateMachine(config: GatewayConfig): Promise<string> {
  const name = config.ALPHAFORGE_STATE_MACHINE;
  const key = `${config.AWS_REGION}:${name}`;
  let pending = cache.stateMachines.get(key);
  if (!pending) {
    pending = (async () => {
      let nextToken: string | undefined;
      do {
        let page;
        try {
          page = await sfn(config.AWS_REGION).send(new ListStateMachinesCommand({ maxResults: 1000, nextToken }));
        } catch (error) {
          throw awsError(error, "ListStateMachines");
        }
        const match = page.stateMachines?.find((machine) => machine.name === name);
        if (match?.stateMachineArn) return match.stateMachineArn;
        nextToken = page.nextToken;
      } while (nextToken);
      throw new GatewayError(
        "internal",
        {
          fr: `Aucune machine Step Functions nommée ${name} dans ${config.AWS_REGION} : vérifiez ALPHAFORGE_STATE_MACHINE.`,
          en: `No Step Functions state machine named ${name} in ${config.AWS_REGION}: check ALPHAFORGE_STATE_MACHINE.`,
        },
        502,
        { mode: "aws", state_machine: name },
      );
    })();
    cache.stateMachines.set(key, pending);
    pending.catch(() => cache.stateMachines.delete(key));
  }
  return pending;
}

const iso = (date: Date | undefined) => (date ? date.toISOString() : null);

export async function stateMachineInfo(config: GatewayConfig): Promise<{ name: string; arn: string }> {
  return { name: config.ALPHAFORGE_STATE_MACHINE, arn: await resolveStateMachine(config) };
}

async function describe(config: GatewayConfig, executionArn: string): Promise<ExecutionDetail> {
  let output;
  try {
    output = await sfn(config.AWS_REGION).send(new DescribeExecutionCommand({ executionArn }));
  } catch (error) {
    if (error instanceof Error && error.name === "ExecutionDoesNotExist") {
      throw new GatewayError("not_found", { fr: "Exécution introuvable.", en: "Execution not found." }, 404, {
        execution_arn: executionArn,
      });
    }
    throw awsError(error, "DescribeExecution");
  }
  const parsedOutput = parseJsonText(output.output);
  return {
    execution_arn: output.executionArn ?? executionArn,
    name: output.name ?? executionArn.split(":").pop() ?? executionArn,
    status: (output.status ?? "RUNNING") as ExecutionStatus,
    start_date: iso(output.startDate) ?? new Date(0).toISOString(),
    stop_date: iso(output.stopDate),
    outcome: summarizeRunOutput(parsedOutput),
    input: parseJsonText(output.input),
    output: parsedOutput,
    error: output.error ?? null,
    cause: output.cause ?? null,
  };
}

/** Recent executions, with per-collector status read from each finished run's output. */
export async function listExecutions(config: GatewayConfig, limit = 10): Promise<ExecutionSummary[]> {
  const stateMachineArn = await resolveStateMachine(config);
  let page;
  try {
    page = await sfn(config.AWS_REGION).send(new ListExecutionsCommand({ stateMachineArn, maxResults: limit }));
  } catch (error) {
    throw awsError(error, "ListExecutions");
  }
  const executions = page.executions ?? [];
  return Promise.all(
    executions.map(async (execution): Promise<ExecutionSummary> => {
      const summary: ExecutionSummary = {
        execution_arn: execution.executionArn ?? "",
        name: execution.name ?? "",
        status: (execution.status ?? "RUNNING") as ExecutionStatus,
        start_date: iso(execution.startDate) ?? new Date(0).toISOString(),
        stop_date: iso(execution.stopDate),
        outcome: null,
      };
      if (summary.status !== "SUCCEEDED" || !summary.execution_arn) return summary;
      try {
        return { ...summary, outcome: (await describe(config, summary.execution_arn)).outcome };
      } catch {
        return summary;
      }
    }),
  );
}

/** StartExecution without a name: Step Functions names it with a UUID, which becomes the run_id. */
export async function startExecution(config: GatewayConfig, input: CollectRequest): Promise<ExecutionSummary> {
  const stateMachineArn = await resolveStateMachine(config);
  let output;
  try {
    output = await sfn(config.AWS_REGION).send(new StartExecutionCommand({ stateMachineArn, input: JSON.stringify(input) }));
  } catch (error) {
    throw awsError(error, "StartExecution");
  }
  const arn = output.executionArn ?? "";
  return {
    execution_arn: arn,
    name: arn.split(":").pop() ?? arn,
    status: "RUNNING",
    start_date: iso(output.startDate) ?? new Date().toISOString(),
    stop_date: null,
    outcome: null,
  };
}

/** Only executions of the configured state machine are described. */
export async function describeExecution(config: GatewayConfig, executionArn: string): Promise<ExecutionDetail> {
  const stateMachineArn = await resolveStateMachine(config);
  const expectedPrefix = `${stateMachineArn.replace(":stateMachine:", ":execution:")}:`;
  if (!executionArn.startsWith(expectedPrefix)) {
    throw new GatewayError(
      "bad_request",
      { fr: "Cette exécution n'appartient pas à la machine de collecte.", en: "This execution does not belong to the collection machine." },
      400,
      { execution_arn: executionArn },
    );
  }
  return describe(config, executionArn);
}
