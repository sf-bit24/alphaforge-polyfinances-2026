/**
 * Issue #78 (and #80, point 4): the engine's French texts translate its codes, the page says in English
 * that they stay in French, and the trace counts its steps with the right plural.
 */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DecisionView } from "@/components/portfolio/decision-view";
import { DecisionProvider } from "@/components/portfolio/facts";
import { DEMO_PERSONAS, PortfolioBuildResponse, type Decision } from "@/lib/contract/portfolio";
import type { Locale } from "@/lib/contract/schemas";
import { portfolioEn, portfolioFr } from "@/lib/i18n/portfolio";
import { I18nProvider } from "@/lib/i18n/provider";
import { PORTFOLIO_FIXTURES } from "@/lib/mock/decisions";
import { indexFacts, indexTrace } from "@/lib/portfolio/decision";

const fixtures = DEMO_PERSONAS.map((persona) => [persona, PortfolioBuildResponse.parse(PORTFOLIO_FIXTURES[persona])] as const);

/** What an investor reads of a Decision: labels, text values, checks, counterfactuals, statements, trace. */
function frenchTexts(decision: Decision): string[] {
  return [
    decision.disclaimer_fr ?? "",
    ...decision.facts.flatMap((fact) => [fact.label_fr, ...(typeof fact.value === "string" ? [fact.value] : [])]),
    ...decision.constraints.flatMap((check) => [check.description_fr, check.derived_from ?? ""]),
    ...decision.counterfactuals.map((item) => item.change_fr),
    ...Object.values(decision.explanation).flatMap((statements) => statements.map((statement) => statement.text_fr)),
    ...decision.trace.flatMap((event) => (event.output_summary ? [event.output_summary] : [])),
  ];
}

const RAW = /(?<![\p{L}\p{N}_.])(offensive|defensive|technology|energy|refuse|timeline|low_composure)(?![\p{L}\p{N}_])/u;

describe("engine texts of the persona fixtures (issue #78)", () => {
  it("translate the engine's codes instead of writing them", () => {
    for (const [persona, response] of fixtures) {
      const raw = frenchTexts(response.decision).filter((text) => RAW.test(text));
      expect(raw, persona).toEqual([]);
    }
  });

  it("write a percentage with a non-breaking space, as the rest of the page", () => {
    for (const [persona, response] of fixtures) {
      expect(frenchTexts(response.decision).filter((text) => /\d%/.test(text)), persona).toEqual([]);
    }
    const amira = indexFacts(fixtures.find(([persona]) => persona === "amira")![1].decision);
    expect(amira.get("strat.ineligible.AMZN")?.value).toContain("93\u00a0% > 80\u00a0%");
    expect(amira.get("strat.style")?.value).toBe("offensif");
  });

  it("name the lenses and the Judge's verdict in French", () => {
    const robert = fixtures.find(([persona]) => persona === "robert")![1].decision;
    expect(robert.explanation.limits.map((statement) => statement.text_fr)).toContain("Objection maintenue par la lentille « diversité et préférences » au second tour.");
    const request = robert.trace.find((event) => event.agent === "judge" && event.trace_id.endsWith(":demande"));
    expect(request?.output_summary).toMatch(/^refusée ; \d+ violations? bloquantes?$/);
  });
});

function render(locale: Locale): string {
  const response = PortfolioBuildResponse.parse(PORTFOLIO_FIXTURES.robert);
  const lookup = { facts: indexFacts(response.decision), trace: indexTrace(response.decision), open: () => {} };
  const view = createElement(DecisionProvider, { value: lookup }, createElement(DecisionView, { response, fixture: true }));
  // The provider's props type requires `children`; they are passed as the third argument.
  const props = { initialLocale: locale } as Parameters<typeof I18nProvider>[0];
  return renderToStaticMarkup(createElement(I18nProvider, props, view));
}

describe("portfolio page language (issue #78)", () => {
  it("says in English that the engine's texts are in French only", () => {
    expect(portfolioEn.engineLanguage).toContain("French only");
    const html = render("en");
    expect(html).toContain(portfolioEn.engineLanguage);
    expect(html).toContain(`<b>${portfolioEn.constraints.requestCheck}</b>: refusée`);
  });

  it("does not repeat it in French, the engine's own language", () => {
    const html = render("fr");
    expect(html).not.toContain(portfolioFr.engineLanguage);
    expect(html).toContain(`<b>${portfolioFr.constraints.requestCheck}</b> : refusée`);
  });
});

describe("trace step count (issue #80, point 4)", () => {
  it("agrees the plural in both languages", () => {
    expect(portfolioFr.trace.count(1)).toBe("1 étape");
    expect(portfolioFr.trace.count(2)).toBe("2 étapes");
    expect(portfolioEn.trace.count(1)).toBe("1 step");
    expect(portfolioEn.trace.count(2)).toBe("2 steps");
    expect(portfolioEn.trace.count(0)).toBe("0 steps");
  });
});
