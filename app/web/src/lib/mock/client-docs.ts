/**
 * OKF documents of a client base (CONTRACTS.md 5): profil.md, journal.md, index.md, one trace
 * per action, and portefeuille-existant.md once the positions are confirmed. They are rebuilt
 * from the client record, in the client's language.
 */
import type { AccountType, AssetClass, Completeness, KnowledgeLevel, Locale, PortfolioView, Position, ProfileView, RiskLevel, Source, Stage } from "@/lib/contract/schemas";
import { formatDateTime } from "@/lib/i18n/locale";
import { knowledgeLevelOf, type ClientRecord, type JournalEntry } from "./client-record";
import { okfDocument, staleAfter, type StoredDoc } from "./documents";
import { completeness, dimensionViews, effectiveRisk, factLabel, fieldDef, formatMoney, formatPercent, PORTFOLIO_DRAFT_FIELD } from "./profile";
import { questionByField, tr, type L } from "./questions";
import type { Trace } from "./trace";

const EMPTY_CELL = "—";

/** What the investor reads instead of the internal names: dimensions, levels, stages, accounts, classes, flags, actions. */
const DIMENSION_LABELS: Record<string, L> = {
  knowledge: { fr: "Connaissances", en: "Knowledge" },
  objective: { fr: "Objectif", en: "Goal" },
  horizon: { fr: "Horizon", en: "Horizon" },
  risk_tolerance: { fr: "Tolérance au risque", en: "Risk tolerance" },
  risk_capacity: { fr: "Capacité de risque", en: "Risk capacity" },
  constraints: { fr: "Contraintes", en: "Constraints" },
  preferences: { fr: "Préférences", en: "Preferences" },
  behavior: { fr: "Comportement", en: "Behaviour" },
  context: { fr: "Contexte", en: "Context" },
};

const KNOWLEDGE_LABELS: Record<KnowledgeLevel, L> = {
  beginner: { fr: "Débutant", en: "Beginner" },
  intermediate: { fr: "Intermédiaire", en: "Intermediate" },
  advanced: { fr: "Avancé", en: "Advanced" },
};

const RISK_LABELS: Record<RiskLevel, L> = {
  low: { fr: "Faible", en: "Low" },
  low_medium: { fr: "Faible à moyen", en: "Low to medium" },
  medium: { fr: "Moyen", en: "Medium" },
  medium_high: { fr: "Moyen à élevé", en: "Medium to high" },
  high: { fr: "Élevé", en: "High" },
};

const STAGE_LABELS: Record<Stage, L> = {
  base_questions: { fr: "Questions de base", en: "Base questions" },
  existing_portfolio: { fr: "Portefeuille existant", en: "Existing portfolio" },
  portfolio_review: { fr: "Vérification des positions", en: "Position review" },
  followups: { fr: "Questions de suivi de Yan", en: "Yan's follow-up questions" },
  complete: { fr: "Profil complet", en: "Profile complete" },
};

const ACCOUNT_LABELS: Record<AccountType, L> = {
  tfsa: { fr: "CELI", en: "TFSA" },
  rrsp: { fr: "REER", en: "RRSP" },
  resp: { fr: "REEE", en: "RESP" },
  rrif: { fr: "FERR", en: "RRIF" },
  non_registered: { fr: "Non enregistré", en: "Non-registered" },
  unknown: { fr: "Inconnu", en: "Unknown" },
};

const ASSET_CLASS_LABELS: Record<AssetClass, L> = {
  equity: { fr: "Action", en: "Stock" },
  etf_equity: { fr: "FNB d'actions", en: "Equity ETF" },
  etf_bond: { fr: "FNB d'obligations", en: "Bond ETF" },
  etf_commodity: { fr: "FNB de matières premières", en: "Commodity ETF" },
  bond: { fr: "Obligation", en: "Bond" },
  cash: { fr: "Encaisse", en: "Cash" },
  crypto: { fr: "Cryptoactif", en: "Crypto-asset" },
  fund: { fr: "Fonds", en: "Fund" },
  other: { fr: "Autre", en: "Other" },
};

const FLAG_LABELS: Record<string, L> = {
  concentration_single_position: { fr: "Concentration sur une position", en: "Single-position concentration" },
  home_bias_canada: { fr: "Biais domestique (Canada)", en: "Home bias (Canada)" },
  concentration_sector: { fr: "Concentration sectorielle", en: "Sector concentration" },
  crypto_exposure_high: { fr: "Cryptoactifs élevés", en: "High crypto-assets" },
  cash_heavy: { fr: "Beaucoup d'encaisse", en: "Cash heavy" },
  few_holdings: { fr: "Peu de positions", en: "Few holdings" },
  unvalued_positions: { fr: "Lignes non évaluées", en: "Unvalued lines" },
};

const ACTION_LABELS: Record<string, L> = {
  "session.start": { fr: "début du profil", en: "profile start" },
  "session.resume": { fr: "reprise du profil", en: "profile resumed" },
  "base.answer": { fr: "réponse à une question de base", en: "answer to a base question" },
  "portfolio.submit": { fr: "lecture de votre portefeuille", en: "reading of your portfolio" },
  "portfolio.confirm": { fr: "confirmation des positions", en: "position confirmation" },
  "portfolio.skip": { fr: "portefeuille passé", en: "portfolio skipped" },
  "followup.reply": { fr: "échange avec Yan", en: "exchange with Yan" },
  "settings.update": { fr: "réglages", en: "settings" },
  "profile.get": { fr: "lecture du profil", en: "profile read" },
};

/** « Libellé : valeur » in French, "Label: value" in English. */
const colon = (locale: Locale) => (locale === "fr" ? " : " : ": ");

function label(labels: Record<string, L>, key: string | null | undefined, locale: Locale): string {
  if (!key) return EMPTY_CELL;
  const known = labels[key];
  return known ? tr(known, locale) : key;
}

/** The name of a profile field: its label, else its question, else its dimension. */
function fieldName(field: string, locale: Locale): string {
  const def = fieldDef(field);
  if (def) return tr(def.label, locale);
  const question = questionByField(field);
  if (question) return tr(question.prompt, locale);
  return label(DIMENSION_LABELS, field.split(".")[0], locale);
}

/** The value of a fact as the investor reads it: option labels, yes or no, amounts and units, never JSON. */
const valueText = (field: string, value: unknown, locale: Locale): string => factLabel(field, value, locale);

/** Rewrite profil.md, journal.md and index.md, and store the trace of the action (itself a traced step). */
export function writeClientDocs(record: ClientRecord, trace: Trace, action: string): void {
  const fr = record.locale === "fr";
  const at = trace.now;
  const base = `clients/${record.id}/`;
  record.docs.set(`${base}profil.md`, profileDoc(record, at));
  record.docs.set(`${base}journal.md`, journalDoc(record, at));
  const stamp = at.replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  const traceKey = `${base}traces/${stamp}-${action}.json`;
  trace.add({
    kind: "storage",
    actor: "store",
    title: fr ? "Votre profil est enregistré" : "Your profile is saved",
    detail: fr ? "Votre profil, son journal et les étapes suivies" : "Your profile, its journal and the steps taken",
    outputs: { keys: [`${base}profil.md`, `${base}journal.md`, traceKey] },
    durationMs: 12,
  });
  const count = trace.steps.length;
  record.docs.set(traceKey, {
    key: traceKey,
    title: fr ? `Étapes suivies : ${label(ACTION_LABELS, action, "fr")}` : `Steps taken: ${label(ACTION_LABELS, action, "en")}`,
    type: "Trace",
    description: fr ? `${count} ${count > 1 ? "étapes" : "étape"}` : `${count} ${count === 1 ? "step" : "steps"}`,
    updated_at: at,
    content: JSON.stringify({ action, at, steps: trace.steps }, null, 2),
  });
  record.docs.set(`${base}index.md`, indexDoc(record, at));
}

/** Title of a provenance: `base:<question>`, `a1:<turn>`, `a2:<turn>` or `settings`. */
function provenanceTitle(provenance: string, locale: Locale): string {
  const fr = locale === "fr";
  const [kind] = provenance.split(":");
  if (kind === "base") return fr ? "Question de base" : "Base question";
  if (kind === "a1") return fr ? "Échange avec Yan" : "Exchange with Yan";
  if (kind === "a2") return fr ? "Lecture de votre portefeuille par Yan" : "Yan's reading of your portfolio";
  return fr ? "Vos réglages" : "Your settings";
}

/** One source per provenance title of the journal, dated by its first entry. */
function profileSources(record: ClientRecord): Source[] {
  const seen = new Set<string>();
  const sources: Source[] = [];
  for (const entry of record.entries) {
    const title = provenanceTitle(entry.provenance, record.locale);
    if (seen.has(title)) continue;
    seen.add(title);
    sources.push({
      id: entry.provenance.replace(":", "-"),
      title,
      resource: entry.provenance,
      retrieved_at: entry.at,
    });
  }
  return sources;
}

const PROFILE_DOC_TEXT = {
  fr: {
    title: "Profil investisseur",
    description: "Profil en cinq dimensions, niveau de connaissances et complétude.",
    completeness: "Complétude",
    threshold: "seuil",
    cap: "plafond",
    knowledgeLevel: "Niveau de connaissances",
    effectiveRisk: "Risque retenu",
    status: "Statut",
    summary: "Résumé",
    facts: "Vos réponses et leur origine",
    field: "Information",
    value: "Valeur",
    origin: "Origine",
    date: "Date",
    missing: "Ce qui manque",
    nothingMissing: "- Rien",
    statuses: { known: "connue", partial: "partielle", missing: "manquante" },
  },
  en: {
    title: "Investor profile",
    description: "Five-dimension profile, knowledge level and completeness.",
    completeness: "Completeness",
    threshold: "threshold",
    cap: "cap",
    knowledgeLevel: "Knowledge level",
    effectiveRisk: "Risk retained",
    status: "Status",
    summary: "Summary",
    facts: "Your answers and where they come from",
    field: "Detail",
    value: "Value",
    origin: "Origin",
    date: "Date",
    missing: "Missing",
    nothingMissing: "- Nothing",
    statuses: { known: "known", partial: "partial", missing: "missing" },
  },
} satisfies Record<Locale, unknown>;

function profileBody(record: ClientRecord, result: Completeness, dimensions: ProfileView["dimensions"]): string {
  const locale = record.locale;
  const t = PROFILE_DOC_TEXT[locale];
  const rows = Object.entries(dimensions)
    .map(([key, view]) => `| ${label(DIMENSION_LABELS, key, locale)} | ${t.statuses[view.status]} | ${view.summary ?? EMPTY_CELL} |`)
    .join("\n");
  const facts = [...record.values.values()]
    .filter((fact) => fact.field !== PORTFOLIO_DRAFT_FIELD)
    .map(
      (fact) =>
        `| ${fieldName(fact.field, locale)} | ${valueText(fact.field, fact.value, locale)} | ${provenanceTitle(fact.provenance, locale)} | ${formatDateTime(fact.at, locale)} |`,
    )
    .join("\n");
  const missing = result.missing.map((item) => `- ${item.label} (${label(DIMENSION_LABELS, item.dimension, locale)})`).join("\n");
  const percent = (share: number) => formatPercent(share, locale);
  return `# ${t.title}

${t.completeness} : **${percent(result.displayed)}** (${t.threshold} ${percent(result.threshold)}, ${t.cap} ${percent(result.cap)}). ${t.knowledgeLevel} : ${label(KNOWLEDGE_LABELS, knowledgeLevelOf(record), locale)}. ${t.effectiveRisk} : ${label(RISK_LABELS, effectiveRisk(record.values), locale)}.

| Dimension | ${t.status} | ${t.summary} |
| --- | --- | --- |
${rows}

## ${t.facts}

| ${t.field} | ${t.value} | ${t.origin} | ${t.date} |
| --- | --- | --- | --- |
${facts || "| — | — | — | — |"}

## ${t.missing}

${missing || t.nothingMissing}`;
}

function profileDoc(record: ClientRecord, at: string): StoredDoc {
  const t = PROFILE_DOC_TEXT[record.locale];
  const result = completeness(record.values, record.locale);
  const dimensions = dimensionViews(record.values, record.locale);
  return okfDocument(
    `clients/${record.id}/profil.md`,
    {
      type: "Investor Profile",
      title: t.title,
      description: t.description,
      tags: ["profil-investisseur"],
      status: record.stage === "complete" ? "stable" : "draft",
      owners: ["alphaforge-a1"],
      sensitivity: "client",
      generated: { by: record.a1Turns > 0 ? "agent:A1" : "code:questionnaire", at },
      stale_after: staleAfter(at),
      sources: profileSources(record),
      data: {
        stage: record.stage,
        knowledge_level: knowledgeLevelOf(record),
        effective_risk: effectiveRisk(record.values),
        completeness: { score: result.score, displayed: result.displayed },
        dimensions: Object.fromEntries(Object.entries(dimensions).map(([key, view]) => [key, view.fields])),
      },
    },
    profileBody(record, result, dimensions),
  );
}

function journalLine(entry: JournalEntry, locale: Locale): string {
  const fr = locale === "fr";
  const head = `- ${formatDateTime(entry.at, locale)} · **${provenanceTitle(entry.provenance, locale)}** ·`;
  if (entry.kind === "answer") {
    const previous = "previous" in entry ? ` (${fr ? "avant" : "was"}${colon(locale)}${valueText(entry.field, entry.previous, locale)})` : "";
    return `${head} ${fieldName(entry.field, locale)}${colon(locale)}${valueText(entry.field, entry.value, locale)}${previous}`;
  }
  if (entry.kind === "message") return fr ? `${head} message : « ${entry.text} »` : `${head} message: "${entry.text}"`;
  return `${head} ${fr ? "étape" : "step"}${colon(locale)}${label(STAGE_LABELS, entry.previous, locale)} → ${label(STAGE_LABELS, entry.value, locale)}`;
}

function journalDoc(record: ClientRecord, at: string): StoredDoc {
  const fr = record.locale === "fr";
  const lines = record.entries
    .filter((entry) => entry.kind !== "answer" || entry.field !== PORTFOLIO_DRAFT_FIELD)
    .map((entry) => journalLine(entry, record.locale));
  return okfDocument(
    `clients/${record.id}/journal.md`,
    {
      type: "Profile Journal",
      title: fr ? "Journal du profil" : "Profile journal",
      description: fr ? "Chaque réponse, avec son origine et sa date." : "Every answer, with where it comes from and its date.",
      tags: ["profil-investisseur"],
      status: "draft",
      owners: ["alphaforge-a1"],
      sensitivity: "client",
      generated: { by: "code:store", at },
      stale_after: staleAfter(at),
      sources: profileSources(record),
      data: { entries: record.entries },
    },
    `# ${fr ? "Journal du profil" : "Profile journal"}\n\n${lines.join("\n") || (fr ? "Aucune réponse pour l'instant." : "No answer yet.")}`,
  );
}

const PORTFOLIO_DOC_TEXT = {
  fr: {
    title: "Portefeuille existant",
    description: "Positions que vous avez confirmées, et expositions calculées selon des règles fixes.",
    security: "Titre",
    name: "Nom",
    quantity: "Quantité",
    currency: "Devise",
    account: "Compte",
    value: "Valeur (CAD)",
    totalValue: "Valeur totale",
    assetClasses: "Classes d'actifs",
    currencies: "Devises",
    markets: "Marchés",
    sectors: "Secteurs",
    flags: "Signaux",
  },
  en: {
    title: "Existing portfolio",
    description: "Positions you confirmed, and exposures computed with fixed rules.",
    security: "Security",
    name: "Name",
    quantity: "Quantity",
    currency: "Currency",
    account: "Account",
    value: "Value (CAD)",
    totalValue: "Total value",
    assetClasses: "Asset classes",
    currencies: "Currencies",
    markets: "Markets",
    sectors: "Sectors",
    flags: "Flags",
  },
} satisfies Record<Locale, unknown>;

function positionRow(position: Position, locale: Locale): string {
  const cells = [
    position.ticker,
    position.name,
    typeof position.quantity === "number" ? position.quantity.toLocaleString(locale === "fr" ? "fr-CA" : "en-CA") : null,
    position.currency,
    position.account_type ? label(ACCOUNT_LABELS, position.account_type, locale) : null,
    typeof position.value_cad === "number" ? formatMoney(position.value_cad, locale) : null,
  ];
  return `| ${cells.map((cell) => cell ?? EMPTY_CELL).join(" | ")} |`;
}

function portfolioBody(portfolio: PortfolioView, locale: Locale): string {
  const t = PORTFOLIO_DOC_TEXT[locale];
  const { exposures } = portfolio;
  const rows = portfolio.positions.map((position) => positionRow(position, locale)).join("\n");
  const shares = (byName: Record<string, number>, labels: Record<string, L> = {}) =>
    Object.entries(byName)
      .map(([name, share]) => `${label(labels, name, locale)} ${formatPercent(share, locale)}`)
      .join(", ");
  return `# ${t.title}

| ${t.security} | ${t.name} | ${t.quantity} | ${t.currency} | ${t.account} | ${t.value} |
| --- | --- | --- | --- | --- | --- |
${rows || "| — | — | — | — | — | — |"}

- ${t.totalValue} : ${formatMoney(exposures.total_value_cad, locale)}
- ${t.assetClasses} : ${shares(exposures.by_asset_class, ASSET_CLASS_LABELS)}
- ${t.currencies} : ${shares(exposures.by_currency)}
- ${t.markets} : ${shares(exposures.by_market)}
- ${t.sectors} : ${shares(exposures.by_sector)}
- ${t.flags} : ${exposures.flags.map((flag) => label(FLAG_LABELS, flag, locale)).join(", ") || EMPTY_CELL}`;
}

/** portefeuille-existant.md, written when the investor confirms the positions. */
export function portfolioDoc(record: ClientRecord, portfolio: PortfolioView, at: string): StoredDoc {
  const t = PORTFOLIO_DOC_TEXT[record.locale];
  return okfDocument(
    `clients/${record.id}/portefeuille-existant.md`,
    {
      type: "Existing Portfolio",
      title: t.title,
      description: t.description,
      tags: ["construction-portefeuille", "profil-investisseur"],
      status: "stable",
      owners: ["alphaforge-a2"],
      sensitivity: "client",
      generated: { by: "agent:A2", at },
      stale_after: staleAfter(at, 1),
      sources: portfolio.sources,
      data: { positions: portfolio.positions, exposures: portfolio.exposures },
    },
    portfolioBody(portfolio, record.locale),
  );
}

function indexDoc(record: ClientRecord, at: string): StoredDoc {
  const fr = record.locale === "fr";
  const docs = [...record.docs.values()].filter((doc) => doc.key.endsWith(".md") && !doc.key.endsWith("/index.md"));
  const traces = [...record.docs.keys()].filter((key) => key.includes("/traces/")).length;
  return okfDocument(
    `clients/${record.id}/index.md`,
    {
      type: "Index",
      title: fr ? "Vos documents" : "Your documents",
      description: fr ? "Les documents de votre profil." : "The documents of your profile.",
      tags: ["index"],
      status: "draft",
      owners: ["alphaforge-a1"],
      sensitivity: "client",
      generated: { by: "code:store", at },
      stale_after: staleAfter(at),
      sources: [],
      data: { documents: docs.length, traces },
    },
    `# ${fr ? "Vos documents" : "Your documents"}

${docs.map((doc) => `- **${doc.title}** : ${doc.description}`).join("\n")}`,
  );
}
