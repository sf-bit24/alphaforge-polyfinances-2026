import { createHash } from "node:crypto";

/** What the runtime accepts as a client_id (app/agents/src/alphaforge/profile/state.py, `UUID4`). */
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/**
 * The client_id of an account (CONTRACTS.md 7.1): one account, one base `clients/<client_id>/`.
 * A Cognito `sub` is a UUID v4 and is used as is. Any other `sub` gives a UUID derived from
 * SHA-256(`alphaforge:` + sub), with the version 4 and RFC 4122 variant bits set: the same account
 * always finds the same base, and the runtime accepts the id.
 */
export function accountClientId(sub: string): string {
  const lower = sub.toLowerCase();
  if (UUID_V4.test(lower)) return lower;
  const bytes = createHash("sha256").update(`alphaforge:${sub}`, "utf8").digest().subarray(0, 16);
  bytes.writeUInt8((bytes.readUInt8(6) & 0x0f) | 0x40, 6);
  bytes.writeUInt8((bytes.readUInt8(8) & 0x3f) | 0x80, 8);
  const hex = bytes.toString("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
