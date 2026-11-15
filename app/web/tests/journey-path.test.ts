import { describe, expect, it } from "vitest";
import type { AgentRequestInput } from "@/lib/contract/requests";
import { AgentRequest } from "@/lib/contract/requests";
import { ClientState, type AnswerValue } from "@/lib/contract/schemas";
import { answeredBaseCount, itemForStage, plant, resumeLayout, sayFor, shortcutIndex, START, type PathLayout } from "@/lib/journey/path";
import { MockRuntime } from "@/lib/mock/runtime";

/** Answers of the simulator's base questions; `q_has_portfolio` is set per test. */
const ANSWERS: Record<string, AnswerValue> = {
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
};

async function send(runtime: MockRuntime, request: AgentRequestInput) {
  return ClientState.parse(await runtime.handle(AgentRequest.parse(request)));
}

/** Walk the journey as the UI does: plant at `stand + 1` after every answer, from the start. */
async function walk(hasPortfolio: boolean) {
  const runtime = new MockRuntime({ delayScale: 0 });
  let state = await send(runtime, { action: "session.start", locale: "fr" });
  let layout: PathLayout = plant(START, 0, state.stage);
  const snapshots: Array<{ state: ClientState; layout: PathLayout }> = [{ state, layout }];
  while (state.stage === "base_questions") {
    const question = state.questions[0];
    if (!question) throw new Error("no question");
    const value = question.id === "q_has_portfolio" ? hasPortfolio : ANSWERS[question.id];
    if (value === undefined) throw new Error(`no answer for ${question.id}`);
    state = await send(runtime, { action: "base.answer", client_id: state.client_id, question_id: question.id, value });
    layout = plant(layout, layout.stand + 1, state.stage);
    snapshots.push({ state, layout });
  }
  return { runtime, state, layout, snapshots };
}

describe("journey path", () => {
  it("plants a sign post per base question, then the house, and resumes to the same place", async () => {
    const { state, layout, snapshots } = await walk(false);
    expect(state.stage).toBe("followups");
    expect(layout.house).toBe(layout.stand);
    expect(layout.planted).toBe(layout.stand);
    const answered = answeredBaseCount(state);
    expect(answered).toBeGreaterThan(10);
    expect(layout.stand).toBe(answered);
    expect(Object.values(layout.signs).every((kind) => kind === "question")).toBe(true);
    // Every intermediate state, resumed from storage, puts the walker where the live walk was.
    for (const snapshot of snapshots) {
      const resumed = resumeLayout(snapshot.state);
      expect(resumed.stand).toBe(snapshot.layout.stand);
      expect(resumed.house).toBe(snapshot.layout.house);
      expect(resumed.signs).toEqual(snapshot.layout.signs);
      expect(resumed.planted).toBeNull();
    }
  });

  it("puts a briefcase stop before the house when the investor shares a portfolio", async () => {
    const { runtime, state, layout } = await walk(true);
    expect(state.stage).toBe("existing_portfolio");
    expect(layout.signs[layout.stand]).toBe("portfolio");
    expect(resumeLayout(state)).toEqual({ ...layout, planted: null });

    const reviewed = await send(runtime, { action: "portfolio.submit", client_id: state.client_id, text: "100 RY.TO CELI\n25 AAPL REER" });
    expect(reviewed.stage).toBe("portfolio_review");
    expect(itemForStage(reviewed.stage)).toBe("portfolio");
    expect(resumeLayout(reviewed).stand).toBe(layout.stand);

    const positions = (reviewed.portfolio?.positions ?? []).map((position) => ({ ...position }));
    const confirmed = await send(runtime, { action: "portfolio.confirm", client_id: state.client_id, positions });
    expect(confirmed.stage).toBe("followups");
    const atHouse = plant(layout, layout.stand + 1, confirmed.stage);
    expect(atHouse.house).toBe(layout.stand + 1);
    expect(atHouse.signs[layout.stand]).toBe("portfolio");
    const resumed = resumeLayout(confirmed);
    expect(resumed.house).toBe(atHouse.house);
    expect(resumed.signs).toEqual(atHouse.signs);
  });

  it("goes straight to the house when the portfolio step is skipped", async () => {
    const { runtime, state, layout } = await walk(true);
    const skipped = await send(runtime, { action: "portfolio.skip", client_id: state.client_id });
    expect(skipped.stage).toBe("followups");
    expect(plant(layout, layout.stand + 1, skipped.stage).house).toBe(layout.stand + 1);
  });

  it("counts answered base questions by their provenance, once per question", () => {
    const fact = (provenance: string) => ({ field: "x", value: 1, provenance, at: "2026-11-14T10:00:00Z" });
    const profile = { facts: [fact("base:q_a"), fact("base:q_a"), fact("base:q_b"), fact("a1:1"), fact("settings")] };
    expect(answeredBaseCount({ profile } as unknown as ClientState)).toBe(2);
  });
});

describe("assistant lines and shortcuts", () => {
  it("greets first, welcomes back, announces a new dimension, and varies within one", () => {
    expect(sayFor("knowledge", null, 0, false)).toEqual({ kind: "first" });
    expect(sayFor("objective", "objective", 4, true)).toEqual({ kind: "resume" });
    expect(sayFor("horizon", "objective", 5, false)).toEqual({ kind: "dimension", dimension: "horizon" });
    expect(sayFor("knowledge", "knowledge", 1, false)).toEqual({ kind: "same", n: 1 });
    expect(sayFor("horizon", null, 3, false)).toEqual({ kind: "dimension", dimension: "horizon" });
  });

  it("maps keys 1 to 9 onto the available options only", () => {
    expect(shortcutIndex("1", 4)).toBe(0);
    expect(shortcutIndex("4", 4)).toBe(3);
    expect(shortcutIndex("5", 4)).toBeNull();
    expect(shortcutIndex("0", 4)).toBeNull();
    expect(shortcutIndex("a", 4)).toBeNull();
    expect(shortcutIndex("9", 12)).toBe(8);
  });
});
