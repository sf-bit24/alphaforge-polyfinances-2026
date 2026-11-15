import "server-only";

/** What a runtime answered: a JSON body, or an SSE byte stream to pass through. */
export type Upstream =
  | { kind: "json"; status: number; body: unknown }
  | { kind: "stream"; body: ReadableStream<Uint8Array> };

export const SSE_HEADERS = {
  "content-type": "text/event-stream; charset=utf-8",
  // `no-transform` keeps the Next.js compression layer from buffering events.
  "cache-control": "no-cache, no-transform",
  "x-accel-buffering": "no",
  connection: "keep-alive",
} as const;

export function sseResponse(body: ReadableStream<Uint8Array>): Response {
  return new Response(body, { status: 200, headers: SSE_HEADERS });
}

/** Encode an async iterable of contract events as an SSE byte stream. */
export function sseStreamOf(events: AsyncGenerator<unknown>): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      try {
        const { value, done } = await events.next();
        if (done) {
          controller.close();
          return;
        }
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(value)}\n\n`));
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify({ type: "error", error: { code: "internal", message } })}\n\n`),
        );
        controller.close();
      }
    },
    async cancel() {
      await events.return(undefined);
    },
  });
}
