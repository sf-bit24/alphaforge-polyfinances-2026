/**
 * Suite de #77 : le simulateur refuse un NAS de 9 chiffres collés avec la règle du runtime réel
 * (`alphaforge/personal_data.py`), sur le même tableau de cas que les tests Python.
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { AgentRequest, type AgentRequestInput } from "@/lib/contract/requests";
import { ClientState, ErrorEnvelope, KbGetResponse, type AnswerValue, type Locale } from "@/lib/contract/schemas";
import { screenMessage } from "@/lib/mock/agents";
import { MockError } from "@/lib/mock/envelope";
import { containsSin, luhnValid } from "@/lib/mock/personal-data";
import { MockRuntime } from "@/lib/mock/runtime";

type SinCase = { text: string; refused: boolean; why: string };
const CASES: SinCase[] = JSON.parse(readFileSync(new URL("../../agents/tests/fixtures/issue_77_sin_cases.json", import.meta.url), "utf8")).cases;

const SIN_REFUSAL = {
  fr: "Votre message contient un renseignement personnel (NAS) : retirez-le, puis renvoyez-le.",
  en: "Your message contains personal information (SIN): remove it, then send it again.",
};

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

async function state(runtime: MockRuntime, request: AgentRequestInput) {
  return ClientState.parse(await runtime.handle(AgentRequest.parse(request)));
}

async function failure(runtime: MockRuntime, request: AgentRequestInput) {
  return ErrorEnvelope.parse(await runtime.handle(AgentRequest.parse(request))).error;
}

/** A session at the existing-portfolio step, after the base questions. */
async function atExistingPortfolio(runtime: MockRuntime, locale: Locale) {
  let current = await state(runtime, { action: "session.start", locale });
  while (current.stage === "base_questions") {
    const question = current.questions[0];
    const value = question ? BASE_ANSWERS[question.id] : undefined;
    if (!question || value === undefined) throw new Error(`No answer for ${question?.id}`);
    current = await state(runtime, { action: "base.answer", client_id: current.client_id, question_id: question.id, value });
  }
  return current.client_id;
}

describe("issue #77: the simulator refuses a SIN with the rule of the real runtime", () => {
  it("reads the shared table of cases", () => {
    expect(CASES.length).toBeGreaterThan(30);
    expect(CASES.filter((item) => item.refused).length).toBeGreaterThan(5);
  });

  it.each(CASES)("containsSin($text) is $refused ($why)", ({ text, refused }) => {
    expect(containsSin(text)).toBe(refused);
  });

  it.each(CASES.filter((item) => item.refused))("screenMessage refuses $text", ({ text }) => {
    let thrown: unknown = null;
    try {
      screenMessage(text);
    } catch (error) {
      thrown = error;
    }
    expect(thrown).toBeInstanceOf(MockError);
    expect(thrown).toMatchObject({ code: "guardrail_blocked", text: SIN_REFUSAL, details: { reason: "personal_data", entity: "CA_SIN" } });
  });

  it.each(CASES.filter((item) => !item.refused))("screenMessage lets $text through", ({ text }) => {
    expect(() => screenMessage(text)).not.toThrow();
  });

  it("checks the Luhn key of the SIN", () => {
    expect(luhnValid("046454286") && luhnValid("037833100")).toBe(true);
    expect(luhnValid("123456789") || luhnValid("046454287")).toBe(false);
  });

  it.each(["fr", "en"] as const)("refuses « Mon NAS est 046454286 » in followup.reply and journals nothing (%s)", async (locale) => {
    const runtime = new MockRuntime({ delayScale: 0 });
    const id = await atExistingPortfolio(runtime, locale);
    await state(runtime, { action: "portfolio.skip", client_id: id });
    const error = await failure(runtime, { action: "followup.reply", client_id: id, message: "Mon NAS est 046454286" });
    expect(error).toEqual({ code: "guardrail_blocked", message: SIN_REFUSAL[locale], details: { reason: "personal_data", entity: "CA_SIN" } });
    const journal = KbGetResponse.parse(await runtime.handle(AgentRequest.parse({ action: "kb.get", key: `clients/${id}/journal.md`, client_id: id })));
    expect(journal.content).not.toContain("046454286");
  });
});
