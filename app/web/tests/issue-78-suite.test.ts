/**
 * Issue #78, after the end-to-end check in LLM mode: the outcome of Bedrock Guardrails is readable in both
 * languages (line of #94), a lens's evidence missing from the decision stays an audit detail, and counters agree in number
 * (French: 0 and 1 take the singular; English: only 1 does).
 */
import { createElement, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DecisionView } from "@/components/portfolio/decision-view";
import { DecisionProvider } from "@/components/portfolio/facts";
import { Debate } from "@/components/portfolio/judge-panels";
import { PortfolioBuildResponse } from "@/lib/contract/portfolio";
import type { Locale } from "@/lib/contract/schemas";
import { portfolioEn, portfolioFr } from "@/lib/i18n/portfolio";
import { I18nProvider } from "@/lib/i18n/provider";
import { PORTFOLIO_FIXTURES } from "@/lib/mock/decisions";
import { indexFacts, indexTrace } from "@/lib/portfolio/decision";

const robert = () => PortfolioBuildResponse.parse(PORTFOLIO_FIXTURES.robert);

function render(locale: Locale, response: PortfolioBuildResponse, view: (response: PortfolioBuildResponse) => ReactElement): string {
  const lookup = { facts: indexFacts(response.decision), trace: indexTrace(response.decision), open: () => {} };
  // The provider's props type requires `children`; they are passed as the third argument.
  const props = { initialLocale: locale } as Parameters<typeof I18nProvider>[0];
  return renderToStaticMarkup(createElement(I18nProvider, props, createElement(DecisionProvider, { value: lookup }, view(response))));
}

const decisionView = (response: PortfolioBuildResponse) => createElement(DecisionView, { response, fixture: true });

describe("fact check outcome (Bedrock Guardrails)", () => {
  it("shows the readable line of the per-statement check (#94), in French and in English", () => {
    const grounding = { action: "GUARDRAIL_INTERVENED", method: "per_statement", checked: 19, below: 2, errors: 0, threshold: 0.75, min_score: 0.6 };
    const response = { ...robert(), grounding } as PortfolioBuildResponse;
    expect(render("fr", response, decisionView)).toContain("Vérification des faits · 2 énoncés sur 19 s’appuient peu sur les faits cités");
    expect(render("en", response, decisionView)).toContain("Fact check · 2 of 19 statements rest little on the cited facts");
    for (const raw of ["GUARDRAIL_INTERVENED", "Bedrock", "Guardrails", "0,75", "0.75"]) expect(render("fr", response, decisionView)).not.toContain(raw);
  });
});

describe("evidence of a lens missing from the decision", () => {
  it("says it in words, without the identifier (LANGAGE.md)", () => {
    const response = robert();
    const known = response.decision.facts[0]!.fact_id;
    const rejected = {
      lens: "risk",
      status: "rejete" as const,
      why_fr: "preuve inconnue : le fait cité est introuvable dans la décision",
      amendment: { kind: "tighten_limit", target: "risk.cdar_m", value: 0.01, reason_fr: "test", evidence_fact_ids: ["risk.cdar_m", known] },
    };
    const withRound = { ...response, rounds: [{ round: 1 as const, verdicts: {}, amendments: [rejected] }, ...response.rounds.slice(1)] };
    const html = render("fr", withRound, (r) => createElement(Debate, { response: r }));
    expect(html).toContain("preuve inconnue : le fait cité est introuvable dans la décision");
    expect(html).not.toContain("risk.cdar_m");
    expect(html).not.toContain(`>${known}<`); // a fact of the decision stays a chip, not an id
    expect(html).not.toContain("[&#x27;risk.cdar_m&#x27;]");
  });
});

describe("counters agree in number", () => {
  it("take the singular for 0 and 1 in French", () => {
    expect(portfolioFr.constraints.summary(0, 0, 0)).toBe("0 vérification · 0 limite atteinte · 0 limite violée");
    expect(portfolioFr.constraints.summary(1, 1, 1)).toBe("1 vérification · 1 limite atteinte · 1 limite violée");
    expect(portfolioFr.constraints.summary(28, 6, 2)).toBe("28 vérifications · 6 limites atteintes · 2 limites violées");
    expect(portfolioFr.positions.count(0)).toBe("0 position");
    expect(portfolioFr.trace.facts(2)).toBe("2 faits");
  });

  it("take the singular for 1 only in English", () => {
    expect(portfolioEn.positions.count(0)).toBe("0 positions");
    expect(portfolioEn.positions.count(1)).toBe("1 position");
    expect(portfolioEn.positions.count(5)).toBe("5 positions");
    expect(portfolioEn.trace.facts(0)).toBe("0 facts");
    expect(portfolioEn.explanation.more(1)).toBe("+ 1 fact");
    expect(portfolioEn.constraints.summary(1, 0, 0)).toBe("1 check · 0 limits reached · 0 limits violated");
    expect(portfolioEn.constraints.summary(0, 1, 1)).toBe("0 checks · 1 limit reached · 1 limit violated");
  });
});

describe("header of an incomplete profile and of a protection", () => {
  const header = (locale: Locale, response: PortfolioBuildResponse) => render(locale, response, decisionView);

  it("keeps distinct texts for an incomplete profile and a protection", () => {
    expect(portfolioFr.kindText.incomplet).not.toBe(portfolioFr.kindText.protection);
    expect(portfolioEn.kindText.incomplet).not.toBe(portfolioEn.kindText.protection);
    const response = robert();
    const incomplete = { ...response, decision: { ...response.decision, kind: "incomplet" as const, positions: [] } };
    expect(header("fr", incomplete)).toContain(portfolioFr.kindText.incomplet);
  });
});
