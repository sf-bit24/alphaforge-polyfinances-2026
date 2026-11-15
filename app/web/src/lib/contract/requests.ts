/**
 * Requests accepted by the local gateway for the `profile` runtime (CONTRACTS.md 3.2).
 *
 * The gateway validates every request with these schemas before it reaches the
 * mock, the local runtime or AgentCore. Unknown fields are stripped, so only the
 * contract's fields are forwarded.
 */
import { z } from "zod";
import { AccountType, AnswerValue, AssetClass, KnowledgeLevel, Locale } from "./schemas";

export const UPLOAD_LIMITS = {
  maxFiles: 5,
  maxFileBytes: 10 * 1024 * 1024,
  maxTextChars: 1_000_000,
  maxMessageChars: 4_000,
  maxPositions: 500,
} as const;

/** Largest JSON body the gateway reads: five 10 MB files in base64, plus text. */
export const MAX_BODY_BYTES =
  Math.ceil((UPLOAD_LIMITS.maxFiles * UPLOAD_LIMITS.maxFileBytes * 4) / 3) + 4 * 1024 * 1024;

const UUID_PATTERN = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
const CLIENT_PREFIX = new RegExp(`^clients/(${UUID_PATTERN})/$`);
const CLIENT_KEY = new RegExp(`^clients/(${UUID_PATTERN})/[A-Za-z0-9._\\-/]+$`);
const GENERAL_KEY = /^general\/[A-Za-z0-9._\-/]+$/;

export const ClientId = z.uuid();

/** Client id embedded in a `clients/<id>/...` key or prefix, if any. */
export function clientIdOfKey(keyOrPrefix: string): string | null {
  const match = CLIENT_PREFIX.exec(keyOrPrefix) ?? CLIENT_KEY.exec(keyOrPrefix);
  return match?.[1]?.toLowerCase() ?? null;
}

function hasTraversal(key: string): boolean {
  return key.split("/").some((part) => part === ".." || part === ".");
}

function base64Padding(data: string): number {
  if (data.endsWith("==")) return 2;
  return data.endsWith("=") ? 1 : 0;
}

/** Decoded size of a base64 string, without decoding it. */
export function base64DecodedBytes(data: string): number {
  return Math.floor((data.length * 3) / 4) - base64Padding(data);
}

const BASE64 = /^[A-Za-z0-9+/]*={0,2}$/;

export const UploadFile = z
  .object({
    name: z.string().trim().min(1).max(255),
    media_type: z
      .string()
      .trim()
      .max(255)
      .optional()
      .transform((value) => value || "application/octet-stream"),
    data_base64: z.string().min(1),
  })
  .superRefine((file, ctx) => {
    if (file.data_base64.length % 4 !== 0 || !BASE64.test(file.data_base64)) {
      ctx.addIssue({ code: "custom", path: ["data_base64"], message: "Invalid base64 content" });
      return;
    }
    const bytes = base64DecodedBytes(file.data_base64);
    if (bytes > UPLOAD_LIMITS.maxFileBytes) {
      ctx.addIssue({
        code: "custom",
        path: ["data_base64"],
        message: `File ${file.name} is ${bytes} bytes; the limit is ${UPLOAD_LIMITS.maxFileBytes}`,
      });
    }
  });
export type UploadFile = z.infer<typeof UploadFile>;

/** A position as sent back by the investor in `portfolio.confirm`. */
export const PositionInput = z.object({
  id: z.string().trim().min(1).max(64),
  raw: z.string().max(2_000).nullish(),
  ticker: z.string().trim().max(32).nullish(),
  name: z.string().max(200).nullish(),
  asset_class: AssetClass.nullish(),
  sector: z.string().max(120).nullish(),
  market: z.string().max(120).nullish(),
  currency: z
    .string()
    .trim()
    .regex(/^[A-Za-z]{3}$/, "ISO 4217 currency code expected")
    .transform((value) => value.toUpperCase())
    .nullish(),
  quantity: z.number().finite().min(0).nullish(),
  market_value: z.number().finite().min(0).nullish(),
  account_type: AccountType.nullish(),
  price: z.number().finite().min(0).nullish(),
  price_date: z.string().max(40).nullish(),
  price_source: z.string().max(200).nullish(),
  value_cad: z.number().finite().min(0).nullish(),
  resolved: z.boolean().default(false),
  notes: z.string().max(1_000).nullish(),
});
export type PositionInput = z.infer<typeof PositionInput>;

const MAX_ANSWER_CHARS = 4_000;
const MAX_ANSWER_OPTIONS = 50;
const MAX_OPTION_CHARS = 500;

function isAnswerValueInBounds(value: AnswerValue): boolean {
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value === "string") return value.length <= MAX_ANSWER_CHARS;
  if (Array.isArray(value)) return value.length <= MAX_ANSWER_OPTIONS && value.every((item) => item.length <= MAX_OPTION_CHARS);
  return true;
}

const answerValue = AnswerValue.refine(isAnswerValueInBounds, { message: "Answer value out of bounds" });

const kbPrefix = z.string().refine(
  (prefix) => prefix === "general/" || CLIENT_PREFIX.test(prefix),
  { message: "prefix must be general/ or clients/<client_id>/" },
);

const kbKey = z
  .string()
  .max(512)
  .refine((key) => (GENERAL_KEY.test(key) || CLIENT_KEY.test(key)) && !hasTraversal(key), {
    message: "key must be a general/ or clients/<client_id>/ document",
  });

export const AgentRequest = z.discriminatedUnion("action", [
  z.object({ action: z.literal("health") }),
  z.object({ action: z.literal("session.start"), locale: Locale, client_id: ClientId.optional() }),
  z.object({ action: z.literal("session.resume"), client_id: ClientId, locale: Locale.optional() }),
  z.object({
    action: z.literal("base.answer"),
    client_id: ClientId,
    question_id: z.string().trim().min(1).max(100),
    value: answerValue,
  }),
  z
    .object({
      action: z.literal("portfolio.submit"),
      client_id: ClientId,
      text: z.string().max(UPLOAD_LIMITS.maxTextChars).optional(),
      files: z.array(UploadFile).max(UPLOAD_LIMITS.maxFiles).optional(),
      stream: z.boolean().optional(),
    })
    .refine((req) => (req.text?.trim().length ?? 0) > 0 || (req.files?.length ?? 0) > 0, {
      message: "Provide text or at least one file",
      path: ["text"],
    }),
  z.object({
    action: z.literal("portfolio.confirm"),
    client_id: ClientId,
    positions: z.array(PositionInput).min(1).max(UPLOAD_LIMITS.maxPositions),
  }),
  z.object({ action: z.literal("portfolio.skip"), client_id: ClientId }),
  z.object({
    action: z.literal("followup.reply"),
    client_id: ClientId,
    answers: z
      .array(z.object({ question_id: z.string().trim().min(1).max(100), value: answerValue }))
      .max(10)
      .optional(),
    message: z.string().max(UPLOAD_LIMITS.maxMessageChars).optional(),
    stop: z.boolean().optional(),
    stream: z.boolean().optional(),
  }),
  z
    .object({
      action: z.literal("settings.update"),
      client_id: ClientId,
      locale: Locale.optional(),
      knowledge_level: KnowledgeLevel.optional(),
    })
    .refine((req) => req.locale !== undefined || req.knowledge_level !== undefined, {
      message: "Provide locale or knowledge_level",
    }),
  z.object({ action: z.literal("profile.get"), client_id: ClientId }),
  z
    .object({ action: z.literal("kb.list"), prefix: kbPrefix, client_id: ClientId.optional() })
    .refine((req) => sameClient(req.prefix, req.client_id), {
      message: "A clients/ prefix is only served with the matching client_id",
      path: ["client_id"],
    }),
  z
    .object({ action: z.literal("kb.get"), key: kbKey, client_id: ClientId.optional() })
    .refine((req) => sameClient(req.key, req.client_id), {
      message: "A clients/ key is only served with the matching client_id",
      path: ["client_id"],
    }),
]);
export type AgentRequest = z.infer<typeof AgentRequest>;
export type AgentRequestInput = z.input<typeof AgentRequest>;
export type AgentAction = AgentRequest["action"];

export const AGENT_ACTIONS: readonly AgentAction[] = [
  "health",
  "session.start",
  "session.resume",
  "base.answer",
  "portfolio.submit",
  "portfolio.confirm",
  "portfolio.skip",
  "followup.reply",
  "settings.update",
  "profile.get",
  "kb.list",
  "kb.get",
];

/** Actions that may answer with `text/event-stream` (section 3.4). */
export const STREAMABLE_ACTIONS: readonly AgentAction[] = ["portfolio.submit", "followup.reply"];

function sameClient(keyOrPrefix: string, clientId: string | undefined): boolean {
  const owner = clientIdOfKey(keyOrPrefix);
  if (owner === null) return true;
  return clientId !== undefined && clientId.toLowerCase() === owner;
}

/**
 * Body of `POST /api/collect` (input of the Step Functions machine, section 6).
 * The interface never sets `run_id` nor the execution name: Step Functions names the
 * execution with a UUID, which becomes the run_id.
 */
export const CollectRequest = z.object({
  since: z.iso.date().optional(),
  tickers: z
    .array(z.string().trim().regex(/^[A-Za-z0-9.\-^=]{1,15}$/, "Invalid ticker"))
    .max(50)
    .optional(),
});
export type CollectRequest = z.infer<typeof CollectRequest>;
