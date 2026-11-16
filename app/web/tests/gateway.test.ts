import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { MAX_BODY_BYTES, UPLOAD_LIMITS } from "@/lib/contract/requests";
import { ClientState, ErrorEnvelope, StreamEvent } from "@/lib/contract/schemas";
import { handleAgent, handleCollectPost, validateAgentRequest } from "@/lib/server/gateway";
import { GatewayError } from "@/lib/server/errors";
import { SseParser, decodeAgentEvents } from "@/lib/sse";

const CLIENT = "8f0c3a8e-5d7b-4e2a-9f51-2c6d3b1a7e90";
const OTHER = "0f1e2d3c-4b5a-4968-8776-655443322110";

function expectGatewayError(run: () => unknown, code: string) {
  try {
    run();
  } catch (error) {
    expect(error).toBeInstanceOf(GatewayError);
    expect((error as GatewayError).code).toBe(code);
    return error as GatewayError;
  }
  throw new Error("expected a GatewayError");
}

describe("gateway request validation", () => {
  it("refuses unknown actions and missing fields", () => {
    expectGatewayError(() => validateAgentRequest({ action: "portfolio.delete" }), "unknown_action");
    expectGatewayError(() => validateAgentRequest({ nothing: true }), "bad_request");
    expectGatewayError(() => validateAgentRequest({ action: "base.answer", client_id: CLIENT }), "bad_request");
    expectGatewayError(() => validateAgentRequest({ action: "session.start", locale: "de" }), "bad_request");
  });

  it("names a new client on session.start so the AgentCore session is the client", () => {
    const request = validateAgentRequest({ action: "session.start", locale: "fr" });
    expect(request).toMatchObject({ action: "session.start" });
    expect("client_id" in request && request.client_id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("strips fields outside the contract, and `stream` from non-streamable actions", () => {
    const request = validateAgentRequest({ action: "portfolio.skip", client_id: CLIENT, stream: true, admin: true });
    expect(request).toEqual({ action: "portfolio.skip", client_id: CLIENT });
  });

  it("enforces upload limits: 5 files, 10 MB each, valid base64, text or file", () => {
    const file = (bytes: number) => ({ name: "a.csv", media_type: "text/csv", data_base64: Buffer.alloc(bytes, 65).toString("base64") });
    expectGatewayError(
      () => validateAgentRequest({ action: "portfolio.submit", client_id: CLIENT, files: Array.from({ length: 6 }, () => file(10)) }),
      "bad_request",
    );
    const tooBig = expectGatewayError(
      () => validateAgentRequest({ action: "portfolio.submit", client_id: CLIENT, files: [file(UPLOAD_LIMITS.maxFileBytes + 1)] }),
      "bad_request",
    );
    expect(tooBig.text.en).toMatch(/10 MB/);
    expectGatewayError(
      () => validateAgentRequest({ action: "portfolio.submit", client_id: CLIENT, files: [{ name: "a", media_type: "", data_base64: "not base64!" }] }),
      "bad_request",
    );
    expectGatewayError(() => validateAgentRequest({ action: "portfolio.submit", client_id: CLIENT, text: "   " }), "bad_request");
    const ok = validateAgentRequest({ action: "portfolio.submit", client_id: CLIENT, files: [{ ...file(UPLOAD_LIMITS.maxFileBytes), media_type: "" }] });
    expect(ok.action === "portfolio.submit" && ok.files?.[0]?.media_type).toBe("application/octet-stream");
  });

  it("serves clients/ keys only with the matching client_id, and refuses path traversal", () => {
    expectGatewayError(() => validateAgentRequest({ action: "kb.get", key: `clients/${CLIENT}/profil.md` }), "bad_request");
    expectGatewayError(() => validateAgentRequest({ action: "kb.get", key: `clients/${CLIENT}/profil.md`, client_id: OTHER }), "bad_request");
    expectGatewayError(() => validateAgentRequest({ action: "kb.get", key: "general/../clients/x.md" }), "bad_request");
    expectGatewayError(() => validateAgentRequest({ action: "kb.list", prefix: "staging/" }), "bad_request");
    expect(validateAgentRequest({ action: "kb.get", key: `clients/${CLIENT}/profil.md`, client_id: CLIENT }).action).toBe("kb.get");
    expect(validateAgentRequest({ action: "kb.list", prefix: "general/" }).action).toBe("kb.list");
  });
});

describe("gateway in mock mode", () => {
  const previous = process.env.AGENT_MODE;
  beforeEach(() => {
    process.env.AGENT_MODE = "mock";
  });
  afterEach(() => {
    process.env.AGENT_MODE = previous;
  });

  const post = (body: unknown, headers: Record<string, string> = {}) =>
    handleAgent(new Request("http://localhost/api/agent", { method: "POST", body: JSON.stringify(body), headers: { "content-type": "application/json", ...headers } }));

  it("returns a ClientState, and contract error codes with HTTP statuses", async () => {
    const started = await post({ action: "session.start", locale: "fr" });
    expect(started.status).toBe(200);
    const state = ClientState.parse(await started.json());
    const conflict = await post({ action: "base.answer", client_id: state.client_id, question_id: "q_goal", value: "growth" });
    expect(conflict.status).toBe(409);
    expect(ErrorEnvelope.parse(await conflict.json()).error.code).toBe("conflict");
    const unknown = await post({ action: "drop.tables" }, { "x-alphaforge-locale": "en" });
    expect(unknown.status).toBe(400);
    const body = ErrorEnvelope.parse(await unknown.json());
    expect(body.error).toMatchObject({ code: "unknown_action", message: "This action is not available.", details: { action: "drop.tables" } });
    expect(body.release).toBeNull();
  });

  it("refuses an oversized body before reading it", async () => {
    const response = await handleAgent(
      new Request("http://localhost/api/agent", {
        method: "POST",
        body: "{}",
        headers: { "content-type": "application/json", "content-length": String(MAX_BODY_BYTES + 1) },
      }),
    );
    expect(response.status).toBe(413);
  });

  it("streams SSE for followup.reply with stream: true", async () => {
    const started = ClientState.parse(await (await post({ action: "session.start", locale: "fr" })).json());
    const response = await post({ action: "followup.reply", client_id: started.client_id, stream: true });
    expect(response.headers.get("content-type")).toMatch(/text\/event-stream/);
    expect(response.headers.get("cache-control")).toMatch(/no-transform/);
    const parser = new SseParser();
    const messages = [...parser.push(await response.text()), ...parser.finish()];
    const events = messages.flatMap(decodeAgentEvents).map((event) => (event.ok ? StreamEvent.parse(event.event) : null));
    expect(events.at(-1)).toMatchObject({ type: "error", error: { code: "conflict" } });
  });

  it("starts a collection without a run_id or a name", async () => {
    const response = await handleCollectPost(
      new Request("http://localhost/api/collect", { method: "POST", body: JSON.stringify({ since: "2026-11-07", run_id: "2026-11-14T10:00:00" }) }),
    );
    const body = (await response.json()) as { ok: boolean; execution: { name: string } };
    expect(body.ok).toBe(true);
    expect(body.execution.name).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  });
});
