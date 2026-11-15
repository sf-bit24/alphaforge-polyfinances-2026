import { handlePortfolio } from "@/lib/server/gateway";

export const dynamic = "force-dynamic";

/** Gateway to the `portfolio` runtime: the `build` action of CONTRACTS.md 12 (JSON only). */
export async function POST(request: Request): Promise<Response> {
  return handlePortfolio(request);
}
