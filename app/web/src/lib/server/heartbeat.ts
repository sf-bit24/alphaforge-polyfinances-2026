import "server-only";

/**
 * A slow JSON answer kept alive with spaces. CloudFront cuts an origin that stays silent for
 * `origin_read_timeout` (60 s, the maximum without a quota increase, `infrastructure/infra/web.tf`)
 * and answers 504; a portfolio build in `llm` mode takes about two minutes. Past `afterMs` the
 * gateway answers 200 at once, writes a space every `everyMs`, then the JSON envelope:
 * `JSON.parse` skips leading whitespace, and the browser reads errors from the envelope.
 */

/** How long the gateway waits for the runtime before it switches to the streamed answer. */
export const HEARTBEAT_AFTER_MS = 20_000;
/** One space this often while the runtime works: well under CloudFront's 60 s. */
export const HEARTBEAT_EVERY_MS = 15_000;

export const HEARTBEAT_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  // `no-transform` keeps the Next.js compression layer from holding the spaces back.
  "cache-control": "no-cache, no-transform",
  "x-accel-buffering": "no",
} as const;

export interface HeartbeatOptions {
  /** The answer to write when the work fails, formatted like the gateway's other errors. */
  fallback: (error: unknown) => Response;
  /** The browser's request: once it is aborted, the stream stops. */
  signal?: AbortSignal;
  afterMs?: number;
  everyMs?: number;
}

/** A space now and every `everyMs`, then the body of `answer`, then the end of the stream. */
function heartbeatStream(answer: Promise<Response>, options: HeartbeatOptions): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const { signal, fallback } = options;
  let interval: ReturnType<typeof setInterval> | undefined;
  let finished = false;
  let onAbort = () => {};
  const stop = () => {
    finished = true;
    clearInterval(interval);
    signal?.removeEventListener("abort", onAbort);
  };
  return new ReadableStream<Uint8Array>({
    start(controller) {
      const end = (body?: string) => {
        if (finished) return;
        stop();
        if (body !== undefined) controller.enqueue(encoder.encode(body));
        controller.close();
      };
      const space = () => controller.enqueue(encoder.encode(" "));
      onAbort = () => end();
      space();
      interval = setInterval(space, options.everyMs ?? HEARTBEAT_EVERY_MS);
      signal?.addEventListener("abort", onAbort, { once: true });
      if (signal?.aborted) end();
      const text = answer.then((response) => response.text()).catch((error: unknown) => fallback(error).text());
      void text.then(end);
    },
    // The browser went away: no more spaces, and the late answer is dropped.
    cancel: stop,
  });
}

/**
 * The answer of `work` as is when it comes within `afterMs` (same status, same body); otherwise
 * a 200 stream of spaces that ends with its JSON body. A rejection of `work` becomes `fallback`.
 */
export async function withHeartbeat(work: Promise<Response>, options: HeartbeatOptions): Promise<Response> {
  const answer = work.catch(options.fallback);
  let timer: ReturnType<typeof setTimeout> | undefined;
  const late = new Promise<null>((resolve) => {
    timer = setTimeout(() => resolve(null), options.afterMs ?? HEARTBEAT_AFTER_MS);
  });
  const early = await Promise.race([answer, late]);
  clearTimeout(timer);
  if (early) return early;
  return new Response(heartbeatStream(answer, options), { status: 200, headers: HEARTBEAT_HEADERS });
}
