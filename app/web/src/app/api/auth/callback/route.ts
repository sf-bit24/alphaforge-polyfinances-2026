import { handleCallback } from "@/lib/server/auth/routes";

export const dynamic = "force-dynamic";

/** Return from Cognito: exchange the code, verify the ID token, open the session cookie. */
export async function GET(request: Request): Promise<Response> {
  return handleCallback(request);
}
