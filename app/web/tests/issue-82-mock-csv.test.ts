/**
 * Issue #82: the simulator's A2 reads a broker CSV with a header by column name, keeps an explicit
 * symbol outside the starter universe unidentified (VFV.TO is not SPY), reads CASH as cash, and the
 * guardrail masks usual account numbers in the pasted text. Like the real runtime (#77), a SIN is refused.
 */
import { describe, expect, it } from "vitest";
import type { AgentRequestInput } from "@/lib/contract/requests";
import { AgentRequest, PositionInput } from "@/lib/contract/requests";
import { ClientState, ErrorEnvelope, KbGetResponse, type AnswerValue, type Locale, type Position } from "@/lib/contract/schemas";
import { screenMessage } from "@/lib/mock/agents";
import { MockError } from "@/lib/mock/envelope";
import { computeExposures, extractPositions, normalizeConfirmed } from "@/lib/mock/portfolio";
import { MockRuntime } from "@/lib/mock/runtime";
import { findAssetByTicker, USDCAD } from "@/lib/mock/starter";

const CSV = [
  "Symbole,Description,Quantité,Prix,Valeur marchande,Devise",
  "XIU.TO,iShares S&P/TSX 60,150,38.20,5730.00,CAD",
  "VFV.TO,Vanguard S&P 500 Index ETF,40,152.10,6084.00,CAD",
  "RY.TO,Banque Royale du Canada,25,182.45,4561.25,CAD",
  "AAPL,Apple Inc.,10,231.50,2315.00,USD",
  "ZAG.TO,BMO Aggregate Bond Index ETF,200,14.05,2810.00,CAD",
  "CASH,Encaisse,,,1200.00,CAD",
].join("\n");

const csvFile = (content: string) => ({ name: "releve-disnat.csv", media_type: "text/csv", data_base64: Buffer.from(content).toString("base64") });

const close = (ticker: string) => findAssetByTicker(ticker)?.close ?? Number.NaN;

/** The file at the starter's last closes for the securities of the universe, at its declared values for the others. */
const EXPECTED_TOTAL = 150 * close("XIU.TO") + 25 * close("RY.TO") + 10 * close("AAPL") * USDCAD + 6084 + 2810 + 1200;

const byRaw = (positions: Position[], prefix: string) => positions.find((position) => position.raw?.startsWith(prefix));

function expectIssueCsvRead(positions: Position[]) {
  // The header is not a row: six lines, six positions, and nothing is matched by name to SPY.
  expect(positions).toHaveLength(6);
  expect(positions.map((position) => position.ticker)).not.toContain("SPY");
  expect(byRaw(positions, "XIU.TO")).toMatchObject({ ticker: "XIU.TO", quantity: 150, resolved: true, value_cad: 8182.5 });
  expect(byRaw(positions, "VFV.TO")).toMatchObject({ ticker: "VFV.TO", quantity: 40, resolved: false, currency: "CAD", value_cad: 6084 });
  expect(byRaw(positions, "RY.TO")).toMatchObject({ ticker: "RY.TO", quantity: 25, resolved: true });
  expect(byRaw(positions, "AAPL")).toMatchObject({ ticker: "AAPL", quantity: 10, currency: "USD", resolved: true });
  expect(byRaw(positions, "ZAG.TO")).toMatchObject({ ticker: "ZAG.TO", quantity: 200, resolved: false, value_cad: 2810 });
  expect(byRaw(positions, "CASH")).toMatchObject({
    asset_class: "cash",
    name: "Encaisse",
    currency: "CAD",
    market_value: 1200,
    value_cad: 1200,
    resolved: true,
  });
  expect(computeExposures(positions).total_value_cad).toBeCloseTo(EXPECTED_TOTAL, 1);
}

describe("issue #82: a broker CSV with a header", () => {
  it("reads a file by column name: quantity, value, currency; VFV.TO stays unidentified, CASH is cash", () => {
    const { positions, unresolved } = extractPositions({ files: [csvFile(CSV)] }, "fr");
    expectIssueCsvRead(positions);
    expect(unresolved.map((item) => item.raw.split(",")[0])).toEqual(["VFV.TO", "ZAG.TO"]);
    expect(unresolved.every((item) => item.position_id)).toBe(true);
    expect(computeExposures(positions).by_asset_class.cash).toBeCloseTo(1200 / EXPECTED_TOTAL, 3);
  });

  it("reads the same table pasted as text, after an introduction line, without masking its amounts", () => {
    const screened = screenMessage(`Mon CELI chez Disnat, compte 123-45678-9 :\n${CSV}`);
    expect(screened.masked).toBe(1);
    expectIssueCsvRead(extractPositions({ text: screened.text }, "fr").positions);
  });

  it("uses quantity times price when a row has no value, and reads semicolons and quoted cells", () => {
    const csv = 'Symbole;Description;Quantité;Prix;Devise\nVFV.TO;"Vanguard S&P 500; Index ETF";40;152,10;CAD\nRY.TO;Banque Royale;25;182,45;CAD\nTotal;;;;CAD';
    const { positions } = extractPositions({ files: [csvFile(csv)] }, "en");
    expect(positions).toHaveLength(2);
    expect(positions[0]).toMatchObject({ ticker: "VFV.TO", name: "Vanguard S&P 500; Index ETF", quantity: 40, market_value: 6084, resolved: false });
    expect(positions[1]).toMatchObject({ ticker: "RY.TO", quantity: 25, resolved: true });
    expect(positions[1]?.value_cad).toBeCloseTo(25 * close("RY.TO"), 2);
  });

  it("keeps an explicit listed symbol of free text unidentified instead of matching a name", () => {
    const { positions } = extractPositions({ text: "40 VFV.TO Vanguard S&P 500\n5 000 $ en encaisse" }, "fr");
    expect(positions[0]).toMatchObject({ ticker: "VFV.TO", quantity: 40, resolved: false });
    expect(positions[1]).toMatchObject({ asset_class: "cash", market_value: 5000, value_cad: 5000, resolved: true });
  });

  it("keeps a confirmed cash row as cash", () => {
    const { positions } = extractPositions({ files: [csvFile(CSV)] }, "en");
    const cash = byRaw(positions, "CASH");
    expect(cash && normalizeConfirmed(cash, "en")).toMatchObject({ asset_class: "cash", value_cad: 1200, resolved: true, notes: null });
  });
});

/** What `portfolio.confirm` makes of the review sent back unchanged. */
const confirmedUnchanged = (positions: Position[]) => positions.map((position) => normalizeConfirmed(PositionInput.parse(position), "fr"));

describe("issue #82: confirming the review without a change keeps every value", () => {
  it.each([
    ["the issue's file", CSV],
    ["a value declared in CAD for a USD listing", "Symbole,Description,Quantité,Prix,Valeur marchande,Devise\nAAPL,Apple Inc.,,,2315.00,CAD"],
    ["a value declared in USD for a CAD listing", "Symbole,Description,Quantité,Prix,Valeur marchande,Devise\nXIU.TO,iShares,,,5730,USD"],
  ])("%s", (_case, csv) => {
    const { positions } = extractPositions({ files: [csvFile(csv)] }, "fr");
    const confirmed = confirmedUnchanged(positions);
    expect(confirmed.map((position) => position.value_cad)).toEqual(positions.map((position) => position.value_cad));
    expect(confirmed.map((position) => position.currency)).toEqual(positions.map((position) => position.currency));
  });

  it("values a declared value in the currency the line gives", () => {
    const csv = "Symbole,Description,Quantité,Prix,Valeur marchande,Devise\nAAPL,Apple Inc.,,,2315.00,CAD";
    const [apple] = extractPositions({ files: [csvFile(csv)] }, "fr").positions;
    expect(apple).toMatchObject({ ticker: "AAPL", quantity: null, market_value: 2315, currency: "CAD", value_cad: 2315 });
  });
});

describe("issue #82: CASH.TO is an ETF, not cash", () => {
  it("keeps 100 CASH.TO of free text unidentified with its 100 shares, before and after confirmation", () => {
    const { positions } = extractPositions({ text: "100 CASH.TO" }, "fr");
    const expected = { ticker: "CASH.TO", quantity: 100, resolved: false, value_cad: null };
    expect(positions).toEqual([expect.objectContaining({ ...expected, asset_class: null })]);
    expect(confirmedUnchanged(positions)).toEqual([expect.objectContaining({ ...expected, asset_class: "other" })]);
  });

  it("keeps a CASH.TO row of a CSV as a security, with its symbol and quantity", () => {
    const csv = "Symbole,Description,Quantité,Prix,Valeur marchande,Devise\nCASH.TO,Global X High Interest Savings ETF,100,50.05,5005,CAD";
    const { positions } = extractPositions({ files: [csvFile(csv)] }, "fr");
    const expected = { ticker: "CASH.TO", name: "Global X High Interest Savings ETF", quantity: 100, value_cad: 5005, resolved: false };
    expect(positions).toEqual([expect.objectContaining(expected)]);
    expect(confirmedUnchanged(positions)).toEqual([expect.objectContaining(expected)]);
    expect(confirmedUnchanged(positions)[0]?.asset_class).not.toBe("cash");
  });

  it("reads only an exact cash word as cash in the symbol column", () => {
    const csv = "Symbole,Description,Valeur marchande,Devise\nCASHFLOW,Fonds XYZ,1000,CAD\nEncaisse,,1200,CAD\n,Liquidités,300,CAD";
    const { positions } = extractPositions({ files: [csvFile(csv)] }, "fr");
    expect(positions.map((position) => [position.ticker, position.asset_class])).toEqual([
      ["CASHFLOW", null],
      [null, "cash"],
      [null, "cash"],
    ]);
  });
});

describe("issue #82: cash without an amount", () => {
  it.each([
    ["fr", "montant de l'encaisse manquant"],
    ["en", "cash amount missing"],
  ] as const)("stays unresolved and is listed, like _resolve_cash (%s)", (locale, reason) => {
    const csv = "Symbole,Description,Quantité,Valeur marchande,Devise\nRY.TO,Banque Royale,25,,CAD\nCASH,Encaisse,,,CAD";
    const { positions, unresolved } = extractPositions({ files: [csvFile(csv)] }, locale);
    expect(positions[1]).toMatchObject({ asset_class: "cash", value_cad: null, resolved: false });
    expect(unresolved).toEqual([{ raw: "CASH,Encaisse,,,CAD", reason, position_id: positions[1]?.id }]);
    expect(confirmedUnchanged(positions)[1]).toMatchObject({ asset_class: "cash", resolved: false });
  });
});

describe("issue #82: a header with a date", () => {
  it.each(["Valeur marchande au 2026-11-12", "Valeur marchande (12/11/2026)"])("reads the columns of a header with %j", (column) => {
    const csv = `Symbole,Description,Quantité,Prix,${column},Devise\nXIU.TO,iShares S&P/TSX 60,150,38.20,5730.00,CAD`;
    const { positions } = extractPositions({ files: [csvFile(csv)] }, "fr");
    expect(positions).toEqual([expect.objectContaining({ ticker: "XIU.TO", quantity: 150, market_value: 5730, value_cad: 8182.5 })]);
  });

  it("does not take a free-text line with a quantity for a header", () => {
    const { positions } = extractPositions({ text: "Titre RY.TO, quantité 100\n25 AAPL" }, "fr");
    expect(positions.map((position) => [position.ticker, position.quantity])).toEqual([
      ["RY.TO", 100],
      ["AAPL", 25],
    ]);
  });
});

describe("issue #82: account numbers in the pasted text", () => {
  it("masks usual account numbers", () => {
    const screened = screenMessage("Mon CELI chez Disnat, compte 123-45678-9 :");
    expect(screened.text).toBe("Mon CELI chez Disnat, compte [masqué] :");
    expect(screened.masked).toBe(1);
    expect(screenMessage("Transit-institution-compte : 12345-003-1234567").text).toBe("Transit-institution-compte : [masqué]");
    expect(screenMessage("Compte no 123 45678 9 chez BMO").text).toBe("Compte no [masqué] chez BMO");
    expect(screenMessage("account #12345678").masked).toBe(1);
    expect(screenMessage("No de compte : 12345, CELI").text).toBe("No de compte : [masqué], CELI");
    // The quantity after the account number stays.
    expect(screenMessage("Compte no 98765 150 XIU.TO").text).toBe("Compte no [masqué] 150 XIU.TO");
  });

  it("does not mask amounts, quantities, prices or dates", () => {
    const text = [
      "150 XIU.TO à 38,20 $, valeur 5 730,00 $",
      "Encaisse : 1 200 $; compte : 25 000 $; compte 1500 actions",
      "J'ai 1500000 $ dans mon REER, et 2 500 000 $ en tout",
      "Relevé du 2026-11-12",
    ].join("\n");
    const screened = screenMessage(text);
    expect(screened.text).toBe(text);
    expect(screened.masked).toBe(0);
  });

  it.each([
    "Dans mon compte 2 500 parts de XIU.TO",
    "Voici mon compte :\n1 500 XIU.TO\n200 ZAG.TO",
    "Mon compte : 50 000",
    "Mon compte : 50 000 CAD",
    "account 10000 shares of AAPL",
    "Quantité\tSymbole\tValeur\tCompte\n2 500\tXIU.TO\t95 500 $\tCELI",
    "Compte 98765 150 XIU.TO",
  ])("does not mask a quantity or an amount after the word account: %j", (text) => {
    expect(screenMessage(text)).toMatchObject({ text, masked: 0 });
  });

  it("keeps the quantity of a pasted line after an account word", () => {
    const { positions } = extractPositions({ text: screenMessage("Voici mon compte :\n12000 XIU.TO").text }, "fr");
    expect(positions).toEqual([expect.objectContaining({ ticker: "XIU.TO", quantity: 12000, value_cad: 12000 * close("XIU.TO") })]);
  });
});

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
async function atExistingPortfolio(runtime: MockRuntime, locale: Locale = "fr") {
  let current = await state(runtime, { action: "session.start", locale });
  while (current.stage === "base_questions") {
    const question = current.questions[0];
    const value = question ? BASE_ANSWERS[question.id] : undefined;
    if (!question || value === undefined) throw new Error(`No answer for ${question?.id}`);
    current = await state(runtime, { action: "base.answer", client_id: current.client_id, question_id: question.id, value });
  }
  expect(current.stage).toBe("existing_portfolio");
  return current.client_id;
}

describe("issue #82: portfolio.submit of the e2e run", () => {
  it("reads the CSV and never repeats the account number of the pasted text", async () => {
    const runtime = new MockRuntime({ delayScale: 0 });
    const id = await atExistingPortfolio(runtime);
    const review = await state(runtime, {
      action: "portfolio.submit",
      client_id: id,
      text: "Mon CELI chez Disnat, compte 123-45678-9 :",
      files: [csvFile(CSV)],
    });
    expectIssueCsvRead(review.portfolio?.positions ?? []);
    expect(JSON.stringify(review)).not.toContain("123-45678-9");
    expect(review.trace.find((step) => step.kind === "guardrail")?.outputs).toMatchObject({ masked: 1 });
    expect(review.message).not.toMatch(/585/);
  });
});

/** The refusal of the real runtime (agentkit.py, `personal_data_error`, #77). */
const SIN_REFUSAL = {
  code: "guardrail_blocked",
  message: {
    fr: "Votre message contient un renseignement personnel (NAS) : retirez-le, puis renvoyez-le.",
    en: "Your message contains personal information (SIN): remove it, then send it again.",
  },
  details: { reason: "personal_data", entity: "CA_SIN" },
} as const;

function thrown(run: () => unknown): unknown {
  try {
    run();
  } catch (error) {
    return error;
  }
  return null;
}

describe("issue #82: a SIN is refused like in the real runtime, other personal data stays masked", () => {
  it.each(["Mon NAS est 123 456 789", "SIN: 046-454-286", "NAS 046 454-286, compte no 12345"])("screenMessage refuses %j", (text) => {
    const error = thrown(() => screenMessage(text));
    expect(error).toBeInstanceOf(MockError);
    expect(error).toMatchObject({ code: SIN_REFUSAL.code, text: SIN_REFUSAL.message, details: SIN_REFUSAL.details });
  });

  it("masks the other personal data, and a SIN-like number written without separators", () => {
    expect(screenMessage("moi@exemple.ca, 514-555-1234, compte 123-45678-9, 123456789")).toMatchObject({
      text: "[masqué], [masqué], compte [masqué], [masqué]",
      masked: 4,
    });
  });

  it.each(["fr", "en"] as const)("refuses a SIN in followup.reply, and journals nothing (%s)", async (locale) => {
    const runtime = new MockRuntime({ delayScale: 0 });
    const id = await atExistingPortfolio(runtime, locale);
    await state(runtime, { action: "portfolio.skip", client_id: id });
    const message = "Mon NAS est 046 454 286, je prépare ma retraite";
    const error = await failure(runtime, { action: "followup.reply", client_id: id, message });
    expect(error).toEqual({ code: SIN_REFUSAL.code, message: SIN_REFUSAL.message[locale], details: SIN_REFUSAL.details });
    const journal = KbGetResponse.parse(await runtime.handle(AgentRequest.parse({ action: "kb.get", key: `clients/${id}/journal.md`, client_id: id })));
    // The full SIN, with or without separators: the journal holds timestamps, whose digits can contain « 046 ».
    expect(journal.content).not.toMatch(/046\D?454\D?286/);
  });

  it("refuses a SIN in portfolio.submit, and keeps the existing-portfolio step", async () => {
    const runtime = new MockRuntime({ delayScale: 0 });
    const id = await atExistingPortfolio(runtime);
    const error = await failure(runtime, { action: "portfolio.submit", client_id: id, text: "NAS : 046-454-286\n100 RY.TO", files: [csvFile(CSV)] });
    expect(error).toEqual({ code: SIN_REFUSAL.code, message: SIN_REFUSAL.message.fr, details: SIN_REFUSAL.details });
    const resumed = await state(runtime, { action: "session.resume", client_id: id });
    expect(resumed).toMatchObject({ stage: "existing_portfolio", portfolio: null });
    // Without the SIN, the same text and file are read, the other personal data masked.
    const review = await state(runtime, { action: "portfolio.submit", client_id: id, text: "moi@exemple.ca\n100 RY.TO", files: [csvFile(CSV)] });
    expect(review.stage).toBe("portfolio_review");
    expect(review.trace.find((step) => step.kind === "guardrail")?.outputs).toMatchObject({ masked: 1 });
  });
});
