import { jsonResponse, localeOf, toGatewayError } from "../errors";
import { authConfigOrThrow, unauthorized } from "./guard";
import { readSession } from "./session";

/**
 * The check of `src/proxy.ts`, before any page or route (CONTRACTS.md 7.1). In cognito mode,
 * a page without a session goes to `/login`, an `/api/*` route answers 401 with the error
 * envelope. The routes check the session again themselves: the proxy is not the only guard.
 */
const PUBLIC_PATHS = new Set(["/login", "/api/health", "/api/ping"]);
const PUBLIC_PREFIX = "/api/auth/";

export function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.has(pathname) || pathname.startsWith(PUBLIC_PREFIX);
}

/** null: the request goes on; otherwise the answer (redirect to `/login`, 401, or 500 for a broken configuration). */
export function guardRequest(request: Request): Response | null {
  const url = new URL(request.url);
  // The load balancer's probe never depends on the sign-in configuration.
  if (url.pathname === "/api/ping") return null;
  let config;
  try {
    config = authConfigOrThrow();
  } catch (error) {
    const gatewayError = toGatewayError(error);
    return jsonResponse(gatewayError.status, gatewayError.envelope(localeOf(request)));
  }
  if (config.AUTH_MODE === "off" || isPublicPath(url.pathname) || readSession(request, config)) return null;
  if (url.pathname.startsWith("/api/")) return jsonResponse(401, unauthorized().envelope(localeOf(request)));
  const login = new URL("/login", config.APP_URL);
  login.searchParams.set("next", `${url.pathname}${url.search}`);
  return Response.redirect(login, 307);
}
