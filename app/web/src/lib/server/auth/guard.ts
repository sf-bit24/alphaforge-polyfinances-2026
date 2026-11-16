import { ConfigError, getAuthConfig, type AuthConfig, type CognitoConfig } from "../config";
import { GatewayError } from "../errors";
import { isAdmin, readSession, type AccountSession } from "./session";

/**
 * Who calls the gateway (CONTRACTS.md 7.1). With `AUTH_MODE=off`, nobody in particular: the
 * request goes on as before. With `AUTH_MODE=cognito`, the signed-in account, whose client_id
 * replaces any client_id of the body: an investor never reads nor writes another base.
 */
export type Identity = { mode: "off" } | { mode: "cognito"; config: CognitoConfig; session: AccountSession };

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** The sign-in settings; a ConfigError becomes a 500 envelope that names the variables. */
export function authConfigOrThrow(): AuthConfig {
  try {
    return getAuthConfig();
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    const names = error.issues.map((issue) => issue.variable).join(", ");
    throw new GatewayError(
      "internal",
      { fr: `Configuration de la connexion invalide : ${names}`, en: `Invalid sign-in configuration: ${names}` },
      500,
      { issues: error.issues },
    );
  }
}

export function unauthorized(): GatewayError {
  return new GatewayError(
    "unauthorized",
    { fr: "Connexion requise : votre session est absente ou expirée.", en: "Sign-in required: your session is missing or expired." },
    401,
    { login: "/login" },
  );
}

export function forbidden(text: { fr: string; en: string }, details: Record<string, unknown>): GatewayError {
  return new GatewayError("forbidden", text, 403, details);
}

/** The caller of a route; throws `unauthorized` (401) in cognito mode without a valid session. */
export function identityOf(request: Request): Identity {
  const config = authConfigOrThrow();
  if (config.AUTH_MODE === "off") return { mode: "off" };
  const session = readSession(request, config);
  if (!session) throw unauthorized();
  return { mode: "cognito", config, session };
}

function sameClient(value: unknown, own: string): boolean {
  return typeof value === "string" && value.toLowerCase() === own;
}

function foreignClient(field: string): GatewayError {
  return forbidden(
    { fr: "Ce profil n’est pas celui de votre compte.", en: "This profile is not your account’s." },
    { field },
  );
}

/** `kb.list` and `kb.get` on `clients/`: only the account's own base, `clients/<own client_id>/`. */
function bindKb(raw: Record<string, unknown>, own: string): Record<string, unknown> {
  const field = raw.action === "kb.list" ? "prefix" : "key";
  const target = raw[field];
  if (typeof target !== "string" || !target.startsWith("clients/")) return raw;
  if (!sameClient(target.split("/")[1], own)) throw foreignClient(field);
  return { ...raw, client_id: own };
}

/**
 * The body of `POST /api/agent` bound to the caller, before validation: in cognito mode, a foreign
 * `client_id` or `clients/` key is refused (403), and every client action gets the account's
 * client_id (`session.start` without one opens the account's base, created on first use).
 */
export function bindAgentBody(raw: unknown, identity: Identity): unknown {
  if (identity.mode === "off" || !isRecord(raw) || typeof raw.action !== "string") return raw;
  const own = identity.session.client_id;
  if (raw.client_id !== undefined && !sameClient(raw.client_id, own)) throw foreignClient("client_id");
  if (raw.action === "health") return raw;
  if (raw.action === "kb.list" || raw.action === "kb.get") return bindKb(raw, own);
  return { ...raw, client_id: own };
}

/**
 * The body of `POST /api/portfolio` bound to the caller: a FICTION demo persona stays open to any
 * signed-in account; otherwise the build is for the account's own profile, never another one.
 */
export function bindPortfolioBody(raw: unknown, identity: Identity): unknown {
  if (identity.mode === "off" || !isRecord(raw)) return raw;
  const own = identity.session.client_id;
  if (raw.client_id !== undefined && !sameClient(raw.client_id, own)) throw foreignClient("client_id");
  if (raw.persona !== undefined && raw.client_id === undefined) return raw;
  return { ...raw, client_id: own };
}

/** Starting a collection run: members of the `admin` group only, in cognito mode. */
export function requireAdmin(identity: Identity): void {
  if (identity.mode === "off" || isAdmin(identity.session)) return;
  throw forbidden(
    { fr: "Seul le groupe admin lance une collecte.", en: "Only the admin group starts a collection run." },
    { required_group: "admin" },
  );
}
