import { invokeTldoole } from "@/lib/tldoole/server";
import { TldooleRequestSchema } from "@/lib/tldoole/types";

export const dynamic = "force-dynamic";

/** Gateway to the `tldoole` runtime: `feed`, `feedback`, `request` (CONTRACTS.md 8). */
export async function POST(request: Request): Promise<Response> {
  let json: unknown;
  try {
    json = await request.json();
  } catch {
    return Response.json({ ok: false, release: null, error: { code: "bad_request", message: "JSON invalide." } }, { status: 400 });
  }
  const parsed = TldooleRequestSchema.safeParse(json);
  if (!parsed.success) {
    return Response.json(
      { ok: false, release: null, error: { code: "bad_request", message: "Requête tldoole invalide.", details: parsed.error.issues } },
      { status: 400 },
    );
  }
  const upstream = await invokeTldoole(parsed.data, request.signal);
  return Response.json(upstream.body, { status: upstream.status >= 400 ? upstream.status : 200 });
}
