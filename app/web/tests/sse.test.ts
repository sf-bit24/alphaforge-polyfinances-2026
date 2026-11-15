import { describe, expect, it } from "vitest";
import { decodeAgentEvents, encodeSseEvent, readAgentEvents, SseParser } from "@/lib/sse";
import * as examples from "./fixtures/contract-examples";

const trace = { type: "trace", step: examples.traceStep };
const delta = { type: "delta", text: "morceau du message de l'agent" };
const result = { type: "result", result: examples.clientState };

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function collect(chunks: string[]) {
  const out = [];
  for await (const event of readAgentEvents(streamOf(chunks))) out.push(event);
  return out;
}

describe("SseParser", () => {
  it("parses events separated by blank lines", () => {
    const parser = new SseParser();
    const messages = parser.push(`data: {"a":1}\n\ndata: {"b":2}\n\n`);
    expect(messages.map((message) => message.data)).toEqual(['{"a":1}', '{"b":2}']);
  });

  it("handles chunks split anywhere, including inside a CRLF", () => {
    const parser = new SseParser();
    const text = `data: {"a":1}\r\n\r\ndata: {"b":2}\r\n\r\n`;
    const messages = [];
    for (const char of text) messages.push(...parser.push(char));
    messages.push(...parser.finish());
    expect(messages.map((message) => message.data)).toEqual(['{"a":1}', '{"b":2}']);
  });

  it("supports CR line ends, comments, event names, ids and multi-line data", () => {
    const parser = new SseParser();
    const messages = [
      ...parser.push(": keep-alive\revent: custom\rid: 7\rdata: line one\rdata: line two\r\r"),
      ...parser.finish(),
    ];
    expect(messages).toEqual([{ event: "custom", data: "line one\nline two", id: "7" }]);
  });

  it("accepts `data:` without a space and ignores retry and unknown fields", () => {
    const parser = new SseParser();
    const messages = [...parser.push("retry: 1000\nfoo: bar\ndata:{\"x\":1}\n\n"), ...parser.finish()];
    expect(messages.map((message) => message.data)).toEqual(['{"x":1}']);
  });

  it("delivers a last event that has no trailing blank line", () => {
    const parser = new SseParser();
    expect(parser.push('data: {"last":true}')).toEqual([]);
    expect(parser.finish().map((message) => message.data)).toEqual(['{"last":true}']);
  });
});

describe("contract events", () => {
  it("decodes trace, delta and result events across chunk boundaries", async () => {
    const wire = [trace, delta, result].map((event) => `data: ${JSON.stringify(event)}\n\n`).join("");
    const chunks = [wire.slice(0, 17), wire.slice(17, 400), wire.slice(400)];
    const events = await collect(chunks);
    expect(events.every((event) => event.ok)).toBe(true);
    expect(events.map((event) => (event.ok ? event.event.type : "invalid"))).toEqual(["trace", "delta", "result"]);
  });

  it("accepts one JSON event per data line without blank lines between them", () => {
    const decoded = decodeAgentEvents({ event: "message", id: null, data: `${JSON.stringify(delta)}\n${JSON.stringify(trace)}` });
    expect(decoded.map((event) => (event.ok ? event.event.type : "invalid"))).toEqual(["delta", "trace"]);
  });

  it("reports events outside the contract instead of throwing", () => {
    const [invalid] = decodeAgentEvents({ event: "message", id: null, data: '{"type":"trace","step":{"id":"x"}}' });
    expect(invalid?.ok).toBe(false);
    const [notJson] = decodeAgentEvents({ event: "message", id: null, data: "hello" });
    expect(notJson).toMatchObject({ ok: false, reason: "not JSON" });
  });

  it("skips empty and [DONE] messages", () => {
    expect(decodeAgentEvents({ event: "message", id: null, data: "[DONE]" })).toEqual([]);
    expect(decodeAgentEvents({ event: "message", id: null, data: "  " })).toEqual([]);
  });

  it("round-trips with the encoder", async () => {
    const error = { type: "error", error: { code: "model_error", message: "…" } } as const;
    const events = await collect([encodeSseEvent(error)]);
    expect(events).toEqual([{ ok: true, event: { ...error, error: { ...error.error } } }]);
  });

  it("decodes a stream whose UTF-8 characters are split across chunks", async () => {
    const bytes = new TextEncoder().encode(`data: ${JSON.stringify({ type: "delta", text: "Évaluée à 95 %" })}\n\n`);
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
        controller.close();
      },
    });
    const events = [];
    for await (const event of readAgentEvents(stream)) events.push(event);
    expect(events).toEqual([{ ok: true, event: { type: "delta", text: "Évaluée à 95 %" } }]);
  });
});
