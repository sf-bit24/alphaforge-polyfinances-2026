import { handleCollectGet, handleCollectPost } from "@/lib/server/gateway";

export const dynamic = "force-dynamic";

/** Recent collection runs, or one run with `?execution_arn=`. */
export async function GET(request: Request): Promise<Response> {
  return handleCollectGet(request);
}

/** Start a collection run of the general base (Step Functions). */
export async function POST(request: Request): Promise<Response> {
  return handleCollectPost(request);
}
