/**
 * Reading the output of the collection state machine (CONTRACTS.md 6).
 *
 * The machine ends with `{run_id, collected: {press, data}, curated, ingestion}`
 * (infrastructure/infra/stepfunctions.tf, state "Termine"). A4 or A5 may end with
 * `status: "error"` without failing the execution; only A6 or the ingestion fail it.
 */
import { z } from "zod";

export const CollectorOutcome = z.object({
  role: z.string(),
  status: z.string(),
  items: z.number().nullable(),
  error: z.string().nullable(),
});
export type CollectorOutcome = z.infer<typeof CollectorOutcome>;

export const RunOutcome = z.object({
  run_id: z.string().nullable(),
  press: CollectorOutcome.nullable(),
  data: CollectorOutcome.nullable(),
  curated: z
    .object({
      status: z.string().nullable(),
      written: z.array(z.string()),
      rejected: z.array(z.object({ key: z.string(), reason: z.string() })),
    })
    .nullable(),
  ingestion: z.object({ status: z.string().nullable(), job_id: z.string().nullable() }).nullable(),
});
export type RunOutcome = z.infer<typeof RunOutcome>;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

function errorText(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value;
  if (isRecord(value)) {
    const name = typeof value.Error === "string" ? value.Error : null;
    const cause = typeof value.Cause === "string" ? value.Cause : null;
    if (name || cause) return [name, cause].filter(Boolean).join(": ");
  }
  return JSON.stringify(value);
}

/** `items` when the collector counts them, else the number of `keys` it wrote. */
function itemCount(value: Record<string, unknown>): number | null {
  if (typeof value.items === "number") return value.items;
  return Array.isArray(value.keys) ? value.keys.length : null;
}

function collector(value: unknown, role: string): CollectorOutcome | null {
  if (!isRecord(value)) return null;
  return {
    role: typeof value.role === "string" ? value.role : role,
    status: typeof value.status === "string" ? value.status : "unknown",
    items: itemCount(value),
    error: errorText(value.error),
  };
}

function curatedOutcome(curated: Record<string, unknown>): NonNullable<RunOutcome["curated"]> {
  const rejected = Array.isArray(curated.rejected) ? curated.rejected : [];
  return {
    status: typeof curated.status === "string" ? curated.status : null,
    written: Array.isArray(curated.written) ? curated.written.filter((key): key is string => typeof key === "string") : [],
    rejected: rejected.filter(isRecord).map((item) => ({ key: String(item.key ?? ""), reason: String(item.reason ?? "") })),
  };
}

function ingestionOutcome(ingestion: Record<string, unknown>): NonNullable<RunOutcome["ingestion"]> {
  return {
    status: typeof ingestion.status === "string" ? ingestion.status : null,
    job_id: typeof ingestion.job_id === "string" ? ingestion.job_id : null,
  };
}

/** Summarize a state machine output; `null` if there is none (running, or failed). */
export function summarizeRunOutput(output: unknown): RunOutcome | null {
  if (!isRecord(output)) return null;
  const collected = isRecord(output.collected) ? output.collected : {};
  return {
    run_id: typeof output.run_id === "string" ? output.run_id : null,
    press: collector(collected.press, "press"),
    data: collector(collected.data, "data"),
    curated: isRecord(output.curated) ? curatedOutcome(output.curated) : null,
    ingestion: isRecord(output.ingestion) ? ingestionOutcome(output.ingestion) : null,
  };
}

/** Parse a JSON string from Step Functions (input or output), keeping the raw text if it is not JSON. */
export function parseJsonText(text: string | null | undefined): unknown {
  if (text === null || text === undefined || text === "") return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
