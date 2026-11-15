import { describe, expect, it } from "vitest";
import { AgentRequest, type AgentRequestInput } from "@/lib/contract/requests";
import { ClientState, type Locale } from "@/lib/contract/schemas";
import { dictionaries } from "@/lib/i18n/dictionary";
import { sampleAnswer } from "@/lib/journey/sample-profile";
import { extractFacts } from "@/lib/mock/agents";
import { MockRuntime } from "@/lib/mock/runtime";

/** The example the dashboard offers in its free-text field, after « par exemple : » or "for example:". */
function placeholderExample(locale: Locale): string {
  const example = /:\s*(.+)$/.exec(dictionaries[locale].followups.messagePlaceholder)?.[1];
  if (!example) throw new Error(`No example in the ${locale} placeholder`);
  return example;
}

/** What the simulator's A1 reads in a message, by field. */
const facts = (message: string) => Object.fromEntries(extractFacts(message, new Map()).map((fact) => [fact.field, fact.value]));

const EXAMPLE_FACTS = { "risk_capacity.emergency_fund": 6, "risk_capacity.high_interest_debt": false };

async function state(runtime: MockRuntime, request: AgentRequestInput) {
  const parsed = ClientState.safeParse(await runtime.handle(AgentRequest.parse(request)));
  if (!parsed.success) throw new Error(`Not a ClientState: ${parsed.error.message}`);
  return parsed.data;
}

/** A session past the base questions, answered with the sample profile (« Passer les questions »). */
async function sampleSession(locale: Locale) {
  const runtime = new MockRuntime({ delayScale: 0 });
  let current = await state(runtime, { action: "session.start", locale });
  while (current.stage === "base_questions") {
    const next = current.questions[0];
    if (!next) throw new Error("base_questions without a question");
    current = await state(runtime, { action: "base.answer", client_id: current.client_id, question_id: next.id, value: sampleAnswer(next) });
  }
  return { runtime, current };
}

describe("issue #81: the free-text example of the dashboard", () => {
  it.each(["fr", "en"] as const)("records a 6-month emergency fund, no high-interest debt and no theme (%s)", (locale) => {
    expect(facts(placeholderExample(locale))).toEqual(EXAMPLE_FACTS);
  });

  it("reads the example as the investor types it, with a straight apostrophe and a capital", () => {
    expect(facts("J'ai six mois de dépenses de côté et aucune dette.")).toEqual(EXAMPLE_FACTS);
  });

  it.each([
    ["fr", "C'est noté : fonds d'urgence de 6 mois et aucune dette à taux élevé."],
    ["en", "Noted: 6-month emergency fund and no high-interest debt."],
  ] as const)("is understood by the simulator after the sample profile (%s)", async (locale, acknowledgement) => {
    const { runtime, current } = await sampleSession(locale);
    expect(current.stage).toBe("followups");
    const reply = await state(runtime, { action: "followup.reply", client_id: current.client_id, message: placeholderExample(locale) });
    const byField = new Map(reply.profile.facts.map((fact) => [fact.field, fact]));
    expect(byField.get("risk_capacity.emergency_fund")).toMatchObject({ value: 6, provenance: expect.stringMatching(/^a1:/) });
    expect(byField.get("risk_capacity.high_interest_debt")).toMatchObject({ value: false });
    expect(byField.has("preferences.themes")).toBe(false);
    expect(reply.completeness.missing.map((missing) => missing.field)).not.toContain("emergency_fund");
    expect(reply.questions.map((question) => question.field)).not.toContain("emergency_fund");
    expect(reply.message?.split("\n\n")[0]).toBe(acknowledgement);
  });

  it("reads the dashboard's other message: no theme, and no credit card debt", () => {
    expect(facts("J'ai aussi une hypothèque à 6 % et je n'ai pas de dettes de carte de crédit.")).toEqual({
      "risk_capacity.high_interest_debt": false,
    });
  });

  it("reads the typographic apostrophe like the straight one", () => {
    expect(facts("Je dois pouvoir retirer n’importe quand.")).toEqual({ "constraints.liquidity_need": true });
    expect(facts("Je retirerai tout d’un coup.")).toEqual({ "horizon.withdrawal_pattern": "lump_sum" });
  });
});

describe("issue #81: themes of interest", () => {
  it.each([
    "J'ai un CELI.",
    "J’ai un CELI.",
    "Je n'ai pas de CELI.",
    "J'en ai un.",
    "Ai-je assez épargné ?",
    "J'AI UN CELI.",
    "Une épargne suffisante, c'est intéressant et rassurant.",
    "J'ai étudié à Polytechnique.",
    "Je fais un peu d'analyse technique.",
  ])("records no theme for « %s »", (message) => {
    expect(facts(message)).not.toHaveProperty(["preferences.themes"]);
  });

  it.each([
    ["L'IA m'intéresse.", ["technology"]],
    ["L’IA m'intéresse.", ["technology"]],
    ["J'aime l'intelligence artificielle.", ["technology"]],
    ["I like AI stocks.", ["technology"]],
    ["Artificial intelligence and tech companies.", ["technology"]],
    ["La technologie et la santé.", ["technology", "health"]],
    ["Health care and high-tech.", ["technology", "health"]],
  ])("reads the themes of « %s »", (message, themes) => {
    expect(facts(message)["preferences.themes"]).toEqual(themes);
  });

  it("does not read « larmes » as weapons", () => {
    expect(facts("Pas de larmes, mais pas de tabac.")["preferences.exclusions"]).toEqual(["tobacco"]);
    expect(facts("J'évite les armes.")["preferences.exclusions"]).toEqual(["weapons"]);
  });
});

describe("issue #81: emergency fund in words", () => {
  it.each([
    ["Un mois de dépenses de côté.", 1],
    ["J'ai trois mois d'épargne de précaution.", 3],
    ["Douze mois de côté en cas d'urgence.", 12],
    ["One month of savings.", 1],
    ["I have twelve months of expenses set aside.", 12],
    ["An emergency fund of nine months.", 9],
    ["J'ai 6 mois de côté.", 6],
    ["18 months of savings.", 18],
  ])("reads « %s » as a %i-month fund", (message, months) => {
    expect(facts(message)["risk_capacity.emergency_fund"]).toBe(months);
  });

  it.each(["Aucun mois de côté.", "Dix-huit mois de côté.", "Twenty-four months of savings.", "120 mois d'épargne."])(
    "does not misread « %s »",
    (message) => {
      expect(facts(message)).not.toHaveProperty(["risk_capacity.emergency_fund"]);
    },
  );
});
