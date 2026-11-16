/**
 * « Répartition de votre argent »: the optional `allocation` of the build response parses (and its absence
 * too), its rows are formatted in French and in English from the engine's own numbers, the panel hides
 * without an allocation, and the positions table gets an amount column only with one.
 */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AllocationBreakdown } from "@/components/portfolio/allocation-breakdown";
import { DecisionView } from "@/components/portfolio/decision-view";
import { DecisionProvider } from "@/components/portfolio/facts";
import { PortfolioBuildResponse } from "@/lib/contract/portfolio";
import type { Locale } from "@/lib/contract/schemas";
import { portfolioEn, portfolioFr } from "@/lib/i18n/portfolio";
import { I18nProvider } from "@/lib/i18n/provider";
import { PORTFOLIO_FIXTURES } from "@/lib/mock/decisions";
import { allocationAmount, allocationShare, bucketLabel, positionAmounts } from "@/lib/portfolio/allocation";
import { indexFacts, indexTrace, shortlistReason } from "@/lib/portfolio/decision";

/** A hand-written allocation in the engine's shape (test data only: the numbers are not derived here). */
const ALLOCATION = {
  amount_cad: 50000,
  currency: "CAD",
  positions: [
    { asset_id: "SPY", name: "SPDR S&P 500", asset_class: "etf_equity", class_key: "fnb_actions", currency: "USD", sector: null, role: "coeur", weight: 0.48, amount_cad: 24000, fact_id: "mix.amount.SPY" },
    { asset_id: "AGG", name: "iShares Core US Aggregate Bond", asset_class: "etf_bond", class_key: "obligations", currency: "USD", sector: null, role: "coeur", weight: 0.15, amount_cad: 7500, fact_id: "mix.amount.AGG" },
    { asset_id: "TSLA", name: "Tesla", asset_class: "equity", class_key: "actions_individuelles", currency: "USD", sector: "Consumer Cyclical", role: "satellite", weight: 0.03, amount_cad: null, fact_id: "mix.amount.TSLA" },
  ],
  by_class: [
    { key: "fnb_actions", label_fr: "FNB d'actions", weight: 0.69, amount_cad: 34500, fact_id: "level" },
    { key: "obligations", label_fr: "Obligations", weight: 0.15, amount_cad: 7500, fact_id: "mix.class.obligations" },
    { key: "nouvelle_classe", label_fr: "Classe inconnue", weight: 0.16, amount_cad: 8000, fact_id: null },
  ],
  by_currency: [
    { key: "USD", label_fr: "Dollar américain", weight: 0.97, amount_cad: 48500, fact_id: "mix.currency.USD" },
    { key: "CAD", label_fr: "Dollar canadien", weight: 0.03, amount_cad: 1500, fact_id: "mix.currency.CAD" },
  ],
  by_sector: [
    { key: "tech", label_fr: "Technologie", weight: 0.22, amount_cad: 11000, fact_id: "mix.sector.tech", basis: "lookthrough" },
    { key: "energie", label_fr: "Énergie", weight: 0.03, amount_cad: 1500, fact_id: "mix.sector.energie", basis: "direct" },
    { key: "non_ventile", label_fr: "Non ventilé", weight: 0.75, amount_cad: 37500, fact_id: "mix.sector.non_ventile", basis: "non_ventile" },
  ],
  sector_coverage: 0.25,
};

const amira = () => structuredClone(PORTFOLIO_FIXTURES.amira) as Record<string, unknown>;
const withAllocation = (allocation: unknown) => PortfolioBuildResponse.parse({ ...amira(), allocation });

function render(response: PortfolioBuildResponse, locale: Locale, node: "view" | "panel" = "view"): string {
  const lookup = { facts: indexFacts(response.decision), trace: indexTrace(response.decision), open: () => {} };
  const child = node === "view" ? createElement(DecisionView, { response, fixture: true }) : createElement(AllocationBreakdown, { allocation: response.allocation });
  const props = { initialLocale: locale } as Parameters<typeof I18nProvider>[0];
  return renderToStaticMarkup(createElement(I18nProvider, props, createElement(DecisionProvider, { value: lookup }, child)));
}

describe("allocation contract", () => {
  it("parses an engine allocation", () => {
    const response = withAllocation(ALLOCATION);
    expect(response.allocation?.amount_cad).toBe(50000);
    expect(response.allocation?.by_class.map((row) => row.key)).toEqual(["fnb_actions", "obligations", "nouvelle_classe"]);
    expect(response.allocation?.by_sector[0]?.basis).toBe("lookthrough");
    expect(response.allocation?.positions[2]?.amount_cad).toBeNull();
    expect(response.allocation?.sector_coverage).toBe(0.25);
  });

  it("still parses an older response without allocation, or with a null one", () => {
    // Les fixtures réexportées par le moteur portent désormais une allocation : on la retire pour simuler l'ancienne réponse.
    const older = structuredClone(PORTFOLIO_FIXTURES.amira) as Record<string, unknown>;
    delete older.allocation;
    expect(PortfolioBuildResponse.parse(older).allocation).toBeUndefined();
    expect(withAllocation(null).allocation).toBeNull();
  });

  it("accepts an allocation without an amount, and refuses a weight outside 0..1", () => {
    expect(withAllocation({ ...ALLOCATION, amount_cad: null }).allocation?.amount_cad).toBeNull();
    const bad = structuredClone(ALLOCATION);
    bad.by_class[0]!.weight = 1.5;
    expect(PortfolioBuildResponse.safeParse({ ...amira(), allocation: bad }).success).toBe(false);
  });
});

describe("allocation display helpers", () => {
  it("format a share and an amount in French like the engine, and the English way in English", () => {
    expect(allocationShare(0.48, "fr")).toBe("48,0 %");
    expect(allocationShare(0.48, "en")).toBe("48.0%");
    expect(allocationAmount(31300, "fr")).toBe("31 300 $");
    expect(allocationAmount(31300, "en")).toBe("$31,300");
    expect(allocationAmount(null, "fr")).toBeNull();
    expect(allocationAmount(undefined, "en")).toBeNull();
  });

  it("name a known class in the interface language, else keep the engine's label", () => {
    expect(bucketLabel({ key: "obligations", label_fr: "Obligations" }, portfolioEn.allocation.classes)).toBe("Bonds");
    expect(bucketLabel({ key: "crypto", label_fr: "Crypto" }, portfolioFr.allocation.classes)).toBe("Cryptoactifs");
    expect(bucketLabel({ key: "x", label_fr: "Classe inconnue" }, portfolioEn.allocation.classes)).toBe("Classe inconnue");
    expect(Object.keys(portfolioEn.allocation.classes).sort()).toEqual(Object.keys(portfolioFr.allocation.classes).sort());
  });

  it("look up the engine's amount of each position", () => {
    const amounts = positionAmounts(withAllocation(ALLOCATION).allocation);
    expect(amounts.get("SPY")).toBe(24000);
    expect(amounts.get("TSLA")).toBeNull();
    expect(positionAmounts(null).size).toBe(0);
  });
});

describe("« Répartition de votre argent » panel", () => {
  it("shows the three breakdowns, the total and the sector coverage in French", () => {
    const html = render(withAllocation(ALLOCATION), "fr");
    const v = portfolioFr.allocation;
    for (const text of [v.title, v.byClass, v.bySector, v.byCurrency, v.total, "50 000 $", "69,0 %", "34 500 $", v.classes.fnb_actions, v.basis.lookthrough, "Technologie"]) {
      expect(html).toContain(text);
    }
    expect(html).toContain(v.coverage("25,0 %"));
    // Amount column of the positions table, from allocation.positions; « — » where the engine gave none.
    expect(html).toContain(`>${v.amount}</th>`);
    expect(html).toContain("24 000 $");
  });

  it("shows it in English", () => {
    const html = render(withAllocation(ALLOCATION), "en");
    const v = portfolioEn.allocation;
    for (const text of [v.title, v.byClass, "$50,000", "69.0%", "$34,500", "Equity ETFs", "Canadian dollar (CAD)", v.coverage("25.0%")]) expect(html).toContain(text);
  });

  it("opens the fact of a row that has one, and shows no chip for a fact absent from the decision", () => {
    const html = render(withAllocation(ALLOCATION), "fr", "panel");
    expect(html).toContain('aria-haspopup="dialog"');
    expect(html).not.toContain("mix.class.obligations");
  });

  it("says nothing about coverage when every sector is known", () => {
    const html = render(withAllocation({ ...ALLOCATION, sector_coverage: 1 }), "fr", "panel");
    expect(html).not.toContain("non ventilé.");
  });

  it("hides the panel and the amount column without an allocation", () => {
    for (const allocation of [undefined, null]) {
      const html = render(withAllocation(allocation), "fr");
      expect(html).not.toContain(portfolioFr.allocation.title);
      expect(html).not.toContain(`>${portfolioFr.allocation.amount}</th>`);
    }
  });
});

describe("why no single stock is kept (strat.K)", () => {
  it("takes the engine's reason as is from the processing of strat.K", () => {
    const robert = PortfolioBuildResponse.parse(PORTFOLIO_FIXTURES.robert);
    const why = shortlistReason(indexFacts(robert.decision));
    expect(why?.fact.fact_id).toBe("strat.K");
    expect(why?.reason).toBe("niveau N0 : aucun titre individuel");
    expect(shortlistReason(new Map())).toBeNull();
  });

  it("shows it under « Aucun titre individuel retenu », with the fact chip", () => {
    const robert = PortfolioBuildResponse.parse(PORTFOLIO_FIXTURES.robert);
    expect(robert.strategy?.shortlist).toEqual([]);
    const html = render(robert, "fr");
    expect(html).toContain(portfolioFr.style.noShortlist);
    expect(html).toContain(`${portfolioFr.style.shortlistReason} : niveau N0 : aucun titre individuel`);
    // Amira keeps two stocks: no reason line.
    expect(render(withAllocation(null), "fr")).not.toContain(portfolioFr.style.shortlistReason);
  });
});
