/**
 * Simulated Step Functions collection (CONTRACTS.md 6): A4 and A5 in parallel,
 * then A6 curates and writes to the general base, then the Knowledge Base ingests.
 *
 * Like the real machine (infrastructure/infra/stepfunctions.tf), executions are named
 * by a UUID that becomes the run_id, a failed A4 or A5 ends its branch with
 * `status: "error"` without failing the run, and the output is
 * `{run_id, collected: {press, data}, curated, ingestion}`. Status is derived from
 * elapsed time, so no timer is needed.
 */
import { randomUUID } from "node:crypto";
import { summarizeRunOutput } from "@/lib/contract/collect";
import type { CollectRequest } from "@/lib/contract/requests";
import type { ExecutionDetail, ExecutionStatus, ExecutionSummary } from "@/lib/contract/schemas";
import { okfDocument, staleAfter, type StoredDoc } from "./documents";
import { GENERAL_SOURCES } from "./general-seed";
import { STARTER_SOURCES } from "./starter";

const STATE_MACHINE = "alphaforge-sandbox-collecte";
const ARN_PREFIX = `arn:aws:states:us-east-1:000000000000:execution:${STATE_MACHINE}:`;
const RUN_DURATION_MS = 9_000;

interface MockExecution {
  name: string;
  startedAt: number;
  durationMs: number;
  input: Record<string, unknown>;
  status: "SUCCEEDED" | "FAILED";
  output: Record<string, unknown> | null;
  docs: StoredDoc[];
  applied: boolean;
  error: string | null;
  cause: string | null;
}

const iso = (timeMs: number) => new Date(timeMs).toISOString();

function marker(role: "press" | "data", runId: string, startedAt: number, items: number) {
  return {
    status: "ok",
    role,
    run_id: runId,
    items,
    keys: Array.from({ length: items }, (_, index) => `staging/${runId}/${role}/item-${String(index + 1).padStart(2, "0")}.json`),
    error: null,
    started_at: iso(startedAt + 400),
    finished_at: iso(startedAt + 5_000),
  };
}

/** What A6 did with the collected items: the documents it wrote, and the items it rejected. */
interface Curation {
  written: string[];
  rejected: Array<{ key: string; reason: string }>;
}

/** Output of a run that succeeded; with `dataFailed`, A5 missed its marker and its branch ended in error. */
function successOutput(runId: string, startedAt: number, { written, rejected }: Curation, { dataFailed = false } = {}) {
  return {
    run_id: runId,
    collected: {
      press: marker("press", runId, startedAt, 3),
      data: dataFailed
        ? { status: "error", role: "data", error: "aucune réponse dans le délai prévu" }
        : marker("data", runId, startedAt, 2),
    },
    curated: {
      status: "ok",
      role: "supervisor",
      run_id: runId,
      written,
      rejected,
      error: null,
      started_at: iso(startedAt + 5_200),
      finished_at: iso(startedAt + 7_500),
    },
    ingestion: {
      job_id: `MOCK${runId.replace(/-/g, "").slice(0, 6).toUpperCase()}`,
      status: "COMPLETE",
      statistics: { numberOfDocumentsScanned: 8, numberOfNewDocumentsIndexed: written.length, numberOfDocumentsFailed: 0 },
    },
  };
}

function watchNote(runId: string, at: string): StoredDoc {
  const day = at.slice(0, 10);
  const [year, month] = day.split("-");
  return okfDocument(
    `general/actualites/${year}/${month}/note-de-veille-${runId.slice(0, 8)}.md`,
    {
      type: "News",
      title: `Note de veille simulée du ${day}`,
      description: "Synthèse de démonstration tirée des séries du jeu de départ; aucun article de presse réel n'est lu dans cette démonstration.",
      tags: ["donnees-marche", "actualites"],
      status: "draft",
      owners: ["alphaforge-a6"],
      sensitivity: "public",
      generated: { by: "mock:A6", at },
      stale_after: staleAfter(at, 1),
      sources: [GENERAL_SOURCES.macro, GENERAL_SOURCES.fx],
      data: { run_id: runId, published_at: STARTER_SOURCES.macro.observed_at, observed_at: STARTER_SOURCES.macro.observed_at },
    },
    `# Note de veille simulée du ${day}

> Document de démonstration : en temps normal, notre veille lit la presse et les données publiques, et n'ajoute que des éléments sourcés et datés.

- Le taux cible du financement à un jour de la Banque du Canada est de **2,50 %** depuis le 2026-10-29 (observé le 2026-11-12).
- Le dollar américain valait **1,4255 $ CA** le 2026-11-12 (Banque du Canada, FXUSDCAD).
- Le rendement des obligations du Canada à 10 ans était de **3,78 %** le 2026-11-12.

Séries citées : [taux USD/CAD](donnees/usdcad/usdcad-2026-11.md), [taux directeur et rendements obligataires](donnees/taux-directeur/banque-du-canada-2026-11.md).`,
  );
}

export class MockCollector {
  private readonly executions: MockExecution[] = [];

  readonly stateMachine = {
    name: STATE_MACHINE,
    arn: `arn:aws:states:us-east-1:000000000000:stateMachine:${STATE_MACHINE}`,
  };

  constructor(
    private readonly onWrite: (docs: StoredDoc[]) => void,
    private readonly now: () => number = () => Date.now(),
  ) {
    // A scheduled run where A5 missed its marker: the run still succeeds with A4's items.
    const scheduled = "6f1d2c3b-4a59-4e8f-9b7a-1c2d3e4f5a60";
    const scheduledAt = Date.parse("2026-11-14T06:00:00Z");
    this.executions.push({
      name: scheduled,
      startedAt: scheduledAt,
      durationMs: 1_384_000,
      input: {},
      status: "SUCCEEDED",
      output: successOutput(
        scheduled,
        scheduledAt,
        {
          written: ["general/donnees/usdcad/usdcad-2026-11.md", "general/donnees/taux-directeur/banque-du-canada-2026-11.md"],
          rejected: [{ key: `staging/${scheduled}/press/item-02.json`, reason: "publié après sa date de récupération" }],
        },
        { dataFailed: true },
      ),
      docs: [],
      applied: true,
      error: null,
      cause: null,
    });
    // A run where A6 timed out: only an A6 or ingestion failure fails the execution.
    const failed = "0b8e7d6c-5f4a-4b3c-8d2e-1f0a9b8c7d6e";
    this.executions.push({
      name: failed,
      startedAt: Date.parse("2026-11-13T06:00:00Z"),
      durationMs: 2_455_000,
      input: {},
      status: "FAILED",
      output: null,
      docs: [],
      applied: true,
      error: "MarkerTimeout",
      cause: "La vérification n'a pas terminé dans le délai prévu.",
    });
  }

  /** StartExecution without a name: the UUID name becomes the run_id. */
  start(request: CollectRequest): ExecutionSummary {
    const startedAt = this.now();
    const name = randomUUID();
    const doc = watchNote(name, iso(startedAt + RUN_DURATION_MS));
    const execution: MockExecution = {
      name,
      startedAt,
      durationMs: RUN_DURATION_MS,
      input: { ...request },
      status: "SUCCEEDED",
      output: successOutput(name, startedAt, {
        written: [doc.key],
        rejected: [{ key: `staging/${name}/press/item-03.json`, reason: "doublon d'un document existant" }],
      }),
      docs: [doc],
      applied: false,
      error: null,
      cause: null,
    };
    this.executions.unshift(execution);
    return this.summary(execution);
  }

  list(): ExecutionSummary[] {
    return this.executions.map((execution) => this.summary(execution));
  }

  describe(arn: string): ExecutionDetail | null {
    const execution = this.executions.find((candidate) => ARN_PREFIX + candidate.name === arn);
    if (!execution) return null;
    const summary = this.summary(execution);
    const finished = summary.status !== "RUNNING";
    return {
      ...summary,
      input: execution.input,
      output: finished ? execution.output : null,
      error: finished ? execution.error : null,
      cause: finished ? execution.cause : null,
    };
  }

  private status(execution: MockExecution): ExecutionStatus {
    return this.now() < execution.startedAt + execution.durationMs ? "RUNNING" : execution.status;
  }

  private summary(execution: MockExecution): ExecutionSummary {
    const status = this.status(execution);
    if (status !== "RUNNING" && !execution.applied) {
      execution.applied = true;
      if (execution.status === "SUCCEEDED") this.onWrite(execution.docs);
    }
    return {
      execution_arn: ARN_PREFIX + execution.name,
      name: execution.name,
      status,
      start_date: iso(execution.startedAt),
      stop_date: status === "RUNNING" ? null : iso(execution.startedAt + execution.durationMs),
      outcome: status === "RUNNING" ? null : summarizeRunOutput(execution.output),
    };
  }
}
