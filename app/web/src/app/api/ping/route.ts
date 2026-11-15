export const dynamic = "force-dynamic";

/** Liveness of the Next.js server for the load balancer: no AWS call (`/api/health` opens an AgentCore session). */
export function GET(): Response {
  return Response.json({ ok: true });
}
