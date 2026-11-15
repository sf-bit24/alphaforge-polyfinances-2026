/**
 * Server-Sent Events, as produced by the `profile` runtime (CONTRACTS.md 3.4).
 *
 * `SseParser` follows the WHATWG event-stream rules (LF, CRLF or CR line ends,
 * comments, multi-line `data:`), across arbitrary chunk boundaries. The contract
 * puts one JSON event per `data:` line, so `decodeAgentEvents` also accepts a
 * message whose data lines are separate JSON documents (a runtime that forgets
 * the blank line between events).
 */
import { StreamEvent } from "./contract/schemas";

export interface SseMessage {
  event: string;
  data: string;
  id: string | null;
}

export class SseParser {
  private buffer = "";
  private dataLines: string[] = [];
  private eventName = "";
  private lastId: string | null = null;
  private pendingCr = false;

  /** Feed a decoded text chunk; returns the messages it completed. */
  push(chunk: string): SseMessage[] {
    const out: SseMessage[] = [];
    let text = chunk;
    // A CR at the end of the previous chunk may be the first half of a CRLF.
    if (this.pendingCr && text.startsWith("\n")) text = text.slice(1);
    this.pendingCr = false;
    this.buffer += text;

    let start = 0;
    for (let i = 0; i < this.buffer.length; i += 1) {
      const ch = this.buffer[i];
      if (ch !== "\n" && ch !== "\r") continue;
      this.processLine(this.buffer.slice(start, i), out);
      if (ch === "\r") {
        if (i + 1 < this.buffer.length) {
          if (this.buffer[i + 1] === "\n") i += 1;
        } else {
          this.pendingCr = true;
        }
      }
      start = i + 1;
    }
    this.buffer = this.buffer.slice(start);
    return out;
  }

  /** End of stream: a last event without its trailing blank line is still delivered. */
  finish(): SseMessage[] {
    const out: SseMessage[] = [];
    if (this.buffer.length > 0) {
      this.processLine(this.buffer, out);
      this.buffer = "";
    }
    this.dispatch(out);
    return out;
  }

  private processLine(line: string, out: SseMessage[]): void {
    if (line === "") {
      this.dispatch(out);
      return;
    }
    if (line.startsWith(":")) return;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    switch (field) {
      case "data":
        this.dataLines.push(value);
        break;
      case "event":
        this.eventName = value;
        break;
      case "id":
        if (!value.includes("\u0000")) this.lastId = value;
        break;
      default:
        // `retry` and unknown fields are ignored.
        break;
    }
  }

  private dispatch(out: SseMessage[]): void {
    if (this.dataLines.length === 0) {
      this.eventName = "";
      return;
    }
    out.push({ event: this.eventName || "message", data: this.dataLines.join("\n"), id: this.lastId });
    this.dataLines = [];
    this.eventName = "";
  }
}

export type DecodedEvent =
  | { ok: true; event: StreamEvent }
  | { ok: false; raw: string; reason: string };

function decodeJson(raw: string): DecodedEvent {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { ok: false, raw, reason: "not JSON" };
  }
  const result = StreamEvent.safeParse(parsed);
  if (!result.success) {
    const issue = result.error.issues[0];
    const where = issue?.path.length ? issue.path.join(".") : "event";
    return { ok: false, raw, reason: `${where}: ${issue?.message ?? "invalid event"}` };
  }
  return { ok: true, event: result.data };
}

/** Turn one SSE message into contract events (usually exactly one). */
export function decodeAgentEvents(message: SseMessage): DecodedEvent[] {
  const data = message.data.trim();
  if (data === "" || data === "[DONE]") return [];
  const whole = decodeJson(data);
  if (whole.ok || !data.includes("\n")) return [whole];
  return data
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "")
    .map(decodeJson);
}

/** Encode one contract event as an SSE message. */
export function encodeSseEvent(event: StreamEvent): string {
  return `data: ${JSON.stringify(event)}\n\n`;
}

/** Read a byte stream of SSE and yield decoded contract events as they arrive. */
export async function* readAgentEvents(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<DecodedEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  let drained = false;
  try {
    while (true) {
      if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
      const { value, done } = await reader.read();
      if (done) break;
      for (const message of parser.push(decoder.decode(value, { stream: true }))) {
        yield* decodeAgentEvents(message);
      }
    }
    drained = true;
    const tail = decoder.decode();
    const messages = [...(tail ? parser.push(tail) : []), ...parser.finish()];
    for (const message of messages) yield* decodeAgentEvents(message);
  } finally {
    // Stopped early (abort, or the consumer returned): close the connection.
    if (!drained) await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
