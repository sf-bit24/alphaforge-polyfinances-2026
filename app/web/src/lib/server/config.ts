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

/* ------------------------------------------------------------------ */
/* Sign-in (CONTRACTS.md 7.1)                                          */
/* ------------------------------------------------------------------ */

const required = <T extends z.ZodType>(schema: T) => z.preprocess(blankAsUndefined, schema);
const httpsUrl = z.url({ protocol: /^https$/ });

/**
 * `AUTH_MODE=off` (default): no sign-in, the browser keeps its client_id (modes mock, local and aws as before).
 * `AUTH_MODE=cognito`: every page and `/api/*` route needs a session; the client_id comes from the account.
 */
const AuthConfigSchema = z.discriminatedUnion("AUTH_MODE", [
  z.object({ AUTH_MODE: z.literal("off") }),
  z.object({
    AUTH_MODE: z.literal("cognito"),
    /** `https://cognito-idp.<region>.amazonaws.com/<user pool id>` (output `auth_issuer`). */
    COGNITO_ISSUER: required(z.string().regex(/^https:\/\/cognito-idp\.[a-z0-9-]+\.amazonaws\.com\/[a-z0-9-]+_[A-Za-z0-9]+$/)),
    /** Public app client, no secret (output `auth_client_id`). */
    COGNITO_CLIENT_ID: required(z.string().regex(/^[A-Za-z0-9]{1,128}$/)),
    /** Managed login domain, `https://<prefix>.auth.<region>.amazoncognito.com` (output `auth_domain`). */
    COGNITO_DOMAIN: required(httpsUrl.transform((url) => new URL(url).origin)),
    /** Public origin of the interface: CloudFront, or `http://localhost:3000` with next dev. */
    APP_URL: required(z.url({ protocol: /^https?$/ }).transform((url) => new URL(url).origin)),
    /** Key of the session cookie (AES-256-GCM): at least 32 characters, never sent to the browser. */
    AUTH_SESSION_SECRET: required(z.string().min(32)),
  }),
]);

export type AuthConfig = z.infer<typeof AuthConfigSchema>;
export type CognitoConfig = Extract<AuthConfig, { AUTH_MODE: "cognito" }>;

/** The sign-in settings, read at request time; a missing or invalid variable in `cognito` mode is a ConfigError. */
export function getAuthConfig(): AuthConfig {
  const mode = blankAsUndefined(process.env.AUTH_MODE) ?? "off";
  const parsed = AuthConfigSchema.safeParse({
    AUTH_MODE: mode,
    COGNITO_ISSUER: process.env.COGNITO_ISSUER,
    COGNITO_CLIENT_ID: process.env.COGNITO_CLIENT_ID,
    COGNITO_DOMAIN: process.env.COGNITO_DOMAIN,
    APP_URL: process.env.APP_URL,
    AUTH_SESSION_SECRET: process.env.AUTH_SESSION_SECRET,
  });
  if (!parsed.success) {
    throw new ConfigError(
      parsed.error.issues.map((issue) => ({ variable: String(issue.path[0] ?? "AUTH_MODE"), message: issue.message })),
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

/* ------------------------------------------------------------------ */
/* Account deletion (CONTRACTS.md 7.1), AGENT_MODE=aws only            */
/* ------------------------------------------------------------------ */

const DeletionConfigSchema = z.object({
  /** Bucket of the OKF bases, as for the runtimes (`aws_s3_bucket.this`). */
  ALPHAFORGE_BUCKET: required(z.string().regex(/^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/)),
  /** Prefix of the client Knowledge Bases `<prefix>-client-<client_id>` (`local.prefix`, client_kb.tf). */
  ALPHAFORGE_CLIENT_KB_PREFIX: required(z.string().regex(/^[A-Za-z0-9][A-Za-z0-9-]{0,40}$/)),
  /** S3 Vectors bucket of the indexes `client-<client_id>` (client_kb.tf). */
  ALPHAFORGE_CLIENT_KB_VECTOR_BUCKET: required(z.string().regex(/^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/)),
});
export type DeletionConfig = z.infer<typeof DeletionConfigSchema> & { USER_POOL_ID: string };

/** What the deletion acts on, set by Terraform on the web task (auth.tf); the user pool comes from COGNITO_ISSUER. */
export function getDeletionConfig(auth: CognitoConfig): DeletionConfig {
  const parsed = DeletionConfigSchema.safeParse({
    ALPHAFORGE_BUCKET: process.env.ALPHAFORGE_BUCKET,
    ALPHAFORGE_CLIENT_KB_PREFIX: process.env.ALPHAFORGE_CLIENT_KB_PREFIX,
    ALPHAFORGE_CLIENT_KB_VECTOR_BUCKET: process.env.ALPHAFORGE_CLIENT_KB_VECTOR_BUCKET,
  });
  if (!parsed.success) {
    throw new ConfigError(parsed.error.issues.map((issue) => ({ variable: String(issue.path[0] ?? "?"), message: issue.message })));
  }
  return { ...parsed.data, USER_POOL_ID: new URL(auth.COGNITO_ISSUER).pathname.slice(1) };
}
