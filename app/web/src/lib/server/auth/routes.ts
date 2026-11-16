import "server-only";
import { z } from "zod";
import type { AuthMeResponse } from "@/lib/contract/auth";
import { LOCALE_COOKIE, parseLocale } from "@/lib/i18n/locale";
import type { CognitoConfig } from "../config";
import { jsonResponse, localeOf, toGatewayError } from "../errors";
import { authConfigOrThrow, forbidden, unauthorized } from "./guard";
import { authorizeUrl, exchangeCode, logoutUrl, newTransaction, sameText, sessionFromClaims, verifyIdToken, type LoginTransaction } from "./oidc";
import { nowSeconds, seal, unseal } from "./seal";
import {
  LOGIN_COOKIE,
  LOGIN_COOKIE_PATH,
  clearedSessionCookie,
  cookieHeader,
  cookieValue,
  isAdmin,
  readSession,
  sessionCookie,
} from "./session";

/** Routes `/api/auth/*` (CONTRACTS.md 7.1). With `AUTH_MODE=off` they only send the browser back to the interface. */

/** A sign-in started more than ten minutes ago is abandoned. */
const LOGIN_TTL_SECONDS = 600;
const SAFE_BASE = "http://alphaforge.invalid";

function redirect(location: string | URL, cookies: string[] = [], status = 302): Response {
  const headers = new Headers({ location: String(location), "cache-control": "no-store" });
  for (const cookie of cookies) headers.append("set-cookie", cookie);
  return new Response(null, { status, headers });
}

function errorResponse(error: unknown, request: Request): Response {
  const gatewayError = toGatewayError(error);
  return jsonResponse(gatewayError.status, gatewayError.envelope(localeOf(request)));
}

/**
 * A path of the interface to come back to. Another site, `//host` (even once normalized: `/.//host`,
 * `/a/..//host`, `/%2e//host`), a backslash, `/login` or an API route give `/`.
 */
export function safeNext(value: string | null | undefined): string {
  if (!value || value.length > 512 || !value.startsWith("/") || value.includes("\\")) return "/";
  try {
    const url = new URL(value, SAFE_BASE);
    const path = url.pathname;
    if (url.origin !== SAFE_BASE || path.startsWith("//") || path.startsWith("/api/") || path === "/login") return "/";
    return `${path}${url.search}`;
  } catch {
    return "/";
  }
}

/** `state` as made by `newTransaction`: 32 random bytes in base64url. */
const STATE = /^[A-Za-z0-9_-]{43}$/;

/** One cookie per sign-in in progress, named after its state: two tabs signing in do not overwrite each other. */
export function loginCookieName(state: string): string {
  return `${LOGIN_COOKIE}_${state.slice(0, 16)}`;
}

const Transaction = z.object({ state: z.string().min(1), nonce: z.string().min(1), verifier: z.string().min(43), next: z.string() });

/** The sign-in of this `state`, if its cookie is there, intact, unexpired and for the same state. */
function readTransaction(request: Request, config: CognitoConfig, state: string | null): LoginTransaction | null {
  if (!state || !STATE.test(state)) return null;
  const sealed = cookieValue(request, loginCookieName(state));
  const parsed = Transaction.safeParse(unseal(sealed, { secret: config.AUTH_SESSION_SECRET, purpose: "login" }));
  if (!parsed.success || !sameText(state, parsed.data.state)) return null;
  return { ...parsed.data, next: safeNext(parsed.data.next) };
}

function loginCookie(config: CognitoConfig, state: string, value: string, maxAge: number): string {
  return cookieHeader(loginCookieName(state), value, { config, maxAge, path: LOGIN_COOKIE_PATH });
}

/** `GET /api/auth/login?next=/path`: a new state, nonce and PKCE verifier, then the managed login page. */
export function handleLogin(request: Request): Response {
  try {
    const config = authConfigOrThrow();
    const next = safeNext(new URL(request.url).searchParams.get("next"));
    if (config.AUTH_MODE === "off") return redirect(next);
    const transaction = newTransaction(next);
    const sealed = seal({ ...transaction }, { secret: config.AUTH_SESSION_SECRET, purpose: "login", expiresAt: nowSeconds() + LOGIN_TTL_SECONDS });
    const locale = parseLocale(cookieValue(request, LOCALE_COOKIE));
    return redirect(authorizeUrl(config, transaction, locale), [loginCookie(config, transaction.state, sealed, LOGIN_TTL_SECONDS)]);
  } catch (error) {
    return errorResponse(error, request);
  }
}

/** The ID token of the code, checked; null when the exchange or a check fails (logged, never shown). */
async function sessionCookieOf(config: CognitoConfig, code: string, transaction: LoginTransaction): Promise<string | null> {
  try {
    const idToken = await exchangeCode(config, code, transaction.verifier);
    return sessionCookie(sessionFromClaims(await verifyIdToken(idToken, config, transaction.nonce)), config);
  } catch (error) {
    console.error("Sign-in callback failed:", error instanceof Error ? error.message : String(error));
    return null;
  }
}

/** `GET /api/auth/callback?code&state`: exchange the code, verify the ID token, open the session. */
export async function handleCallback(request: Request): Promise<Response> {
  try {
    const config = authConfigOrThrow();
    if (config.AUTH_MODE === "off") return redirect("/");
    const params = new URL(request.url).searchParams;
    const state = params.get("state");
    const cleared = state && STATE.test(state) ? [loginCookie(config, state, "", 0)] : [];
    const failure = (reason: string) => redirect(new URL(`/login?error=${reason}`, config.APP_URL), cleared);
    if (params.has("error")) return failure("denied");
    const transaction = readTransaction(request, config, state);
    const code = params.get("code");
    if (!transaction || !code) return failure("state");
    const session = await sessionCookieOf(config, code, transaction);
    if (!session) return failure("token");
    return redirect(new URL(transaction.next, config.APP_URL), [...cleared, session]);
  } catch (error) {
    return errorResponse(error, request);
  }
}

/**
 * Whether a form post comes from another site. `Sec-Fetch-Site` is set by the browser and cannot be forged by a page;
 * it decides when present. `Origin` is only a fallback for browsers without it: with `Referrer-Policy: no-referrer`
 * (next.config.ts), Chrome sends `Origin: null` even for the interface's own form, so `null` says nothing.
 */
export function isCrossSitePost(request: Request, appUrl: string): boolean {
  const site = request.headers.get("sec-fetch-site");
  if (site !== null) return site !== "same-origin" && site !== "none";
  const origin = request.headers.get("origin");
  return origin !== null && origin !== "null" && origin !== appUrl;
}

/**
 * `POST /api/auth/logout`: forget the session here, then end the managed login session at Cognito.
 * A form posted from another site is refused (`isCrossSitePost`): nobody signs you out from elsewhere.
 */
export function handleLogout(request: Request): Response {
  try {
    const config = authConfigOrThrow();
    if (config.AUTH_MODE === "off") return redirect("/", [], 303);
    if (isCrossSitePost(request, config.APP_URL)) {
      const details = { origin: request.headers.get("origin"), sec_fetch_site: request.headers.get("sec-fetch-site") };
      throw forbidden({ fr: "Déconnexion refusée : demande venue d’un autre site.", en: "Sign-out refused: request from another site." }, details);
    }
    return redirect(logoutUrl(config), [clearedSessionCookie(config)], 303);
  } catch (error) {
    return errorResponse(error, request);
  }
}

/** `GET /api/auth/me`: the sign-in mode and the account; 401 in cognito mode without a session. */
export function handleMe(request: Request): Response {
  try {
    const config = authConfigOrThrow();
    if (config.AUTH_MODE === "off") return jsonResponse(200, { ok: true, mode: "off", user: null } satisfies AuthMeResponse);
    const session = readSession(request, config);
    if (!session) throw unauthorized();
    const user = {
      email: session.email,
      client_id: session.client_id,
      groups: session.groups,
      admin: isAdmin(session),
      expires_at: new Date(session.exp * 1000).toISOString(),
    };
    return jsonResponse(200, { ok: true, mode: "cognito", user } satisfies AuthMeResponse);
  } catch (error) {
    return errorResponse(error, request);
  }
}
