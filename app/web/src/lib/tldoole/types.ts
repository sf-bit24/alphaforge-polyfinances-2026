/**
 * Contract of the `tldoole` runtime as seen by the interface (CONTRACTS.md, section 8):
 * `feed`, `feedback` and `request`. Responses are validated loosely: an added field never breaks the UI.
 */
import { z } from "zod";

const ClientId = z.uuid();
const VideoId = z.string().regex(/^v\d{8}t\d{6}-[a-z0-9_]{2,40}-[0-9a-f]{4}$/);

export const TldooleRequestSchema = z.discriminatedUnion("action", [
  z.object({ action: z.literal("feed"), client_id: ClientId }),
  z.object({
    action: z.literal("feedback"),
    client_id: ClientId,
    video_id: VideoId,
    verdict: z.enum(["understood", "unclear"]).optional(),
    quiz_answer: z.number().int().min(0).max(5).optional(),
  }),
  z.object({ action: z.literal("request"), client_id: ClientId, concept_id: z.string().regex(/^[a-z][a-z0-9_]{1,40}$/) }),
]);
export type TldooleRequest = z.infer<typeof TldooleRequestSchema>;

export const VIDEO_STATUSES = ["queued", "scripting", "rendering", "ready", "failed"] as const;
export type VideoStatus = (typeof VIDEO_STATUSES)[number];

const Source = z.looseObject({ id: z.string(), title: z.string(), resource: z.string().optional() });

const Why = z.looseObject({
  kind: z.string(),
  quote: z.string().optional(),
  field: z.string().optional(),
  value: z.unknown().optional(),
  provenance: z.string().optional(),
  at: z.string().nullable().optional(),
});

export const VideoCardSchema = z.looseObject({
  video_id: z.string(),
  concept_id: z.string(),
  label: z.string().nullable(),
  title: z.string().nullable(),
  status: z.enum(VIDEO_STATUSES),
  level: z.string().nullable(),
  locale: z.string().nullable(),
  reason: z.string().nullable(),
  version: z.number().default(1),
  created_at: z.string().nullable(),
  updated_at: z.string().nullable(),
  duration_ms: z.number().nullable(),
  why: z.array(Why).default([]),
  quiz: z.object({ question: z.string(), options: z.array(z.string()) }).nullable(),
  sources: z.array(Source).default([]),
  feedback: z
    .looseObject({ verdict: z.string(), quiz_answer: z.number().nullable().optional(), correct: z.boolean().nullable().optional() })
    .nullable(),
  error: z.looseObject({ code: z.string(), message: z.string() }).nullable(),
  doc_key: z.string().optional(),
  video_url: z.string().nullable(),
  poster_url: z.string().nullable(),
  captions_url: z.string().nullable(),
});
export type VideoCard = z.infer<typeof VideoCardSchema>;

export const GapSchema = z.looseObject({
  concept_id: z.string(),
  label: z.string().nullable(),
  status: z.string().nullable(),
  confidence: z.number().nullable(),
  reason: z.string().nullable(),
  detector: z.string().nullable(),
  video_id: z.string().nullable().optional(),
  detected_at: z.string().nullable().optional(),
});
export type Gap = z.infer<typeof GapSchema>;

export const FeedSchema = z.looseObject({
  client_id: z.string(),
  locale: z.enum(["fr", "en"]).default("fr"),
  videos: z.array(VideoCardSchema),
  gaps: z.array(GapSchema).default([]),
  pending: z.number().default(0),
  catalog: z.array(z.object({ concept_id: z.string(), label: z.string(), title: z.string() })).default([]),
});
export type Feed = z.infer<typeof FeedSchema>;

export const FeedbackSchema = z.looseObject({
  video: VideoCardSchema,
  quiz: z.object({ correct: z.boolean(), answer: z.number(), explanation: z.string().nullable() }).nullable(),
  follow_up: VideoCardSchema.nullable(),
});
export type FeedbackResult = z.infer<typeof FeedbackSchema>;

export const RequestResultSchema = z.looseObject({ video: VideoCardSchema, created: z.boolean() });
export type RequestResult = z.infer<typeof RequestResultSchema>;

export const ErrorEnvelopeSchema = z.object({
  ok: z.literal(false),
  error: z.looseObject({ code: z.string(), message: z.string() }),
});
