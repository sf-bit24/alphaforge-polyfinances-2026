/**
 * Issue #82: the simulator's A2 reads a broker CSV with a header by column name, keeps an explicit
 * symbol outside the starter universe unidentified (VFV.TO is not SPY), reads CASH as cash, and the
 * guardrail masks usual account numbers in the pasted text.
 */
import { describe, expect, it } from "vitest";
import type { AgentRequestInput } from "@/lib/contract/requests";
import { AgentRequest } from "@/lib/contract/requests";
import { ClientState, type AnswerValue, type Position } from "@/lib/contract/schemas";
import { screenMessage } from "@/lib/mock/agents";
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

describe("issue #82: account numbers in the pasted text", () => {
  it("masks usual account numbers, and keeps the SIN masked", () => {
    const screened = screenMessage("Mon CELI chez Disnat, compte 123-45678-9 :");
    expect(screened.text).toBe("Mon CELI chez Disnat, compte [masqué] :");
    expect(screened.masked).toBe(1);
    expect(screenMessage("Transit-institution-compte : 12345-003-1234567").text).toBe("Transit-institution-compte : [masqué]");
    expect(screenMessage("Compte no 123 45678 9 chez BMO").text).toBe("Compte no [masqué] chez BMO");
    expect(screenMessage("account #12345678").masked).toBe(1);
    expect(screenMessage("Mon NAS est 123 456 789").text).toBe("Mon NAS est [masqué]");
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

/** A session at the existing-portfolio step, after the base questions. */
async function atExistingPortfolio(runtime: MockRuntime) {
  let current = await state(runtime, { action: "session.start", locale: "fr" });
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
