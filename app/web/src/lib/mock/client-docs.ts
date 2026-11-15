/**
 * OKF documents of a client base (CONTRACTS.md 5): profil.md, journal.md, index.md, one trace
 * per action, and portefeuille-existant.md once the positions are confirmed. They are rebuilt
 * from the client record, in the client's language.
 */
import type { Completeness, Locale, PortfolioView, Position, ProfileView, Source } from "@/lib/contract/schemas";
import { knowledgeLevelOf, type ClientRecord, type JournalEntry } from "./client-record";
import { okfDocument, staleAfter, type StoredDoc } from "./documents";
import { completeness, dimensionViews, effectiveRisk, formatPercent } from "./profile";
import type { Trace } from "./trace";

const EMPTY_CELL = "—";

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
    title: fr ? "Base du client mise à jour" : "Client base updated",
    detail: fr ? `profil.md, journal.md et la trace de ${action}` : `profil.md, journal.md and the ${action} trace`,
    outputs: { keys: [`${base}profil.md`, `${base}journal.md`, traceKey] },
    durationMs: 12,
  });
  record.docs.set(traceKey, {
    key: traceKey,
    title: fr ? `Trace : ${action}` : `Trace: ${action}`,
    type: "Trace",
    description: fr ? `${trace.steps.length} étapes` : `${trace.steps.length} steps`,
    updated_at: at,
    content: JSON.stringify({ action, at, steps: trace.steps }, null, 2),
  });
  record.docs.set(`${base}index.md`, indexDoc(record, at));
}

/** Title of a provenance: `base:<question>`, `a1:<turn>`, `a2:<turn>` or `settings`. */
function provenanceTitle(provenance: string): string {
  const [kind, ref] = provenance.split(":");
  if (kind === "base") return `Réponse à ${ref}`;
  if (kind === "a1") return `Relance A1, tour ${ref}`;
  if (kind === "a2") return `Analyse A2, tour ${ref}`;
  return "Réglages de l'investisseur";
}

/** One source per provenance of the journal, dated by its first entry. */
function profileSources(record: ClientRecord): Source[] {
  const seen = new Set<string>();
  const sources: Source[] = [];
  for (const entry of record.entries) {
    if (seen.has(entry.provenance)) continue;
    seen.add(entry.provenance);
    sources.push({
      id: entry.provenance.replace(":", "-"),
      title: provenanceTitle(entry.provenance),
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
    effectiveRisk: "Risque effectif",
    status: "Statut",
    summary: "Résumé",
    facts: "Faits et provenance",
    field: "Champ",
    value: "Valeur",
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
    effectiveRisk: "Effective risk",
    status: "Status",
    summary: "Summary",
    facts: "Facts and provenance",
    field: "Field",
    value: "Value",
    missing: "Missing",
    nothingMissing: "- Nothing",
    statuses: { known: "known", partial: "partial", missing: "missing" },
  },
} satisfies Record<Locale, unknown>;

function profileBody(record: ClientRecord, result: Completeness, dimensions: ProfileView["dimensions"]): string {
  const locale = record.locale;
  const t = PROFILE_DOC_TEXT[locale];
  const rows = Object.entries(dimensions)
    .map(([key, view]) => `| ${key} | ${t.statuses[view.status]} | ${view.summary ?? EMPTY_CELL} |`)
    .join("\n");
  const facts = [...record.values.values()]
    .map((fact) => `| ${fact.field} | ${JSON.stringify(fact.value)} | ${fact.provenance} | ${fact.at} |`)
    .join("\n");
  const missing = result.missing.map((item) => `- ${item.label} (${item.dimension})`).join("\n");
  const percent = (share: number) => formatPercent(share, locale);
  return `# ${t.title}

${t.completeness} : **${percent(result.displayed)}** (${t.threshold} ${percent(result.threshold)}, ${t.cap} ${percent(result.cap)}). ${t.knowledgeLevel} : ${knowledgeLevelOf(record) ?? EMPTY_CELL}. ${t.effectiveRisk} : ${effectiveRisk(record.values) ?? EMPTY_CELL}.

| Dimension | ${t.status} | ${t.summary} |
| --- | --- | --- |
${rows}

## ${t.facts}

| ${t.field} | ${t.value} | Provenance | Date |
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
  const head = `- \`${entry.at}\` · **${entry.provenance}** ·`;
  if (entry.kind === "answer") {
    const previous = "previous" in entry ? ` (${fr ? "avant" : "was"} ${JSON.stringify(entry.previous)})` : "";
    return `${head} ${entry.field} = ${JSON.stringify(entry.value)}${previous}`;
  }
  if (entry.kind === "message") return `${head} message : « ${entry.text} »`;
  return `${head} ${fr ? "étape" : "stage"} ${entry.previous ?? EMPTY_CELL} → ${entry.value} (${entry.note})`;
}

function journalDoc(record: ClientRecord, at: string): StoredDoc {
  const fr = record.locale === "fr";
  const lines = record.entries.map((entry) => journalLine(entry, record.locale));
  return okfDocument(
    `clients/${record.id}/journal.md`,
    {
      type: "Profile Journal",
      title: fr ? "Journal du profil" : "Profile journal",
      description: fr ? "Chaque réponse, avec sa provenance et sa date." : "Every answer, with its provenance and date.",
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
    description: "Positions confirmées par l'investisseur et expositions calculées par le code.",
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
    description: "Positions confirmed by the investor and exposures computed by code.",
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

function positionRow(position: Position): string {
  const cells = [position.ticker, position.name, position.quantity, position.currency, position.account_type, position.value_cad];
  return `| ${cells.map((cell) => cell ?? EMPTY_CELL).join(" | ")} |`;
}

function portfolioBody(portfolio: PortfolioView, locale: Locale): string {
  const t = PORTFOLIO_DOC_TEXT[locale];
  const { exposures } = portfolio;
  const rows = portfolio.positions.map(positionRow).join("\n");
  const shares = (byName: Record<string, number>) =>
    Object.entries(byName)
      .map(([name, share]) => `${name} ${formatPercent(share, locale)}`)
      .join(", ");
  return `# ${t.title}

| Ticker | ${t.name} | ${t.quantity} | ${t.currency} | ${t.account} | ${t.value} |
| --- | --- | --- | --- | --- | --- |
${rows || "| — | — | — | — | — | — |"}

- ${t.totalValue} : ${exposures.total_value_cad} CAD
- ${t.assetClasses} : ${shares(exposures.by_asset_class)}
- ${t.currencies} : ${shares(exposures.by_currency)}
- ${t.markets} : ${shares(exposures.by_market)}
- ${t.sectors} : ${shares(exposures.by_sector)}
- ${t.flags} : ${exposures.flags.join(", ") || EMPTY_CELL}`;
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
      title: fr ? "Base du client" : "Client base",
      description: fr ? "Documents OKF propres à cet investisseur." : "OKF documents of this investor.",
      tags: ["index"],
      status: "draft",
      owners: ["alphaforge-a1"],
      sensitivity: "client",
      generated: { by: "code:store", at },
      stale_after: staleAfter(at),
      sources: [],
      data: { documents: docs.length, traces },
    },
    `# ${fr ? "Base du client" : "Client base"}

${docs.map((doc) => `- [${doc.title}](${doc.key.split("/").pop()}) : ${doc.description}`).join("\n")}
- ${fr ? `${traces} trace(s) d'exécution dans` : `${traces} execution trace(s) in`} \`traces/\``,
  );
}
