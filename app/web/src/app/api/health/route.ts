import { handleHealth } from "@/lib/server/gateway";

export const dynamic = "force-dynamic";

/** Mode of the gateway and `health` answer of the runtime. */
export async function GET(request: Request): Promise<Response> {
  return handleHealth(request);
}
