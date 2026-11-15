/**
 * Trace of one action (CONTRACTS.md 4): the observable steps, and the script of stream events
 * that replays them with realistic delays.
 */
import type { Source, StreamEvent, TraceKind, TraceStep } from "@/lib/contract/schemas";

export interface ScriptItem {
  event: StreamEvent;
  delayMs: number;
}

/** A step as an action describes it; `Trace.add` numbers and dates it. */
export interface TraceStepInput {
  kind: TraceKind;
  actor: string;
  title: string;
  detail?: string;
  inputs?: unknown;
  outputs?: unknown;
  sources?: Source[];
  durationMs: number;
}

const MIN_REPLAY_DELAY_MS = 60;
const MAX_REPLAY_DELAY_MS = 900;

/** Collects trace steps and stream events with a simulated clock. */
export class Trace {
  readonly steps: TraceStep[] = [];
  readonly script: ScriptItem[] = [];
  private clock: number;

  constructor(start: number) {
    this.clock = start;
  }

  get now(): string {
    return new Date(this.clock).toISOString();
  }

  add(step: TraceStepInput): TraceStep {
    const full: TraceStep = {
      id: `st_${String(this.steps.length + 1).padStart(2, "0")}`,
      at: this.now,
      kind: step.kind,
      actor: step.actor,
      title: step.title,
      detail: step.detail ?? null,
      inputs: step.inputs ?? {},
      outputs: step.outputs ?? {},
      sources: step.sources ?? [],
      duration_ms: step.durationMs,
    };
    this.clock += step.durationMs;
    this.steps.push(full);
    const delayMs = Math.min(MAX_REPLAY_DELAY_MS, Math.max(MIN_REPLAY_DELAY_MS, step.durationMs));
    this.script.push({ event: { type: "trace", step: full }, delayMs });
    return full;
  }

  /**
   * One `delta` per agent message, carrying the whole message (CONTRACTS.md 3.4): the runtime passes it
   * through a `finish_turn` tool once the model has written it, so it arrives after `totalMs`.
   */
  message(text: string, totalMs: number): void {
    this.script.push({ event: { type: "delta", text }, delayMs: totalMs });
  }
}
