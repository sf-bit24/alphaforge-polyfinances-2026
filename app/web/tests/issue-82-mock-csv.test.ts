/**
 * Issue #82: the simulator's A2 reads a broker CSV with a header by column name, keeps an explicit
 * symbol outside the starter universe unidentified (VFV.TO is not SPY), and reads CASH as cash.
 */
import { describe, expect, it } from "vitest";
import type { Position } from "@/lib/contract/schemas";
import { computeExposures, extractPositions, normalizeConfirmed } from "@/lib/mock/portfolio";
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
