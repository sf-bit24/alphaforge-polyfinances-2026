/**
 * The finance engine's own texts as the client reads them (app/web/LANGAGE.md). The engine writes its labels,
 * provenances and sentences for the audit, with internal names (« étape 0 », « lentille », « look-through », a
 * Brain reference, a Greek parameter) and source keys (`strategy.yaml@0.1.0#floors`, `judge:F4`). The recorded
 * decisions of the simulator freeze those texts, so the screen rewords them here, with a few targeted
 * replacements. A number is never touched: only the words around it change.
 */
import type { DecisionTraceEvent } from "@/lib/contract/portfolio";
import type { PortfolioStrings } from "@/lib/i18n/portfolio";

const APOS = "['’]";

/** Ordered: the longer phrases first, so that « sans l'étape 0 » is not split by the generic rule. */
const REWORDINGS: ReadonlyArray<readonly [RegExp, string]> = [
  // Step 0 of the engine: the style of the portfolio (LANGAGE.md, « l'étape 0, le style »).
  [/\s*\(étape 0\)/g, ""],
  [new RegExp(` du mandat sans l${APOS}étape 0`, "g"), " sans le style du portefeuille"],
  [new RegExp(`sans l${APOS}étape 0`, "g"), "sans le style du portefeuille"],
  [new RegExp(`de l${APOS}étape 0`, "g"), "du style du portefeuille"],
  [new RegExp(`par l${APOS}étape 0`, "g"), "par le style du portefeuille"],
  [new RegExp(`l${APOS}étape 0`, "g"), "le style du portefeuille"],
  [/Étape 0 appliquée/g, "Style du portefeuille appliqué"],
  [/étape 0 appliquée/g, "style du portefeuille appliqué"],
  [/Étape 0 abandonnée/g, "Style du portefeuille abandonné"],
  [/étape 0 abandonnée/g, "style du portefeuille abandonné"],
  [/Étape 0/g, "Style du portefeuille"],
  [/étape 0/g, "style du portefeuille"],
  [/Style de composition/g, "Style du portefeuille"],
  [/style de composition/g, "style du portefeuille"],
  // The lenses of the debate: the four viewpoints.
  [/\bde la lentille\b/g, "du point de vue"],
  [/\bLa lentille\b/g, "Le point de vue"],
  [/\bla lentille\b/g, "le point de vue"],
  [/\b(les|des|aux) lentilles\b/g, "$1 quatre points de vue"],
  [/\blentilles\b/g, "points de vue"],
  [/\blentille\b/g, "point de vue"],
  // ETF contents counted through (« look-through »).
  [/\s*\(look-through\)/g, " (en tenant compte du contenu des FNB)"],
  [/\blook-through\b/g, "en tenant compte du contenu des FNB"],
  // References and parameters of the engine's design: a Brain sheet, a Greek letter, a formula number.
  [/\s*\(Brain [^)]*\)/g, ""],
  [/\(δ des titres individuels\)/g, "(limite des titres individuels)"],
  [/\s*\([τδπφ]\s*=\s*[^)]*\)/g, ""],
  [/\s*\(F\d\)/g, ""],
  [/\b(optimiseur) F\d\b/g, "$1"],
  [/, \d+ gabarits? remis/g, ""],
  // The labels as the screen spells them, and the risk measures as finance writes them.
  [/\bHYPOTHESE\b/g, "HYPOTHÈSE"],
  [/\bCVAR\b/g, "CVaR"],
  [/\bCDAR\b/g, "CDaR"],
];

/** A label, a provenance or a sentence of the engine, in the client's words. */
export function engineText(text: string): string {
  return REWORDINGS.reduce((out, [pattern, replacement]) => out.replace(pattern, replacement), text);
}

/** A part of a processing note that only an engineer reads: code, a formula, a configuration key, a proxy id. */
const TECHNICAL = /[{}=·φπτδ⌊⌋_#<>|]|\byaml\b|prix dual|\bF\d\b|\bCLARABEL\b|\bR\s*=|^[A-Z0-9.]+$|vecteur|→ (defensive|dynamique|offensive)\b/i;

/**
 * The processing note of a source (« rendements mensuels CAD 2018-10-31..2026-09-30 (96 mois) »), or `null`
 * when it is a formula or a key: the proxies' table is dropped, the date range reads « du … au … ».
 */
export function plainProcessing(text: string | null | undefined): string | null {
  if (!text) return null;
  const cleaned = engineText(text)
    .replace(/,?\s*proxys? \{[^}]*\}/g, "")
    .replace(/,?\s*proxy [A-Z_]+/g, "")
    .replace(/(\d{4}-\d{2}(?:-\d{2})?)\s*(?:\.\.|→|–)\s*(\d{4}-\d{2}(?:-\d{2})?)/g, "$1 – $2")
    .trim();
  if (!cleaned || TECHNICAL.test(cleaned)) return null;
  return cleaned;
}

export const SOURCE_KINDS = [
  "returns",
  "levels",
  "style",
  "viewpoints",
  "optimizer",
  "check",
  "counterfactual",
  "scenarios",
  "request",
  "holdings",
  "profile",
  "mandate",
  "news",
  "filing",
  "esg",
  "knowledge",
  "issuer",
  "replay",
  "other",
] as const;
export type SourceKind = (typeof SOURCE_KINDS)[number];

/** Ordered: the first pattern that matches the dataset key names the source. */
const SOURCE_PATTERNS: ReadonlyArray<readonly [RegExp, SourceKind]> = [
  [/^okf-news:/, "news"],
  [/^okf-filing:/, "filing"],
  [/^okf-esg:/, "esg"],
  [/^okf:/, "knowledge"],
  [/^emetteur:/, "issuer"],
  [/^client:portefeuille/, "holdings"],
  [/^contrefactuel/, "counterfactual"],
  [/^scenario/, "scenarios"],
  [/^evolution:/, "replay"],
  [/^interaction investisseur/, "request"],
  [/backtest|^pit:|monthly_returns/, "returns"],
  [/^optimi[sz]/, "optimizer"],
  [/^judge|judge\.py/, "check"],
  [/emphasis/, "viewpoints"],
  [/strategy/, "style"],
  [/risk_levels|^policy/, "levels"],
  [/^mandat/, "mandate"],
  [/^profil/, "profile"],
];

/** What kind of source a fact's dataset key is, for its title on screen (never the key itself). */
export function sourceKind(dataset: string): SourceKind {
  return SOURCE_PATTERNS.find(([pattern]) => pattern.test(dataset))?.[1] ?? "other";
}

export const STEP_KINDS = [
  "profile",
  "status",
  "esg",
  "style",
  "scoring",
  "selection",
  "feasibility",
  "styleFinal",
  "optimize",
  "viewpoint",
  "advocate",
  "merge",
  "check",
  "requestCheck",
  "framed",
  "request",
  "counterfactuals",
  "explanation",
  "scenarios",
  "factCheck",
  "other",
] as const;
export type StepKind = (typeof STEP_KINDS)[number];

const STEP_AGENTS: Readonly<Record<string, StepKind>> = {
  "s0.policy_compiler": "profile",
  "s0.status": "status",
  "s0c.esg_exclusions": "esg",
  "s0b.strategy": "style",
  "s0b.scoring": "scoring",
  "s0b.select": "selection",
  "s0b.feasibility": "feasibility",
  "s0b.final": "styleFinal",
  "s2.optimize": "optimize",
  a3: "advocate",
  "a3.advocate": "advocate",
  "s3.merge": "merge",
  request: "request",
  counterfactuals: "counterfactuals",
  explainer: "explanation",
  "explainer.scenarios": "scenarios",
  explainability: "factCheck",
};

/** What a step of the engine did, in the client's words; a lens step also names its viewpoint (`lens`). */
export function stepKind(event: Pick<DecisionTraceEvent, "agent" | "tool" | "trace_id">): { kind: StepKind; lens?: string } {
  const lens = /^lens\.(.+)$/.exec(event.agent)?.[1];
  if (lens) return { kind: "viewpoint", lens };
  if (event.agent === "judge") {
    if (event.tool === "framed_alternative") return { kind: "framed" };
    return { kind: event.trace_id.endsWith(":demande") ? "requestCheck" : "check" };
  }
  if (Object.hasOwn(STEP_AGENTS, event.agent)) return { kind: STEP_AGENTS[event.agent] ?? "other" };
  return { kind: event.tool === "scenario_risk" ? "scenarios" : "other" };
}

/** The title of a step of the simulator, in the client's words: « Point de vue « Risque » », « Vérification finale ». */
export function stepTitle(event: Pick<DecisionTraceEvent, "agent" | "tool" | "trace_id">, v: Pick<PortfolioStrings, "trace" | "debate">): string {
  const { kind, lens } = stepKind(event);
  const name = lens && Object.hasOwn(v.debate.lenses, lens) ? v.debate.lenses[lens] : undefined;
  if (kind === "viewpoint" && name) return v.trace.viewpoint(name);
  return v.trace.steps[kind];
}
