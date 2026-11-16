import { describe, expect, it } from "vitest";
import { summarizeRunOutput } from "@/lib/contract/collect";
import {
  ClientState,
  Completeness,
  ErrorEnvelope,
  HealthResponse,
  KbGetResponse,
  KbListResponse,
  PortfolioView,
  ProfileView,
  Question,
  StreamEvent,
  TraceStep,
} from "@/lib/contract/schemas";
import { parseOkf } from "@/lib/okf";
import * as examples from "./fixtures/contract-examples";

describe("contract examples (CONTRACTS.md 3.3)", () => {
  it("parses Question", () => {
    const question = Question.parse(examples.question);
    expect(question.kind).toBe("single_choice");
    expect(question.options).toHaveLength(3);
  });

  it("parses a behavior question (short profile, read by step 0)", () => {
    const question = Question.parse({ ...examples.question, id: "q_hype_reaction", dimension: "behavior", field: "behavior.hype_reaction" });
    expect(question.dimension).toBe("behavior");
    expect(() => Question.parse({ ...examples.question, dimension: "mood" })).toThrow();
  });

  it("parses Completeness, ProfileView, PortfolioView and TraceStep", () => {
    expect(Completeness.parse(examples.completeness).ready).toBe(false);
    expect(ProfileView.parse(examples.profileView).dimensions.risk_capacity.status).toBe("missing");
    expect(PortfolioView.parse(examples.portfolioView).exposures.flags).toContain("home_bias_canada");
    expect(TraceStep.parse(examples.traceStep).duration_ms).toBe(3);
  });

  it("parses the ClientState envelope and the error envelope", () => {
    const state = ClientState.parse(examples.clientState);
    expect(state.stage).toBe("base_questions");
    expect(ErrorEnvelope.parse(examples.errorEnvelope).error.code).toBe("invalid_answer");
    expect(HealthResponse.parse(examples.health).role).toBe("profile");
  });

  it("reads the optional fields added from the Python runtime", () => {
    expect(Question.parse(examples.question).field).toBe("horizon_band");
    const profile = ProfileView.parse(examples.profileView);
    expect(profile.risk).toEqual({ tolerance: "high", capacity: "medium", effective: "medium" });
    expect(profile.dimensions.context?.status).toBe("partial");
    const portfolio = PortfolioView.parse(examples.portfolioView);
    expect(portfolio.fx).toMatchObject({ pair: "USDCAD", rate: 1.4255, source: "starter:fx_usdcad_daily.csv" });
    expect(portfolio.unresolved[0]?.position_id).toBe("p2");
    // Opaque ids: A1 follow-ups and fallback questions.
    expect(Question.parse({ ...examples.question, id: "a1_2_1", source: "a1", field: null }).id).toBe("a1_2_1");
    expect(Question.parse({ ...examples.question, id: "fb_3_1", source: "deterministic" }).source).toBe("deterministic");
    // Unknown actors and runtime flags are open strings.
    for (const actor of ["A3", "A9", "custom_tool"]) expect(TraceStep.parse({ ...examples.traceStep, actor }).actor).toBe(actor);
    const flags = ["concentration_sector", "crypto_exposure_high", "cash_heavy", "few_holdings", "unvalued_positions"];
    expect(PortfolioView.parse({ ...examples.portfolioView, exposures: { ...examples.portfolioView.exposures, flags } }).exposures.flags).toEqual(flags);
  });

  it("still parses a runtime that omits the newer optional fields", () => {
    const question: Record<string, unknown> = { ...examples.question };
    delete question.field;
    expect(Question.parse(question).field).toBeUndefined();
    const profile: Record<string, unknown> = { ...examples.profileView, dimensions: { ...examples.profileView.dimensions } };
    delete profile.risk;
    delete (profile.dimensions as Record<string, unknown>).context;
    expect(ProfileView.parse(profile).risk).toBeUndefined();
    const portfolio: Record<string, unknown> = { ...examples.portfolioView, unresolved: [{ raw: "x", reason: "y" }] };
    delete portfolio.fx;
    expect(PortfolioView.parse(portfolio).fx).toBeUndefined();
  });

  it("defaults optional fields an older runtime may omit", () => {
    const withoutRequired: Record<string, unknown> = { ...examples.question };
    delete withoutRequired.required;
    expect(Question.parse(withoutRequired).required).toBe(true);
    const withoutSources: Record<string, unknown> = { ...examples.traceStep };
    delete withoutSources.sources;
    expect(TraceStep.parse(withoutSources).sources).toEqual([]);
  });

  it("reads client_kb, the client's own knowledge base, and accepts a runtime without it", () => {
    const clientKb = { status: "active", knowledge_base_id: "KB12345678", documents: 6, pending: 1 };
    expect(ClientState.parse({ ...examples.clientState, client_kb: clientKb }).client_kb).toEqual(clientKb);
    expect(ClientState.parse(examples.clientState).client_kb).toBeUndefined();
    const disabled = { status: "disabled", knowledge_base_id: null, documents: 0, pending: 0 };
    expect(ClientState.parse({ ...examples.clientState, client_kb: disabled }).client_kb?.status).toBe("disabled");
    expect(ClientState.safeParse({ ...examples.clientState, client_kb: { ...clientKb, status: "ready" } }).success).toBe(false);
  });

  it("keeps unknown optional fields out of the parsed value (forward compatible)", () => {
    const parsed = Question.parse({ ...examples.question, future_field: 1 });
    expect("future_field" in parsed).toBe(false);
  });

  it("rejects values outside the contract", () => {
    expect(Question.safeParse({ ...examples.question, kind: "slider" }).success).toBe(false);
    expect(Completeness.safeParse({ ...examples.completeness, score: 1.2 }).success).toBe(false);
    expect(TraceStep.safeParse({ ...examples.traceStep, kind: "thinking" }).success).toBe(false);
    expect(ClientState.safeParse({ ...examples.clientState, client_id: "not-a-uuid" }).success).toBe(false);
    expect(PortfolioView.safeParse({ ...examples.portfolioView, status: "final" }).success).toBe(false);
  });

  it("enforces the number of questions per stage", () => {
    const two = { ...examples.clientState, questions: [examples.question, { ...examples.question, id: "q_goal" }] };
    expect(ClientState.safeParse(two).success).toBe(false);
    const none = { ...examples.clientState, questions: [] };
    expect(ClientState.safeParse(none).success).toBe(false);
    const followups = { ...examples.clientState, stage: "followups", questions: [] };
    expect(ClientState.safeParse(followups).success).toBe(true);
    const tooMany = { ...examples.clientState, stage: "followups", questions: Array(4).fill(examples.question) };
    expect(ClientState.safeParse(tooMany).success).toBe(false);
    const complete = { ...examples.clientState, stage: "complete", questions: [examples.question] };
    expect(ClientState.safeParse(complete).success).toBe(false);
  });

  it("parses the four stream events (CONTRACTS.md 3.4)", () => {
    expect(StreamEvent.parse({ type: "trace", step: examples.traceStep }).type).toBe("trace");
    expect(StreamEvent.parse({ type: "delta", text: "morceau" }).type).toBe("delta");
    expect(StreamEvent.parse({ type: "result", result: examples.clientState }).type).toBe("result");
    expect(StreamEvent.parse({ type: "error", error: { code: "model_error", message: "…" } }).type).toBe("error");
    expect(StreamEvent.safeParse({ type: "progress", value: 1 }).success).toBe(false);
  });

  it("parses kb.list and kb.get", () => {
    const list = KbListResponse.parse({
      ok: true,
      release: "1a2b3c4d",
      items: [{ key: "general/index.md", title: "Index", type: "Index", description: "…", updated_at: "2026-11-14T23:10:00Z" }],
    });
    expect(list.items[0]?.key).toBe("general/index.md");
    expect(KbGetResponse.parse({ ok: true, release: "1a2b3c4d", key: "general/index.md", content: "---\ntype: Index\n---\n# Index" }).key).toBe(
      "general/index.md",
    );
  });
});

describe("OKF documents (CONTRACTS.md 5)", () => {
  it("splits the YAML frontmatter from the Markdown body", () => {
    const doc = parseOkf(
      '---\ntype: Investor Profile\ntitle: Profil investisseur\ngenerated: { by: "agent:A1", at: "2026-11-14T23:10:00Z" }\nsources:\n  - { id: base-q_horizon, title: "Réponse à q_horizon", resource: "base:q_horizon" }\ndata: {}\n---\n\n# Profil\n',
    );
    expect(doc.error).toBeNull();
    expect(doc.frontmatter?.type).toBe("Investor Profile");
    expect((doc.frontmatter?.generated as { by: string }).by).toBe("agent:A1");
    expect(doc.body.trim()).toBe("# Profil");
  });

  it("reports an unreadable frontmatter instead of throwing", () => {
    const doc = parseOkf("---\ntype: [unclosed\n---\nbody");
    expect(doc.frontmatter).toBeNull();
    expect(doc.error).not.toBeNull();
  });
});

describe("collection output (CONTRACTS.md 6)", () => {
  it("reads per-collector status, A6 results and ingestion", () => {
    const outcome = summarizeRunOutput(examples.collectionOutput);
    expect(outcome?.press).toMatchObject({ status: "ok", items: 12 });
    expect(outcome?.data).toMatchObject({ status: "error", error: "BedrockAgentCore.ValidationException: run_id refusé" });
    expect(outcome?.curated?.written).toEqual(["general/actualites/2026/11/taux.md"]);
    expect(outcome?.curated?.rejected[0]?.reason).toBe("sans date de publication");
    expect(outcome?.ingestion?.status).toBe("COMPLETE");
  });

  it("returns null without output (running, or failed by A6 or ingestion)", () => {
    expect(summarizeRunOutput(null)).toBeNull();
    expect(summarizeRunOutput("not json")).toBeNull();
  });
});
