/**
 * Zod schemas of the `portfolio` runtime (CONTRACTS.md 12): the `build` request and its response.
 *
 * The response carries a finance `Decision` (app/agents/src/alphaforge/finance/contracts/decision.py,
 * schema 0.1.0) and the summary of step 0 (`StrategyResult.summary()`, finance/strategy/select.py).
 * As for the profile runtime, objects strip unknown fields (a new field must be optional), while the
 * enumerations the screen depends on (kind, labels, status, style) are strict. `Decision` also re-checks
 * the integrity rules of the Python model, so a drift in the backend fails here and not on screen:
 * every cited fact_id exists, every fact points at a trace event, a proposition's weights sum to 1.
 *
 * The interface displays these objects; it computes nothing financial from them.
 */
import { z } from "zod";
import { Locale } from "./schemas";

const timestamp = z
  .string()
  .min(1)
  .refine((value) => !Number.isNaN(Date.parse(value)), { message: "Invalid ISO 8601 timestamp" });
const isoDate = z.iso.date();
const share = z.number().min(0).max(1);

/** Fictional demo profiles of the finance engine (tests/finance/policy/_personas.py). */
export const DEMO_PERSONAS = ["amira", "mateo", "robert"] as const;
export const DemoPersona = z.enum(DEMO_PERSONAS);
export type DemoPersona = z.infer<typeof DemoPersona>;

/** `finance.strategy.STYLES`. */
export const STYLES = ["defensive", "dynamique", "offensive"] as const;
export const Style = z.enum(STYLES);
export type Style = z.infer<typeof Style>;

export const BUILD_MODES = ["llm", "rules"] as const;
export const BuildMode = z.enum(BUILD_MODES);
export type BuildMode = z.infer<typeof BuildMode>;

/* ------------------------------------------------------------------ */
/* Decision (contracts/decision.py, v0.1.0)                            */
/* ------------------------------------------------------------------ */

export const FACT_LABELS = ["FAIT", "HYPOTHESE", "FICTION"] as const;
export const FactLabel = z.enum(FACT_LABELS);
export type FactLabel = z.infer<typeof FactLabel>;

export const FactSource = z.object({
  dataset: z.string().min(1),
  url: z.string().nullish(),
  licence: z.string().nullish(),
  retrieved_utc: timestamp.nullish(),
  sha256: z.string().nullish(),
  processing: z.string().nullish(),
});
export type FactSource = z.infer<typeof FactSource>;

export const DecisionFact = z.object({
  fact_id: z.string().min(1),
  label_fr: z.string(),
  value: z.union([z.number(), z.string()]).nullable(),
  unit: z.string(),
  currency: z.enum(["CAD", "USD", "EUR"]).nullish(),
  as_of: isoDate.nullish(),
  published: isoDate.nullish(),
  status: FactLabel,
  sources: z.array(FactSource).min(1),
  trace_id: z.string().min(1),
});
export type DecisionFact = z.infer<typeof DecisionFact>;

export const DecisionTraceEvent = z.object({
  trace_id: z.string().min(1),
  parent_id: z.string().nullish(),
  agent: z.string().min(1),
  tool: z.string().nullish(),
  inputs: z.record(z.string(), z.unknown()).default({}),
  output_summary: z.string().nullish(),
  fact_ids: z.array(z.string()).default([]),
  started_utc: timestamp,
  ended_utc: timestamp.nullish(),
  status: z.enum(["ok", "erreur", "refus"]),
  message: z.string().nullish(),
  data_version: z.string().nullish(),
  code_version: z.string().nullish(),
  seed: z.number().int().nullish(),
  model_id: z.string().nullish(),
  otel_trace_id: z.string().nullish(),
  otel_span_id: z.string().nullish(),
});
export type DecisionTraceEvent = z.infer<typeof DecisionTraceEvent>;

/** `role` is open in the contract (« coeur », « satellite », « reserve »...); the screen knows the first two. */
export const DecisionPosition = z.object({
  asset_id: z.string().min(1),
  weight: share,
  goal_id: z.string().nullish(),
  role: z.string().nullish(),
  rationale_fact_ids: z.array(z.string()).default([]),
});
export type DecisionPosition = z.infer<typeof DecisionPosition>;

export const ConstraintCheck = z.object({
  rule_id: z.string().min(1),
  description_fr: z.string(),
  derived_from: z.string(),
  limit: z.number().nullish(),
  value_fact_id: z.string().nullish(),
  active: z.boolean().default(false),
  violated: z.boolean().default(false),
  shadow_price: z.number().nullish(),
  blocking: z.boolean().default(true),
});
export type ConstraintCheck = z.infer<typeof ConstraintCheck>;

export const Statement = z.object({
  text_fr: z.string(),
  fact_ids: z.array(z.string()).default([]),
  label: FactLabel.default("FAIT"),
});
export type Statement = z.infer<typeof Statement>;

/** The four questions of the NBDB workshop. */
export const EXPLANATION_SECTIONS = ["data_used", "why", "limits", "what_would_change"] as const;
export type ExplanationSection = (typeof EXPLANATION_SECTIONS)[number];

export const Explanation = z.object({
  data_used: z.array(Statement),
  why: z.array(Statement),
  limits: z.array(Statement),
  what_would_change: z.array(Statement),
});
export type Explanation = z.infer<typeof Explanation>;

export const Counterfactual = z.object({
  change_fr: z.string(),
  result_fact_ids: z.array(z.string()).min(1),
});
export type Counterfactual = z.infer<typeof Counterfactual>;

export const DECISION_KINDS = ["proposition", "refus_encadre", "position_attente", "incomplet", "protection"] as const;
export const DecisionKind = z.enum(DECISION_KINDS);
export type DecisionKind = z.infer<typeof DecisionKind>;

/** Same tolerance as `WEIGHT_TOLERANCE` in decision.py. */
const WEIGHT_TOLERANCE = 1e-6;

export const Decision = z
  .object({
    schema_version: z.literal("0.1.0"),
    decision_id: z.string().min(1),
    profile_id: z.string().min(1),
    profile_version: z.number().int().min(1),
    created_utc: timestamp,
    kind: DecisionKind,
    simulation_only: z.literal(true),
    positions: z.array(DecisionPosition).default([]),
    facts: z.array(DecisionFact).default([]),
    constraints: z.array(ConstraintCheck).default([]),
    counterfactuals: z.array(Counterfactual).default([]),
    explanation: Explanation,
    reprofile_triggers_fired: z.array(z.string()).default([]),
    trace: z.array(DecisionTraceEvent).min(1),
    disclaimer_fr: z.string(),
  })
  .superRefine((decision, ctx) => {
    // Integrity rules of Decision._integrity (decision.py): the screen relies on them for its fact chips.
    const factIds = new Set<string>();
    for (const fact of decision.facts) {
      if (factIds.has(fact.fact_id)) ctx.addIssue({ code: "custom", path: ["facts"], message: `Duplicate fact_id ${fact.fact_id}` });
      factIds.add(fact.fact_id);
    }
    const traceIds = new Set(decision.trace.map((event) => event.trace_id));
    for (const fact of decision.facts) {
      if (!traceIds.has(fact.trace_id)) {
        ctx.addIssue({ code: "custom", path: ["facts"], message: `Fact ${fact.fact_id}: trace_id ${fact.trace_id} is not in the trace` });
      }
    }
    const cited = new Set<string>();
    for (const section of EXPLANATION_SECTIONS) for (const statement of decision.explanation[section]) statement.fact_ids.forEach((id) => cited.add(id));
    for (const position of decision.positions) position.rationale_fact_ids.forEach((id) => cited.add(id));
    for (const counterfactual of decision.counterfactuals) counterfactual.result_fact_ids.forEach((id) => cited.add(id));
    for (const check of decision.constraints) if (check.value_fact_id) cited.add(check.value_fact_id);
    const unknown = [...cited].filter((id) => !factIds.has(id)).sort();
    if (unknown.length > 0) {
      ctx.addIssue({ code: "custom", path: ["facts"], message: `Cited without a Fact: ${unknown.slice(0, 5).join(", ")}` });
    }
    if (decision.kind === "proposition") {
      if (decision.positions.length === 0) ctx.addIssue({ code: "custom", path: ["positions"], message: "A proposition must have positions" });
      // A validation of the backend's own invariant, never shown on screen.
      const total = decision.positions.reduce((sum, position) => sum + position.weight, 0);
      if (decision.positions.length > 0 && Math.abs(total - 1) > WEIGHT_TOLERANCE) {
        ctx.addIssue({ code: "custom", path: ["positions"], message: `Weights sum to ${total}, not 1` });
      }
      if (decision.constraints.some((check) => check.violated && check.blocking)) {
        ctx.addIssue({ code: "custom", path: ["constraints"], message: "A proposition cannot violate a blocking constraint" });
      }
    }
  });
export type Decision = z.infer<typeof Decision>;

/* ------------------------------------------------------------------ */
/* Step 0 and debate (strategy/select.py, debate/schemas.py)           */
/* ------------------------------------------------------------------ */

/** `StrategyResult.summary()`. */
export const StrategySummary = z.object({
  style: Style,
  from_level: Style,
  applied: z.boolean(),
  shortlist: z.array(z.string()),
  growth_floor: share.nullable(),
  floors: z.record(z.string(), share),
  sector_caps: z.record(z.string(), share),
  fallback: z.array(z.string()),
  version: z.string().min(1),
});
export type StrategySummary = z.infer<typeof StrategySummary>;

export const LENS_VERDICTS = ["soutien", "objection_maintenue", "objection_satisfaite"] as const;
export const LensVerdict = z.enum(LENS_VERDICTS);
export type LensVerdict = z.infer<typeof LensVerdict>;

/** `AppliedAmendment`: an amendment of a lens, applied or rejected by the code. */
export const AppliedAmendment = z.object({
  lens: z.string(),
  status: z.enum(["applique", "rejete"]),
  why_fr: z.string(),
  amendment: z.object({
    kind: z.string(),
    target: z.string(),
    value: z.number().nullish(),
    reason_fr: z.string(),
    evidence_fact_ids: z.array(z.string()).default([]),
  }),
  before: z.union([z.number(), z.string()]).nullish(),
  after: z.union([z.number(), z.string()]).nullish(),
});
export type AppliedAmendment = z.infer<typeof AppliedAmendment>;

export const DebateRoundSummary = z.object({
  round: z.union([z.literal(1), z.literal(2)]),
  verdicts: z.record(z.string(), LensVerdict).default({}),
  amendments: z.array(AppliedAmendment).default([]),
});
export type DebateRoundSummary = z.infer<typeof DebateRoundSummary>;

/** Bedrock Guardrails contextual grounding (`grounding_check`), only when a guardrail is configured. */
export const Grounding = z.object({ action: z.string().nullish(), assessments: z.unknown().optional() });
export type Grounding = z.infer<typeof Grounding>;

/* ------------------------------------------------------------------ */
/* `build`                                                             */
/* ------------------------------------------------------------------ */

const TICKER = /^[A-Za-z0-9.\-^=]{1,15}$/;

/** A precise request of the investor, e.g. « 50 000 $ dans TSLA » (`pipeline.Request`). */
export const InvestorRequest = z.object({
  ticker: z.string().trim().regex(TICKER, "Invalid ticker"),
  amount_cad: z.number().finite().positive().optional(),
  weight: z.number().finite().gt(0).max(1).optional(),
});
export type InvestorRequest = z.infer<typeof InvestorRequest>;

/**
 * Body of `POST /api/portfolio`, forwarded as the runtime's `build` action. `client_id` builds the
 * investor's own profile; `persona` (FICTION demo profile) is the coordinator's optional payload field.
 * At least one of them is required. Unknown fields are stripped before the call.
 */
export const PortfolioBuildRequest = z
  .object({
    action: z.literal("build").default("build"),
    client_id: z.uuid().optional(),
    persona: DemoPersona.optional(),
    as_of: isoDate.optional(),
    strategy: z.boolean().optional(),
    style_preference: Style.optional(),
    request: InvestorRequest.optional(),
    mode: BuildMode.optional(),
    locale: Locale.optional(),
  })
  .refine((body) => body.client_id !== undefined || body.persona !== undefined, {
    message: "Provide client_id or persona",
    path: ["client_id"],
  });
export type PortfolioBuildRequest = z.infer<typeof PortfolioBuildRequest>;
export type PortfolioBuildRequestInput = z.input<typeof PortfolioBuildRequest>;

/**
 * Response of `build`. `client_id` and `decision_key` may be absent for a persona build that has no
 * investor base (question open with the coordinator); `persona` is echoed when the runtime sends it.
 */
export const PortfolioBuildResponse = z.object({
  ok: z.literal(true),
  release: z.string(),
  client_id: z.uuid().nullish(),
  persona: DemoPersona.nullish(),
  as_of: isoDate,
  mode: BuildMode,
  simulation_only: z.literal(true),
  decision_key: z.string().nullish(),
  decision: Decision,
  rounds: z.array(DebateRoundSummary).default([]),
  explanation_report: z.array(z.string()).default([]),
  grounding: Grounding.nullish(),
  strategy: StrategySummary.nullable(),
});
export type PortfolioBuildResponse = z.infer<typeof PortfolioBuildResponse>;
