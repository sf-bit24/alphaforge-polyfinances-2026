/**
 * « Supprimer mon compte » (CONTRACTS.md 7.1): the guard of `POST /api/auth/delete-account`, the prefix checked
 * before every deletion, the order of the steps (the Cognito user last, never after a failure), the pagination of
 * ListObjectVersions, the batches of DeleteObjects and the idempotence of each step, with fake AWS SDK clients.
 */
import { randomUUID } from "node:crypto";
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ErrorEnvelope } from "@/lib/contract/schemas";
import { DeleteAccountResponse, isDeleteConfirmation } from "@/lib/contract/auth";
import { getMockRuntime } from "@/lib/mock/runtime";
import { accountClientId } from "@/lib/server/auth/client-id";
import {
  assertInBase,
  clientPrefix,
  DELETE_BATCH,
  DeletionError,
  deleteAccountData,
  type DeletionClients,
  type DeletionTarget,
} from "@/lib/server/auth/account-deletion";
import { handleDeleteAccount } from "@/lib/server/auth/delete-account";
import { handleMe } from "@/lib/server/auth/routes";
import { sessionCookie, type AccountSession } from "@/lib/server/auth/session";
import { getAuthConfig, type CognitoConfig } from "@/lib/server/config";
import { handleAgent } from "@/lib/server/gateway";

const SECRET = "test-secret-of-at-least-thirty-two-characters";
const OTHER = "0f1e2d3c-4b5a-4968-8776-655443322110";
const COGNITO_ENV = {
  AUTH_MODE: "cognito",
  COGNITO_ISSUER: "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_Test123",
  COGNITO_CLIENT_ID: "client123abc",
  COGNITO_DOMAIN: "https://alphaforge-test.auth.us-east-1.amazoncognito.com",
  APP_URL: "https://d123.cloudfront.net",
  AUTH_SESSION_SECRET: SECRET,
};
const DELETION_ENV = {
  ALPHAFORGE_BUCKET: "alphaforge-sandbox-kb-123456789012",
  ALPHAFORGE_CLIENT_KB_PREFIX: "alphaforge-sandbox",
  ALPHAFORGE_CLIENT_KB_VECTOR_BUCKET: "alphaforge-sandbox-client-vectors",
};
const ENV_NAMES = [...Object.keys(COGNITO_ENV), ...Object.keys(DELETION_ENV), "AGENT_MODE"];
const saved = Object.fromEntries(ENV_NAMES.map((name) => [name, process.env[name]]));

function setEnv(values: Record<string, string | undefined>) {
  for (const name of ENV_NAMES) {
    if (values[name] === undefined) delete process.env[name];
    else process.env[name] = values[name];
  }
}

afterAll(() => setEnv(saved));

const inAnHour = () => Math.floor(Date.now() / 1000) + 3600;

/** A new account each time: a deleted account's sessions are refused for the rest of the run. */
function newAccount(sub: string = randomUUID()): { sub: string; clientId: string; cookie: string } {
  const clientId = accountClientId(sub);
  const session: AccountSession = { sub, email: "ana@example.com", groups: [], client_id: clientId, exp: inAnHour() };
  const cookie = (sessionCookie(session, getAuthConfig() as CognitoConfig).split(";")[0] ?? "").trim();
  return { sub, clientId, cookie };
}

/** What Chrome sends for the interface's own fetch under Referrer-Policy: no-referrer. */
const SAME_ORIGIN = { origin: "null", "sec-fetch-site": "same-origin" };

function deleteRequest(body: unknown, headers: Record<string, string> = {}) {
  return new Request("http://localhost/api/auth/delete-account", {
    method: "POST",
    headers: { "content-type": "application/json", ...SAME_ORIGIN, ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

async function errorOf(response: Response) {
  return ErrorEnvelope.parse(await response.json()).error;
}

/* ------------------------------------------------------------------ */
/* Fake AWS SDK clients                                                */
/* ------------------------------------------------------------------ */

type Call = { name: string; input: Record<string, unknown> };
type Handler = (input: Record<string, unknown>) => unknown;

const awsError = (name: string) => Object.assign(new Error(`${name} (fake)`), { name });

/** One `send` for the four clients: each call is recorded, then answered by the handler of its command. */
function fakeAws(handlers: Record<string, Handler>) {
  const calls: Call[] = [];
  const send = vi.fn(async (command: { input: Record<string, unknown> }) => {
    const name = command.constructor.name.replace(/Command$/, "");
    calls.push({ name, input: command.input });
    const handler = handlers[name];
    if (!handler) throw new Error(`Unexpected AWS call ${name}`);
    return handler(command.input);
  });
  const client = { send } as unknown as DeletionClients["s3"];
  const clients = { bedrock: client, vectors: client, s3: client, cognito: client } as unknown as DeletionClients;
  return { clients, calls, names: () => calls.map((call) => call.name) };
}

function target(clientId: string, sub = clientId): DeletionTarget {
  return {
    clientId,
    sub,
    userPoolId: "us-east-1_Test123",
    bucket: DELETION_ENV.ALPHAFORGE_BUCKET,
    kbPrefix: DELETION_ENV.ALPHAFORGE_CLIENT_KB_PREFIX,
    vectorBucket: DELETION_ENV.ALPHAFORGE_CLIENT_KB_VECTOR_BUCKET,
  };
}

const kbName = (clientId: string) => `alphaforge-sandbox-client-${clientId}`;
const clientTags = (clientId: string) => ({ "alphaforge:scope": "client", "alphaforge:client_id": clientId, "alphaforge:prefix": "alphaforge-sandbox" });

/** An account with one Knowledge Base and its index, and `versions` keys under its base (one version each). */
function happyHandlers(clientId: string, versions = 3): Record<string, Handler> {
  const keys = Array.from({ length: versions }, (_, index) => `clients/${clientId}/doc-${index}.md`);
  let listed = false;
  return {
    ListKnowledgeBases: () => ({
      knowledgeBaseSummaries: [
        { knowledgeBaseId: "GENERAL001", name: "alphaforge-sandbox-kb", status: "ACTIVE" },
        { knowledgeBaseId: "OTHERKB001", name: kbName(OTHER), status: "ACTIVE" },
        { knowledgeBaseId: "OWNKB00001", name: kbName(clientId), status: "ACTIVE" },
      ],
    }),
    GetKnowledgeBase: ({ knowledgeBaseId }) => ({
      knowledgeBase: { knowledgeBaseId, knowledgeBaseArn: `arn:aws:bedrock:us-east-1:123456789012:knowledge-base/${String(knowledgeBaseId)}`, status: "ACTIVE" },
    }),
    ListTagsForResource: () => ({ tags: clientTags(clientId) }),
    DeleteKnowledgeBase: ({ knowledgeBaseId }) => ({ knowledgeBaseId, status: "DELETING" }),
    DeleteIndex: () => ({}),
    ListObjectVersions: () => {
      // First pass: the versions; second pass: nothing left.
      const page = listed ? {} : { Versions: keys.map((Key) => ({ Key, VersionId: `v-${Key}` })), IsTruncated: false };
      listed = true;
      return page;
    },
    DeleteObjects: () => ({ Deleted: [] }),
    AdminDeleteUser: () => ({}),
  };
}

/* ------------------------------------------------------------------ */
/* The four steps                                                      */
/* ------------------------------------------------------------------ */

describe("deletion steps (fake AWS clients)", () => {
  beforeEach(() => setEnv({ ...COGNITO_ENV, AGENT_MODE: "aws" }));

  it("runs in order: Knowledge Base, index, every version, then the Cognito user", async () => {
    const clientId = randomUUID();
    const aws = fakeAws(happyHandlers(clientId));
    const report = await deleteAccountData(target(clientId), aws.clients);
    expect(aws.names()).toEqual([
      "ListKnowledgeBases",
      "GetKnowledgeBase",
      "ListTagsForResource",
      "DeleteKnowledgeBase",
      "DeleteIndex",
      "ListObjectVersions",
      "DeleteObjects",
      "ListObjectVersions",
      "AdminDeleteUser",
    ]);
    expect(report).toEqual({ knowledge_bases: ["OWNKB00001"], vector_index: "deleted", objects: 3, account: "deleted" });
    // Only the client's own base, never the general one nor another client's.
    const kbCalls = aws.calls.filter((call) => call.name === "DeleteKnowledgeBase");
    expect(kbCalls.map((call) => call.input.knowledgeBaseId)).toEqual(["OWNKB00001"]);
    expect(aws.calls.find((call) => call.name === "DeleteIndex")?.input).toEqual({
      vectorBucketName: "alphaforge-sandbox-client-vectors",
      indexName: `client-${clientId}`,
    });
    expect(aws.calls.find((call) => call.name === "ListObjectVersions")?.input).toMatchObject({
      Bucket: DELETION_ENV.ALPHAFORGE_BUCKET,
      Prefix: `clients/${clientId}/`,
    });
    const deleted = aws.calls.find((call) => call.name === "DeleteObjects")?.input as { Delete: { Objects: Array<{ Key: string; VersionId: string }> } };
    expect(deleted.Delete.Objects.every((entry) => entry.Key.startsWith(`clients/${clientId}/`) && entry.VersionId.startsWith("v-"))).toBe(true);
    expect(aws.calls.at(-1)?.input).toEqual({ UserPoolId: "us-east-1_Test123", Username: clientId });
  });

  it("follows ListKnowledgeBases pages and leaves a base already being deleted alone", async () => {
    const clientId = randomUUID();
    const handlers = happyHandlers(clientId, 0);
    const aws = fakeAws({
      ...handlers,
      ListKnowledgeBases: ({ nextToken }) =>
        nextToken
          ? { knowledgeBaseSummaries: [{ knowledgeBaseId: "OWNKB00001", name: kbName(clientId), status: "DELETING" }] }
          : { knowledgeBaseSummaries: [{ knowledgeBaseId: "GENERAL001", name: "alphaforge-sandbox-kb" }], nextToken: "page-2" },
      GetKnowledgeBase: ({ knowledgeBaseId }) => ({
        knowledgeBase: { knowledgeBaseId, knowledgeBaseArn: "arn:aws:bedrock:us-east-1:1:knowledge-base/OWNKB00001", status: "DELETING" },
      }),
    });
    const report = await deleteAccountData(target(clientId), aws.clients);
    expect(aws.calls.filter((call) => call.name === "ListKnowledgeBases").map((call) => call.input.nextToken)).toEqual([undefined, "page-2"]);
    expect(aws.names()).not.toContain("DeleteKnowledgeBase");
    expect(report.knowledge_bases).toEqual(["OWNKB00001"]);
  });

  it("is idempotent: no Knowledge Base, no index, no object, no user is not an error", async () => {
    const clientId = randomUUID();
    const aws = fakeAws({
      ListKnowledgeBases: () => ({ knowledgeBaseSummaries: [] }),
      DeleteIndex: () => {
        throw awsError("NotFoundException");
      },
      ListObjectVersions: () => ({ IsTruncated: false }),
      AdminDeleteUser: () => {
        throw awsError("UserNotFoundException");
      },
    });
    expect(await deleteAccountData(target(clientId), aws.clients)).toEqual({
      knowledge_bases: [],
      vector_index: "absent",
      objects: 0,
      account: "absent",
    });
    expect(aws.names()).not.toContain("DeleteObjects");
  });

  it("takes a Knowledge Base gone between the list and the delete as done", async () => {
    const clientId = randomUUID();
    const aws = fakeAws({
      ...happyHandlers(clientId, 0),
      GetKnowledgeBase: () => {
        throw awsError("ResourceNotFoundException");
      },
    });
    expect((await deleteAccountData(target(clientId), aws.clients)).knowledge_bases).toEqual([]);
    expect(aws.names()).toContain("AdminDeleteUser");
  });

  it("follows ListObjectVersions pages and deletes by batches of 1000, delete markers included", async () => {
    const clientId = randomUUID();
    const prefix = `clients/${clientId}/`;
    const entries = (from: number, count: number) => Array.from({ length: count }, (_, index) => ({ Key: `${prefix}k-${from + index}`, VersionId: `v${from + index}` }));
    const pages: Record<string, unknown> = {
      start: { Versions: entries(0, 900), DeleteMarkers: entries(900, 100), IsTruncated: true, NextKeyMarker: `${prefix}k-999`, NextVersionIdMarker: "v999" },
      [`${prefix}k-999|v999`]: { Versions: entries(1000, 1000), IsTruncated: true, NextKeyMarker: `${prefix}k-1999`, NextVersionIdMarker: "v1999" },
      [`${prefix}k-1999|v1999`]: { Versions: entries(2000, 400), DeleteMarkers: entries(2400, 100), IsTruncated: false },
    };
    let pass = 0;
    const aws = fakeAws({
      ...happyHandlers(clientId, 0),
      ListObjectVersions: ({ KeyMarker, VersionIdMarker }) => {
        if (!KeyMarker) pass += 1;
        if (pass > 1) return { IsTruncated: false };
        return pages[KeyMarker ? `${String(KeyMarker)}|${String(VersionIdMarker)}` : "start"];
      },
    });
    const report = await deleteAccountData(target(clientId), aws.clients);
    const batches = aws.calls.filter((call) => call.name === "DeleteObjects").map((call) => (call.input as { Delete: { Objects: unknown[] } }).Delete.Objects.length);
    expect(batches).toEqual([DELETE_BATCH, DELETE_BATCH, 500]);
    expect(report.objects).toBe(2500);
    const listings = aws.calls.filter((call) => call.name === "ListObjectVersions").map((call) => [call.input.KeyMarker, call.input.VersionIdMarker]);
    expect(listings).toEqual([
      [undefined, undefined],
      [`${prefix}k-999`, "v999"],
      [`${prefix}k-1999`, "v1999"],
      [undefined, undefined],
    ]);
    expect(aws.names().at(-1)).toBe("AdminDeleteUser");
  });

  it("deletes a version written during the first pass at the next one", async () => {
    const clientId = randomUUID();
    let pass = 0;
    const aws = fakeAws({
      ...happyHandlers(clientId, 0),
      ListObjectVersions: () => {
        pass += 1;
        return pass <= 2 ? { Versions: [{ Key: `clients/${clientId}/late-${pass}.md`, VersionId: `v${pass}` }] } : {};
      },
    });
    expect((await deleteAccountData(target(clientId), aws.clients)).objects).toBe(2);
    expect(aws.names().filter((name) => name === "ListObjectVersions")).toHaveLength(3);
  });

  it("never deletes a key outside clients/<client_id>/, and keeps the Cognito user", async () => {
    const clientId = randomUUID();
    const aws = fakeAws({
      ...happyHandlers(clientId, 0),
      ListObjectVersions: () => ({
        Versions: [
          { Key: `clients/${clientId}/profil.md`, VersionId: "a" },
          { Key: `clients/${OTHER}/profil.md`, VersionId: "b" },
        ],
      }),
    });
    const failure = await deleteAccountData(target(clientId), aws.clients).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(DeletionError);
    expect(failure).toMatchObject({ step: "objects", completed: ["knowledge_base", "vector_index"] });
    expect(aws.names()).not.toContain("DeleteObjects");
    expect(aws.names()).not.toContain("AdminDeleteUser");
  });

  it("refuses a Knowledge Base named after the client without its tags", async () => {
    const clientId = randomUUID();
    const aws = fakeAws({ ...happyHandlers(clientId), ListTagsForResource: () => ({ tags: { ...clientTags(OTHER) } }) });
    await expect(deleteAccountData(target(clientId), aws.clients)).rejects.toMatchObject({ step: "knowledge_base", completed: [] });
    expect(aws.names()).toEqual(["ListKnowledgeBases", "GetKnowledgeBase", "ListTagsForResource"]);
  });

  it.each([
    ["knowledge_base", "DeleteKnowledgeBase", []],
    ["vector_index", "DeleteIndex", ["knowledge_base"]],
    ["objects", "DeleteObjects", ["knowledge_base", "vector_index"]],
  ])("stops at a failed %s step, before AdminDeleteUser", async (step, command, completed) => {
    const clientId = randomUUID();
    const aws = fakeAws({
      ...happyHandlers(clientId),
      [command]: () => {
        throw awsError("AccessDeniedException");
      },
    });
    await expect(deleteAccountData(target(clientId), aws.clients)).rejects.toMatchObject({ step, completed });
    expect(aws.names()).not.toContain("AdminDeleteUser");
  });

  it("stops when DeleteObjects reports keys it could not delete", async () => {
    const clientId = randomUUID();
    const aws = fakeAws({
      ...happyHandlers(clientId),
      DeleteObjects: () => ({ Errors: [{ Key: `clients/${clientId}/doc-0.md`, Code: "AccessDenied" }] }),
    });
    await expect(deleteAccountData(target(clientId), aws.clients)).rejects.toMatchObject({ step: "objects" });
    expect(aws.names()).not.toContain("AdminDeleteUser");
  });

  it("only knows the prefix of an account client_id, never a demo base", () => {
    const clientId = randomUUID();
    expect(clientPrefix(clientId)).toBe(`clients/${clientId}/`);
    for (const bad of ["demo-robert", "", "../general", clientId.toUpperCase(), "6ba7b810-9dad-11d1-80b4-00c04fd430c8", `${clientId}/x`]) {
      expect(() => clientPrefix(bad)).toThrow(/Refused/);
    }
    expect(() => assertInBase("general/methodologie.md", `clients/${clientId}/`)).toThrow(/outside/);
    expect(() => assertInBase(undefined, `clients/${clientId}/`)).toThrow(/outside/);
    expect(() => assertInBase("clients/demo-robert/x.md", "clients/demo-robert/")).toThrow(/outside/);
  });
});

/* ------------------------------------------------------------------ */
/* POST /api/auth/delete-account                                       */
/* ------------------------------------------------------------------ */

describe("POST /api/auth/delete-account", () => {
  beforeEach(() => setEnv({ ...COGNITO_ENV, ...DELETION_ENV, AGENT_MODE: "aws" }));

  it("answers 404 with sign-in off, without touching anything", async () => {
    setEnv({ AGENT_MODE: "mock" });
    const response = await handleDeleteAccount(deleteRequest({ confirmation: "SUPPRIMER" }));
    expect(response.status).toBe(404);
    expect(response.headers.getSetCookie()).toEqual([]);
  });

  it("answers 401 without a session", async () => {
    const response = await handleDeleteAccount(deleteRequest({ confirmation: "SUPPRIMER" }));
    expect(response.status).toBe(401);
    expect((await errorOf(response)).code).toBe("unauthorized");
  });

  it("refuses a request from another site (403), as the sign-out does", async () => {
    const { cookie } = newAccount();
    const aws = fakeAws({});
    for (const headers of [
      { "sec-fetch-site": "cross-site", origin: "null" },
      { "sec-fetch-site": "same-site", origin: "https://d123.cloudfront.net" },
    ]) {
      const response = await handleDeleteAccount(deleteRequest({ confirmation: "SUPPRIMER" }, { cookie, ...headers }), aws.clients);
      expect(response.status).toBe(403);
      expect(response.headers.getSetCookie()).toEqual([]);
    }
    const legacy = new Request("http://localhost/api/auth/delete-account", {
      method: "POST",
      headers: { "content-type": "application/json", origin: "https://evil.example", cookie },
      body: JSON.stringify({ confirmation: "SUPPRIMER" }),
    });
    expect((await handleDeleteAccount(legacy, aws.clients)).status).toBe(403);
    expect(aws.calls).toEqual([]);
  });

  it.each([[{}], [{ confirmation: "" }], [{ confirmation: "oui" }], [{ confirmation: "ana@example.com" }], ["not json"]])(
    "answers 400 to a missing or wrong confirmation: %j",
    async (body) => {
      const { cookie } = newAccount();
      const aws = fakeAws({});
      const response = await handleDeleteAccount(deleteRequest(body, { cookie }), aws.clients);
      expect(response.status).toBe(400);
      expect((await errorOf(response)).code).toBe("bad_request");
      expect(aws.calls).toEqual([]);
    },
  );

  it("answers 400 to a body that is not JSON", async () => {
    const { cookie } = newAccount();
    const response = await handleDeleteAccount(deleteRequest({ confirmation: "DELETE" }, { cookie, "content-type": "text/plain" }));
    expect(response.status).toBe(400);
  });

  it("accepts the word of either language, spaces and case aside", () => {
    for (const word of ["SUPPRIMER", "supprimer", " Supprimer ", "DELETE", "delete"]) expect(isDeleteConfirmation(word)).toBe(true);
    for (const word of ["SUPPRIME", "DELET", "SUPPRIMER MON COMPTE", ""]) expect(isDeleteConfirmation(word)).toBe(false);
  });

  it("deletes the session's base only, whatever the body names, then signs out through Cognito", async () => {
    const sub = "us-east-1:not-a-uuid-v4";
    const account = newAccount(sub);
    const aws = fakeAws(happyHandlers(account.clientId));
    const response = await handleDeleteAccount(
      deleteRequest({ confirmation: "SUPPRIMER", client_id: OTHER, prefix: `clients/${OTHER}/` }, { cookie: account.cookie }),
      aws.clients,
    );
    expect(response.status).toBe(200);
    const body = DeleteAccountResponse.parse(await response.json());
    expect(body.deleted).toEqual({ knowledge_bases: ["OWNKB00001"], vector_index: "deleted", objects: 3, account: "deleted" });
    const logout = new URL(body.logout_url);
    expect(`${logout.origin}${logout.pathname}`).toBe(`${COGNITO_ENV.COGNITO_DOMAIN}/logout`);
    expect(logout.searchParams.get("logout_uri")).toBe("https://d123.cloudfront.net/");
    const cookies = response.headers.getSetCookie();
    expect(cookies).toContain("af_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax; Secure");
    expect(cookies).toContain("af_notice=account_deleted; Path=/login; Max-Age=300; SameSite=Lax; Secure");
    // The derived client_id names the base; the sub is the Cognito username.
    expect(aws.calls.find((call) => call.name === "ListObjectVersions")?.input.Prefix).toBe(`clients/${account.clientId}/`);
    expect(aws.calls.find((call) => call.name === "AdminDeleteUser")?.input).toEqual({ UserPoolId: "us-east-1_Test123", Username: sub });
    expect(JSON.stringify(aws.calls)).not.toContain(OTHER);
    // The same cookie, still held by another device, no longer opens a session.
    expect((await handleMe(new Request("http://localhost/api/auth/me", { headers: { cookie: account.cookie } }))).status).toBe(401);
  });

  it("answers 502 naming the failed step, and keeps the account and the session", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const account = newAccount();
    const aws = fakeAws({
      ...happyHandlers(account.clientId),
      DeleteIndex: () => {
        throw awsError("AccessDeniedException");
      },
    });
    const response = await handleDeleteAccount(deleteRequest({ confirmation: "DELETE" }, { cookie: account.cookie, "x-alphaforge-locale": "en" }), aws.clients);
    expect(response.status).toBe(502);
    expect(response.headers.getSetCookie()).toEqual([]);
    const error = await errorOf(response);
    expect(error.message).toContain("search index");
    expect(error.details).toMatchObject({ source: "gateway", step: "vector_index", completed: ["knowledge_base"], aws_error: "AccessDeniedException" });
    expect(aws.names()).not.toContain("AdminDeleteUser");
    expect((await handleMe(new Request("http://localhost/api/auth/me", { headers: { cookie: account.cookie } }))).status).toBe(200);
  });

  it("names the missing variables in aws mode", async () => {
    setEnv({ ...COGNITO_ENV, AGENT_MODE: "aws" });
    const { cookie } = newAccount();
    const response = await handleDeleteAccount(deleteRequest({ confirmation: "SUPPRIMER" }, { cookie }), fakeAws({}).clients);
    expect(response.status).toBe(500);
    expect((await errorOf(response)).message).toContain("ALPHAFORGE_BUCKET");
  });

  it("refuses AGENT_MODE=local", async () => {
    setEnv({ ...COGNITO_ENV, AGENT_MODE: "local" });
    const { cookie } = newAccount();
    expect((await handleDeleteAccount(deleteRequest({ confirmation: "SUPPRIMER" }, { cookie }))).status).toBe(400);
  });

  it("simulates the deletion in mock mode: the client and its documents are forgotten", async () => {
    setEnv({ ...COGNITO_ENV, AGENT_MODE: "mock" });
    const account = newAccount();
    const started = await handleAgent(
      new Request("http://localhost/api/agent", {
        method: "POST",
        headers: { "content-type": "application/json", cookie: account.cookie },
        body: JSON.stringify({ action: "session.start", locale: "fr" }),
      }),
    );
    expect(started.status).toBe(200);
    const response = await handleDeleteAccount(deleteRequest({ confirmation: "supprimer" }, { cookie: account.cookie }));
    expect(response.status).toBe(200);
    const body = DeleteAccountResponse.parse(await response.json());
    expect(body.deleted.account).toBe("deleted");
    expect(body.deleted.objects).toBeGreaterThan(0);
    expect(getMockRuntime().forgetClient(account.clientId)).toBeNull();
  });
});
