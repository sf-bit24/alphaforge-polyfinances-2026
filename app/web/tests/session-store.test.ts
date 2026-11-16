/**
 * Characterization of the client session store: every snapshot it publishes, every
 * localStorage write and every gateway call, in order, for the main flows.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, type StreamHandlers } from "@/lib/client/api";
import { SessionStore, type ConversationEntry, type SessionSnapshot, type TraceRun } from "@/lib/client/session-store";

type Reply = { state: Record<string, unknown>; steps?: unknown[]; deltas?: string[] } | { error: unknown };

const gateway = vi.hoisted(() => ({ script: [] as unknown[], log: [] as string[] }));

vi.mock("@/lib/client/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/client/api")>();
  const answer = async (name: string, request: unknown, options: unknown, handlers?: StreamHandlers) => {
    gateway.log.push(`${name} ${JSON.stringify(request)} ${JSON.stringify(options)}`);
    const reply = gateway.script.shift() as Reply | undefined;
    if (!reply) throw new Error("no scripted reply");
    if ("error" in reply) throw reply.error;
    for (const step of reply.steps ?? []) handlers?.onTrace(step as never);
    for (const text of reply.deltas ?? []) handlers?.onDelta(text);
    return reply.state;
  };
  return {
    ...actual,
    callAgent: (request: unknown, _schema: unknown, options: unknown) => answer("callAgent", request, options),
    callAgentStream: (request: unknown, handlers: StreamHandlers, options: unknown) =>
      answer("callAgentStream", request, options, handlers),
  };
});

const CLIENT = "11111111-1111-4111-8111-111111111111";
const STEP = { id: "s1", kind: "agent", title: "step" };
const QUESTION = { id: "a1_1_1", prompt: "Why?" };
const state = (overrides: Record<string, unknown> = {}) => ({
  client_id: CLIENT,
  stage: "base_questions",
  message: null,
  questions: [],
  trace: [STEP],
  ...overrides,
});

let stored: Map<string, string>;

function describeRun(run: TraceRun): string {
  const error = run.error ? `:${run.error.code}/${run.error.message}` : "";
  return `${run.id}:${run.action}:${run.status}:${run.steps.length}:${run.durationMs}${run.streamed ? ":streamed" : ""}${error}`;
}

function describeEntry(entry: ConversationEntry): string {
  if (entry.role === "user") return `${entry.id}:user:${entry.answers.length}:${entry.message}:${entry.stop}`;
  return `${entry.id}:agent:${entry.message}:${entry.questions.length}:${entry.stage}:${entry.runId}`;
}

function describeSnapshot(snapshot: SessionSnapshot): string {
  const error = snapshot.error ? `${snapshot.error.code}/${snapshot.error.message}@${snapshot.errorAction}` : "-";
  return [
    snapshot.hydrated ? "hydrated" : "dry",
    `client=${snapshot.clientId}`,
    `stage=${snapshot.state?.stage ?? "-"}`,
    `resuming=${snapshot.resuming}`,
    `pending=${snapshot.pending}`,
    `error=${error}`,
    `notice=${snapshot.notice}`,
    `stream=${JSON.stringify(snapshot.streamText)}`,
    `live=${snapshot.liveRun ? describeRun(snapshot.liveRun) : "-"}`,
    `runs=[${snapshot.runs.map(describeRun).join(" ")}]`,
    `conversation=[${snapshot.conversation.map(describeEntry).join(" ")}]`,
    `revision=${snapshot.revision}`,
  ].join(" ");
}

function newStore(): SessionStore {
  const store = new SessionStore();
  store.subscribe(() => gateway.log.push(`notify ${describeSnapshot(store.getSnapshot())}`));
  store.configure("en", { network: "Network down", invalidResponse: "Bad answer", noResult: "No result" });
  return store;
}

function script(...replies: Reply[]): void {
  gateway.script.push(...replies);
}

beforeEach(() => {
  let uuid = 0;
  let clock = 1000;
  gateway.script = [];
  gateway.log = [];
  stored = new Map();
  const localStorage = {
    getItem: (key: string) => stored.get(key) ?? null,
    setItem: (key: string, value: string) => {
      gateway.log.push(`storage.set ${key} ${value}`);
      stored.set(key, value);
    },
    removeItem: (key: string) => {
      gateway.log.push(`storage.remove ${key}`);
      stored.delete(key);
    },
  };
  vi.stubGlobal("window", { localStorage });
  vi.spyOn(globalThis.crypto, "randomUUID").mockImplementation(() => `uuid-${(uuid += 1)}` as `${string}-${string}-${string}-${string}-${string}`);
  vi.spyOn(performance, "now").mockImplementation(() => (clock += 10));
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-15T12:00:00.000Z"));
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("SessionStore", () => {
  it("starts a session, records a failure, retries it, and refuses a second request in flight", async () => {
    const store = newStore();
    await store.init();
    script({ state: state() });
    gateway.log.push(`result ${await store.start()}`);
    script({ error: new ApiError("conflict", "Busy", { at: "q_goal" }) });
    gateway.log.push(`result ${await store.answerBase("q_goal", "growth")}`);
    script({ state: state({ stage: "existing_portfolio", trace: [] }) });
    gateway.log.push(`result ${await store.retry()}`);
    gateway.log.push(`result ${await store.retry()}`);
    script({ state: state({ stage: "followups" }) }, { state: state() });
    const first = store.skipPortfolio();
    gateway.log.push(`second ${await store.confirmPortfolio([{ id: "p1", resolved: true }])}`);
    gateway.log.push(`result ${await first}`, `state ${store.getState()?.stage}`);
    expect(gateway.log).toMatchInlineSnapshot(`
      [
        "notify hydrated client=null stage=- resuming=false pending=null error=- notice=null stream="" live=- runs=[] conversation=[] revision=0",
        "notify hydrated client=null stage=- resuming=false pending=session.start error=- notice=null stream="" live=uuid-1:session.start:running:0:null runs=[] conversation=[] revision=0",
        "callAgent {"action":"session.start","locale":"en"} {"locale":"en","messages":{"network":"Network down","invalidResponse":"Bad answer","noResult":"No result"}}",
        "storage.set alphaforge.client_id 11111111-1111-4111-8111-111111111111",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=base_questions resuming=false pending=null error=- notice=null stream="" live=- runs=[uuid-1:session.start:ok:1:10] conversation=[] revision=1",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 [{"id":"uuid-1","action":"session.start","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[{"id":"s1","kind":"agent","title":"step"}],"error":null}]",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 []",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=base_questions resuming=false pending=null error=- notice=null stream="" live=- runs=[uuid-1:session.start:ok:1:10] conversation=[] revision=1",
        "result true",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=base_questions resuming=false pending=base.answer error=- notice=null stream="" live=uuid-2:base.answer:running:0:null runs=[uuid-1:session.start:ok:1:10] conversation=[] revision=1",
        "callAgent {"action":"base.answer","client_id":"11111111-1111-4111-8111-111111111111","question_id":"q_goal","value":"growth"} {"locale":"en","messages":{"network":"Network down","invalidResponse":"Bad answer","noResult":"No result"}}",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=base_questions resuming=false pending=null error=conflict/Busy@base.answer notice=null stream="" live=- runs=[uuid-2:base.answer:error:0:10:conflict/Busy uuid-1:session.start:ok:1:10] conversation=[] revision=1",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 [{"id":"uuid-2","action":"base.answer","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"error","streamed":false,"steps":[],"error":{"code":"conflict","message":"Busy"}},{"id":"uuid-1","action":"session.start","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[{"id":"s1","kind":"agent","title":"step"}],"error":null}]",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 []",
        "result false",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=base_questions resuming=false pending=base.answer error=- notice=null stream="" live=uuid-3:base.answer:running:0:null runs=[uuid-2:base.answer:error:0:10:conflict/Busy uuid-1:session.start:ok:1:10] conversation=[] revision=1",
        "callAgent {"action":"base.answer","client_id":"11111111-1111-4111-8111-111111111111","question_id":"q_goal","value":"growth"} {"locale":"en","messages":{"network":"Network down","invalidResponse":"Bad answer","noResult":"No result"}}",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=existing_portfolio resuming=false pending=null error=- notice=null stream="" live=- runs=[uuid-3:base.answer:ok:0:10 uuid-2:base.answer:error:0:10:conflict/Busy uuid-1:session.start:ok:1:10] conversation=[] revision=2",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 [{"id":"uuid-3","action":"base.answer","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[],"error":null},{"id":"uuid-2","action":"base.answer","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"error","streamed":false,"steps":[],"error":{"code":"conflict","message":"Busy"}},{"id":"uuid-1","action":"session.start","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[{"id":"s1","kind":"agent","title":"step"}],"error":null}]",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 []",
        "result true",
        "result false",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=existing_portfolio resuming=false pending=portfolio.skip error=- notice=null stream="" live=uuid-4:portfolio.skip:running:0:null runs=[uuid-3:base.answer:ok:0:10 uuid-2:base.answer:error:0:10:conflict/Busy uuid-1:session.start:ok:1:10] conversation=[] revision=2",
        "callAgent {"action":"portfolio.skip","client_id":"11111111-1111-4111-8111-111111111111"} {"locale":"en","messages":{"network":"Network down","invalidResponse":"Bad answer","noResult":"No result"}}",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=null error=- notice=null stream="" live=- runs=[uuid-4:portfolio.skip:ok:1:10 uuid-3:base.answer:ok:0:10 uuid-2:base.answer:error:0:10:conflict/Busy uuid-1:session.start:ok:1:10] conversation=[] revision=3",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 [{"id":"uuid-4","action":"portfolio.skip","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[{"id":"s1","kind":"agent","title":"step"}],"error":null},{"id":"uuid-3","action":"base.answer","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[],"error":null},{"id":"uuid-2","action":"base.answer","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"error","streamed":false,"steps":[],"error":{"code":"conflict","message":"Busy"}},{"id":"uuid-1","action":"session.start","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[{"id":"s1","kind":"agent","title":"step"}],"error":null}]",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 []",
        "second false",
        "result true",
        "state followups",
      ]
    `);
  });

  it("streams follow-up replies, adds conversation entries, and drops the optimistic entry on failure", async () => {
    const store = newStore();
    await store.init();
    script({ state: state({ stage: "followups", trace: [] }) });
    await store.start();
    gateway.log.length = 0;
    script({ state: state({ stage: "followups", message: "Tell me more", questions: [QUESTION], trace: [STEP, STEP] }), steps: [STEP, STEP], deltas: ["Tell", "Tell me more"] });
    const answers = [{ question_id: "a1_1_1", value: 3, prompt: "Why?", display: "3 / 5" }];
    gateway.log.push(`result ${await store.reply({ answers, message: "  because  " })}`);
    script({ state: state({ stage: "followups", message: null, questions: [], trace: [] }) });
    gateway.log.push(`result ${await store.reply({})}`);
    script({ error: new Error("boom") });
    gateway.log.push(`result ${await store.reply({ message: "again" })}`);
    script({ error: new DOMException("The user aborted", "AbortError") });
    gateway.log.push(`result ${await store.reply({ stop: true })}`);
    script({ error: "plain failure" });
    gateway.log.push(`result ${await store.submitPortfolio({ text: "  ", files: [] })}`);
    script({ state: state({ stage: "portfolio_review" }), steps: [STEP] });
    const files = [{ name: "a.csv", media_type: "text/csv", data_base64: "QQ==" }];
    gateway.log.push(`result ${await store.submitPortfolio({ text: "100 RY.TO", files })}`);
    expect(gateway.log).toMatchInlineSnapshot(`
      [
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=followup.reply error=- notice=null stream="" live=uuid-3:followup.reply:running:0:null:streamed runs=[uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false] revision=1",
        "callAgentStream {"action":"followup.reply","client_id":"11111111-1111-4111-8111-111111111111","answers":[{"question_id":"a1_1_1","value":3}],"message":"because"} {"locale":"en","messages":{"network":"Network down","invalidResponse":"Bad answer","noResult":"No result"}}",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=followup.reply error=- notice=null stream="" live=uuid-3:followup.reply:running:1:null:streamed runs=[uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false] revision=1",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=followup.reply error=- notice=null stream="" live=uuid-3:followup.reply:running:2:null:streamed runs=[uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false] revision=1",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=followup.reply error=- notice=null stream="Tell" live=uuid-3:followup.reply:running:2:null:streamed runs=[uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false] revision=1",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=followup.reply error=- notice=null stream="Tell me more" live=uuid-3:followup.reply:running:2:null:streamed runs=[uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false] revision=1",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=null error=- notice=null stream="" live=- runs=[uuid-3:followup.reply:ok:2:10:streamed uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false uuid-4:agent:Tell me more:1:followups:uuid-3] revision=2",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 [{"id":"uuid-3","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":true,"steps":[{"id":"s1","kind":"agent","title":"step"},{"id":"s1","kind":"agent","title":"step"}],"error":null},{"id":"uuid-1","action":"session.start","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[],"error":null}]",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 [{"id":"uuid-2","role":"user","at":"2026-11-15T12:00:00.000Z","answers":[{"question_id":"a1_1_1","prompt":"Why?","display":"3 / 5"}],"message":"because","stop":false},{"id":"uuid-4","role":"agent","at":"2026-11-15T12:00:00.000Z","message":"Tell me more","questions":[{"id":"a1_1_1","prompt":"Why?"}],"stage":"followups","runId":"uuid-3"}]",
        "result true",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=followup.reply error=- notice=null stream="" live=uuid-5:followup.reply:running:0:null:streamed runs=[uuid-3:followup.reply:ok:2:10:streamed uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false uuid-4:agent:Tell me more:1:followups:uuid-3] revision=2",
        "callAgentStream {"action":"followup.reply","client_id":"11111111-1111-4111-8111-111111111111"} {"locale":"en","messages":{"network":"Network down","invalidResponse":"Bad answer","noResult":"No result"}}",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=null error=- notice=null stream="" live=- runs=[uuid-5:followup.reply:ok:0:10:streamed uuid-3:followup.reply:ok:2:10:streamed uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false uuid-4:agent:Tell me more:1:followups:uuid-3] revision=3",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 [{"id":"uuid-5","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":true,"steps":[],"error":null},{"id":"uuid-3","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":true,"steps":[{"id":"s1","kind":"agent","title":"step"},{"id":"s1","kind":"agent","title":"step"}],"error":null},{"id":"uuid-1","action":"session.start","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[],"error":null}]",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 [{"id":"uuid-2","role":"user","at":"2026-11-15T12:00:00.000Z","answers":[{"question_id":"a1_1_1","prompt":"Why?","display":"3 / 5"}],"message":"because","stop":false},{"id":"uuid-4","role":"agent","at":"2026-11-15T12:00:00.000Z","message":"Tell me more","questions":[{"id":"a1_1_1","prompt":"Why?"}],"stage":"followups","runId":"uuid-3"}]",
        "result true",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=followup.reply error=- notice=null stream="" live=uuid-7:followup.reply:running:0:null:streamed runs=[uuid-5:followup.reply:ok:0:10:streamed uuid-3:followup.reply:ok:2:10:streamed uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false uuid-4:agent:Tell me more:1:followups:uuid-3 uuid-6:user:0:again:false] revision=3",
        "callAgentStream {"action":"followup.reply","client_id":"11111111-1111-4111-8111-111111111111","message":"again"} {"locale":"en","messages":{"network":"Network down","invalidResponse":"Bad answer","noResult":"No result"}}",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=null error=internal/boom@followup.reply notice=null stream="" live=- runs=[uuid-7:followup.reply:error:0:10:streamed:internal/boom uuid-5:followup.reply:ok:0:10:streamed uuid-3:followup.reply:ok:2:10:streamed uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false uuid-4:agent:Tell me more:1:followups:uuid-3] revision=3",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 [{"id":"uuid-7","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"error","streamed":true,"steps":[],"error":{"code":"internal","message":"boom"}},{"id":"uuid-5","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":true,"steps":[],"error":null},{"id":"uuid-3","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":true,"steps":[{"id":"s1","kind":"agent","title":"step"},{"id":"s1","kind":"agent","title":"step"}],"error":null},{"id":"uuid-1","action":"session.start","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[],"error":null}]",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 [{"id":"uuid-2","role":"user","at":"2026-11-15T12:00:00.000Z","answers":[{"question_id":"a1_1_1","prompt":"Why?","display":"3 / 5"}],"message":"because","stop":false},{"id":"uuid-4","role":"agent","at":"2026-11-15T12:00:00.000Z","message":"Tell me more","questions":[{"id":"a1_1_1","prompt":"Why?"}],"stage":"followups","runId":"uuid-3"}]",
        "result false",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=followup.reply error=- notice=null stream="" live=uuid-9:followup.reply:running:0:null:streamed runs=[uuid-7:followup.reply:error:0:10:streamed:internal/boom uuid-5:followup.reply:ok:0:10:streamed uuid-3:followup.reply:ok:2:10:streamed uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false uuid-4:agent:Tell me more:1:followups:uuid-3 uuid-8:user:0:null:true] revision=3",
        "callAgentStream {"action":"followup.reply","client_id":"11111111-1111-4111-8111-111111111111","stop":true} {"locale":"en","messages":{"network":"Network down","invalidResponse":"Bad answer","noResult":"No result"}}",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=null error=aborted/Aborted@followup.reply notice=null stream="" live=- runs=[uuid-9:followup.reply:error:0:10:streamed:aborted/Aborted uuid-7:followup.reply:error:0:10:streamed:internal/boom uuid-5:followup.reply:ok:0:10:streamed uuid-3:followup.reply:ok:2:10:streamed uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false uuid-4:agent:Tell me more:1:followups:uuid-3] revision=3",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 [{"id":"uuid-9","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"error","streamed":true,"steps":[],"error":{"code":"aborted","message":"Aborted"}},{"id":"uuid-7","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"error","streamed":true,"steps":[],"error":{"code":"internal","message":"boom"}},{"id":"uuid-5","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":true,"steps":[],"error":null},{"id":"uuid-3","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":true,"steps":[{"id":"s1","kind":"agent","title":"step"},{"id":"s1","kind":"agent","title":"step"}],"error":null},{"id":"uuid-1","action":"session.start","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[],"error":null}]",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 [{"id":"uuid-2","role":"user","at":"2026-11-15T12:00:00.000Z","answers":[{"question_id":"a1_1_1","prompt":"Why?","display":"3 / 5"}],"message":"because","stop":false},{"id":"uuid-4","role":"agent","at":"2026-11-15T12:00:00.000Z","message":"Tell me more","questions":[{"id":"a1_1_1","prompt":"Why?"}],"stage":"followups","runId":"uuid-3"}]",
        "result false",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=portfolio.submit error=- notice=null stream="" live=uuid-10:portfolio.submit:running:0:null:streamed runs=[uuid-9:followup.reply:error:0:10:streamed:aborted/Aborted uuid-7:followup.reply:error:0:10:streamed:internal/boom uuid-5:followup.reply:ok:0:10:streamed uuid-3:followup.reply:ok:2:10:streamed uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false uuid-4:agent:Tell me more:1:followups:uuid-3] revision=3",
        "callAgentStream {"action":"portfolio.submit","client_id":"11111111-1111-4111-8111-111111111111"} {"locale":"en","messages":{"network":"Network down","invalidResponse":"Bad answer","noResult":"No result"}}",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=null error=internal/plain failure@portfolio.submit notice=null stream="" live=- runs=[uuid-10:portfolio.submit:error:0:10:streamed:internal/plain failure uuid-9:followup.reply:error:0:10:streamed:aborted/Aborted uuid-7:followup.reply:error:0:10:streamed:internal/boom uuid-5:followup.reply:ok:0:10:streamed uuid-3:followup.reply:ok:2:10:streamed uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false uuid-4:agent:Tell me more:1:followups:uuid-3] revision=3",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 [{"id":"uuid-10","action":"portfolio.submit","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"error","streamed":true,"steps":[],"error":{"code":"internal","message":"plain failure"}},{"id":"uuid-9","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"error","streamed":true,"steps":[],"error":{"code":"aborted","message":"Aborted"}},{"id":"uuid-7","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"error","streamed":true,"steps":[],"error":{"code":"internal","message":"boom"}},{"id":"uuid-5","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":true,"steps":[],"error":null},{"id":"uuid-3","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":true,"steps":[{"id":"s1","kind":"agent","title":"step"},{"id":"s1","kind":"agent","title":"step"}],"error":null},{"id":"uuid-1","action":"session.start","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[],"error":null}]",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 [{"id":"uuid-2","role":"user","at":"2026-11-15T12:00:00.000Z","answers":[{"question_id":"a1_1_1","prompt":"Why?","display":"3 / 5"}],"message":"because","stop":false},{"id":"uuid-4","role":"agent","at":"2026-11-15T12:00:00.000Z","message":"Tell me more","questions":[{"id":"a1_1_1","prompt":"Why?"}],"stage":"followups","runId":"uuid-3"}]",
        "result false",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=portfolio.submit error=- notice=null stream="" live=uuid-11:portfolio.submit:running:0:null:streamed runs=[uuid-10:portfolio.submit:error:0:10:streamed:internal/plain failure uuid-9:followup.reply:error:0:10:streamed:aborted/Aborted uuid-7:followup.reply:error:0:10:streamed:internal/boom uuid-5:followup.reply:ok:0:10:streamed uuid-3:followup.reply:ok:2:10:streamed uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false uuid-4:agent:Tell me more:1:followups:uuid-3] revision=3",
        "callAgentStream {"action":"portfolio.submit","client_id":"11111111-1111-4111-8111-111111111111","text":"100 RY.TO","files":[{"name":"a.csv","media_type":"text/csv","data_base64":"QQ=="}]} {"locale":"en","messages":{"network":"Network down","invalidResponse":"Bad answer","noResult":"No result"}}",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=portfolio.submit error=- notice=null stream="" live=uuid-11:portfolio.submit:running:1:null:streamed runs=[uuid-10:portfolio.submit:error:0:10:streamed:internal/plain failure uuid-9:followup.reply:error:0:10:streamed:aborted/Aborted uuid-7:followup.reply:error:0:10:streamed:internal/boom uuid-5:followup.reply:ok:0:10:streamed uuid-3:followup.reply:ok:2:10:streamed uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false uuid-4:agent:Tell me more:1:followups:uuid-3] revision=3",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=portfolio_review resuming=false pending=null error=- notice=null stream="" live=- runs=[uuid-11:portfolio.submit:ok:1:10:streamed uuid-10:portfolio.submit:error:0:10:streamed:internal/plain failure uuid-9:followup.reply:error:0:10:streamed:aborted/Aborted uuid-7:followup.reply:error:0:10:streamed:internal/boom uuid-5:followup.reply:ok:0:10:streamed uuid-3:followup.reply:ok:2:10:streamed uuid-1:session.start:ok:0:10] conversation=[uuid-2:user:1:because:false uuid-4:agent:Tell me more:1:followups:uuid-3] revision=4",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 [{"id":"uuid-11","action":"portfolio.submit","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":true,"steps":[{"id":"s1","kind":"agent","title":"step"}],"error":null},{"id":"uuid-10","action":"portfolio.submit","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"error","streamed":true,"steps":[],"error":{"code":"internal","message":"plain failure"}},{"id":"uuid-9","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"error","streamed":true,"steps":[],"error":{"code":"aborted","message":"Aborted"}},{"id":"uuid-7","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"error","streamed":true,"steps":[],"error":{"code":"internal","message":"boom"}},{"id":"uuid-5","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":true,"steps":[],"error":null},{"id":"uuid-3","action":"followup.reply","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":true,"steps":[{"id":"s1","kind":"agent","title":"step"},{"id":"s1","kind":"agent","title":"step"}],"error":null},{"id":"uuid-1","action":"session.start","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[],"error":null}]",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 [{"id":"uuid-2","role":"user","at":"2026-11-15T12:00:00.000Z","answers":[{"question_id":"a1_1_1","prompt":"Why?","display":"3 / 5"}],"message":"because","stop":false},{"id":"uuid-4","role":"agent","at":"2026-11-15T12:00:00.000Z","message":"Tell me more","questions":[{"id":"a1_1_1","prompt":"Why?"}],"stage":"followups","runId":"uuid-3"}]",
        "result true",
      ]
    `);
  });

  it("keeps the runs of a quiet action without trace, and clears runs and errors on demand", async () => {
    const store = newStore();
    await store.init();
    script({ state: state() });
    await store.start();
    gateway.log.length = 0;
    script({ state: state({ trace: [] }) });
    gateway.log.push(`result ${await store.updateSettings({ locale: "en", knowledge_level: "advanced" })}`);
    script({ state: state() });
    gateway.log.push(`result ${await store.refreshProfile()}`);
    script({ error: new ApiError("internal", "Down") });
    gateway.log.push(`result ${await store.refreshProfile()}`);
    store.dismissError();
    store.clearRuns();
    expect(gateway.log).toMatchInlineSnapshot(`
      [
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=base_questions resuming=false pending=settings.update error=- notice=null stream="" live=uuid-2:settings.update:running:0:null runs=[uuid-1:session.start:ok:1:10] conversation=[] revision=1",
        "callAgent {"action":"settings.update","client_id":"11111111-1111-4111-8111-111111111111","locale":"en","knowledge_level":"advanced"} {"locale":"en","messages":{"network":"Network down","invalidResponse":"Bad answer","noResult":"No result"}}",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=base_questions resuming=false pending=null error=- notice=null stream="" live=- runs=[uuid-1:session.start:ok:1:10] conversation=[] revision=2",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 [{"id":"uuid-1","action":"session.start","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[{"id":"s1","kind":"agent","title":"step"}],"error":null}]",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 []",
        "result true",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=base_questions resuming=false pending=profile.get error=- notice=null stream="" live=uuid-3:profile.get:running:0:null runs=[uuid-1:session.start:ok:1:10] conversation=[] revision=2",
        "callAgent {"action":"profile.get","client_id":"11111111-1111-4111-8111-111111111111"} {"locale":"en","messages":{"network":"Network down","invalidResponse":"Bad answer","noResult":"No result"}}",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=base_questions resuming=false pending=null error=- notice=null stream="" live=- runs=[uuid-3:profile.get:ok:1:10 uuid-1:session.start:ok:1:10] conversation=[] revision=3",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 [{"id":"uuid-3","action":"profile.get","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[{"id":"s1","kind":"agent","title":"step"}],"error":null},{"id":"uuid-1","action":"session.start","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[{"id":"s1","kind":"agent","title":"step"}],"error":null}]",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 []",
        "result true",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=base_questions resuming=false pending=profile.get error=- notice=null stream="" live=uuid-4:profile.get:running:0:null runs=[uuid-3:profile.get:ok:1:10 uuid-1:session.start:ok:1:10] conversation=[] revision=3",
        "callAgent {"action":"profile.get","client_id":"11111111-1111-4111-8111-111111111111"} {"locale":"en","messages":{"network":"Network down","invalidResponse":"Bad answer","noResult":"No result"}}",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=base_questions resuming=false pending=null error=internal/Down@profile.get notice=null stream="" live=- runs=[uuid-4:profile.get:error:0:10:internal/Down uuid-3:profile.get:ok:1:10 uuid-1:session.start:ok:1:10] conversation=[] revision=3",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 [{"id":"uuid-4","action":"profile.get","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"error","streamed":false,"steps":[],"error":{"code":"internal","message":"Down"}},{"id":"uuid-3","action":"profile.get","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[{"id":"s1","kind":"agent","title":"step"}],"error":null},{"id":"uuid-1","action":"session.start","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[{"id":"s1","kind":"agent","title":"step"}],"error":null}]",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 []",
        "result false",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=base_questions resuming=false pending=null error=- notice=null stream="" live=- runs=[uuid-4:profile.get:error:0:10:internal/Down uuid-3:profile.get:ok:1:10 uuid-1:session.start:ok:1:10] conversation=[] revision=3",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=base_questions resuming=false pending=null error=- notice=null stream="" live=- runs=[] conversation=[] revision=3",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 []",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 []",
      ]
    `);
  });

  it("resumes a stored session and shows A1's pending message", async () => {
    stored.set("alphaforge.client_id", CLIENT);
    stored.set(`alphaforge.runs.${CLIENT}`, JSON.stringify([{ id: "old", action: "session.start", startedAt: "2026-11-14T10:00:00.000Z", durationMs: 5, status: "ok", streamed: false, steps: [], error: null }]));
    const store = newStore();
    script({ state: state({ stage: "followups", message: "Welcome back", questions: [QUESTION] }) });
    await store.init();
    await store.init();
    expect(gateway.log).toMatchInlineSnapshot(`
      [
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=- resuming=true pending=null error=- notice=null stream="" live=- runs=[old:session.start:ok:0:5] conversation=[] revision=0",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=- resuming=true pending=session.resume error=- notice=null stream="" live=uuid-1:session.resume:running:0:null runs=[old:session.start:ok:0:5] conversation=[] revision=0",
        "callAgent {"action":"session.resume","client_id":"11111111-1111-4111-8111-111111111111","locale":"en"} {"locale":"en","messages":{"network":"Network down","invalidResponse":"Bad answer","noResult":"No result"}}",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=true pending=null error=- notice=null stream="" live=- runs=[uuid-1:session.resume:ok:1:10 old:session.start:ok:0:5] conversation=[] revision=1",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 [{"id":"uuid-1","action":"session.resume","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[{"id":"s1","kind":"agent","title":"step"}],"error":null},{"id":"old","action":"session.start","startedAt":"2026-11-14T10:00:00.000Z","durationMs":5,"status":"ok","streamed":false,"steps":[],"error":null}]",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 []",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=true pending=null error=- notice=null stream="" live=- runs=[uuid-1:session.resume:ok:1:10 old:session.start:ok:0:5] conversation=[uuid-2:agent:Welcome back:1:followups:undefined] revision=1",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 [{"id":"uuid-1","action":"session.resume","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[{"id":"s1","kind":"agent","title":"step"}],"error":null},{"id":"old","action":"session.start","startedAt":"2026-11-14T10:00:00.000Z","durationMs":5,"status":"ok","streamed":false,"steps":[],"error":null}]",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 [{"id":"uuid-2","role":"agent","at":"2026-11-15T12:00:00.000Z","message":"Welcome back","questions":[{"id":"a1_1_1","prompt":"Why?"}],"stage":"followups"}]",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=followups resuming=false pending=null error=- notice=null stream="" live=- runs=[uuid-1:session.resume:ok:1:10 old:session.start:ok:0:5] conversation=[uuid-2:agent:Welcome back:1:followups:undefined] revision=1",
      ]
    `);
  });

  it("forgets a stored session the runtime no longer knows, then restarts", async () => {
    stored.set("alphaforge.client_id", CLIENT);
    stored.set(`alphaforge.conversation.${CLIENT}`, "not json");
    const store = newStore();
    script({ error: new ApiError("not_found", "Unknown client") });
    await store.init();
    script({ state: state({ client_id: "22222222-2222-4222-8222-222222222222" }) });
    gateway.log.push(`result ${await store.restart()}`);
    store.forget();
    gateway.log.push(`resume ${await store.resume()}`);
    expect(gateway.log).toMatchInlineSnapshot(`
      [
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=- resuming=true pending=null error=- notice=null stream="" live=- runs=[] conversation=[] revision=0",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=- resuming=true pending=session.resume error=- notice=null stream="" live=uuid-1:session.resume:running:0:null runs=[] conversation=[] revision=0",
        "callAgent {"action":"session.resume","client_id":"11111111-1111-4111-8111-111111111111","locale":"en"} {"locale":"en","messages":{"network":"Network down","invalidResponse":"Bad answer","noResult":"No result"}}",
        "notify hydrated client=11111111-1111-4111-8111-111111111111 stage=- resuming=true pending=null error=not_found/Unknown client@session.resume notice=null stream="" live=- runs=[uuid-1:session.resume:error:0:10:not_found/Unknown client] conversation=[] revision=0",
        "storage.set alphaforge.runs.11111111-1111-4111-8111-111111111111 [{"id":"uuid-1","action":"session.resume","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"error","streamed":false,"steps":[],"error":{"code":"not_found","message":"Unknown client"}}]",
        "storage.set alphaforge.conversation.11111111-1111-4111-8111-111111111111 []",
        "storage.remove alphaforge.client_id",
        "storage.remove alphaforge.runs.11111111-1111-4111-8111-111111111111",
        "storage.remove alphaforge.conversation.11111111-1111-4111-8111-111111111111",
        "notify hydrated client=null stage=- resuming=false pending=null error=- notice=not_found stream="" live=- runs=[] conversation=[] revision=0",
        "notify hydrated client=null stage=- resuming=false pending=null error=- notice=not_found stream="" live=- runs=[] conversation=[] revision=0",
        "notify hydrated client=null stage=- resuming=false pending=null error=- notice=null stream="" live=- runs=[] conversation=[] revision=0",
        "notify hydrated client=null stage=- resuming=false pending=session.start error=- notice=null stream="" live=uuid-2:session.start:running:0:null runs=[] conversation=[] revision=0",
        "callAgent {"action":"session.start","locale":"en"} {"locale":"en","messages":{"network":"Network down","invalidResponse":"Bad answer","noResult":"No result"}}",
        "storage.set alphaforge.client_id 22222222-2222-4222-8222-222222222222",
        "notify hydrated client=22222222-2222-4222-8222-222222222222 stage=base_questions resuming=false pending=null error=- notice=null stream="" live=- runs=[uuid-2:session.start:ok:1:10] conversation=[] revision=1",
        "storage.set alphaforge.runs.22222222-2222-4222-8222-222222222222 [{"id":"uuid-2","action":"session.start","startedAt":"2026-11-15T12:00:00.000Z","durationMs":10,"status":"ok","streamed":false,"steps":[{"id":"s1","kind":"agent","title":"step"}],"error":null}]",
        "storage.set alphaforge.conversation.22222222-2222-4222-8222-222222222222 []",
        "notify hydrated client=22222222-2222-4222-8222-222222222222 stage=base_questions resuming=false pending=null error=- notice=null stream="" live=- runs=[uuid-2:session.start:ok:1:10] conversation=[] revision=1",
        "result true",
        "storage.remove alphaforge.client_id",
        "storage.remove alphaforge.runs.22222222-2222-4222-8222-222222222222",
        "storage.remove alphaforge.conversation.22222222-2222-4222-8222-222222222222",
        "notify hydrated client=null stage=- resuming=false pending=null error=- notice=null stream="" live=- runs=[] conversation=[] revision=0",
        "resume false",
      ]
    `);
  });

  it("with sign-in on, resumes the account's client_id, not the browser's, and opens a new account quietly", async () => {
    const account = "33333333-3333-4333-8333-333333333333";
    stored.set("alphaforge.client_id", CLIENT);
    const store = newStore();
    script({ error: new ApiError("not_found", "Unknown client") });
    await store.init({ source: "account", clientId: account });
    const calls = gateway.log.filter((line) => line.startsWith("callAgent"));
    expect(calls).toHaveLength(1);
    expect(calls[0]).toContain(`"action":"session.resume","client_id":"${account}"`);
    expect(gateway.log).toContain(`storage.set alphaforge.client_id ${account}`);
    // A new account has no base yet: no « profile not found » notice, session.start creates it.
    expect(store.getSnapshot()).toMatchObject({ hydrated: true, clientId: null, notice: null, error: null });
  });

  it("with sign-in on and no session, resumes nothing", async () => {
    stored.set("alphaforge.client_id", CLIENT);
    const store = newStore();
    await store.init({ source: "none" });
    expect(gateway.log.some((line) => line.startsWith("callAgent"))).toBe(false);
    expect(store.getSnapshot()).toMatchObject({ hydrated: true, clientId: null });
  });
});
