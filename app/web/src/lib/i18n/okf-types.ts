/**
 * Labels of the OKF document types (CONTRACTS.md, section 5). The `type` of a document stays in
 * English in its frontmatter and in `kb.list`; only its display is translated. A type missing
 * from this table is shown as is.
 */
import type { Locale } from "@/lib/contract/schemas";

/**
 * `DOC_TYPES` of `app/agents/src/alphaforge/okf.py` (the runtimes write nothing else), plus
 * `Trace`, the type the mock simulator gives to the JSON traces of a client.
 */
export const OKF_TYPES = [
  "Investor Profile",
  "Existing Portfolio",
  "Profile Journal",
  "News",
  "Data Series",
  "Methodology",
  "Financial Concept",
  "Company Fundamentals",
  "Index",
  "Profile Note",
  "Fact",
  "Market Signal",
  "Regulatory Filing",
  "Research Brief",
  "Stock Features",
  "Portfolio Decision",
  "Trace",
] as const;

export type OkfType = (typeof OKF_TYPES)[number];

const LABELS: Record<Locale, Record<OkfType, string>> = {
  fr: {
    "Investor Profile": "Profil d’investisseur",
    "Existing Portfolio": "Portefeuille existant",
    "Profile Journal": "Journal du profil",
    News: "Actualité",
    "Data Series": "Série de données",
    Methodology: "Méthodologie",
    "Financial Concept": "Notion financière",
    "Company Fundamentals": "Fondamentaux d’une société",
    Index: "Sommaire",
    "Profile Note": "Note de profil",
    Fact: "Fait sourcé",
    "Market Signal": "Signal de contexte",
    "Regulatory Filing": "Dépôt réglementaire",
    "Research Brief": "Synthèse de recherche",
    "Stock Features": "Caractéristiques d’un titre",
    "Portfolio Decision": "Décision de portefeuille",
    Trace: "Étapes suivies",
  },
  en: {
    "Investor Profile": "Investor profile",
    "Existing Portfolio": "Existing portfolio",
    "Profile Journal": "Profile journal",
    News: "News",
    "Data Series": "Data series",
    Methodology: "Methodology",
    "Financial Concept": "Financial concept",
    "Company Fundamentals": "Company fundamentals",
    Index: "Contents",
    "Profile Note": "Profile note",
    Fact: "Sourced fact",
    "Market Signal": "Context signal",
    "Regulatory Filing": "Regulatory filing",
    "Research Brief": "Research brief",
    "Stock Features": "Stock features",
    "Portfolio Decision": "Portfolio decision",
    Trace: "Steps taken",
  },
};

const isOkfType = (type: string): type is OkfType => (OKF_TYPES as readonly string[]).includes(type);

/** The label of an OKF type in `locale`; an unknown type falls back to its raw value. */
export function okfTypeLabel(type: string, locale: Locale): string {
  return isOkfType(type) ? LABELS[locale][type] : type;
}
