/**
 * Zod schemas for every payload of app/CONTRACTS.md (version 1).
 *
 * Objects are not strict: the contract allows new optional fields, which zod strips.
 * Enumerations that drive the interface (stage, kind, status...) are strict; open
 * sets (actor, flags, provenance, error code) are plain strings so that a new value
 * does not break a whole response.
 */
import { z } from "zod";
import { RunOutcome } from "./collect";

/** ISO 8601 timestamp or date, as emitted by Python's isoformat(). */
const timestamp = z
  .string()
  .min(1)
  .refine((value) => !Number.isNaN(Date.parse(value)), { message: "Invalid ISO 8601 timestamp" });

const share = z.number().min(0).max(1);
const jsonRecord = z.record(z.string(), z.unknown());

export const LOCALES = ["fr", "en"] as const;
export const Locale = z.enum(LOCALES);
export type Locale = z.infer<typeof Locale>;

export const STAGES = [
  "base_questions",
  "existing_portfolio",
  "portfolio_review",
  "followups",
  "complete",
] as const;
export const Stage = z.enum(STAGES);
export type Stage = z.infer<typeof Stage>;

export const DIMENSIONS = [
  "knowledge",
  "objective",
  "horizon",
  "risk_tolerance",
  "risk_capacity",
  "constraints",
  "preferences",
  "behavior",
  "context",
] as const;
export const Dimension = z.enum(DIMENSIONS);
export type Dimension = z.infer<typeof Dimension>;

/** The five BNCD dimensions, with tolerance and capacity measured separately. */
export const PROFILE_DIMENSIONS = [
  "objective",
  "horizon",
  "risk_tolerance",
  "risk_capacity",
  "constraints",
  "preferences",
] as const;
export const ProfileDimensionKey = z.enum(PROFILE_DIMENSIONS);
export type ProfileDimensionKey = z.infer<typeof ProfileDimensionKey>;

export const QUESTION_KINDS = [
  "single_choice",
  "multi_choice",
  "boolean",
  "number",
  "money",
  "percent",
  "scale",
  "text",
] as const;
export const QuestionKind = z.enum(QUESTION_KINDS);
export type QuestionKind = z.infer<typeof QuestionKind>;

export const KNOWLEDGE_LEVELS = ["beginner", "intermediate", "advanced"] as const;
export const KnowledgeLevel = z.enum(KNOWLEDGE_LEVELS);
export type KnowledgeLevel = z.infer<typeof KnowledgeLevel>;

export const RISK_LEVELS = ["low", "low_medium", "medium", "medium_high", "high"] as const;
export const RiskLevel = z.enum(RISK_LEVELS);
export type RiskLevel = z.infer<typeof RiskLevel>;

export const ASSET_CLASSES = [
  "equity",
  "etf_equity",
  "etf_bond",
  "etf_commodity",
  "bond",
  "cash",
  "crypto",
  "fund",
  "other",
] as const;
export const AssetClass = z.enum(ASSET_CLASSES);
export type AssetClass = z.infer<typeof AssetClass>;

export const ACCOUNT_TYPES = ["tfsa", "rrsp", "resp", "rrif", "non_registered", "unknown"] as const;
export const AccountType = z.enum(ACCOUNT_TYPES);
export type AccountType = z.infer<typeof AccountType>;

export const TRACE_KINDS = ["deterministic", "agent", "model", "tool", "storage", "guardrail"] as const;
export const TraceKind = z.enum(TRACE_KINDS);
export type TraceKind = z.infer<typeof TraceKind>;

/** Actors listed by the contract; `TraceStep.actor` itself stays an open string. */
export const KNOWN_ACTORS = [
  "questionnaire",
  "completeness",
  "A1",
  "A2",
  "A4",
  "A5",
  "A6",
  "store",
  "guardrail",
] as const;

export const ERROR_CODES = [
  "bad_request",
  "unknown_action",
  "not_found",
  "invalid_answer",
  "conflict",
  "model_error",
  "guardrail_blocked",
  "internal",
] as const;
export type ErrorCode = (typeof ERROR_CODES)[number];

/** Value of an answer, by question kind (section 3.3). */
export const AnswerValue = z.union([z.string(), z.number(), z.boolean(), z.array(z.string())]);
export type AnswerValue = z.infer<typeof AnswerValue>;

export const Source = z.object({
  id: z.string(),
  title: z.string(),
  resource: z.string(),
  published_at: timestamp.nullish(),
  observed_at: timestamp.nullish(),
  retrieved_at: timestamp.nullish(),
});
export type Source = z.infer<typeof Source>;

export const QuestionOption = z.object({ value: z.string(), label: z.string() });
export type QuestionOption = z.infer<typeof QuestionOption>;

export const Question = z.object({
  id: z.string().min(1),
  source: z.enum(["deterministic", "a1"]),
  dimension: Dimension,
  kind: QuestionKind,
  prompt: z.string().min(1),
  help: z.string().nullish(),
  options: z.array(QuestionOption).nullish(),
  min: z.number().nullish(),
  max: z.number().nullish(),
  unit: z.string().nullish(),
  required: z.boolean().default(true),
  /** Profile field the answer fills, or null. Opaque to the interface, like `id`. */
  field: z.string().nullish(),
});
export type Question = z.infer<typeof Question>;

export const MissingField = z.object({
  dimension: Dimension,
  field: z.string(),
  label: z.string(),
});
export type MissingField = z.infer<typeof MissingField>;

export const Completeness = z.object({
  score: share,
  displayed: share,
  threshold: share,
  cap: share,
  ready: z.boolean(),
  missing: z.array(MissingField),
});
export type Completeness = z.infer<typeof Completeness>;

export const DimensionView = z.object({
  status: z.enum(["known", "partial", "missing"]),
  summary: z.string().nullable(),
  fields: jsonRecord,
});
export type DimensionView = z.infer<typeof DimensionView>;
export type DimensionStatus = DimensionView["status"];

export const Fact = z.object({
  field: z.string(),
  value: z.unknown(),
  provenance: z.string(),
  at: timestamp,
});
export type Fact = z.infer<typeof Fact>;

export const DocumentRef = z.object({ key: z.string(), title: z.string() });
export type DocumentRef = z.infer<typeof DocumentRef>;

/** Tolerance, capacity and their minimum, all computed by code (optional in ProfileView). */
export const RiskDetail = z.object({
  tolerance: RiskLevel.nullable(),
  capacity: RiskLevel.nullable(),
  effective: RiskLevel.nullable(),
});
export type RiskDetail = z.infer<typeof RiskDetail>;

export const ProfileView = z.object({
  knowledge_level: KnowledgeLevel.nullable(),
  effective_risk: RiskLevel.nullable(),
  dimensions: z.object({
    objective: DimensionView,
    horizon: DimensionView,
    risk_tolerance: DimensionView,
    risk_capacity: DimensionView,
    constraints: DimensionView,
    preferences: DimensionView,
    /** Context of the investor (amount, existing portfolio); optional. */
    context: DimensionView.optional(),
  }),
  risk: RiskDetail.optional(),
  facts: z.array(Fact),
  /** Only filled by `profile.get`. */
  documents: z.array(DocumentRef).optional(),
});
export type ProfileView = z.infer<typeof ProfileView>;

export const Position = z.object({
  id: z.string().min(1),
  raw: z.string().nullish(),
  ticker: z.string().nullish(),
  name: z.string().nullish(),
  asset_class: AssetClass.nullish(),
  sector: z.string().nullish(),
  market: z.string().nullish(),
  currency: z.string().nullish(),
  quantity: z.number().nullish(),
  market_value: z.number().nullish(),
  account_type: AccountType.nullish(),
  price: z.number().nullish(),
  price_date: z.string().nullish(),
  price_source: z.string().nullish(),
  value_cad: z.number().nullish(),
  resolved: z.boolean(),
  notes: z.string().nullish(),
});
export type Position = z.infer<typeof Position>;

export const Exposures = z.object({
  total_value_cad: z.number().min(0),
  by_asset_class: z.record(z.string(), share),
  by_currency: z.record(z.string(), share),
  by_market: z.record(z.string(), share),
  by_sector: z.record(z.string(), share),
  top_positions: z.array(z.object({ id: z.string(), weight: share })),
  flags: z.array(z.string()),
});
export type Exposures = z.infer<typeof Exposures>;

/** Rate used to convert USD to CAD, with its source (optional in PortfolioView). */
export const FxRate = z.object({
  pair: z.string(),
  rate: z.number().positive(),
  date: z.string(),
  source: z.string(),
});
export type FxRate = z.infer<typeof FxRate>;

/** `position_id` points at the row of `positions` that could not be valued, when there is one. */
export const UnresolvedItem = z.object({ raw: z.string(), reason: z.string(), position_id: z.string().nullish() });
export type UnresolvedItem = z.infer<typeof UnresolvedItem>;

export const PortfolioView = z.object({
  positions: z.array(Position),
  unresolved: z.array(UnresolvedItem),
  fx: FxRate.nullish(),
  exposures: Exposures,
  status: z.enum(["draft", "confirmed"]),
  sources: z.array(Source),
});
export type PortfolioView = z.infer<typeof PortfolioView>;

export const TraceStep = z.object({
  id: z.string(),
  at: timestamp,
  kind: TraceKind,
  actor: z.string().min(1),
  title: z.string(),
  detail: z.string().nullish(),
  inputs: z.unknown().optional(),
  outputs: z.unknown().optional(),
  sources: z.array(Source).default([]),
  duration_ms: z.number().min(0).nullish(),
});
export type TraceStep = z.infer<typeof TraceStep>;

export const ErrorBody = z.object({
  code: z.string().min(1),
  message: z.string(),
  details: z.unknown().optional(),
});
export type ErrorBody = z.infer<typeof ErrorBody>;

export const ErrorEnvelope = z.object({
  ok: z.literal(false),
  /** Always present for runtime errors; `null` when the local gateway itself failed. */
  release: z.string().nullish(),
  error: ErrorBody,
});
export type ErrorEnvelope = z.infer<typeof ErrorEnvelope>;

const ClientStateObject = z.object({
  ok: z.literal(true),
  release: z.string(),
  client_id: z.uuid(),
  locale: Locale,
  stage: Stage,
  message: z.string().nullable(),
  questions: z.array(Question),
  profile: ProfileView,
  completeness: Completeness,
  portfolio: PortfolioView.nullable(),
  trace: z.array(TraceStep),
});

/** Cardinality of `questions` per stage (section 3.2). */
function questionCountFits(stage: Stage, count: number): boolean {
  if (stage === "base_questions") return count === 1;
  if (stage === "followups") return count <= 3;
  return count === 0;
}

export const ClientState = ClientStateObject.superRefine((state, context) => {
  const count = state.questions.length;
  if (!questionCountFits(state.stage, count)) {
    context.addIssue({
      code: "custom",
      path: ["questions"],
      message: `Stage ${state.stage} cannot carry ${count} question(s)`,
    });
  }
});
export type ClientState = z.infer<typeof ClientState>;

export const HealthResponse = z.object({
  ok: z.literal(true),
  role: z.string(),
  release: z.string(),
  env: z.string(),
});
export type HealthResponse = z.infer<typeof HealthResponse>;

export const KbItem = z.object({
  key: z.string().min(1),
  title: z.string().nullish(),
  type: z.string().nullish(),
  description: z.string().nullish(),
  updated_at: timestamp.nullish(),
});
export type KbItem = z.infer<typeof KbItem>;

export const KbListResponse = z.object({
  ok: z.literal(true),
  release: z.string(),
  items: z.array(KbItem),
});
export type KbListResponse = z.infer<typeof KbListResponse>;

export const KbGetResponse = z.object({
  ok: z.literal(true),
  release: z.string(),
  key: z.string(),
  content: z.string(),
});
export type KbGetResponse = z.infer<typeof KbGetResponse>;

/** One `data:` event of a streamed response (section 3.4). */
export const StreamEvent = z.discriminatedUnion("type", [
  z.object({ type: z.literal("trace"), step: TraceStep }),
  z.object({ type: z.literal("delta"), text: z.string() }),
  z.object({ type: z.literal("result"), result: ClientState }),
  z.object({ type: z.literal("error"), error: ErrorBody }),
]);
export type StreamEvent = z.infer<typeof StreamEvent>;

/** Any non-streamed response: the action's success shape, or the error envelope. */
export function envelopeOf<T extends z.ZodType>(success: T) {
  return z.union([success, ErrorEnvelope]);
}

/* ------------------------------------------------------------------ */
/* Collection (Step Functions) as exposed by the local gateway.        */
/* Not part of CONTRACTS.md: the shapes below are app/web's own API.   */
/* ------------------------------------------------------------------ */

export const EXECUTION_STATUSES = [
  "RUNNING",
  "SUCCEEDED",
  "FAILED",
  "TIMED_OUT",
  "ABORTED",
  "PENDING_REDRIVE",
] as const;
export const ExecutionStatus = z.enum(EXECUTION_STATUSES);
export type ExecutionStatus = z.infer<typeof ExecutionStatus>;

export const ExecutionSummary = z.object({
  execution_arn: z.string(),
  name: z.string(),
  status: ExecutionStatus,
  start_date: timestamp,
  stop_date: timestamp.nullable(),
  /** Per-collector status, documents and ingestion, from the output once the run is over. */
  outcome: RunOutcome.nullable(),
});
export type ExecutionSummary = z.infer<typeof ExecutionSummary>;

export const ExecutionDetail = ExecutionSummary.extend({
  input: z.unknown().nullable(),
  output: z.unknown().nullable(),
  error: z.string().nullable(),
  cause: z.string().nullable(),
});
export type ExecutionDetail = z.infer<typeof ExecutionDetail>;

export const ExecutionListResponse = z.object({
  ok: z.literal(true),
  state_machine: z.object({ name: z.string(), arn: z.string() }),
  executions: z.array(ExecutionSummary),
});
export type ExecutionListResponse = z.infer<typeof ExecutionListResponse>;

export const ExecutionStartResponse = z.object({ ok: z.literal(true), execution: ExecutionSummary });
export type ExecutionStartResponse = z.infer<typeof ExecutionStartResponse>;

export const ExecutionDetailResponse = z.object({ ok: z.literal(true), execution: ExecutionDetail });
export type ExecutionDetailResponse = z.infer<typeof ExecutionDetailResponse>;

/** `GET /api/health`: gateway mode plus the runtime's own `health` answer. */
export const GatewayHealth = z.object({
  ok: z.boolean(),
  mode: z.enum(["mock", "local", "aws"]),
  agent: HealthResponse.nullable(),
  runtime: z
    .object({ name: z.string(), arn: z.string().nullable(), status: z.string().nullable() })
    .nullable(),
  error: ErrorBody.nullable(),
});
export type GatewayHealth = z.infer<typeof GatewayHealth>;
