import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ErrorEnvelope } from "@/lib/contract/schemas";
import { handlePortfolio } from "@/lib/server/gateway";
import { HEARTBEAT_AFTER_MS, HEARTBEAT_EVERY_MS } from "@/lib/server/heartbeat";

/**
 * CloudFront cuts an origin silent for 60 s: a slow build is answered 200 at once, kept alive with
 * spaces, and ends with the JSON envelope. A fast answer keeps its status and body.
 */

const CLIENT = "8f0c3a8e-5d7b-4e2a-9f51-2c6d3b1a7e90";
const SUCCESS = { ok: true, simulation_only: true, persona: "amira", decision: { decision_id: "d-1" } };
const NOT_FOUND = { ok: false, release: "r1", error: { code: "not_found", message: "Profil introuvable.", details: {} } };

interface Deferred {
  /** Settles once the gateway has called the runtime. */
  called: Promise<void>;
  resolve: (response: Response) => void;
}

/** A local runtime that answers when the test says so (or fails when the request is aborted). */
function slowRuntime(): Deferred {
  let markCalled = () => {};
  const deferred: Deferred = { called: new Promise((resolve) => (markCalled = resolve)), resolve: () => {} };
  vi.stubGlobal(
    "fetch",
    vi.fn(
      (_url: string, init?: RequestInit) =>
        new Promise<Response>((resolve, reject) => {
          deferred.resolve = resolve;
          init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
          markCalled();
        }),
    ),
  );
  return deferred;
}

/** Put an environment variable back, removing it if it was not set. */
function restoreEnv(name: string, value: string | undefined): void {
  if (value === undefined) delete process.env[name];
  else process.env[name] = value;
}

const runtimeJson = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const post = (signal?: AbortSignal) =>
  handlePortfolio(
    new Request("http://localhost/api/portfolio", {
      method: "POST",
      body: JSON.stringify({ action: "build", client_id: CLIENT, mode: "llm" }),
      headers: { "content-type": "application/json", "x-alphaforge-locale": "en" },
      signal,
    }),
  );

/** The gateway's answer once it has switched to the stream (fake time moved past the wait). */
async function switched(signal?: AbortSignal): Promise<Response> {
  const pending = post(signal);
  await vi.advanceTimersByTimeAsync(HEARTBEAT_AFTER_MS);
  return pending;
}

async function readChunk(reader: ReadableStreamDefaultReader<Uint8Array>): Promise<string> {
  const { value, done } = await reader.read();
  return done ? "" : new TextDecoder().decode(value);
}

async function readRest(reader: ReadableStreamDefaultReader<Uint8Array>): Promise<string> {
  const decoder = new TextDecoder();
  let text = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return text + decoder.decode();
    text += decoder.decode(value, { stream: true });
  }
}

describe("portfolio gateway kept alive past CloudFront's 60 s", () => {
  const previous = { mode: process.env.AGENT_MODE, url: process.env.LOCAL_PORTFOLIO_URL };
  beforeEach(() => {
    process.env.AGENT_MODE = "local";
    process.env.LOCAL_PORTFOLIO_URL = "http://127.0.0.1:8081/invocations";
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    restoreEnv("AGENT_MODE", previous.mode);
    restoreEnv("LOCAL_PORTFOLIO_URL", previous.url);
  });

  it("waits less than CloudFront's limit and beats well under it", () => {
    expect(HEARTBEAT_AFTER_MS).toBeLessThan(60_000);
    expect(HEARTBEAT_EVERY_MS).toBeLessThanOrEqual(30_000);
  });

  it("passes a fast answer through unchanged: status, headers and body", async () => {
    const runtime = slowRuntime();
    const pending = post();
    await runtime.called;
    await vi.advanceTimersByTimeAsync(1_000);
    runtime.resolve(runtimeJson(404, NOT_FOUND));
    const response = await pending;
    expect(response.status).toBe(404);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.text()).toBe(JSON.stringify(NOT_FOUND));
    expect(vi.getTimerCount()).toBe(0);

    const fast = slowRuntime();
    const success = post();
    await fast.called;
    fast.resolve(runtimeJson(200, SUCCESS));
    const ok = await success;
    expect(ok.status).toBe(200);
    expect(await ok.json()).toEqual(SUCCESS);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("keeps a fast gateway error (no runtime) unchanged", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("fetch failed"))));
    const response = await post();
    expect(response.status).toBe(502);
    expect(ErrorEnvelope.parse(await response.json()).error.code).toBe("internal");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("answers a slow build 200 at once, spaces first, then the envelope", async () => {
    const runtime = slowRuntime();
    const response = await switched();
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/json; charset=utf-8");
    expect(response.headers.get("cache-control")).toBe("no-cache, no-transform");
    expect(response.headers.get("x-accel-buffering")).toBe("no");
    expect(response.headers.get("content-length")).toBeNull();

    const reader = response.body!.getReader();
    expect(await readChunk(reader)).toBe(" ");
    await vi.advanceTimersByTimeAsync(HEARTBEAT_EVERY_MS);
    expect(await readChunk(reader)).toBe(" ");
    await vi.advanceTimersByTimeAsync(HEARTBEAT_EVERY_MS * 4);
    runtime.resolve(runtimeJson(200, SUCCESS));
    const text = "  " + (await readRest(reader));
    expect(text).toMatch(/^ {2,}\{/);
    expect(JSON.parse(text)).toEqual(SUCCESS);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("writes a runtime error envelope that comes after the switch", async () => {
    const runtime = slowRuntime();
    const response = await switched();
    runtime.resolve(runtimeJson(404, NOT_FOUND));
    const text = await response.text();
    expect(response.status).toBe(200);
    expect(text).toMatch(/^ +\{/);
    expect(JSON.parse(text)).toEqual(NOT_FOUND);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("formats an error thrown after the switch like the gateway's other errors", async () => {
    const runtime = slowRuntime();
    const response = await switched();
    await vi.advanceTimersByTimeAsync(HEARTBEAT_EVERY_MS);
    runtime.resolve(new Response("<html>upstream</html>", { status: 504 }));
    const text = await response.text();
    expect(text).toMatch(/^ {2,}\{/);
    const envelope = ErrorEnvelope.parse(JSON.parse(text));
    expect(envelope.error.code).toBe("internal");
    expect(envelope.error.message).toMatch(/HTTP 504/);
    expect(envelope.error.details).toMatchObject({ source: "gateway" });
    expect(vi.getTimerCount()).toBe(0);
  });

  it("stops beating when the browser aborts the request", async () => {
    slowRuntime();
    const controller = new AbortController();
    const response = await switched(controller.signal);
    const reader = response.body!.getReader();
    expect(await readChunk(reader)).toBe(" ");
    controller.abort();
    expect(await readRest(reader)).toBe("");
    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(HEARTBEAT_EVERY_MS * 3);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("stops beating when the stream is cancelled", async () => {
    const runtime = slowRuntime();
    const response = await switched();
    await response.body!.cancel();
    expect(vi.getTimerCount()).toBe(0);
    runtime.resolve(runtimeJson(200, SUCCESS));
    await vi.advanceTimersByTimeAsync(HEARTBEAT_EVERY_MS);
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("portfolio gateway in mock mode", () => {
  const previous = process.env.AGENT_MODE;
  beforeEach(() => {
    process.env.AGENT_MODE = "mock";
  });
  afterEach(() => restoreEnv("AGENT_MODE", previous));

  it("answers the fixture as plain JSON, without the stream", async () => {
    const response = await handlePortfolio(
      new Request("http://localhost/api/portfolio", { method: "POST", body: JSON.stringify({ action: "build", persona: "amira" }) }),
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    const text = await response.text();
    expect(text.startsWith("{")).toBe(true);
    expect(JSON.parse(text)).toMatchObject({ ok: true, persona: "amira" });
  });
});
