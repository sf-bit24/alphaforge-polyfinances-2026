/**
 * After « Supprimer mon compte », a session cookie kept on another device must not open the base again, even on
 * another ECS task or after a restart (CONTRACTS.md 7.1): in aws mode, the routes ask Cognito whether the account
 * still exists (AdminGetUser), with a cache per account; a transient Cognito error lets the request through.
 */
import { randomUUID } from "node:crypto";
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { accountClientId } from "@/lib/server/auth/client-id";
import { handleMe } from "@/lib/server/auth/routes";
import { sessionCookie, type AccountSession } from "@/lib/server/auth/session";
import { getAuthConfig, type CognitoConfig } from "@/lib/server/config";
import { handleAgent, handleCollectGet, handleCollectPost, handlePortfolio } from "@/lib/server/gateway";

/** Cognito, faked: AdminGetUser answers what `cognito.answer` says for each username. */
const cognito = vi.hoisted(() => ({
  answer: (() => ({})) as (username: string) => unknown,
  calls: [] as Array<{ name: string; input: Record<string, unknown> }>,
}));

vi.mock("@/lib/server/auth/account-deletion", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/server/auth/account-deletion")>();
  const send = async (command: { input: Record<string, unknown> }) => {
    const name = command.constructor.name.replace(/Command$/, "");
    cognito.calls.push({ name, input: command.input });
    if (name !== "AdminGetUser") throw new Error(`Unexpected AWS call ${name}`);
    return cognito.answer(String(command.input.Username));
  };
  const client = { send };
  return { ...actual, awsDeletionClients: () => ({ bedrock: client, vectors: client, s3: client, cognito: client }) };
});

const ENV = {
  AUTH_MODE: "cognito",
  COGNITO_ISSUER: "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_Test123",
  COGNITO_CLIENT_ID: "client123abc",
  COGNITO_DOMAIN: "https://alphaforge-test.auth.us-east-1.amazoncognito.com",
  APP_URL: "https://d123.cloudfront.net",
  AUTH_SESSION_SECRET: "test-secret-of-at-least-thirty-two-characters",
  AGENT_MODE: "aws",
};
const saved = Object.fromEntries(Object.keys(ENV).map((name) => [name, process.env[name]]));

function setEnv(values: Record<string, string | undefined>) {
  for (const name of Object.keys(ENV)) {
    if (values[name] === undefined) delete process.env[name];
    else process.env[name] = values[name];
  }
}

const gone = (name = "UserNotFoundException") => () => {
  throw Object.assign(new Error(`${name} (fake)`), { name });
};

/** A new account each time: the cache and the revocations are per account. */
function account(groups: string[] = []) {
  const sub = randomUUID();
  const session: AccountSession = { sub, email: "ana@example.com", groups, client_id: accountClientId(sub), exp: Math.floor(Date.now() / 1000) + 3600 };
  const cookie = (sessionCookie(session, getAuthConfig() as CognitoConfig).split(";")[0] ?? "").trim();
  return { sub, cookie };
}

const me = (cookie: string) => handleMe(new Request("http://localhost/api/auth/me", { headers: { cookie } }));
const post = (path: string, body: unknown, cookie: string) =>
  new Request(`http://localhost${path}`, { method: "POST", headers: { "content-type": "application/json", cookie }, body: JSON.stringify(body) });
const checksOf = (sub: string) => cognito.calls.filter((call) => call.name === "AdminGetUser" && call.input.Username === sub);

beforeEach(() => {
  setEnv(ENV);
  cognito.calls.length = 0;
  cognito.answer = () => ({});
});

afterEach(() => vi.useRealTimers());
afterAll(() => setEnv(saved));

describe("account still in Cognito (aws mode)", () => {
  it("answers 401 on /api/auth/me for a deleted account, then refuses it without asking again", async () => {
    const deleted = account();
    cognito.answer = gone();
    expect((await me(deleted.cookie)).status).toBe(401);
    expect(checksOf(deleted.sub)[0]?.input).toEqual({ UserPoolId: "us-east-1_Test123", Username: deleted.sub });
    expect((await me(deleted.cookie)).status).toBe(401);
    expect(checksOf(deleted.sub)).toHaveLength(1);
  });

  it.each([
    ["POST /api/agent session.start", (cookie: string) => handleAgent(post("/api/agent", { action: "session.start", locale: "fr" }, cookie))],
    ["POST /api/portfolio", (cookie: string) => handlePortfolio(post("/api/portfolio", { action: "build", persona: "amira" }, cookie))],
    ["GET /api/collect", (cookie: string) => handleCollectGet(new Request("http://localhost/api/collect", { headers: { cookie } }))],
    ["POST /api/collect (admin)", (cookie: string) => handleCollectPost(post("/api/collect", {}, cookie))],
  ])("refuses a deleted account before any runtime call: %s", async (_label, call) => {
    const deleted = account(["admin"]);
    cognito.answer = gone();
    const response = await call(deleted.cookie);
    expect(response.status).toBe(401);
    // Only AdminGetUser: no AgentCore, no Step Functions.
    expect(cognito.calls.map((entry) => entry.name)).toEqual(["AdminGetUser"]);
  });

  it("keeps an existing account for 5 minutes, then asks again", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    const live = account();
    expect((await me(live.cookie)).status).toBe(200);
    expect((await me(live.cookie)).status).toBe(200);
    expect(checksOf(live.sub)).toHaveLength(1);
    vi.setSystemTime(Date.now() + 301_000);
    expect((await me(live.cookie)).status).toBe(200);
    expect(checksOf(live.sub)).toHaveLength(2);
  });

  it("asks once for concurrent requests of the same account", async () => {
    const live = account();
    const statuses = await Promise.all([me(live.cookie), me(live.cookie), me(live.cookie)]);
    expect(statuses.map((response) => response.status)).toEqual([200, 200, 200]);
    expect(checksOf(live.sub)).toHaveLength(1);
  });

  it("lets the request through when Cognito fails otherwise, logs it, and waits 30 s before asking again", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const unsure = account();
    cognito.answer = gone("ThrottlingException");
    expect((await me(unsure.cookie)).status).toBe(200);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("ThrottlingException"));
    expect((await me(unsure.cookie)).status).toBe(200);
    expect(checksOf(unsure.sub)).toHaveLength(1);
    // The account was deleted meanwhile: the next check after the wait finds it.
    cognito.answer = gone();
    vi.setSystemTime(Date.now() + 31_000);
    expect((await me(unsure.cookie)).status).toBe(401);
    expect(checksOf(unsure.sub)).toHaveLength(2);
  });

  it("does not ask Cognito outside aws mode", async () => {
    setEnv({ ...ENV, AGENT_MODE: "mock" });
    cognito.answer = gone();
    const local = account();
    expect((await me(local.cookie)).status).toBe(200);
    expect((await handleAgent(post("/api/agent", { action: "session.start", locale: "fr" }, local.cookie))).status).toBe(200);
    expect(cognito.calls).toEqual([]);
  });
});
