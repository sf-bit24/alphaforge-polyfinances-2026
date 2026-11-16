import { describe, expect, it } from "vitest";
import type { AgentRequestInput } from "@/lib/contract/requests";
import { AgentRequest } from "@/lib/contract/requests";
import {
  ClientState,
  ErrorEnvelope,
  ExecutionSummary,
  HealthResponse,
  KbGetResponse,
  KbListResponse,
  StreamEvent,
  type AnswerValue,
} from "@/lib/contract/schemas";
import { MockRuntime } from "@/lib/mock/runtime";
import { parseOkf } from "@/lib/okf";

const BASE_ANSWERS: Record<string, AnswerValue> = {
  q_invest_frequency: "yearly",
  q_news_follow: "weekly",
  q_self_assessment: "intermediate",
  q_goal: "growth",
  q_income_need: 12000,
  q_amount: 50000,
  q_horizon: "gt10",
  q_liquidity: true,
  q_drawdown_reaction: "hold",
  q_risk_scale: 7,
  q_income_stability: "stable",
  q_savings_share: 30,
  q_accounts: ["tfsa", "rrsp"],
  q_exclusions: ["tobacco"],
  q_exclusions_other: "Les entreprises de jeux vidéo",
  q_has_portfolio: true,
};

function newRuntime() {
  return new MockRuntime({ delayScale: 0 });
}

async function call(runtime: MockRuntime, request: AgentRequestInput) {
  return runtime.handle(AgentRequest.parse(request));
}

async function state(runtime: MockRuntime, request: AgentRequestInput) {
  const response = await call(runtime, request);
  const parsed = ClientState.safeParse(response);
  if (!parsed.success) throw new Error(`Not a ClientState: ${JSON.stringify(response).slice(0, 400)} ${parsed.error.message}`);
  return parsed.data;
}

async function failure(runtime: MockRuntime, request: AgentRequestInput) {
  return ErrorEnvelope.parse(await call(runtime, request)).error;
}

async function stream(runtime: MockRuntime, request: AgentRequestInput) {
  const events = [];
  for await (const event of runtime.stream(AgentRequest.parse(request))) events.push(StreamEvent.parse(event));
  return events;
}

/** Answer base questions from `answers` until the stage changes; returns the ids asked. */
async function answerBase(runtime: MockRuntime, clientId: string, answers: Record<string, AnswerValue>) {
  let current = await state(runtime, { action: "session.resume", client_id: clientId });
  const asked: string[] = [];
  while (current.stage === "base_questions") {
    const question = current.questions[0];
    if (!question) throw new Error("base_questions without a question");
    const value = answers[question.id];
    if (value === undefined) throw new Error(`No answer for ${question.id}`);
    asked.push(question.id);
    current = await state(runtime, { action: "base.answer", client_id: clientId, question_id: question.id, value });
    expect(current.trace.length).toBeGreaterThan(0);
  }
  return { asked, state: current };
}

describe("mock runtime: health and sessions", () => {
  it("answers health like every role", async () => {
    const runtime = newRuntime();
    expect(HealthResponse.parse(await call(runtime, { action: "health" }))).toMatchObject({ role: "profile" });
  });

  it("starts with the knowledge questions and traces the rules", async () => {
    const runtime = newRuntime();
    const start = await state(runtime, { action: "session.start", locale: "fr" });
    expect(start.stage).toBe("base_questions");
    expect(start.questions[0]?.id).toBe("q_invest_frequency");
    expect(start.questions[0]?.dimension).toBe("knowledge");
    expect(start.completeness).toMatchObject({ score: 0, threshold: 0.7, cap: 0.95, ready: false });
    expect(start.trace.map((step) => step.kind)).toEqual(expect.arrayContaining(["storage", "deterministic"]));
  });

  it("reuses a given client_id and resumes without changing anything", async () => {
    const runtime = newRuntime();
    const id = "11111111-2222-4333-8444-555555555555";
    await state(runtime, { action: "session.start", locale: "en", client_id: id });
    const resumed = await state(runtime, { action: "session.resume", client_id: id });
    expect(resumed.client_id).toBe(id);
    expect(resumed.locale).toBe("en");
    expect(resumed.questions[0]?.prompt).toMatch(/invested/);
    const again = await state(runtime, { action: "session.resume", client_id: id, locale: "fr" });
    expect(again.questions[0]?.prompt).toMatch(/placé/);
    expect((await state(runtime, { action: "session.resume", client_id: id })).locale).toBe("en");
  });

  it("creates the client knowledge base, then indexes every Markdown document of the base", async () => {
    const runtime = newRuntime();
    const start = await state(runtime, { action: "session.start", locale: "fr" });
    expect(start.client_kb).toMatchObject({ status: "creating", documents: 0, pending: 3 });
    expect(start.client_kb?.knowledge_base_id).toMatch(/^MOCK/);
    expect(start.trace.map((step) => step.title)).toContain("Espace de vos documents personnels préparé");
    const resumed = await state(runtime, { action: "session.resume", client_id: start.client_id });
    expect(resumed.client_kb).toMatchObject({ status: "active", documents: 3, pending: 0 });
    expect(resumed.trace.map((step) => step.title)).toContain("Vos documents personnels sont mis à jour");
    const profile = await state(runtime, { action: "profile.get", client_id: start.client_id });
    expect(profile.client_kb).toMatchObject({ status: "active", documents: 3, pending: 0 });
    expect(profile.trace.map((step) => step.title)).not.toContain("Vos documents personnels sont mis à jour");
  });

  it("returns not_found for an unknown client", async () => {
    const runtime = newRuntime();
    const error = await failure(runtime, { action: "session.resume", client_id: "9b2e7c1a-0d3f-4a5b-8c6d-7e8f9a0b1c2d" });
    expect(error.code).toBe("not_found");
  });
});

describe("mock runtime: base questions", () => {
  it("validates answers by kind and refuses the wrong question", async () => {
    const runtime = newRuntime();
    const start = await state(runtime, { action: "session.start", locale: "fr" });
    const id = start.client_id;
    const invalid = await failure(runtime, { action: "base.answer", client_id: id, question_id: "q_invest_frequency", value: "sometimes" });
    expect(invalid.code).toBe("invalid_answer");
    expect(invalid.details).toMatchObject({ allowed: ["never", "few", "yearly", "monthly"] });
    const wrong = await failure(runtime, { action: "base.answer", client_id: id, question_id: "q_goal", value: "growth" });
    expect(wrong.code).toBe("conflict");
    const early = await failure(runtime, { action: "portfolio.skip", client_id: id });
    expect(early.code).toBe("conflict");
  });

  it("asks the deterministic order without branches, then the existing portfolio", async () => {
    const runtime = newRuntime();
    const start = await state(runtime, { action: "session.start", locale: "fr" });
    const { asked, state: after } = await answerBase(runtime, start.client_id, BASE_ANSWERS);
    expect(asked).toEqual([
      "q_invest_frequency",
      "q_news_follow",
      "q_self_assessment",
      "q_goal",
      "q_amount",
      "q_horizon",
      "q_drawdown_reaction",
      "q_risk_scale",
      "q_income_stability",
      "q_savings_share",
      "q_accounts",
      "q_exclusions",
      "q_has_portfolio",
    ]);
    expect(after.stage).toBe("existing_portfolio");
    expect(after.questions).toEqual([]);
    expect(after.profile.knowledge_level).toBe("intermediate");
    expect(after.profile.effective_risk).not.toBeNull();
    expect(after.profile.facts.find((fact) => fact.field === "horizon.horizon_band")).toMatchObject({ value: "gt10", provenance: "base:q_horizon" });
    // Every fact carries its value as the investor reads it, in the language of the view (`Fact.label`).
    const labels = new Map(after.profile.facts.map((fact) => [fact.field, fact.label]));
    expect(labels.get("horizon.horizon_band")).toBe("10 ans et plus");
    expect(labels.get("constraints.accounts")).toBe("CELI, REER");
    expect(labels.get("context.has_portfolio")).toBe("Oui");
    expect(labels.get("objective.amount")).toMatch(/^50\s000\s\$$/);
    expect(labels.get("risk_tolerance.risk_scale")).toBe("7 sur 10");
    expect(after.profile.facts.every((fact) => typeof fact.label === "string" && fact.label.length > 0)).toBe(true);
    expect(after.completeness.ready).toBe(false);
  });

  it("follows the branches of the rules", async () => {
    const runtime = newRuntime();
    const start = await state(runtime, { action: "session.start", locale: "en" });
    const { asked, state: after } = await answerBase(runtime, start.client_id, {
      ...BASE_ANSWERS,
      q_goal: "income",
      q_horizon: "lt3",
      q_exclusions: ["other"],
      q_has_portfolio: false,
    });
    expect(asked).toEqual(expect.arrayContaining(["q_income_need", "q_liquidity", "q_exclusions_other"]));
    expect(asked.indexOf("q_income_need")).toBe(asked.indexOf("q_goal") + 1);
    expect(asked.indexOf("q_liquidity")).toBe(asked.indexOf("q_horizon") + 1);
    // Existing portfolio = no: straight to the follow-ups.
    expect(after.stage).toBe("followups");
    expect(after.message).toBeNull();
    expect(after.questions).toEqual([]);
    // A horizon under 3 years limits the risk capacity, hence the effective risk.
    expect(after.profile.effective_risk).toBe("low");
  });
});

describe("mock runtime: from base questions to a complete profile", () => {
  it("runs the whole stage machine", async () => {
    const runtime = newRuntime();
    const start = await state(runtime, { action: "session.start", locale: "fr" });
    const id = start.client_id;
    await answerBase(runtime, id, BASE_ANSWERS);

    // existing_portfolio -> portfolio_review (A2)
    const csv = Buffer.from("ticker,quantité,compte\nMSFT,10,REER\n").toString("base64");
    const pdf = Buffer.from("%PDF-1.7\u0000binary").toString("base64");
    const review = await state(runtime, {
      action: "portfolio.submit",
      client_id: id,
      text: "100 RY.TO CELI\n25 AAPL REER\n0,05 BTC\nfonds maison XYZ",
      files: [
        { name: "releve.csv", media_type: "text/csv", data_base64: csv },
        { name: "releve.pdf", media_type: "application/pdf", data_base64: pdf },
      ],
    });
    expect(review.stage).toBe("portfolio_review");
    expect(review.questions).toEqual([]);
    const portfolio = review.portfolio;
    expect(portfolio?.status).toBe("draft");
    // Like the Python runtime, every line is a row; the unidentified one stays unresolved and is referenced by position_id.
    expect(portfolio?.positions.map((position) => position.ticker)).toEqual(["RY.TO", "AAPL", "BTC-USD", null, "MSFT"]);
    expect(portfolio?.positions[3]).toMatchObject({ id: "p4", raw: "fonds maison XYZ", resolved: false, value_cad: null });
    // French decimal comma on a line that is not comma-delimited.
    expect(portfolio?.positions[2]).toMatchObject({ quantity: 0.05, asset_class: "crypto" });
    expect(portfolio?.positions[2]?.value_cad).toBeCloseTo(0.05 * 71342.97 * 1.4255, 1);
    const ry = portfolio?.positions[0];
    expect(ry).toMatchObject({ quantity: 100, account_type: "tfsa", price: 289.39, value_cad: 28939, resolved: true });
    expect(portfolio?.positions[1]?.value_cad).toBeCloseTo(25 * 354.88 * 1.4255, 1);
    expect(portfolio?.unresolved.map((item) => [item.raw, item.position_id ?? null])).toEqual([
      ["releve.pdf", null],
      ["fonds maison XYZ", "p4"],
    ]);
    expect(portfolio?.fx).toEqual({ pair: "USDCAD", rate: 1.4255, date: "2026-11-12", source: "starter:fx_usdcad_daily.csv" });
    const shares = Object.values(portfolio?.exposures.by_asset_class ?? {}).reduce((sum, share) => sum + share, 0);
    expect(shares).toBeCloseTo(1, 3);
    // Flags of the Python runtime (portfolio.py): RY.TO > 20% of the total and > 40% of the stocks (Financials),
    // four holdings without ETF, unvalued lines; crypto stays under 10% and Canada under 60%.
    expect(portfolio?.exposures.flags).toEqual(["concentration_single_position", "concentration_sector", "few_holdings", "unvalued_positions"]);
    expect(portfolio?.sources.map((source) => source.id)).toEqual(expect.arrayContaining(["starter-prices", "starter-fx"]));
    expect(review.message).toMatch(/4 positions/);
    expect(review.trace.map((step) => step.actor)).toEqual(expect.arrayContaining(["guardrail", "A2", "store"]));

    // portfolio_review -> followups, exposures recomputed by code
    const edited = portfolio!.positions.map((position) => (position.ticker === "AAPL" ? { ...position, quantity: 30 } : position));
    const confirmed = await state(runtime, { action: "portfolio.confirm", client_id: id, positions: edited });
    expect(confirmed.stage).toBe("followups");
    expect(confirmed.portfolio?.status).toBe("confirmed");
    expect(confirmed.portfolio?.positions[1]?.value_cad).toBeCloseTo(30 * 354.88 * 1.4255, 1);
    expect(confirmed.portfolio?.unresolved.map((item) => item.position_id)).toEqual(["p4"]);
    expect(confirmed.message).toBeNull();
    expect(confirmed.questions).toEqual([]);
    const afterConfirm = confirmed.completeness.score;

    // Arrival in followups: A1 asks its first follow-ups.
    const first = await state(runtime, { action: "followup.reply", client_id: id });
    expect(first.stage).toBe("followups");
    // Turn numbers are shared by A1 and A2: A2 was turn 1, so A1's first turn is 2. Ids are a1_<turn>_<n>.
    expect(first.questions.map((question) => question.id)).toEqual(["a1_2_1", "a1_2_2", "a1_2_3"]);
    expect(first.questions.map((question) => question.field)).toEqual(["emergency_fund", "purpose", "withdrawal_pattern"]);
    expect(first.questions.every((question) => question.source === "a1")).toBe(true);
    expect(first.message).toMatch(/%/);
    expect(first.trace.map((step) => step.kind)).toEqual(expect.arrayContaining(["agent", "tool", "model", "guardrail", "storage"]));

    // stop is refused under the threshold
    expect(afterConfirm).toBeLessThan(0.7);
    expect((await failure(runtime, { action: "followup.reply", client_id: id, stop: true })).code).toBe("conflict");

    // answers to A1's questions
    const second = await state(runtime, {
      action: "followup.reply",
      client_id: id,
      answers: [
        { question_id: "a1_2_1", value: 6 },
        { question_id: "a1_2_2", value: "Ma retraite" },
        { question_id: "a1_2_3", value: "gradual" },
      ],
    });
    expect(second.completeness.score).toBeGreaterThan(afterConfirm);
    expect(second.completeness.ready).toBe(true);
    expect(second.profile.facts.find((fact) => fact.field === "risk_capacity.emergency_fund")).toMatchObject({ value: 6, provenance: "a1:3" });
    expect(second.questions.map((question) => question.id)).toEqual(["a1_3_1", "a1_3_2", "a1_3_3"]);
    expect(second.questions.map((question) => question.field)).toEqual(["high_interest_debt", "liquidity_need", "themes"]);

    // An answer to a question A1 did not ask is refused.
    const notAsked = await failure(runtime, { action: "followup.reply", client_id: id, answers: [{ question_id: "a1_2_2", value: "x" }] });
    expect(notAsked.code).toBe("invalid_answer");

    // Free text: A1 extracts facts with its turn as provenance.
    const third = await state(runtime, {
      action: "followup.reply",
      client_id: id,
      message: "Je n'ai aucune dette et les dividendes m'intéressent.",
    });
    const debt = third.profile.facts.find((fact) => fact.field === "risk_capacity.high_interest_debt");
    expect(debt).toMatchObject({ value: false, provenance: "a1:4" });
    expect(third.questions.map((question) => [question.id, question.field])).toEqual([["a1_4_1", "liquidity_need"]]);

    // The investor stops above the threshold.
    const done = await state(runtime, { action: "followup.reply", client_id: id, stop: true });
    expect(done.stage).toBe("complete");
    expect(done.questions).toEqual([]);
    expect(done.completeness.displayed).toBeLessThanOrEqual(done.completeness.cap);

    // complete -> followups on a new reply
    const reopened = await state(runtime, { action: "followup.reply", client_id: id, message: "J'ai maintenant 12 mois de côté en épargne d'urgence." });
    expect(reopened.stage).toBe("followups");
    expect(reopened.profile.facts.find((fact) => fact.field === "risk_capacity.emergency_fund")?.value).toBe(12);

    // The client base, in OKF.
    const list = KbListResponse.parse(await call(runtime, { action: "kb.list", prefix: `clients/${id}/`, client_id: id }));
    const keys = list.items.map((item) => item.key);
    expect(keys).toEqual(
      expect.arrayContaining([`clients/${id}/index.md`, `clients/${id}/profil.md`, `clients/${id}/journal.md`, `clients/${id}/portefeuille-existant.md`]),
    );
    expect(keys.some((key) => key.includes("/traces/"))).toBe(true);
    const profile = KbGetResponse.parse(await call(runtime, { action: "kb.get", key: `clients/${id}/profil.md`, client_id: id }));
    expect(parseOkf(profile.content).frontmatter).toMatchObject({ type: "Investor Profile", sensitivity: "client" });
    const journal = parseOkf(KbGetResponse.parse(await call(runtime, { action: "kb.get", key: `clients/${id}/journal.md`, client_id: id })).content);
    const entries = (journal.frontmatter?.data as { entries: Array<{ kind: string; provenance: string; text?: string }> }).entries;
    expect(new Set(entries.map((entry) => entry.kind))).toEqual(new Set(["answer", "message", "stage"]));
    expect(entries.find((entry) => entry.kind === "message")).toMatchObject({ provenance: "a1:4" });

    const withDocuments = await state(runtime, { action: "profile.get", client_id: id });
    expect(withDocuments.profile.documents?.map((doc) => doc.key)).toContain(`clients/${id}/profil.md`);
  });

  it("streams trace and delta events, then exactly one result identical to JSON mode", async () => {
    const runtime = newRuntime();
    const start = await state(runtime, { action: "session.start", locale: "en" });
    await answerBase(runtime, start.client_id, { ...BASE_ANSWERS, q_has_portfolio: false });
    const events = await stream(runtime, { action: "followup.reply", client_id: start.client_id, stream: true });
    const last = events[events.length - 1];
    expect(last?.type).toBe("result");
    expect(events.filter((event) => event.type === "result" || event.type === "error")).toHaveLength(1);
    // One delta per agent message, carrying the whole message (CONTRACTS.md 3.4).
    expect(events.filter((event) => event.type === "delta")).toHaveLength(1);
    if (last?.type !== "result") throw new Error("no result");
    const streamed = events.filter((event) => event.type === "trace").map((event) => (event.type === "trace" ? event.step : null));
    expect(streamed).toEqual(last.result.trace);
    const text = events.map((event) => (event.type === "delta" ? event.text : "")).join("");
    expect(text).toBe(last.result.message);
  });

  it("streams an error event when the request fails", async () => {
    const runtime = newRuntime();
    const start = await state(runtime, { action: "session.start", locale: "fr" });
    const events = await stream(runtime, { action: "followup.reply", client_id: start.client_id, stream: true });
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ type: "error", error: { code: "conflict" } });
  });
});

describe("mock runtime: guardrails and settings", () => {
  async function inFollowups() {
    const runtime = newRuntime();
    const start = await state(runtime, { action: "session.start", locale: "fr" });
    await answerBase(runtime, start.client_id, { ...BASE_ANSWERS, q_has_portfolio: false });
    await state(runtime, { action: "followup.reply", client_id: start.client_id });
    return { runtime, id: start.client_id };
  }

  it("blocks a transaction request and never journals it", async () => {
    const { runtime, id } = await inFollowups();
    const blocked = await failure(runtime, { action: "followup.reply", client_id: id, message: "Achète 100 actions de TSLA pour moi." });
    expect(blocked.code).toBe("guardrail_blocked");
    const journal = KbGetResponse.parse(await call(runtime, { action: "kb.get", key: `clients/${id}/journal.md`, client_id: id }));
    expect(journal.content).not.toMatch(/TSLA/);
  });

  it("frames a request for personalized advice and masks personal data", async () => {
    const { runtime, id } = await inFollowups();
    const framed = await state(runtime, { action: "followup.reply", client_id: id, message: "Dois-je acheter NVDA ? Écrivez-moi à moi@exemple.ca" });
    expect(framed.message).toMatch(/aucun conseil financier personnalisé/);
    const guardrail = framed.trace.find((step) => step.kind === "guardrail");
    expect(guardrail?.outputs).toMatchObject({ advice_request: true, masked: 1 });
  });

  it("changes the knowledge level from the settings, with its provenance", async () => {
    const { runtime, id } = await inFollowups();
    const updated = await state(runtime, { action: "settings.update", client_id: id, knowledge_level: "advanced", locale: "en" });
    expect(updated.profile.knowledge_level).toBe("advanced");
    expect(updated.locale).toBe("en");
    expect(updated.profile.facts.find((fact) => fact.field === "knowledge.level")).toMatchObject({ provenance: "settings" });
    expect(updated.questions[0]?.prompt).toMatch(/[a-z]/);
  });

  it("serves a clients/ key only with the matching client_id", async () => {
    const { runtime, id } = await inFollowups();
    const other = "0f1e2d3c-4b5a-4968-8776-655443322110";
    const response = await runtime.handle({ action: "kb.get", key: `clients/${id}/profil.md`, client_id: other });
    expect(ErrorEnvelope.parse(response).error.code).toBe("not_found");
  });
});

describe("mock runtime: general base and collection", () => {
  it("lists and reads the general base", async () => {
    const runtime = newRuntime();
    const list = KbListResponse.parse(await call(runtime, { action: "kb.list", prefix: "general/" }));
    expect(list.items.map((item) => item.key)).toEqual(expect.arrayContaining(["general/index.md", "general/methodologie/profil-investisseur.md"]));
    const doc = KbGetResponse.parse(await call(runtime, { action: "kb.get", key: "general/index.md" }));
    expect(parseOkf(doc.content).frontmatter).toMatchObject({ type: "Index", sensitivity: "public" });
  });

  it("names a collection run with a UUID and reports each collector", () => {
    let now = Date.parse("2026-11-14T12:00:00Z");
    const runtime = new MockRuntime({ delayScale: 0, now: () => now });
    const started = ExecutionSummary.parse(runtime.collector.start({ since: "2026-11-07" }));
    expect(started.name).toMatch(/^[0-9a-f-]{36}$/);
    expect(started.name).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
    expect(started.status).toBe("RUNNING");
    expect(started.outcome).toBeNull();
    now += 10_000;
    const finished = runtime.collector.list().find((execution) => execution.name === started.name);
    expect(finished?.status).toBe("SUCCEEDED");
    expect(finished?.outcome?.press?.status).toBe("ok");
    expect(finished?.outcome?.curated?.written[0]).toMatch(/^general\/actualites\//);
    const seeded = runtime.collector.list().find((execution) => execution.outcome?.data?.status === "error");
    expect(seeded?.status).toBe("SUCCEEDED");
  });
});
