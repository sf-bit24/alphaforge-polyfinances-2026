/**
 * Issue #78 (and #80, point 4): the engine's French texts translate its codes, the page says in English
 * that they stay in French, the Judge's provenance column names its identifiers, and the trace counts its
 * steps with the right plural.
 */
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DecisionView } from "@/components/portfolio/decision-view";
import { DecisionProvider } from "@/components/portfolio/facts";
import { Constraints } from "@/components/portfolio/judge-panels";
import { DEMO_PERSONAS, PortfolioBuildResponse, type Decision } from "@/lib/contract/portfolio";
import type { Locale } from "@/lib/contract/schemas";
import { portfolioEn, portfolioFr } from "@/lib/i18n/portfolio";
import { I18nProvider } from "@/lib/i18n/provider";
import { PORTFOLIO_FIXTURES } from "@/lib/mock/decisions";
import { derivedFromLabel, indexFacts, indexTrace } from "@/lib/portfolio/decision";
import { engineText } from "@/lib/portfolio/wording";

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

/* ------------------------------------------------------------------ */
/* Provenance of the Judge's checks (« Dérivée de »)                   */
/* ------------------------------------------------------------------ */

const RISK_LEVELS = new URL("../../agents/src/alphaforge/finance/policy/risk_levels.yaml", import.meta.url);
/** Provenances the engine writes outside the template: compiler.py (_derived_from, employer and sandbox caps), judge.py, pipeline.py. */
const ENGINE_PROVENANCES = [
  "profile.biases[aversion_perte]",
  "profile.composure<40",
  "profile.biases[familiarite] ; profile.employer_equity",
  "profile.requests ; profile.biases[FOMO]",
  "définition d'un portefeuille",
  "policy.universe/excluded",
  "simulation long-only",
  "demande précise de l'investisseur",
];
/** An identifier of the engine: dotted path, `->`, `[…]` or a comparison, as opposed to a sentence. */
const IDENTIFIER = /^[a-z_]+$|->|[a-z_]\.[a-z_]|\[|</;
const parts = (raw: string) => raw.split(";").map((part) => part.trim());

/** `derived_from` of each entry of `limits_template` (read by pattern: PyYAML accepts « 0.025,# … », the `yaml` package does not). */
function templateProvenances(): string[] {
  const text = readFileSync(RISK_LEVELS, "utf8");
  const entries = [...text.matchAll(/\{rule_id:\s*([\w.]+)[\s\S]*?derived_from:\s*"([^"]*)"/g)].map((match) => ({ rule: match[1], from: match[2] ?? "" }));
  expect(entries.map((entry) => entry.rule)).toContain("risk.stress_2022");
  // risk.cdar_m: the compiler replaces « … | composure<40 » by one of the two (ENGINE_PROVENANCES).
  return entries.filter((entry) => entry.rule !== "risk.cdar_m").map((entry) => entry.from);
}

function renderChecks(locale: Locale): string {
  const response = PortfolioBuildResponse.parse(PORTFOLIO_FIXTURES.robert);
  const lookup = { facts: indexFacts(response.decision), trace: indexTrace(response.decision), open: () => {} };
  // Every row shown: the table folds to the binding or violated checks.
  const checks = response.decision.constraints.map((check) => ({ ...check, active: true }));
  const view = createElement(DecisionProvider, { value: lookup }, createElement(Constraints, { checks }));
  const props = { initialLocale: locale } as Parameters<typeof I18nProvider>[0];
  return renderToStaticMarkup(createElement(I18nProvider, props, view));
}

describe("provenance of the Judge's checks (issue #78, review)", () => {
  it("names every identifier the engine writes, in French and in English", () => {
    const provenances = [
      ...templateProvenances(),
      ...ENGINE_PROVENANCES,
      ...fixtures.flatMap(([, response]) => response.decision.constraints.map((check) => check.derived_from)),
    ];
    const identifiers = new Set(provenances.flatMap(parts).filter((part) => IDENTIFIER.test(part)));
    expect(identifiers.size).toBeGreaterThan(10);
    for (const labels of [portfolioFr.constraints.derivedFrom, portfolioEn.constraints.derivedFrom]) {
      expect([...identifiers].filter((part) => !Object.hasOwn(labels, part))).toEqual([]);
      for (const raw of provenances) expect(parts(derivedFromLabel(raw, labels).replaceAll(", ", ";")).filter((part) => IDENTIFIER.test(part)), raw).toEqual([]);
    }
  });

  it("joins the named parts and keeps a sentence of the engine as it is", () => {
    const fr = portfolioFr.constraints.derivedFrom;
    expect(derivedFromLabel("level ; dollar_rule.l_star ; profile.knowledge", fr)).toBe("niveau de risque, règle des dollars (perte admissible), connaissances de l’investisseur");
    expect(derivedFromLabel("profile.composure<40", portfolioEn.constraints.derivedFrom)).toBe("composure below 40");
    expect(derivedFromLabel("étape 0 : style défensif (τ = -0,25)", fr)).toBe("étape 0 : style défensif (τ = -0,25)");
    expect(derivedFromLabel("constructor", fr)).toBe("constructor");
  });

  it("shows the name in the table, in the client's words, never the raw identifier (LANGAGE.md)", () => {
    const fr = renderChecks("fr");
    expect(fr).toContain("<td>sang-froid sous 40</td>");
    expect(fr).toContain("<td>score de risque R du profil, puis niveau, règle des dollars (part actions maximale)</td>");
    expect(fr).toContain("<td>style du portefeuille : style défensif</td>");
    expect(fr).toContain("<td>définition d’un portefeuille</td>");
    const en = renderChecks("en");
    expect(en).toContain("<td>composure below 40</td>");
    expect(en).toContain("<td>risk level</td>");
    expect(en).toContain("<td>definition of a portfolio</td>");
    for (const html of [fr, en]) {
      for (const raw of ["profile.composure", "dollar_rule", "profile-&gt;R", ">level<", "étape 0", "τ", "strat.floor", "conc.single_each", "somme_poids"]) {
        expect(html, raw).not.toContain(raw);
      }
    }
  });

  it("rewords the engine's internal names, never a number", () => {
    expect(engineText("style de composition retenu (étape 0)")).toBe("style du portefeuille retenu");
    expect(engineText("risque minimisé du mandat sans l'étape 0")).toBe("risque minimisé sans le style du portefeuille");
    expect(engineText("étape 0 appliquée au mandat")).toBe("style du portefeuille appliqué au mandat");
    expect(engineText("étape 0 : secteur d'un titre retenu : plafond affiché (Brain D7)")).toBe("style du portefeuille : secteur d'un titre retenu : plafond affiché");
    expect(engineText("plafond d'exposition au secteur de l'énergie (look-through)")).toBe("plafond d'exposition au secteur de l'énergie (en tenant compte du contenu des FNB)");
    expect(engineText("baisse maximale longue 93 % > 80 % (δ des titres individuels)")).toBe("baisse maximale longue 93 % > 80 % (limite des titres individuels)");
    expect(engineText("Objection maintenue par la lentille « diversité et préférences » au second tour.")).toBe(
      "Objection maintenue par le point de vue « diversité et préférences » au second tour.",
    );
    expect(engineText("Sans le style ni la sélection (mandat de base, avant les lentilles), le risque minimisé serait de 3,1 %.")).toBe(
      "Sans le style ni la sélection (mandat de base, avant les quatre points de vue), le risque minimisé serait de 3,1 %.",
    );
    expect(engineText("Poids de la lentille risque")).toBe("Poids du point de vue risque");
    expect(engineText("allocation optimale du mandat (F2)")).toBe("allocation optimale du mandat");
    expect(engineText("0,513")).toBe("0,513");
  });
});
