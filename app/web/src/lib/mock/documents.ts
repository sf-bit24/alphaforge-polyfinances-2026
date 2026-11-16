/**
 * OKF documents of the simulator (CONTRACTS.md 5): a YAML frontmatter, then a
 * Markdown body. The general base is seeded with methodology notes and data
 * series built from the starter dataset; nothing in it concerns a client.
 */
import { stringify } from "yaml";
import type { Source } from "@/lib/contract/schemas";
import { DATA_SERIES, METHODOLOGY_NOTES, type DataSeries, type MethodologyNote } from "./general-seed";

export interface StoredDoc {
  key: string;
  title: string;
  type: string;
  description: string;
  updated_at: string;
  content: string;
}

export interface Frontmatter {
  type: string;
  title: string;
  description: string;
  tags: string[];
  status: "draft" | "stable";
  owners: string[];
  sensitivity: "client" | "public";
  generated: { by: string; at: string };
  stale_after: string;
  sources: Source[];
  data: Record<string, unknown>;
}

export function okfDocument(key: string, frontmatter: Frontmatter, body: string): StoredDoc {
  const yaml = stringify(frontmatter, { lineWidth: 0 }).trimEnd();
  return {
    key,
    title: frontmatter.title,
    type: frontmatter.type,
    description: frontmatter.description,
    updated_at: frontmatter.generated.at,
    content: `---\n${yaml}\n---\n\n${body.trim()}\n`,
  };
}

export function staleAfter(at: string, months = 3): string {
  const date = new Date(at);
  date.setUTCMonth(date.getUTCMonth() + months);
  return date.toISOString().replace(/\.\d{3}Z$/, "Z");
}

const SEED_AT = "2026-11-14T12:00:00Z";
function methodologyDoc(note: MethodologyNote): StoredDoc {
  return okfDocument(
    `general/methodologie/${note.slug}.md`,
    {
      type: "Methodology",
      title: note.title,
      description: note.description,
      tags: note.tags,
      status: "stable",
      owners: ["alphaforge-a6"],
      sensitivity: "public",
      generated: { by: "mock:simulateur", at: SEED_AT },
      stale_after: staleAfter(SEED_AT, 6),
      sources: note.sources,
      data: {},
    },
    note.body,
  );
}

function dataSeriesDoc(series: DataSeries): StoredDoc {
  return okfDocument(
    series.key,
    {
      type: "Data Series",
      title: series.title,
      description: series.description,
      tags: ["donnees-marche"],
      status: "stable",
      owners: ["alphaforge-a6"],
      sensitivity: "public",
      generated: { by: "mock:simulateur", at: SEED_AT },
      stale_after: staleAfter(SEED_AT, 1),
      sources: series.sources,
      data: series.data,
    },
    series.body,
  );
}

/** The general base as it starts: the methodology notes, the data series, and their index. */
export function generalSeed(): StoredDoc[] {
  const docs = [...METHODOLOGY_NOTES.map(methodologyDoc), ...DATA_SERIES.map(dataSeriesDoc)];
  docs.push(generalIndex(docs));
  return docs;
}

export function generalIndex(docs: StoredDoc[]): StoredDoc {
  const listed = docs.filter((doc) => doc.key !== "general/index.md");
  const lines = listed.map((doc) => `- [${doc.title}](${doc.key.replace(/^general\//, "")}) : ${doc.description}`);
  return okfDocument(
    "general/index.md",
    {
      type: "Index",
      title: "Base de connaissances d'AlphaForge AI",
      description: "Sommaire des méthodologies, actualités et séries de données communes à tous les investisseurs.",
      tags: ["index"],
      status: "stable",
      owners: ["alphaforge-a6"],
      sensitivity: "public",
      generated: { by: "mock:simulateur", at: listed.reduce((max, doc) => (doc.updated_at > max ? doc.updated_at : max), SEED_AT) },
      stale_after: staleAfter(SEED_AT, 1),
      sources: [],
      data: { documents: listed.length },
    },
    `# Base de connaissances d'AlphaForge AI

Commune à tous les investisseurs, elle ne contient aucun renseignement sur vous. Notre veille la tient à jour avec des actualités et des données, vérifiées (source et date) avant d'être ajoutées.

${lines.join("\n")}`,
  );
}
