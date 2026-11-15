import { describe, expect, it } from "vitest";
import { exposureGroups, exposureLabel } from "@/components/profile/exposures";
import type { Exposures } from "@/lib/contract/schemas";
import { dictionaries } from "@/lib/i18n/dictionary";
import { STARTER_ASSETS } from "@/lib/mock/starter";

// Issue #80, point 2 : the exposures of the e2e test, keyed by the raw values the runtime sends.
const EXPOSURES: Exposures = {
  total_value_cad: 100_000,
  by_asset_class: { equity: 0.48, etf_equity: 0.2, cash: 0.32 },
  by_currency: { CAD: 0.8, USD: 0.2 },
  by_market: { TSX: 0.5, NASDAQ: 0.18, Cash: 0.32 },
  by_sector: { Unknown: 0.32, "Broad market (Canada)": 0.2, Financials: 0.18, "Information Technology": 0.1, Cash: 0.2 },
  top_positions: [],
  flags: [],
};

// The mock keys a missing sector `other`; with more than six sectors, the tail folds into an "Other" row.
const MOCK_EXPOSURES: Exposures = {
  ...EXPOSURES,
  by_sector: {
    other: 0.3,
    Financials: 0.2,
    Energy: 0.15,
    Utilities: 0.12,
    Industrials: 0.1,
    "Health Care": 0.08,
    "Consumer Staples": 0.05,
  },
};

function rowNames(locale: "fr" | "en", group: "byMarket" | "bySector", exposures = EXPOSURES): string[] {
  const t = dictionaries[locale];
  const found = exposureGroups(exposures, t, locale).find((entry) => entry.title === t.exposures[group]);
  return found?.rows.map((row) => row.name) ?? [];
}

describe("sector and market labels of the exposures (issue #80)", () => {
  it("shows French labels in a French session, never the raw English values", () => {
    const sectors = rowNames("fr", "bySector");
    expect(sectors).toEqual([
      "Non classé",
      "Ensemble du marché (Canada)",
      "Encaisse",
      "Services financiers",
      "Technologies de l’information",
    ]);
    for (const raw of ["Unknown", "Financials", "Information Technology", "Broad market (Canada)", "Cash"]) {
      expect(sectors).not.toContain(raw);
    }
    expect(rowNames("fr", "byMarket")).toEqual(["TSX", "Encaisse", "NASDAQ"]);
  });

  it("keeps English labels in an English session, with Unclassified instead of Unknown", () => {
    expect(rowNames("en", "bySector")).toEqual([
      "Unclassified",
      "Broad market (Canada)",
      "Cash",
      "Financials",
      "Information Technology",
    ]);
    expect(rowNames("en", "byMarket")).toEqual(["TSX", "Cash", "NASDAQ"]);
  });

  it("labels the mock's other key like Unknown, apart from the folded tail", () => {
    const french = rowNames("fr", "bySector", MOCK_EXPOSURES);
    expect(french).toEqual(["Non classé", "Services financiers", "Énergie", "Services publics", "Industrie", "Autre"]);
    expect(new Set(french).size).toBe(french.length);
    const english = rowNames("en", "bySector", MOCK_EXPOSURES);
    expect(english).toEqual(["Unclassified", "Financials", "Energy", "Utilities", "Industrials", "Other"]);
    expect(new Set(english).size).toBe(english.length);
  });

  it("leaves the contract keys unchanged", () => {
    exposureGroups(EXPOSURES, dictionaries.fr, "fr");
    expect(Object.keys(EXPOSURES.by_sector)).toContain("Unknown");
    expect(Object.keys(EXPOSURES.by_market)).toContain("Cash");
  });

  it("has a French label for every sector of the starter universe and the GICS sectors", () => {
    const sectors = new Set([...STARTER_ASSETS.map((asset) => asset.sector), "Real Estate", "Materials"]);
    for (const sector of sectors) {
      const french = exposureLabel("sector", sector, "fr");
      expect(french, sector).not.toBe(sector);
      expect(exposureLabel("sector", sector, "en")).toBe(sector);
    }
  });

  it("keeps exchange names, translates the crypto market and passes an unknown value through", () => {
    for (const market of new Set(STARTER_ASSETS.map((asset) => asset.market))) {
      expect(exposureLabel("market", market, "en")).toBe(market);
    }
    expect(exposureLabel("market", "NYSE Arca", "fr")).toBe("NYSE Arca");
    expect(exposureLabel("market", "Crypto (24/7)", "fr")).toBe("Crypto (24 h/24, 7 j/7)");
    expect(exposureLabel("market", "Unknown", "fr")).toBe("Non classé");
    expect(exposureLabel("market", "other", "fr")).toBe("Non classé");
    expect(exposureLabel("market", "other", "en")).toBe("Unclassified");
    expect(exposureLabel("sector", "Quantum Widgets", "fr")).toBe("Quantum Widgets");
    expect(exposureLabel("sector", "constructor", "fr")).toBe("constructor");
  });
});
