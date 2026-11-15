import { describe, expect, it } from "vitest";
import { AgentRequest, type AgentRequestInput } from "@/lib/contract/requests";
import { ClientState, KbGetResponse, type AnswerValue, type Locale } from "@/lib/contract/schemas";
import { screenMessage } from "@/lib/mock/agents";
import { MockRuntime } from "@/lib/mock/runtime";

/** Answers to the simulator's base questions, with an existing portfolio to analyse. */
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
  q_exclusions_other: "Video game companies",
  q_has_portfolio: true,
};

async function call(runtime: MockRuntime, request: AgentRequestInput) {
  return runtime.handle(AgentRequest.parse(request));
}

async function state(runtime: MockRuntime, request: AgentRequestInput) {
  return ClientState.parse(await call(runtime, request));
}

/** A session past the base questions, at the existing-portfolio step. */
async function atExistingPortfolio(locale: Locale) {
  const runtime = new MockRuntime({ delayScale: 0 });
  let current = await state(runtime, { action: "session.start", locale });
  while (current.stage === "base_questions") {
    const question = current.questions[0];
    const value = question ? BASE_ANSWERS[question.id] : undefined;
    if (!question || value === undefined) throw new Error(`No answer for ${question?.id}`);
    current = await state(runtime, { action: "base.answer", client_id: current.client_id, question_id: question.id, value });
  }
  expect(current.stage).toBe("existing_portfolio");
  return { runtime, id: current.client_id };
}

describe("issue #82 (suite): the mask of personal data is written in the session's language", () => {
  it("screenMessage writes [masked] in English, [masqué] in French and by default", () => {
    expect(screenMessage("My email is me@example.ca", "en").text).toBe("My email is [masked]");
    expect(screenMessage("Mon courriel est moi@exemple.ca", "fr").text).toBe("Mon courriel est [masqué]");
    expect(screenMessage("Mon courriel est moi@exemple.ca").text).toBe("Mon courriel est [masqué]");
  });

  it.each([
    ["en", "[masked]", "[masqué]"],
    ["fr", "[masqué]", "[masked]"],
  ] as const)("in portfolio.submit and in followup.reply (%s)", async (locale, mask, otherMask) => {
    const submitted = await atExistingPortfolio(locale);
    const review = await state(submitted.runtime, { action: "portfolio.submit", client_id: submitted.id, text: "me@example.ca\n100 RY.TO" });
    expect(JSON.stringify(review)).toContain(mask);
    expect(JSON.stringify(review)).not.toContain(otherMask);

    const { runtime, id } = await atExistingPortfolio(locale);
    await state(runtime, { action: "portfolio.skip", client_id: id });
    await state(runtime, { action: "followup.reply", client_id: id, message: "My phone is 514-555-1234." });
    const journal = KbGetResponse.parse(await call(runtime, { action: "kb.get", key: `clients/${id}/journal.md`, client_id: id }));
    expect(journal.content).toContain(`My phone is ${mask}.`);
    expect(journal.content).not.toContain(otherMask);
  });
});
