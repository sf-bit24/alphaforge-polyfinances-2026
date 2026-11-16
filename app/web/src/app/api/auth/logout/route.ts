import { handleLogout } from "@/lib/server/auth/routes";

export const dynamic = "force-dynamic";

/** Sign out: clear the session cookie, then Cognito's `/logout`. */
export function POST(request: Request): Response {
  return handleLogout(request);
}
