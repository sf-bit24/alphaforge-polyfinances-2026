import { describe, expect, it } from "vitest";
import { AgentRequest, type AgentRequestInput } from "@/lib/contract/requests";
import { ClientState, type Question } from "@/lib/contract/schemas";
import { fallbackAnswer, sampleAnswer } from "@/lib/journey/sample-profile";
import { MockRuntime } from "@/lib/mock/runtime";

async function state(runtime: MockRuntime, request: AgentRequestInput) {
  const response = await runtime.handle(AgentRequest.parse(request));
  const parsed = ClientState.safeParse(response);
  if (!parsed.success) throw new Error(`Not a ClientState: ${JSON.stringify(response).slice(0, 400)}`);
  return parsed.data;
}

const question = (over: Partial<Question>): Question => ({
  id: "q_x",
  source: "deterministic",
  dimension: "knowledge",
  kind: "single_choice",
  prompt: "?",
  required: true,
  ...over,
});

describe("sample profile (« Passer les questions »)", () => {
  it("takes the mock simulator from the first question to the summary", async () => {
    const runtime = new MockRuntime({ delayScale: 0 });
    let current = await state(runtime, { action: "session.start", locale: "fr" });
    let answered = 0;
    while (current.stage === "base_questions") {
      const next = current.questions[0];
      if (!next) throw new Error("base_questions without a question");
      current = await state(runtime, { action: "base.answer", client_id: current.client_id, question_id: next.id, value: sampleAnswer(next) });
      answered += 1;
      expect(answered).toBeLessThan(80);
    }
    // No existing portfolio in the sample profile: straight to the house.
    expect(current.stage).toBe("followups");
    expect(current.completeness.score).toBeGreaterThan(0);
  });

  it("keeps the runtime's answers when the question still offers them", () => {
    const goal = question({ id: "q_goal", options: [{ value: "growth", label: "" }, { value: "retirement", label: "" }] });
    expect(sampleAnswer(goal)).toBe("retirement");
    const accounts = question({ id: "q_accounts", kind: "multi_choice", options: [{ value: "tfsa", label: "" }, { value: "resp", label: "" }] });
    expect(sampleAnswer(accounts)).toEqual(["tfsa"]);
    expect(sampleAnswer(question({ id: "q_existing_portfolio", kind: "boolean" }))).toBe(false);
  });

  it("falls back to a valid answer when the type or the options changed", () => {
    // Same id, other questionnaire (the mock asks q_liquidity as yes / no, q_amount as money).
    expect(sampleAnswer(question({ id: "q_liquidity", kind: "boolean" }))).toBe(false);
    expect(sampleAnswer(question({ id: "q_amount", kind: "money", min: 1000, max: 20000 }))).toBe(20000);
    const options = ["dont_know", "low", "mid", "high"].map((value) => ({ value, label: value }));
    expect(fallbackAnswer(question({ options }))).toBe("mid");
    expect(fallbackAnswer(question({ kind: "scale", min: 1, max: 5 }))).toBe(3);
    expect(fallbackAnswer(question({ kind: "multi_choice", options: [{ value: "a", label: "" }, { value: "none", label: "" }] }))).toEqual(["none"]);
  });
});
