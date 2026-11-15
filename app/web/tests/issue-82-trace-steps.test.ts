/**
 * The description of a stored trace (clients/<id>/traces/*.json) counts its steps with the right plural:
 * « 1 étape » / "1 step", « 2 étapes » / "2 steps".
 */
import { describe, expect, it } from "vitest";
import type { Locale } from "@/lib/contract/schemas";
import { writeClientDocs } from "@/lib/mock/client-docs";
import { newClientRecord } from "@/lib/mock/client-record";
import { Trace } from "@/lib/mock/trace";

const AT = Date.parse("2026-11-15T12:00:00Z");

/** The description of the trace document written after `extraSteps` steps, plus the storage step itself. */
function traceDescription(locale: Locale, extraSteps: number): string | undefined {
  const record = newClientRecord("11111111-1111-4111-8111-111111111111", locale, new Date(AT).toISOString());
  const trace = new Trace(AT);
  for (let index = 0; index < extraSteps; index += 1) {
    trace.add({ kind: "deterministic", actor: "questionnaire", title: "step", detail: "", durationMs: 1 });
  }
  writeClientDocs(record, trace, "session.start");
  return [...record.docs.values()].find((doc) => doc.type === "Trace")?.description;
}

describe("trace document description", () => {
  it.each([
    ["fr", 0, "1 étape"],
    ["fr", 1, "2 étapes"],
    ["en", 0, "1 step"],
    ["en", 1, "2 steps"],
  ] as const)("%s, %i step(s) before the storage step: %s", (locale, extraSteps, description) => {
    expect(traceDescription(locale, extraSteps)).toBe(description);
  });
});
