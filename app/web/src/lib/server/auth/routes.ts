import "server-only";
import { z } from "zod";
import type { AuthMeResponse } from "@/lib/contract/auth";
import { LOCALE_COOKIE, parseLocale } from "@/lib/i18n/locale";
import type { CognitoConfig } from "../config";
import { jsonResponse, localeOf, toGatewayError } from "../errors";
import { authConfigOrThrow, unauthorized } from "./guard";
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

/** A path of the interface to come back to. Another site, `//host`, `/login` or an API route give `/`. */
export function safeNext(value: string | null | undefined): string {
  if (!value || value.length > 512 || !value.startsWith("/")) return "/";
  try {
    const url = new URL(value, SAFE_BASE);
    if (url.origin !== SAFE_BASE || url.pathname.startsWith("/api/") || url.pathname === "/login") return "/";
    return `${url.pathname}${url.search}`;
  } catch {
    return "/";
  }
}

const Transaction = z.object({ state: z.string().min(1), nonce: z.string().min(1), verifier: z.string().min(43), next: z.string() });

function readTransaction(request: Request, config: CognitoConfig): LoginTransaction | null {
  const parsed = Transaction.safeParse(unseal(cookieValue(request, LOGIN_COOKIE), { secret: config.AUTH_SESSION_SECRET, purpose: "login" }));
  return parsed.success ? { ...parsed.data, next: safeNext(parsed.data.next) } : null;
}

function loginCookie(config: CognitoConfig, value: string, maxAge: number): string {
  return cookieHeader(LOGIN_COOKIE, value, { config, maxAge, path: LOGIN_COOKIE_PATH });
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
    return redirect(authorizeUrl(config, transaction, locale), [loginCookie(config, sealed, LOGIN_TTL_SECONDS)]);
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
    const transaction = readTransaction(request, config);
    const cleared = loginCookie(config, "", 0);
    const failure = (reason: string) => redirect(new URL(`/login?error=${reason}`, config.APP_URL), [cleared]);
    if (params.has("error")) return failure("denied");
    const code = params.get("code");
    if (!transaction || !code || !sameText(params.get("state"), transaction.state)) return failure("state");
    const session = await sessionCookieOf(config, code, transaction);
    if (!session) return failure("token");
    return redirect(new URL(transaction.next, config.APP_URL), [cleared, session]);
  } catch (error) {
    return errorResponse(error, request);
  }
}

/** `POST /api/auth/logout`: forget the session here, then end the managed login session at Cognito. */
export function handleLogout(request: Request): Response {
  try {
    const config = authConfigOrThrow();
    if (config.AUTH_MODE === "off") return redirect("/", [], 303);
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
