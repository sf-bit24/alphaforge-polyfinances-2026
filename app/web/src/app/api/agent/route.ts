import { handleAgent } from "@/lib/server/gateway";

export const dynamic = "force-dynamic";

/** Gateway to the `profile` runtime: every action of CONTRACTS.md 3.2, JSON or SSE. */
export async function POST(request: Request): Promise<Response> {
  return handleAgent(request);
}
