import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  DEMO_PERSONAS,
  EXPLANATION_SECTIONS,
  PortfolioBuildRequest,
  PortfolioBuildResponse,
  type DecisionFact,
} from "@/lib/contract/portfolio";
import { ErrorEnvelope } from "@/lib/contract/schemas";
import { portfolioEn, portfolioFr } from "@/lib/i18n/portfolio";
import { PORTFOLIO_FIXTURES } from "@/lib/mock/decisions";
import { indexFacts, rankingRows, requestFacts, rowFacts, styleBand } from "@/lib/portfolio/decision";
import { groundingLine } from "@/lib/portfolio/grounding";
import { formatCad, formatEngineValue, formatFact, formatLimit, formatWeight, normalizeNumber, pythonFixed } from "@/lib/portfolio/format";
import { portfolioSessionId } from "@/lib/server/aws";
import { handlePortfolio, validatePortfolioRequest } from "@/lib/server/gateway";
import { GatewayError } from "@/lib/server/errors";

const CLIENT = "8f0c3a8e-5d7b-4e2a-9f51-2c6d3b1a7e90";
const fixtures = Object.fromEntries(DEMO_PERSONAS.map((persona) => [persona, PortfolioBuildResponse.parse(PORTFOLIO_FIXTURES[persona])])) as Record<
  (typeof DEMO_PERSONAS)[number],
  PortfolioBuildResponse
>;
const raw = (persona: (typeof DEMO_PERSONAS)[number]) => structuredClone(PORTFOLIO_FIXTURES[persona]) as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

describe("portfolio contract (CONTRACTS.md 12)", () => {
  it("parses the engine's fixtures of the three FICTION profiles", () => {
    for (const persona of DEMO_PERSONAS) {
      const response = fixtures[persona];
      expect(response.simulation_only).toBe(true);
      expect(response.decision.simulation_only).toBe(true);
      expect(response.decision.facts.length).toBeGreaterThan(0);
      expect(response.strategy?.version).toBeTruthy();
      for (const section of EXPLANATION_SECTIONS) expect(response.decision.explanation[section].length).toBeGreaterThan(0);
    }
    expect(fixtures.amira.decision.kind).toBe("proposition");
    expect(fixtures.mateo.decision.kind).toBe("proposition");
    // Robert's TSLA request exceeds his limits: the Judge refuses it and frames it.
    expect(fixtures.robert.decision.kind).toBe("refus_encadre");
    expect(new Set(fixtures.amira.decision.positions.map((position) => position.role))).toEqual(new Set(["coeur", "satellite"]));
  });

  it("refuses a decision that drifts from decision.py", () => {
    const unknownFact = raw("amira");
    unknownFact.decision.explanation.why[0].fact_ids.push("nope.fact");
    expect(PortfolioBuildResponse.safeParse(unknownFact).success).toBe(false);

    const orphan = raw("amira");
    orphan.decision.facts[0].trace_id = "missing-trace";
    expect(PortfolioBuildResponse.safeParse(orphan).success).toBe(false);

    const weights = raw("mateo");
    weights.decision.positions[0].weight = weights.decision.positions[0].weight / 2;
    expect(PortfolioBuildResponse.safeParse(weights).success).toBe(false);

    const kind = raw("amira");
    kind.decision.kind = "conseil";
    expect(PortfolioBuildResponse.safeParse(kind).success).toBe(false);

    const label = raw("amira");
    label.decision.facts[0].status = "PEUT-ETRE";
    expect(PortfolioBuildResponse.safeParse(label).success).toBe(false);

    const style = raw("amira");
    style.strategy.style = "agressif";
    expect(PortfolioBuildResponse.safeParse(style).success).toBe(false);
  });

  it("tolerates new optional fields, as the contract allows", () => {
    const extra = raw("robert");
    extra.new_top_level = { any: 1 };
    extra.decision.facts[0].new_field = "ok";
    const parsed = PortfolioBuildResponse.parse(extra);
    expect("new_top_level" in parsed).toBe(false);
    expect(parsed.decision.kind).toBe("refus_encadre");
  });

  it("parses a persona build of the deployed runtime, with its audit link and X-Ray trace", () => {
    const body = raw("amira");
    Object.assign(body, {
      client_id: "demo-amira",
      persona: "amira",
      persona_label: "Amira (FICTION)",
      fiction: true,
      xray_trace_id: "1-4a83a163-8b8d316f426177014f865e8b",
      audit: {
        seq: 0,
        record_hash: "4ba45eb548e66e8de880511c4e5de1b7ece6aa076ab8d1e1d9d39b825021282b",
        prev_hash: "0".repeat(64),
        s3_key: "decisions/demo-amira/000000-dec-demo-amira-v1-4a22bd8d.json",
        otel_trace_id: "4a83a1638b8d316f426177014f865e8b",
        xray_trace_id: "1-4a83a163-8b8d316f426177014f865e8b",
      },
    });
    const response = PortfolioBuildResponse.parse(body);
    expect(response.client_id).toBe("demo-amira");
    expect(response.fiction).toBe(true);
    expect(response.audit && "seq" in response.audit ? response.audit.seq : null).toBe(0);
    expect(PortfolioBuildResponse.parse({ ...body, audit: { error: "ClientError" }, xray_trace_id: null }).audit).toEqual({ error: "ClientError" });
    expect(PortfolioBuildResponse.safeParse({ ...body, client_id: "demo-Amira" }).success).toBe(false);
    expect(PortfolioBuildResponse.safeParse({ ...body, xray_trace_id: "4a83a1638b8d316f426177014f865e8b" }).success).toBe(false);
  });

  it("validates the build request: a client or a persona, known styles and modes", () => {
    expect(PortfolioBuildRequest.parse({ persona: "robert", request: { ticker: "TSLA", amount_cad: 50_000 } })).toMatchObject({ action: "build", persona: "robert" });
    expect(PortfolioBuildRequest.parse({ client_id: CLIENT, mode: "rules", admin: true })).toEqual({ action: "build", client_id: CLIENT, mode: "rules" });
    expect(PortfolioBuildRequest.safeParse({}).success).toBe(false);
    expect(PortfolioBuildRequest.safeParse({ persona: "jules" }).success).toBe(false);
    expect(PortfolioBuildRequest.safeParse({ persona: "amira", style_preference: "agressif" }).success).toBe(false);
    expect(PortfolioBuildRequest.safeParse({ persona: "amira", mode: "turbo" }).success).toBe(false);
    expect(PortfolioBuildRequest.safeParse({ persona: "amira", request: { ticker: "TSLA; rm -rf" } }).success).toBe(false);
    expect(PortfolioBuildRequest.safeParse({ persona: "amira", as_of: "30/09/2026" }).success).toBe(false);
  });
});

describe("engine number formats", () => {
  it("rounds half to even like Python's format", () => {
    expect(pythonFixed(2.25, 1)).toBe("2.2");
    expect(pythonFixed(2.35, 1)).toBe("2.4"); // 2.35 is not a tie in binary (2.35000000000000008882)
    expect(pythonFixed(2.5, 0)).toBe("2");
    expect(pythonFixed(3.5, 0)).toBe("4");
    expect(pythonFixed(-2.5, 0)).toBe("-2");
    expect(pythonFixed(-0.00001, 1)).toBe("-0.0");
  });

  it("formats fractions, dollars, durations and text as facts.fmt", () => {
    expect(formatEngineValue(0.0225, "%")).toBe("2,2 %");
    expect(formatEngineValue(0.0625, "%")).toBe("6,2 %");
    expect(formatEngineValue(0.0475, "%")).toBe("4,8 %");
    expect(formatEngineValue(0.123, "%")).toBe("12,3 %");
    expect(formatEngineValue(-0.172625, "%")).toBe("-17,3 %");
    expect(formatEngineValue(3000, "CAD")).toBe("3 000 $");
    expect(formatEngineValue(17256405779.189888, "CAD")).toBe("17 256 405 779 $");
    expect(formatEngineValue(824.2849084868053, "CAD")).toBe("824 $");
    expect(formatEngineValue(-1234567, "CAD")).toBe("-1 234 567 $");
    expect(formatEngineValue(5, "mois")).toBe("5,0 mois");
    expect(formatEngineValue(7, "années")).toBe("7,0 années");
    expect(formatEngineValue(2.264838, "ratio")).toBe("2,265");
    expect(formatEngineValue(20, "titres")).toBe("20");
    expect(formatEngineValue("N4", "niveau")).toBe("N4");
    expect(formatEngineValue(null, "%")).toBe("n.d.");
    expect(formatWeight(0.48)).toBe("48,0 %");
    expect(formatCad(50_000)).toBe("50 000 $");
  });

  it("shows the Judge's fractions as percentages", () => {
    expect(formatFact({ value: 0.814916, unit: "part du portefeuille" })).toBe("81,5 %");
    expect(formatFact({ value: 1, unit: "poids" })).toBe("100,0 %");
    expect(formatFact({ value: 2.264838, unit: "ratio" })).toBe("2,265");
    expect(formatLimit(0.12, "volatilité annualisée")).toBe("12,0 %");
    expect(formatLimit(null, "%")).toBe("—");
  });

  /** Port of `explain._NUM` and `explain.verify`: every number of a statement is a cited fact's value. */
  const NUMBER = /(?<![A-Za-z_.])-?\d[\d\s]*(?:[.,]\d+)?(?![A-Za-z_])/g;
  const numbers = (text: string) => new Set([...text.matchAll(NUMBER)].map((match) => normalizeNumber(match[0])).filter((value) => /\d/.test(value)));
  const ALWAYS_ALLOWED = new Set(["1", "2", "3", "4", "12", "95", "2022"]);

  it("matches the engine: each number written in a statement is the formatted value of a fact it cites", () => {
    let checked = 0;
    for (const persona of DEMO_PERSONAS) {
      const decision = fixtures[persona].decision;
      const facts = indexFacts(decision);
      for (const section of EXPLANATION_SECTIONS) {
        // Statements without facts are fixed texts of the engine (e.g. « 2018-2026 »), never verified numbers.
        for (const statement of decision.explanation[section].filter((item) => item.fact_ids.length > 0)) {
          const allowed = new Set<string>();
          for (const id of statement.fact_ids) {
            const fact = facts.get(id) as DecisionFact;
            numbers(formatEngineValue(fact.value, fact.unit)).forEach((value) => allowed.add(value));
          }
          const extra = [...numbers(statement.text_fr)].filter((value) => !allowed.has(value) && !ALWAYS_ALLOWED.has(value));
          expect({ persona, text: statement.text_fr, extra }).toEqual({ persona, text: statement.text_fr, extra: [] });
          checked += numbers(statement.text_fr).size;
        }
      }
    }
    expect(checked).toBeGreaterThan(20);
  });
});

describe("decision selectors", () => {
  it("rank single stocks by the engine's rank, with tickers that contain dots", () => {
    const rows = rankingRows(indexFacts(fixtures.amira.decision), fixtures.amira.strategy);
    expect(rows.length).toBeGreaterThan(5);
    const ranks = rows.map((row) => row.rank?.value);
    expect(ranks).toEqual([...ranks].sort((a, b) => Number(a) - Number(b)));
    const kept = rows.filter((row) => row.shortlisted).map((row) => row.ticker);
    expect(new Set(kept)).toEqual(new Set(fixtures.amira.strategy?.shortlist));
    const enb = rows.find((row) => row.ticker === "ENB.TO");
    expect(enb?.features.vol?.fact_id).toBe("strat.feat.ENB.TO.vol");
    expect(enb?.features.liquidity_cad?.unit).toBe("CAD");
    expect(enb?.momentumRank?.fact_id).toBe("strat.sens.mom.rank.ENB.TO");
    expect(enb?.floor?.fact_id).toBe("strat.floor.ENB.TO");
    if (!enb) throw new Error("ENB.TO is ranked in Amira's decision");
    expect(rowFacts(enb).every((fact) => fact.fact_id.includes("ENB.TO"))).toBe(true);
    const setAside = rows.filter((row) => row.ineligible);
    expect(setAside.length).toBeGreaterThan(0);
    expect(setAside.every((row) => typeof row.ineligible?.value === "string")).toBe(true);
  });

  it("finds the equity band of step 0", () => {
    const amira = styleBand(indexFacts(fixtures.amira.decision));
    expect(amira.eMin?.unit).toBe("%");
    expect(amira.eCap?.unit).toBe("%");
    expect(amira.target?.fact_id).toBe("strat.band_target");
    // Mateo's step 0 sets no equity target (growth_floor null): the view says so instead of drawing one.
    expect(fixtures.mateo.strategy?.growth_floor).toBeNull();
    expect(styleBand(indexFacts(fixtures.mateo.decision)).target).toBeUndefined();
  });

  it("finds Robert's request and the Judge's check of it", () => {
    const decision = fixtures.robert.decision;
    const request = requestFacts(decision, indexFacts(decision));
    expect(request.weight?.fact_id).toBe("request.weight");
    expect(request.checks.some((event) => event.status === "refus")).toBe(true);
  });
});

describe("portfolio gateway", () => {
  const previous = process.env.AGENT_MODE;
  beforeEach(() => {
    process.env.AGENT_MODE = "mock";
  });
  afterEach(() => {
    process.env.AGENT_MODE = previous;
  });

  const post = (body: unknown, headers: Record<string, string> = {}) =>
    handlePortfolio(new Request("http://localhost/api/portfolio", { method: "POST", body: JSON.stringify(body), headers: { "content-type": "application/json", ...headers } }));

  it("serves the engine's fixture of a persona in mock mode", async () => {
    for (const persona of DEMO_PERSONAS) {
      const response = await post({ action: "build", persona });
      expect(response.status).toBe(200);
      const body = PortfolioBuildResponse.parse(await response.json());
      expect(body.persona).toBe(persona);
      expect(body.decision.decision_id).toBe(fixtures[persona].decision.decision_id);
    }
  });

  it("answers contract errors with HTTP statuses", async () => {
    const own = await post({ client_id: CLIENT }, { "x-alphaforge-locale": "en" });
    expect(own.status).toBe(404);
    expect(ErrorEnvelope.parse(await own.json()).error.code).toBe("not_found");
    const empty = await post({});
    expect(empty.status).toBe(400);
    expect(ErrorEnvelope.parse(await empty.json()).error.code).toBe("bad_request");
    const action = await post({ action: "delete", persona: "amira" });
    expect(action.status).toBe(400);
    expect(ErrorEnvelope.parse(await action.json()).error.code).toBe("unknown_action");
    const big = await handlePortfolio(
      new Request("http://localhost/api/portfolio", { method: "POST", body: "{}", headers: { "content-type": "application/json", "content-length": String(64 * 1024) } }),
    );
    expect(big.status).toBe(413);
  });

  it("strips fields outside the contract before the call", () => {
    expect(validatePortfolioRequest({ persona: "mateo", stream: true, admin: 1 })).toEqual({ action: "build", persona: "mateo" });
    expect(() => validatePortfolioRequest([])).toThrow(GatewayError);
  });

  it("names the AgentCore session after the client, or a stable one per persona", () => {
    expect(portfolioSessionId({ action: "build", client_id: CLIENT })).toBe(CLIENT);
    const session = portfolioSessionId({ action: "build", persona: "amira" });
    expect(session.length).toBeGreaterThanOrEqual(33);
    expect(session).toContain("amira");
    expect(portfolioSessionId({ action: "build", persona: "amira" })).toBe(session);
  });
});

describe("portfolio strings", () => {
  type Tree = { [key: string]: unknown };
  const shape = (value: unknown, path = ""): string[] => {
    if (Array.isArray(value)) return [`${path}[${value.length}]`, ...value.flatMap((item, index) => shape(item, `${path}[${index}]`))];
    if (typeof value === "function") return [`${path}()`];
    if (value && typeof value === "object") return Object.keys(value as Tree).sort().flatMap((key) => shape((value as Tree)[key], `${path}.${key}`));
    return [`${path}:${typeof value}`];
  };

  it("have the same structure in French and English, and the four questions of the workshop", () => {
    expect(shape(portfolioEn)).toEqual(shape(portfolioFr));
    expect(Object.values(portfolioFr.explanation.sections)).toEqual([
      "Quelles données ?",
      "Pourquoi ce choix ?",
      "Quelles limites ?",
      "Qu’est-ce qui changerait la réponse ?",
    ]);
    expect(portfolioFr.banner).toBe("Simulation éducative — aucun conseil, aucune transaction");
    expect(portfolioFr.style.badge(portfolioFr.style.styles.offensive)).toBe("Style offensif");
  });
});

describe("grounding line (Bedrock Guardrails, per statement)", () => {
  const perStatement = {
    action: "NONE",
    method: "per_statement",
    checked: 19,
    below: 0,
    errors: 0,
    retries: 0,
    min_score: 0.79,
    threshold: 0.75,
    sources: ["general/methodologie/scoring-par-style.md"],
    statements: [{ section: "why", index: 0, action: "NONE", score: 0.79, threshold: 0.75, relevance: 0.97, scope: "section", retries: 0 }],
  };

  it("parses the engine's per-statement result and the older single-call shape", () => {
    expect(PortfolioBuildResponse.shape.grounding.parse(perStatement)?.statements?.[0]?.scope).toBe("section");
    expect(PortfolioBuildResponse.shape.grounding.parse({ action: "GUARDRAIL_INTERVENED", assessments: [] })?.method).toBeUndefined();
  });

  it("says how many statements are grounded, with the engine's own scores", () => {
    expect(groundingLine(perStatement, portfolioFr.grounding, "fr")).toBe(
      "19 énoncés ancrés dans les faits cités, la décision et les fiches de méthode (score minimal 0,79, seuil 0,75)",
    );
    expect(groundingLine(perStatement, portfolioEn.grounding, "en")).toContain("lowest score 0.79, threshold 0.75");
  });

  it("names statements below the threshold and checks that could not run", () => {
    const below = { ...perStatement, action: "GUARDRAIL_INTERVENED", below: 2, errors: 1 };
    expect(groundingLine(below, portfolioFr.grounding, "fr")).toBe(
      "2 énoncés sur 19 sous le seuil d’ancrage (0,75) : voir le rapport de vérification · 1 vérification impossible",
    );
    expect(groundingLine({ ...perStatement, action: "ERROR", checked: 0 }, portfolioFr.grounding, "fr")).toBe(portfolioFr.grounding.failed);
  });

  it("keeps the raw outcome for an older response, and nothing without a check", () => {
    expect(groundingLine({ action: "GUARDRAIL_INTERVENED" }, portfolioFr.grounding, "fr")).toBe("Résultat : GUARDRAIL_INTERVENED");
    expect(groundingLine({ action: null }, portfolioFr.grounding, "fr")).toBeNull();
  });
});
