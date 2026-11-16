import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { createRemoteJWKSet, jwtVerify, type JWTPayload, type JWTVerifyGetKey } from "jose";
import type { Locale } from "@/lib/contract/schemas";
import type { CognitoConfig } from "../config";
import { accountClientId } from "./client-id";
import type { AccountSession } from "./session";

/**
 * OpenID Connect with the Cognito managed login, server side: authorization code with PKCE,
 * state and nonce. The public app client has no secret; the ID token is checked against the
 * JWKS of the user pool (signature, `iss`, `aud`, `exp`, `token_use`, `nonce`).
 */
export type LoginTransaction = {
  state: string;
  nonce: string;
  verifier: string;
  /** Path of the interface to open after the sign-in. */
  next: string;
};

const randomToken = () => randomBytes(32).toString("base64url");

export function newTransaction(next: string): LoginTransaction {
  return { state: randomToken(), nonce: randomToken(), verifier: randomToken(), next };
}

export function redirectUri(config: CognitoConfig): string {
  return `${config.APP_URL}/api/auth/callback`;
}

/** The managed login page, in the interface language (`lang`). */
export function authorizeUrl(config: CognitoConfig, transaction: LoginTransaction, locale: Locale): URL {
  const url = new URL("/oauth2/authorize", config.COGNITO_DOMAIN);
  url.search = new URLSearchParams({
    response_type: "code",
    client_id: config.COGNITO_CLIENT_ID,
    redirect_uri: redirectUri(config),
    scope: "openid email profile",
    state: transaction.state,
    nonce: transaction.nonce,
    code_challenge: createHash("sha256").update(transaction.verifier).digest("base64url"),
    code_challenge_method: "S256",
    lang: locale,
  }).toString();
  return url;
}

/** Cognito's `/logout`: ends the managed login session, then back to the interface. */
export function logoutUrl(config: CognitoConfig): URL {
  const url = new URL("/logout", config.COGNITO_DOMAIN);
  url.search = new URLSearchParams({ client_id: config.COGNITO_CLIENT_ID, logout_uri: `${config.APP_URL}/` }).toString();
  return url;
}

/** Exchange the code at the token endpoint; returns the ID token. */
export async function exchangeCode(config: CognitoConfig, code: string, verifier: string): Promise<string> {
  const response = await fetch(new URL("/oauth2/token", config.COGNITO_DOMAIN), {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded", accept: "application/json" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: config.COGNITO_CLIENT_ID,
      code,
      redirect_uri: redirectUri(config),
      code_verifier: verifier,
    }).toString(),
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
  const body = (await response.json().catch(() => null)) as { id_token?: unknown; error?: unknown } | null;
  if (!response.ok || typeof body?.id_token !== "string") {
    throw new Error(`Token endpoint answered ${response.status} (${String(body?.error ?? "no id_token")})`);
  }
  return body.id_token;
}

const keySets = new Map<string, JWTVerifyGetKey>();

/** The JWKS of the user pool, fetched once and cached by jose (keys rotate rarely). */
function poolKeys(issuer: string): JWTVerifyGetKey {
  let keys = keySets.get(issuer);
  if (!keys) {
    keys = createRemoteJWKSet(new URL(`${issuer}/.well-known/jwks.json`));
    keySets.set(issuer, keys);
  }
  return keys;
}

export function sameText(left: unknown, right: string): boolean {
  if (typeof left !== "string") return false;
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function verifyIdToken(idToken: string, config: CognitoConfig, nonce: string): Promise<JWTPayload> {
  const { payload } = await jwtVerify(idToken, poolKeys(config.COGNITO_ISSUER), {
    issuer: config.COGNITO_ISSUER,
    audience: config.COGNITO_CLIENT_ID,
    algorithms: ["RS256"],
    requiredClaims: ["sub", "exp", "iat"],
  });
  if (payload.token_use !== "id") throw new Error("Not an ID token");
  if (!sameText(payload.nonce, nonce)) throw new Error("Nonce mismatch");
  return payload;
}

/** The session of a verified ID token: the client_id is derived from `sub`, the groups are `cognito:groups`. */
export function sessionFromClaims(claims: JWTPayload): AccountSession {
  const sub = String(claims.sub);
  const groups = claims["cognito:groups"];
  return {
    sub,
    email: typeof claims.email === "string" ? claims.email : null,
    groups: Array.isArray(groups) ? groups.filter((group): group is string => typeof group === "string") : [],
    client_id: accountClientId(sub),
    exp: Number(claims.exp),
  };
}
