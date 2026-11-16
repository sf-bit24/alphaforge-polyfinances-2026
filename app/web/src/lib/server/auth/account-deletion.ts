import "server-only";
import {
  BedrockAgentClient,
  DeleteKnowledgeBaseCommand,
  GetKnowledgeBaseCommand,
  ListKnowledgeBasesCommand,
  ListTagsForResourceCommand,
} from "@aws-sdk/client-bedrock-agent";
import { AdminDeleteUserCommand, CognitoIdentityProviderClient } from "@aws-sdk/client-cognito-identity-provider";
import { DeleteObjectsCommand, ListObjectVersionsCommand, S3Client, type ObjectIdentifier } from "@aws-sdk/client-s3";
import { DeleteIndexCommand, S3VectorsClient } from "@aws-sdk/client-s3vectors";
import type { DeleteAccountResponse, DeletionStepName } from "@/lib/contract/auth";

/**
 * « Supprimer mon compte » (CONTRACTS.md 7.1), in deterministic code run by the Next.js server, never by a runtime
 * or a model. Steps, in this order, each one idempotent (what is already gone is not an error):
 *   1. the client's Knowledge Base `<prefix>-client-<client_id>`, checked by its tags before the delete;
 *   2. its S3 Vectors index `client-<client_id>`;
 *   3. every version and delete marker under `clients/<client_id>/` (the bucket is versioned);
 *   4. the Cognito user.
 * A failed step stops the run: the Cognito user stays, so the investor can try again.
 */
export type DeletionStep = DeletionStepName;

/** What the deletion acts on: the account of the session and the names Terraform gave the resources. */
export interface DeletionTarget {
  clientId: string;
  /** Cognito `sub` of the account: AdminDeleteUser accepts it as the username. */
  sub: string;
  userPoolId: string;
  /** Bucket of the OKF bases (`ALPHAFORGE_BUCKET`). */
  bucket: string;
  /** Prefix of the client Knowledge Bases and of their `alphaforge:prefix` tag (`ALPHAFORGE_CLIENT_KB_PREFIX`). */
  kbPrefix: string;
  /** S3 Vectors bucket of the client indexes (`ALPHAFORGE_CLIENT_KB_VECTOR_BUCKET`). */
  vectorBucket: string;
}

/** The SDK clients used, injected so that tests pass fakes. */
export interface DeletionClients {
  bedrock: Pick<BedrockAgentClient, "send">;
  vectors: Pick<S3VectorsClient, "send">;
  s3: Pick<S3Client, "send">;
  cognito: Pick<CognitoIdentityProviderClient, "send">;
}

export type DeletionReport = DeleteAccountResponse["deleted"];

/** A step that failed: the steps before it are done, the ones after it (the Cognito user first) are not. */
export class DeletionError extends Error {
  constructor(
    readonly step: DeletionStep,
    readonly completed: DeletionStep[],
    readonly reason: unknown,
  ) {
    super(`Account deletion stopped at ${step}: ${reason instanceof Error ? `${reason.name}: ${reason.message}` : String(reason)}`);
    this.name = "DeletionError";
  }
}

/** A client_id as the server makes it (client-id.ts): a lowercase UUID v4, never a `demo-<persona>` base. */
const CLIENT_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/** `clients/<client_id>/`, the only prefix the deletion touches. */
export function clientPrefix(clientId: string): string {
  if (!CLIENT_ID.test(clientId)) throw new Error(`Refused: ${JSON.stringify(clientId)} is not an account client_id`);
  return `clients/${clientId}/`;
}

/** Checked before every call that deletes an object: the key is inside the client's base. */
export function assertInBase(key: string | undefined, prefix: string): string {
  if (!key || !key.startsWith(prefix) || prefix.startsWith("clients/demo-")) {
    throw new Error(`Refused: ${JSON.stringify(key)} is outside ${prefix}`);
  }
  return key;
}

const errorName = (error: unknown) => (error instanceof Error ? error.name : "");

/** `ResourceNotFoundException` and its kin: the resource is already gone. */
function isGone(error: unknown, ...names: string[]): boolean {
  return names.includes(errorName(error));
}

/* ------------------------------------------------------------------ */
/* 1. Knowledge Base                                                   */
/* ------------------------------------------------------------------ */

async function knowledgeBasesNamed(bedrock: DeletionClients["bedrock"], name: string): Promise<string[]> {
  const ids: string[] = [];
  let nextToken: string | undefined;
  do {
    const page = await bedrock.send(new ListKnowledgeBasesCommand({ maxResults: 100, nextToken }));
    for (const summary of page.knowledgeBaseSummaries ?? []) {
      if (summary.name === name && summary.knowledgeBaseId) ids.push(summary.knowledgeBaseId);
    }
    nextToken = page.nextToken;
  } while (nextToken);
  return ids;
}

/** The tags that make a Knowledge Base the client's: `alphaforge:scope=client`, its client_id and the prefix. */
function assertClientTags(tags: Record<string, string> | undefined, target: DeletionTarget, id: string): void {
  const owned =
    tags?.["alphaforge:scope"] === "client" &&
    tags["alphaforge:client_id"] === target.clientId &&
    tags["alphaforge:prefix"] === target.kbPrefix;
  if (!owned) throw new Error(`Refused: Knowledge Base ${id} is named after the client but does not carry its tags`);
}

/** One Knowledge Base: read it, check its tags, delete it unless it is already being deleted. */
async function deleteKnowledgeBase(bedrock: DeletionClients["bedrock"], target: DeletionTarget, id: string): Promise<boolean> {
  try {
    const { knowledgeBase } = await bedrock.send(new GetKnowledgeBaseCommand({ knowledgeBaseId: id }));
    const arn = knowledgeBase?.knowledgeBaseArn;
    if (!arn) throw new Error(`Knowledge Base ${id} has no ARN`);
    const { tags } = await bedrock.send(new ListTagsForResourceCommand({ resourceArn: arn }));
    assertClientTags(tags, target, id);
    if (knowledgeBase.status === "DELETING") return true;
    await bedrock.send(new DeleteKnowledgeBaseCommand({ knowledgeBaseId: id }));
    return true;
  } catch (error) {
    if (isGone(error, "ResourceNotFoundException")) return false;
    throw error;
  }
}

/**
 * The client's Knowledge Bases, found by name (`ListKnowledgeBases`: no `kb.json` to read). Its source is `CUSTOM`
 * in `RETAIN`: it goes with the base without touching the vectors, whose index goes at the next step.
 */
async function deleteKnowledgeBases(clients: DeletionClients, target: DeletionTarget): Promise<string[]> {
  clientPrefix(target.clientId);
  const ids = await knowledgeBasesNamed(clients.bedrock, `${target.kbPrefix}-client-${target.clientId}`);
  const deleted: string[] = [];
  for (const id of ids) {
    if (await deleteKnowledgeBase(clients.bedrock, target, id)) deleted.push(id);
  }
  return deleted;
}

/* ------------------------------------------------------------------ */
/* 2. S3 Vectors index                                                 */
/* ------------------------------------------------------------------ */

async function deleteVectorIndex(clients: DeletionClients, target: DeletionTarget): Promise<DeletionReport["vector_index"]> {
  clientPrefix(target.clientId);
  try {
    await clients.vectors.send(new DeleteIndexCommand({ vectorBucketName: target.vectorBucket, indexName: `client-${target.clientId}` }));
    return "deleted";
  } catch (error) {
    if (isGone(error, "NotFoundException")) return "absent";
    throw error;
  }
}

/* ------------------------------------------------------------------ */
/* 3. Objects of clients/<client_id>/, every version                   */
/* ------------------------------------------------------------------ */

/** `DeleteObjects` takes at most 1000 keys per call. */
export const DELETE_BATCH = 1000;
/** Full passes at most: a write still in flight during one pass is caught by the next. */
const MAX_PASSES = 3;

async function deleteBatch(s3: DeletionClients["s3"], bucket: string, batch: ObjectIdentifier[]): Promise<void> {
  const output = await s3.send(new DeleteObjectsCommand({ Bucket: bucket, Delete: { Objects: batch, Quiet: true } }));
  const failed = output.Errors ?? [];
  if (failed.length > 0) {
    const first = failed[0];
    throw new Error(`DeleteObjects refused ${failed.length} of ${batch.length} versions (${first?.Code}: ${first?.Key})`);
  }
}

/** Where the next page of `ListObjectVersions` starts. */
type Markers = { key?: string; version?: string };

/** One page of `ListObjectVersions` under the prefix, from the markers of the page before. */
async function versionsPage(s3: DeletionClients["s3"], bucket: string, prefix: string, markers: Markers) {
  const page = await s3.send(
    new ListObjectVersionsCommand({ Bucket: bucket, Prefix: prefix, KeyMarker: markers.key, VersionIdMarker: markers.version, MaxKeys: 1000 }),
  );
  const entries = [...(page.Versions ?? []), ...(page.DeleteMarkers ?? [])].map((entry) => ({
    Key: assertInBase(entry.Key, prefix),
    VersionId: entry.VersionId,
  }));
  if (!page.IsTruncated) return { entries, next: null };
  if (!page.NextKeyMarker) throw new Error("ListObjectVersions is truncated without NextKeyMarker");
  return { entries, next: { key: page.NextKeyMarker, version: page.NextVersionIdMarker } };
}

/** One pass: list every version and delete marker under the prefix, delete them by batches of DELETE_BATCH. */
async function deletePass(s3: DeletionClients["s3"], bucket: string, prefix: string): Promise<number> {
  let pending: ObjectIdentifier[] = [];
  let count = 0;
  let markers: Markers | null = {};
  while (markers) {
    const page = await versionsPage(s3, bucket, prefix, markers);
    pending.push(...page.entries);
    while (pending.length >= DELETE_BATCH) {
      await deleteBatch(s3, bucket, pending.slice(0, DELETE_BATCH));
      count += DELETE_BATCH;
      pending = pending.slice(DELETE_BATCH);
    }
    markers = page.next;
  }
  if (pending.length > 0) await deleteBatch(s3, bucket, pending);
  return count + pending.length;
}

/**
 * Passes until one finds nothing, MAX_PASSES at most. If the last one still deleted something, a write keeps coming:
 * one more listing decides, and a base that is still not empty fails the step (the Cognito user stays).
 */
async function deleteObjects(clients: DeletionClients, target: DeletionTarget): Promise<number> {
  const prefix = clientPrefix(target.clientId);
  let total = 0;
  for (let pass = 0; pass < MAX_PASSES; pass += 1) {
    const removed = await deletePass(clients.s3, target.bucket, prefix);
    total += removed;
    if (removed === 0) return total;
  }
  const left = await versionsPage(clients.s3, target.bucket, prefix, {});
  if (left.entries.length > 0) {
    throw new Error(`${prefix} still has versions after ${MAX_PASSES} passes: something keeps writing there`);
  }
  return total;
}

/* ------------------------------------------------------------------ */
/* 4. Cognito user                                                     */
/* ------------------------------------------------------------------ */

async function deleteCognitoUser(clients: DeletionClients, target: DeletionTarget): Promise<DeletionReport["account"]> {
  try {
    await clients.cognito.send(new AdminDeleteUserCommand({ UserPoolId: target.userPoolId, Username: target.sub }));
    return "deleted";
  } catch (error) {
    if (isGone(error, "UserNotFoundException")) return "absent";
    throw error;
  }
}

/** Run one step; a failure becomes a DeletionError that names it and the steps already done. */
async function step<T>(name: DeletionStep, completed: DeletionStep[], run: () => Promise<T>): Promise<T> {
  try {
    const result = await run();
    completed.push(name);
    return result;
  } catch (error) {
    throw new DeletionError(name, [...completed], error);
  }
}

/** The four steps, in order; the Cognito user is deleted only once the data is gone. */
export async function deleteAccountData(target: DeletionTarget, clients: DeletionClients): Promise<DeletionReport> {
  const completed: DeletionStep[] = [];
  const knowledgeBases = await step("knowledge_base", completed, () => deleteKnowledgeBases(clients, target));
  const vectorIndex = await step("vector_index", completed, () => deleteVectorIndex(clients, target));
  const objects = await step("objects", completed, () => deleteObjects(clients, target));
  const account = await step("account", completed, () => deleteCognitoUser(clients, target));
  return { knowledge_bases: knowledgeBases, vector_index: vectorIndex, objects, account };
}

const cache = globalThis as unknown as { __alphaforgeDeletionClients?: Map<string, DeletionClients> };

/** Real SDK clients of a region, made once per server process, with the task role's credentials. */
export function awsDeletionClients(region: string): DeletionClients {
  const clients = (cache.__alphaforgeDeletionClients ??= new Map());
  let made = clients.get(region);
  if (!made) {
    made = {
      bedrock: new BedrockAgentClient({ region }),
      vectors: new S3VectorsClient({ region }),
      s3: new S3Client({ region }),
      cognito: new CognitoIdentityProviderClient({ region }),
    };
    clients.set(region, made);
  }
  return made;
}
