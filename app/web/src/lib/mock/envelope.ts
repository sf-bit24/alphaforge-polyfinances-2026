/**
 * Response envelope of the simulated `profile` runtime (CONTRACTS.md 3.2), and the error an
 * action throws to answer with its `error` branch.
 */
import type { ErrorBody, Locale } from "@/lib/contract/schemas";
import { tr, type L } from "./questions";

export const MOCK_RELEASE = "mock";

export type Envelope = { ok: true; release: string; [key: string]: unknown } | { ok: false; release: string; error: ErrorBody };

export class MockError extends Error {
  constructor(
    readonly code: ErrorBody["code"],
    readonly text: L,
    readonly details: Record<string, unknown> = {},
  ) {
    super(text.en);
  }
}

/** Envelope of a failed action: a contract error in the client's language, `internal` for anything else. */
export function errorEnvelope(error: unknown, locale: Locale): Envelope {
  if (error instanceof MockError) {
    return {
      ok: false,
      release: MOCK_RELEASE,
      error: { code: error.code, message: tr(error.text, locale), details: error.details },
    };
  }
  return {
    ok: false,
    release: MOCK_RELEASE,
    error: { code: "internal", message: error instanceof Error ? error.message : String(error), details: {} },
  };
}
