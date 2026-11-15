/** Browser-side calls to `/api/tldoole`, validated with the tldoole schemas. */
import type { z } from "zod";
import { ErrorEnvelopeSchema, FeedSchema, FeedbackSchema, RequestResultSchema, type TldooleRequest } from "./types";

export class TldooleError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "TldooleError";
  }
}

async function call<T>(request: TldooleRequest, schema: z.ZodType<T>, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch("/api/tldoole", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new TldooleError("network", "Le serveur local ne répond pas.");
  }
  const json: unknown = await response.json().catch(() => null);
  const failure = ErrorEnvelopeSchema.safeParse(json);
  if (failure.success) throw new TldooleError(failure.data.error.code, failure.data.error.message);
  const parsed = schema.safeParse(json);
  if (!parsed.success) throw new TldooleError("invalid_response", "Réponse tldoole inattendue.");
  return parsed.data;
}

export const tldoole = {
  feed: (clientId: string, signal?: AbortSignal) => call({ action: "feed", client_id: clientId }, FeedSchema, signal),
  feedback: (clientId: string, videoId: string, input: { verdict?: "understood" | "unclear"; quiz_answer?: number }) =>
    call({ action: "feedback", client_id: clientId, video_id: videoId, ...input }, FeedbackSchema),
  request: (clientId: string, conceptId: string) =>
    call({ action: "request", client_id: clientId, concept_id: conceptId }, RequestResultSchema),
};
