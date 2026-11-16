import { handleMe } from "@/lib/server/auth/routes";

export const dynamic = "force-dynamic";

/** Sign-in mode and signed-in account (CONTRACTS.md 7.1). */
export function GET(request: Request): Promise<Response> {
  return handleMe(request);
}
