import { createCipheriv, createDecipheriv, hkdfSync, randomBytes } from "node:crypto";

/**
 * Encrypted and authenticated cookie values (AES-256-GCM, `node:crypto`). The key comes from
 * AUTH_SESSION_SECRET by HKDF; the purpose (session, login) is the additional data, so a value
 * sealed for one purpose never opens as another. Format: `v1.<base64url(iv | tag | ciphertext)>`.
 */
const VERSION = "v1";
const IV_BYTES = 12;
const TAG_BYTES = 16;

export interface SealOptions {
  secret: string;
  purpose: "session" | "login";
  /** Unix time (seconds) after which the value no longer opens. */
  expiresAt: number;
}

function keyOf(secret: string): Buffer {
  return Buffer.from(hkdfSync("sha256", secret, "alphaforge", "alphaforge/cookie/v1", 32));
}

export function nowSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

export function seal(payload: Record<string, unknown>, { secret, purpose, expiresAt }: SealOptions): string {
  const iv = randomBytes(IV_BYTES);
  const cipher = createCipheriv("aes-256-gcm", keyOf(secret), iv);
  cipher.setAAD(Buffer.from(purpose, "utf8"));
  const body = Buffer.concat([cipher.update(JSON.stringify({ ...payload, exp: expiresAt }), "utf8"), cipher.final()]);
  return `${VERSION}.${Buffer.concat([iv, cipher.getAuthTag(), body]).toString("base64url")}`;
}

function decrypt(token: string, secret: string, purpose: string): string | null {
  const [version, data, extra] = token.split(".");
  if (version !== VERSION || !data || extra !== undefined) return null;
  const raw = Buffer.from(data, "base64url");
  if (raw.length <= IV_BYTES + TAG_BYTES) return null;
  try {
    const decipher = createDecipheriv("aes-256-gcm", keyOf(secret), raw.subarray(0, IV_BYTES));
    decipher.setAAD(Buffer.from(purpose, "utf8"));
    decipher.setAuthTag(raw.subarray(IV_BYTES, IV_BYTES + TAG_BYTES));
    return Buffer.concat([decipher.update(raw.subarray(IV_BYTES + TAG_BYTES)), decipher.final()]).toString("utf8");
  } catch {
    return null;
  }
}

/** The payload, or null if the value is missing, altered, sealed for another purpose or expired. */
export function unseal(
  token: string | null | undefined,
  { secret, purpose }: Omit<SealOptions, "expiresAt">,
): Record<string, unknown> | null {
  if (!token) return null;
  const text = decrypt(token, secret, purpose);
  if (text === null) return null;
  try {
    const payload: unknown = JSON.parse(text);
    if (typeof payload !== "object" || payload === null || Array.isArray(payload)) return null;
    const record = payload as Record<string, unknown>;
    return typeof record.exp === "number" && record.exp > nowSeconds() ? record : null;
  } catch {
    return null;
  }
}
