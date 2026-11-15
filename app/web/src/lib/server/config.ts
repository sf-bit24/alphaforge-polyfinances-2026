import "server-only";
import { z } from "zod";

/** Environment of the local interface (CONTRACTS.md 7), read at request time. */
const blankAsUndefined = (value: unknown) => (typeof value === "string" && value.trim() === "" ? undefined : value);

const ConfigSchema = z.object({
  AGENT_MODE: z.preprocess(blankAsUndefined, z.enum(["mock", "local", "aws"]).default("mock")),
  LOCAL_AGENT_URL: z.preprocess(blankAsUndefined, z.url().default("http://127.0.0.1:8080/invocations")),
  /** `portfolio` runtime started on this machine (CONTRACTS.md 12), on its own port. */
  LOCAL_PORTFOLIO_URL: z.preprocess(blankAsUndefined, z.url().default("http://127.0.0.1:8081/invocations")),
  AWS_REGION: z.preprocess(blankAsUndefined, z.string().regex(/^[a-z]{2}(-[a-z]+)+-\d$/).default("us-east-1")),
  ALPHAFORGE_PREFIX: z.preprocess(blankAsUndefined, z.string().regex(/^[A-Za-z][A-Za-z0-9_]{0,40}$/).default("alphaforge_sandbox")),
  ALPHAFORGE_STATE_MACHINE: z.preprocess(
    blankAsUndefined,
    z.string().regex(/^[A-Za-z0-9_-]{1,80}$/).default("alphaforge-sandbox-collecte"),
  ),
});

export type GatewayConfig = z.infer<typeof ConfigSchema>;
export type AgentMode = GatewayConfig["AGENT_MODE"];

export class ConfigError extends Error {
  constructor(readonly issues: Array<{ variable: string; message: string }>) {
    super(`Invalid configuration: ${issues.map((issue) => `${issue.variable} (${issue.message})`).join(", ")}`);
  }
}

export function getConfig(): GatewayConfig {
  const parsed = ConfigSchema.safeParse({
    AGENT_MODE: process.env.AGENT_MODE,
    LOCAL_AGENT_URL: process.env.LOCAL_AGENT_URL,
    LOCAL_PORTFOLIO_URL: process.env.LOCAL_PORTFOLIO_URL,
    AWS_REGION: process.env.AWS_REGION,
    ALPHAFORGE_PREFIX: process.env.ALPHAFORGE_PREFIX,
    ALPHAFORGE_STATE_MACHINE: process.env.ALPHAFORGE_STATE_MACHINE,
  });
  if (!parsed.success) {
    throw new ConfigError(
      parsed.error.issues.map((issue) => ({ variable: String(issue.path[0] ?? "?"), message: issue.message })),
    );
  }
  return parsed.data;
}

/** Name of the `profile` runtime, found by `ListAgentRuntimes`. */
export function profileRuntimeName(config: GatewayConfig): string {
  return `${config.ALPHAFORGE_PREFIX}_profile`;
}

/** Name of the optional `portfolio` runtime (CONTRACTS.md 12), found by `ListAgentRuntimes`. */
export function portfolioRuntimeName(config: GatewayConfig): string {
  return `${config.ALPHAFORGE_PREFIX}_portfolio`;
}
