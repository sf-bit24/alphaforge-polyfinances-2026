import { z } from "zod";
import type { CognitoConfig } from "../config";
import { nowSeconds, seal, unseal } from "./seal";

/** Encrypted session of the signed-in account (httpOnly: the browser's JavaScript never reads it). */
export const SESSION_COOKIE = "af_session";
/**
 * state, nonce and PKCE verifier of a sign-in in progress, read back by the callback only. The cookie of
 * each sign-in is `af_login_<first 16 characters of its state>` (`loginCookieName`).
 */
export const LOGIN_COOKIE = "af_login";
export const LOGIN_COOKIE_PATH = "/api/auth";

/** Members of this Cognito group may start a collection run (`POST /api/collect`). */
export const ADMIN_GROUP = "admin";

const AccountSession = z.object({
  sub: z.string().min(1),
  email: z.string().nullable(),
  groups: z.array(z.string()),
  client_id: z.uuid(),
  /** Expiry of the ID token: the session ends with it. */
  exp: z.number().int(),
});
export type AccountSession = z.infer<typeof AccountSession>;

/** The value of one cookie of the request, if present. */
export function cookieValue(request: Request, name: string): string | null {
  const header = request.headers.get("cookie");
  if (!header) return null;
  for (const part of header.split(";")) {
    const index = part.indexOf("=");
    if (index > 0 && part.slice(0, index).trim() === name) return part.slice(index + 1).trim();
  }
  return null;
}

interface CookieOptions {
  config: CognitoConfig;
  maxAge: number;
  path?: string;
}

/** A `Set-Cookie` value: httpOnly, SameSite=Lax, Secure unless the interface runs on http://localhost. */
export function cookieHeader(name: string, value: string, { config, maxAge, path = "/" }: CookieOptions): string {
  const secure = config.APP_URL.startsWith("https://") ? "; Secure" : "";
  return `${name}=${value}; Path=${path}; Max-Age=${Math.max(0, Math.floor(maxAge))}; HttpOnly; SameSite=Lax${secure}`;
}

export function sessionCookie(session: AccountSession, config: CognitoConfig): string {
  const value = seal(session, { secret: config.AUTH_SESSION_SECRET, purpose: "session", expiresAt: session.exp });
  return cookieHeader(SESSION_COOKIE, value, { config, maxAge: session.exp - nowSeconds() });
}

export function clearedSessionCookie(config: CognitoConfig): string {
  return cookieHeader(SESSION_COOKIE, "", { config, maxAge: 0 });
}

/** The session sealed in a cookie value, or null if it is missing, altered or expired. */
export function sessionOf(value: string | null | undefined, config: CognitoConfig): AccountSession | null {
  const parsed = AccountSession.safeParse(unseal(value, { secret: config.AUTH_SESSION_SECRET, purpose: "session" }));
  return parsed.success ? parsed.data : null;
}

/** The session of the request (its `af_session` cookie). */
export function readSession(request: Request, config: CognitoConfig): AccountSession | null {
  return sessionOf(cookieValue(request, SESSION_COOKIE), config);
}

export function isAdmin(session: AccountSession): boolean {
  return session.groups.includes(ADMIN_GROUP);
}
