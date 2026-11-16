/**
 * `portfolio.*` actions of the simulator (CONTRACTS.md 3.2): the fake A2 proposes positions from
 * what the investor provides, the investor corrects and confirms them (or skips the step), and
 * the code computes the exposures.
 */
import type { AgentRequest } from "@/lib/contract/requests";
import type { Exposures, KnowledgeLevel, Locale, PortfolioView, Position, UnresolvedItem } from "@/lib/contract/schemas";
import { formatDate } from "@/lib/i18n/locale";
import { composeA2Message, MODEL_ID, screenMessage, type Screening } from "./agents";
import { portfolioDoc, writeClientDocs } from "./client-docs";
import { knowledgeLevelOf, requireStage, setFact, setStage, type ClientRecord } from "./client-record";
import { clientState } from "./client-state";
import type { Envelope } from "./envelope";
import {
  computeExposures,
  extractPositions,
  fxRate,
  isValued,
  normalizeConfirmed,
  portfolioSources,
  type Extraction,
  type FileReport,
} from "./portfolio";
import { PORTFOLIO_DRAFT_FIELD } from "./profile";
import { tr, type L } from "./questions";
import { PRICE_DATE, STARTER_SOURCES, USDCAD } from "./starter";
import type { Trace, TraceStepInput } from "./trace";

type PortfolioSubmitRequest = Extract<AgentRequest, { action: "portfolio.submit" }>;
type PortfolioConfirmRequest = Extract<AgentRequest, { action: "portfolio.confirm" }>;

const SUMMARY_DELAY_MS = 1_400;

const holdsUsd = (positions: Position[]) => positions.some((position) => position.currency === "USD");

function inputGuardrailStep(screening: Screening, locale: Locale): TraceStepInput {
  const detail: L =
    screening.masked > 0
      ? {
          fr: `${screening.masked} renseignement(s) personnel(s) masqué(s) avant l'analyse`,
          en: `${screening.masked} personal detail(s) masked before analysis`,
        }
      : { fr: "Aucun renseignement bancaire confidentiel détecté", en: "No confidential banking detail detected" };
  return {
    kind: "guardrail",
    actor: "guardrail",
    title: locale === "fr" ? "Vos renseignements personnels protégés" : "Your personal details protected",
    detail: tr(detail, locale),
    outputs: { masked: screening.masked, action: "NONE" },
    durationMs: 140,
  };
}

function analysisStep({ text, files }: PortfolioSubmitRequest, locale: Locale): TraceStepInput {
  const fr = locale === "fr";
  const pastedChars = text?.trim().length ?? 0;
  return {
    kind: "agent",
    actor: "A2",
    title: fr ? "Yan lit votre portefeuille" : "Yan reads your portfolio",
    detail: fr
      ? `${pastedChars ? "texte collé" : "aucun texte"}, ${files?.length ?? 0} fichier(s)`
      : `${pastedChars ? "pasted text" : "no text"}, ${files?.length ?? 0} file(s)`,
    inputs: {
      text_chars: pastedChars,
      files: (files ?? []).map((file) => ({ name: file.name, media_type: file.media_type })),
    },
    durationMs: 220,
  };
}

function readFileStep(file: FileReport, locale: Locale): TraceStepInput {
  const detail: L = file.readable
    ? { fr: `${file.lines} ligne(s) lue(s)`, en: `${file.lines} line(s) read` }
    : {
        fr: "Le simulateur ne lit pas ce type de fichier (PDF, image ou tableur)",
        en: "The simulator does not read this type of file (PDF, image or spreadsheet)",
      };
  return {
    kind: "tool",
    actor: "A2",
    title: locale === "fr" ? `Lecture du fichier ${file.name}` : `Reading the file ${file.name}`,
    detail: tr(detail, locale),
    inputs: { name: file.name, media_type: file.media_type, bytes: file.bytes },
    outputs: { readable: file.readable, lines: file.lines },
    durationMs: 180,
  };
}

function resolveSecuritiesStep(extraction: Extraction, resolved: Position[], locale: Locale): TraceStepInput {
  const fr = locale === "fr";
  return {
    kind: "tool",
    actor: "A2",
    title: fr ? "Titres reconnus" : "Securities recognized",
    detail: fr
      ? `${resolved.length} titre(s) reconnu(s), ${extraction.unresolved.length} élément(s) non reconnu(s)`
      : `${resolved.length} security(ies) recognized, ${extraction.unresolved.length} item(s) not recognized`,
    inputs: { lines: extraction.lines },
    outputs: {
      resolved: resolved.map((position) => position.ticker),
      unresolved: extraction.unresolved.map((item) => item.raw),
    },
    sources: [STARTER_SOURCES.universe],
    durationMs: 260,
  };
}

function pricesStep(resolved: Position[], locale: Locale): TraceStepInput {
  const fr = locale === "fr";
  return {
    kind: "tool",
    actor: "A2",
    title: fr ? "Derniers cours de clôture" : "Last closing prices",
    detail: fr ? `Cours du ${formatDate(PRICE_DATE, locale)}, dans la devise de cotation` : `Prices of ${formatDate(PRICE_DATE, locale)}, in the listing currency`,
    outputs: Object.fromEntries(resolved.map((position) => [position.ticker ?? position.id, position.price])),
    sources: [STARTER_SOURCES.prices],
    durationMs: 190,
  };
}

function fxStep(locale: Locale): TraceStepInput {
  const fr = locale === "fr";
  return {
    kind: "tool",
    actor: "A2",
    title: fr ? "Taux de change USD/CAD" : "USD/CAD exchange rate",
    detail: fr ? `1 USD = 1,4255 CAD le ${formatDate(PRICE_DATE, locale)}` : `1 USD = 1.4255 CAD on ${formatDate(PRICE_DATE, locale)}`,
    outputs: { usdcad: USDCAD, date: PRICE_DATE },
    sources: [STARTER_SOURCES.fx],
    durationMs: 120,
  };
}

/** What A2's tools did with the input: files read, securities resolved, then prices and rate if needed. */
function toolSteps(extraction: Extraction, locale: Locale): TraceStepInput[] {
  const resolved = extraction.positions.filter((position) => position.resolved);
  const steps = extraction.files.map((file) => readFileStep(file, locale));
  steps.push(resolveSecuritiesStep(extraction, resolved, locale));
  if (resolved.length > 0) steps.push(pricesStep(resolved, locale));
  if (holdsUsd(extraction.positions)) steps.push(fxStep(locale));
  return steps;
}

function summaryModelStep(level: KnowledgeLevel | null, summary: string, locale: Locale): TraceStepInput {
  const fr = locale === "fr";
  return {
    kind: "model",
    actor: "A2",
    title: fr ? "Yan rédige le résumé" : "Yan writes the summary",
    detail: fr ? "Yan rédige les phrases; les chiffres sont calculés, jamais inventés" : "Yan writes the sentences; the figures are computed, never made up",
    inputs: { model_id: MODEL_ID, simulated: true, knowledge_level: level },
    outputs: { message_chars: summary.length },
    durationMs: 1_450,
  };
}

function draftExposuresStep(exposures: Exposures, positions: Position[], locale: Locale): TraceStepInput {
  const fr = locale === "fr";
  return {
    kind: "deterministic",
    actor: "A2",
    title: fr ? "Expositions calculées selon des règles fixes" : "Exposures computed with fixed rules",
    detail: fr
      ? `Total ${exposures.total_value_cad.toLocaleString("fr-CA")} $ CA; ${exposures.flags.length || "aucun"} signal(aux) à regarder`
      : `Total CAD ${exposures.total_value_cad.toLocaleString("en-CA")}; ${exposures.flags.length || "no"} signal(s) to look at`,
    outputs: { total_value_cad: exposures.total_value_cad, flags: exposures.flags },
    sources: portfolioSources(positions),
    durationMs: 4,
  };
}

/** `portfolio.submit`: A2 reads the text and files, proposes positions, and summarizes them for the investor. */
export function submitPortfolio(record: ClientRecord, request: PortfolioSubmitRequest, trace: Trace): Envelope {
  const locale = record.locale;
  requireStage(record, ["existing_portfolio", "portfolio_review"], "portfolio.submit");
  record.turn += 1;
  record.lastA2Turn = record.turn;
  const provenance = `a2:${record.turn}`;

  const screening = screenMessage(request.text ?? "", locale);
  trace.add(inputGuardrailStep(screening, locale));
  trace.add(analysisStep(request, locale));
  const extraction = extractPositions({ text: screening.text, files: request.files }, locale);
  const { positions, unresolved } = extraction;
  for (const step of toolSteps(extraction, locale)) trace.add(step);

  const exposures = computeExposures(positions, unresolved.filter((item) => !item.position_id).length);
  const level = knowledgeLevelOf(record);
  const message = composeA2Message({
    level,
    positions: positions.filter((position) => position.resolved).length,
    unresolved: unresolved.map((item) => item.raw),
    exposures,
    usesUsd: holdsUsd(positions),
  });
  trace.message(tr(message, locale), SUMMARY_DELAY_MS);
  trace.add(summaryModelStep(level, tr(message, locale), locale));
  trace.add(draftExposuresStep(exposures, positions, locale));

  record.portfolio = { positions, unresolved, fx: fxRate(), exposures, status: "draft", sources: portfolioSources(positions) };
  record.message = message;
  setStage(record, "portfolio_review", { provenance, at: trace.now, note: "positions proposées par Yan" });
  setFact(record, {
    field: PORTFOLIO_DRAFT_FIELD,
    value: { positions: positions.length, total_value_cad: exposures.total_value_cad },
    provenance,
    at: trace.now,
  });
  writeClientDocs(record, trace, "portfolio.submit");
  return clientState(record, trace, locale);
}

function correctedPositionsStep(positions: Position[], locale: Locale): TraceStepInput {
  const fr = locale === "fr";
  const count = positions.length;
  const outsideUniverse = positions.filter((position) => !position.resolved).length;
  return {
    kind: "deterministic",
    actor: "A2",
    title: fr ? "Vos positions corrigées, relues" : "Your corrected positions, read again",
    detail: fr
      ? `${count} ${count > 1 ? "positions" : "position"}, ${outsideUniverse} hors des titres suivis`
      : `${count} ${count === 1 ? "position" : "positions"}, ${outsideUniverse} outside the tracked securities`,
    inputs: { positions: count },
    outputs: { tickers: positions.map((position) => position.ticker) },
    sources: [STARTER_SOURCES.universe, STARTER_SOURCES.prices],
    durationMs: 6,
  };
}

function confirmedExposuresStep(exposures: Exposures, positions: Position[], locale: Locale): TraceStepInput {
  const fr = locale === "fr";
  return {
    kind: "deterministic",
    actor: "A2",
    title: fr ? "Expositions calculées selon des règles fixes" : "Exposures computed with fixed rules",
    detail: fr
      ? `Par classe d'actifs, devise, marché et secteur; total ${exposures.total_value_cad.toLocaleString("fr-CA")} $ CA`
      : `By asset class, currency, market and sector; total CAD ${exposures.total_value_cad.toLocaleString("en-CA")}`,
    outputs: { by_asset_class: exposures.by_asset_class, flags: exposures.flags },
    sources: portfolioSources(positions),
    durationMs: 5,
  };
}

/** Confirmed positions the code could not value: they stay listed, each pointing at its row. */
function unvaluedItems(positions: Position[], locale: Locale): UnresolvedItem[] {
  return positions
    .filter((position) => !isValued(position))
    .map((position) => ({
      raw: position.raw ?? position.ticker ?? position.id,
      reason:
        locale === "fr"
          ? "position sans valeur : ni cours ni valeur déclarée"
          : "position without a value: no price and no declared value",
      position_id: position.id,
    }));
}

function portfolioWrittenStep(key: string, locale: Locale): TraceStepInput {
  return {
    kind: "storage",
    actor: "store",
    title: locale === "fr" ? "Votre portefeuille est enregistré" : "Your portfolio is saved",
    detail: locale === "fr" ? "Ajouté à vos documents personnels" : "Added to your personal documents",
    outputs: { key },
    durationMs: 11,
  };
}

/** `portfolio.confirm`: the code re-reads the corrected positions, recomputes the exposures and stores the portfolio. */
export function confirmPortfolio(record: ClientRecord, request: PortfolioConfirmRequest, trace: Trace): Envelope {
  const locale = record.locale;
  requireStage(record, ["portfolio_review"], "portfolio.confirm");
  const positions = request.positions.map((position) => normalizeConfirmed(position, locale));
  trace.add(correctedPositionsStep(positions, locale));
  const exposures = computeExposures(positions);
  trace.add(confirmedExposuresStep(exposures, positions, locale));

  const portfolio: PortfolioView = {
    positions,
    unresolved: unvaluedItems(positions, locale),
    fx: fxRate(),
    exposures,
    status: "confirmed",
    sources: portfolioSources(positions),
  };
  record.portfolio = portfolio;
  const provenance = `a2:${Math.max(1, record.lastA2Turn)}`;
  setFact(record, {
    field: "context.existing_portfolio",
    value: { positions: positions.length, total_value_cad: exposures.total_value_cad, flags: exposures.flags },
    provenance,
    at: trace.now,
  });
  setStage(record, "followups", { provenance, at: trace.now, note: "positions confirmées" });
  record.message = null;
  record.pendingA1 = [];
  const key = `clients/${record.id}/portefeuille-existant.md`;
  record.docs.set(key, portfolioDoc(record, portfolio, trace.now));
  trace.add(portfolioWrittenStep(key, locale));
  writeClientDocs(record, trace, "portfolio.confirm");
  return clientState(record, trace, locale);
}

/** `portfolio.skip`: straight to the follow-ups; the existing portfolio stays a missing field. */
export function skipPortfolio(record: ClientRecord, trace: Trace): Envelope {
  const fr = record.locale === "fr";
  requireStage(record, ["existing_portfolio"], "portfolio.skip");
  setStage(record, "followups", { provenance: "base:q_has_portfolio", at: trace.now, note: "portefeuille passé" });
  record.message = null;
  trace.add({
    kind: "deterministic",
    actor: "questionnaire",
    title: fr ? "Portefeuille existant passé" : "Existing portfolio skipped",
    detail: fr ? "La suite du parcours continue sans portefeuille existant : vous pourrez l'ajouter plus tard" : "The journey goes on without an existing portfolio: you can add it later",
    outputs: { stage: "followups" },
    durationMs: 1,
  });
  writeClientDocs(record, trace, "portfolio.skip");
  return clientState(record, trace, record.locale);
}
