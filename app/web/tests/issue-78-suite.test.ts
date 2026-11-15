/**
 * Issue #78, after the end-to-end check in LLM mode: the outcome of Bedrock Guardrails is named in both
 * languages, a lens's evidence missing from the decision stays an audit detail, and counters agree in number
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

describe("Bedrock Guardrails outcome", () => {
  it("names the action in French and in English, the raw action in the tooltip", () => {
    const response = { ...robert(), grounding: { action: "GUARDRAIL_INTERVENED" } };
    const fr = render("fr", response, decisionView);
    expect(fr).toContain("Ancrage vérifié par Bedrock Guardrails · Résultat : le garde-fou est intervenu");
    expect(fr).toContain('title="GUARDRAIL_INTERVENED"');
    expect(fr).not.toContain("Résultat : GUARDRAIL_INTERVENED");
    expect(render("en", response, decisionView)).toContain("Grounding checked by Bedrock Guardrails · Outcome: the guardrail intervened");
    expect(render("fr", { ...robert(), grounding: { action: "NONE" } }, decisionView)).toContain("Résultat : aucune intervention");
  });

  it("shows an action it does not know as is", () => {
    expect(render("fr", { ...robert(), grounding: { action: "NEW_ACTION" } }, decisionView)).toContain("Résultat : NEW_ACTION");
  });
});

describe("evidence of a lens missing from the decision", () => {
  it("says it in words and keeps the identifier small, for the audit", () => {
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
    expect(html).toContain(`title="${portfolioFr.debate.missingEvidence}">risk.cdar_m</p>`);
    expect(html).not.toContain(`>risk.cdar_m ; ${known}<`); // a fact of the decision stays a chip, not an audit id
    expect(html).not.toContain("[&#x27;risk.cdar_m&#x27;]");
  });
});

describe("counters agree in number", () => {
  it("take the singular for 0 and 1 in French", () => {
    expect(portfolioFr.constraints.summary(0, 0, 0)).toBe("0 contrôle · 0 saturé · 0 violé");
    expect(portfolioFr.constraints.summary(1, 1, 1)).toBe("1 contrôle · 1 saturé · 1 violé");
    expect(portfolioFr.constraints.summary(28, 6, 2)).toBe("28 contrôles · 6 saturés · 2 violés");
    expect(portfolioFr.positions.count(0)).toBe("0 position");
    expect(portfolioFr.trace.facts(2)).toBe("2 faits");
  });

  it("take the singular for 1 only in English", () => {
    expect(portfolioEn.positions.count(0)).toBe("0 positions");
    expect(portfolioEn.positions.count(1)).toBe("1 position");
    expect(portfolioEn.positions.count(5)).toBe("5 positions");
    expect(portfolioEn.trace.facts(0)).toBe("0 facts");
    expect(portfolioEn.explanation.more(1)).toBe("+ 1 fact");
    expect(portfolioEn.constraints.summary(1, 0, 0)).toBe("1 check · 0 binding · 0 violated");
    expect(portfolioEn.constraints.summary(0, 0, 0)).toBe("0 checks · 0 binding · 0 violated");
  });
});

describe("header of a decision without an allocation (#76 causes)", () => {
  /** Robert's decision turned into a protection whose facts record the given causes. */
  function protection(causes: string[]): PortfolioBuildResponse {
    const response = robert();
    const model = response.decision.facts[0]!;
    const facts = [...response.decision.facts, ...causes.map((fact_id) => ({ ...model, fact_id }))];
    return { ...response, decision: { ...response.decision, kind: "protection", positions: [], facts } };
  }
  const header = (locale: Locale, response: PortfolioBuildResponse) => render(locale, response, decisionView);

  it("is true for a protection by the dollar rule (acceptable loss, horizon, withdrawals)", () => {
    const fr = header("fr", protection(["protection.l_star", "protection.min_L_plan"]));
    expect(fr).toContain(portfolioFr.kindText.protection);
    expect(fr).toContain("Aucune allocation ne respecte les limites de votre profil");
    expect(fr).not.toContain("signaux de vulnérabilité");
    expect(header("en", protection(["protection.l_star"]))).toContain("No allocation fits the limits of your profile");
  });

  it("names the vulnerability signals only when they are the cause", () => {
    expect(header("fr", protection(["protection.profile_status"]))).toContain(portfolioFr.protectionSignals);
    expect(header("en", protection(["protection.profile_status"]))).toContain(portfolioEn.protectionSignals);
    const both = header("fr", protection(["protection.profile_status", "protection.l_star"]));
    expect(both).toContain(portfolioFr.kindText.protection);
    expect(both).not.toContain(portfolioFr.protectionSignals);
  });

  it("keeps distinct texts for an incomplete profile and a protection", () => {
    expect(portfolioFr.kindText.incomplet).not.toBe(portfolioFr.kindText.protection);
    expect(portfolioEn.kindText.incomplet).not.toBe(portfolioEn.kindText.protection);
    const response = robert();
    const incomplete = { ...response, decision: { ...response.decision, kind: "incomplet" as const, positions: [] } };
    expect(header("fr", incomplete)).toContain(portfolioFr.kindText.incomplet);
  });
});
