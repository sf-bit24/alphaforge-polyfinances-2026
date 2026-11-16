import { handleLogin } from "@/lib/server/auth/routes";

export const dynamic = "force-dynamic";

/** Start a sign-in: state, nonce and PKCE in a short-lived cookie, then Cognito's managed login. */
export function GET(request: Request): Response {
  return handleLogin(request);
}
