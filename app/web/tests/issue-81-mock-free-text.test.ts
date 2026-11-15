import { describe, expect, it } from "vitest";
import { AgentRequest, type AgentRequestInput } from "@/lib/contract/requests";
import { ClientState, type Locale } from "@/lib/contract/schemas";
import { dictionaries } from "@/lib/i18n/dictionary";
import { sampleAnswer } from "@/lib/journey/sample-profile";
import { extractFacts } from "@/lib/mock/agents";
import { dimensionViews, type FieldValues } from "@/lib/mock/profile";
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
    ["Les techs américaines.", ["technology"]],
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
    ["A six-month emergency fund.", 6],
    ["A 6-month cushion.", 6],
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

type MonthsCase = [message: string, months: number];

describe("issue #81: the emergency fund is the number of months nearest a savings word, in the same clause", () => {
  // The two scenarios of the review: the first « N mois » of the message speaks of something else.
  const HOUSE_FIRST: MonthsCase = ["Dans un mois, j'achète une maison; j'ai 4 mois d'épargne de côté.", 4];
  const SCHOOL_FIRST: MonthsCase = ["Ma fille ira à l'école dans douze mois; j'ai un mois d'épargne de précaution.", 1];
  const REVIEW_SCENARIOS = [HOUSE_FIRST, SCHOOL_FIRST];

  it.each<MonthsCase>([
    ...REVIEW_SCENARIOS,
    ["Il y a deux mois, j'ai ouvert un compte d'épargne. J'ai maintenant 3 mois de côté.", 3],
    ["J'ai douze mois de côté, dans un mois je pars en voyage.", 12],
    ["Côté épargne, j'ai six mois.", 6],
    ["In two months I buy a house; I have four months of savings.", 4],
  ])("reads « %s » as a %i-month fund", (message, months) => {
    expect(facts(message)["risk_capacity.emergency_fund"]).toBe(months);
  });

  it("records nothing when no clause ties a number of months to savings", () => {
    expect(facts("Dans un mois, je pars. J'ai de l'épargne.")).not.toHaveProperty(["risk_capacity.emergency_fund"]);
  });

  it.each(REVIEW_SCENARIOS)("is understood by the simulator after the sample profile: « %s »", async (message, months) => {
    const { runtime, current } = await sampleSession("fr");
    const reply = await state(runtime, { action: "followup.reply", client_id: current.client_id, message });
    expect(reply.profile.facts.find((fact) => fact.field === "risk_capacity.emergency_fund")?.value).toBe(months);
  });

  it("keeps the effective risk of the first scenario at medium, as before the number words", async () => {
    const { runtime, current } = await sampleSession("fr");
    const [message] = HOUSE_FIRST;
    const reply = await state(runtime, { action: "followup.reply", client_id: current.client_id, message });
    expect(reply.profile.effective_risk).toBe("medium");
  });
});

describe("issue #81: labels keep their sigla in the profile summary", () => {
  const values: FieldValues = new Map([
    ["preferences.themes", { field: "preferences.themes", value: ["technology", "health"], provenance: "a1:1", at: "2026-11-15T00:00:00Z" }],
    ["preferences.exclusions", { field: "preferences.exclusions", value: ["tobacco", "fossil_fuels"], provenance: "base", at: "2026-11-15T00:00:00Z" }],
  ]);

  it.each([
    ["fr", "Exclut : tabac, énergies fossiles · intérêt : technologie et IA, santé"],
    ["en", "Excludes: tobacco, fossil fuels · interest: technology and AI, health care"],
  ] as const)("%s", (locale, summary) => {
    expect(dimensionViews(values, locale).preferences.summary).toBe(summary);
  });
});

describe("issue #81 (suite): the negation of a high-interest debt, in English and in French", () => {
  const debt = (message: string) => facts(message)["risk_capacity.high_interest_debt"];

  it.each([
    "I also have a 6% mortgage and no credit card debt.",
    "No credit card debt.",
    "I have no high-interest debt.",
    "I have no debts.",
    "I don't have any debt.",
    "I don’t have any credit card debt.",
    "I do not have any high interest debt.",
    "I have never had any debt.",
    "I am debt-free.",
    "I have no credit card.",
    "Zero debt.",
    "Pas de dette.",
    "Aucune dette de carte de crédit.",
    "Je n'ai pas de dette.",
    "Je n’ai aucune dette.",
    "Je n'ai pas vraiment de dettes.",
    "Je n'ai plus de dettes.",
    "Je n'ai jamais eu de dettes.",
    "Je n'ai pas de carte de crédit.",
    "J'ai aussi une hypothèque à 6 % et je n'ai pas de dettes de carte de crédit.",
    // « ni », "neither", "nor", and « autre », "other" (review of the suite).
    "Je n'ai ni dette ni prêt.",
    "Je n'ai aucune autre dette.",
    "Je n'ai pas d'autre dette que l'hypothèque.",
    "I have no other debt.",
    "I have neither debt nor loans.",
  ])("« %s » records no high-interest debt", (message) => {
    expect(debt(message)).toBe(false);
  });

  it.each([
    "I have credit card debt.",
    "No, I have credit card debt.",
    "I can't pay off my credit card debt.",
    "I have no savings and some credit card debt.",
    "J'ai une dette de carte de crédit.",
    "J'ai plus de dettes que d'épargne.",
    "Je n'arrive pas à rembourser ma carte de crédit.",
    "Non, j'ai des dettes sur mes cartes de crédit.",
    "Je n'ai ni épargne ni plan, seulement des dettes.",
    "Neither my savings nor my income covers my credit card debt.",
    "J'ai d'autres dettes.",
    "I have other debts.",
  ])("« %s » records a high-interest debt", (message) => {
    expect(debt(message)).toBe(true);
  });

  it("is understood by the simulator in an English session", async () => {
    const { runtime, current } = await sampleSession("en");
    const message = "I also have a 6% mortgage and no credit card debt.";
    const reply = await state(runtime, { action: "followup.reply", client_id: current.client_id, message });
    expect(reply.profile.facts.find((fact) => fact.field === "risk_capacity.high_interest_debt")?.value).toBe(false);
    expect(reply.message?.split("\n\n")[0]).toBe("Noted: no high-interest debt.");
  });
});
