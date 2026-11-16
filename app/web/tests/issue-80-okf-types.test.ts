import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { matchingItems } from "@/components/kb/match";
import type { KbItem } from "@/lib/contract/schemas";
import { OKF_TYPES, okfTypeLabel } from "@/lib/i18n/okf-types";
import { parseOkf } from "@/lib/okf";

const path = (relative: string) => fileURLToPath(new URL(relative, import.meta.url));

/** `DOC_TYPES` of the Python runtimes, read from okf.py. */
function pythonDocTypes(): string[] {
  const source = readFileSync(path("../../agents/src/alphaforge/okf.py"), "utf8");
  const block = /^DOC_TYPES = \(([\s\S]*?)^\)/m.exec(source)?.[1] ?? "";
  const code = block.replace(/#.*$/gm, "");
  return [...code.matchAll(/"([^"]+)"/g)].map((match) => match[1] ?? "");
}

/** The `type` of every seed document of app/knowledge/general/. */
function seedTypes(): string[] {
  const root = path("../../knowledge/general/");
  const files = readdirSync(root, { recursive: true, encoding: "utf8" }).filter((file) => file.endsWith(".md"));
  return files.map((file) => String(parseOkf(readFileSync(join(root, file), "utf8")).frontmatter?.type ?? ""));
}

/** The OKF types the mock simulator writes (`type: "…"` in src/lib/mock/). */
function mockTypes(): string[] {
  const root = path("../src/lib/mock/");
  const files = readdirSync(root).filter((file) => file.endsWith(".ts"));
  return files.flatMap((file) => [...readFileSync(join(root, file), "utf8").matchAll(/\btype: "([A-Z][A-Za-z ]+)"/g)].map((match) => match[1] ?? ""));
}

describe("okfTypeLabel (#80)", () => {
  it("translates the types seen in the e2e test into French", () => {
    expect(okfTypeLabel("Methodology", "fr")).toBe("Méthodologie");
    expect(okfTypeLabel("Data Series", "fr")).toBe("Série de données");
    expect(okfTypeLabel("News", "fr")).toBe("Actualité");
    expect(okfTypeLabel("Index", "fr")).toBe("Sommaire");
    expect(okfTypeLabel("Profile Note", "fr")).toBe("Note de profil");
    expect(okfTypeLabel("Profile Journal", "fr")).toBe("Journal du profil");
    expect(okfTypeLabel("Investor Profile", "fr")).toBe("Profil d’investisseur");
    expect(okfTypeLabel("Portfolio Decision", "fr")).toBe("Décision de portefeuille");
    expect(okfTypeLabel("Financial Concept", "fr")).toBe("Notion financière");
    expect(okfTypeLabel("Existing Portfolio", "fr")).toBe("Portefeuille existant");
    // Same names as the general/ folders (t.kb.groups) and the sections of A6's index.
    expect(okfTypeLabel("Market Signal", "fr")).toBe("Signal de contexte");
    expect(okfTypeLabel("Fact", "fr")).toBe("Fait sourcé");
  });

  it("gives English labels in sentence case", () => {
    expect(okfTypeLabel("Data Series", "en")).toBe("Data series");
    expect(okfTypeLabel("Profile Note", "en")).toBe("Profile note");
    expect(okfTypeLabel("Investor Profile", "en")).toBe("Investor profile");
    expect(okfTypeLabel("Fact", "en")).toBe("Sourced fact");
    expect(okfTypeLabel("Market Signal", "en")).toBe("Context signal");
    expect(okfTypeLabel("News", "en")).toBe("News");
  });

  it("falls back to the raw value of an unknown type", () => {
    for (const locale of ["fr", "en"] as const) {
      expect(okfTypeLabel("Custom Type", locale)).toBe("Custom Type");
      expect(okfTypeLabel("data series", locale)).toBe("data series");
      expect(okfTypeLabel("", locale)).toBe("");
      // Not a key of the table, even though every object has it.
      expect(okfTypeLabel("toString", locale)).toBe("toString");
      expect(okfTypeLabel("constructor", locale)).toBe("constructor");
    }
  });

  it("labels every type the runtimes, the seeds and the simulator write", () => {
    const python = pythonDocTypes();
    expect(python).toContain("Portfolio Decision");
    const written = new Set([...python, ...seedTypes(), ...mockTypes()]);
    expect(written.size).toBeGreaterThan(15);
    for (const type of written) expect(OKF_TYPES).toContain(type);
  });

  it("translates every known type into French", () => {
    for (const type of OKF_TYPES) {
      expect(okfTypeLabel(type, "fr")).not.toBe("");
      expect(okfTypeLabel(type, "en")).not.toBe("");
      expect(okfTypeLabel(type, "fr")).not.toBe(type);
    }
  });
});

describe("matchingItems (#80)", () => {
  const items: KbItem[] = [
    { key: "general/donnees/xiu-to.md", title: "XIU.TO, cours quotidiens", type: "Data Series", description: "Série Yahoo Finance" },
    { key: "general/methodologie/risque.md", title: "Mesure du risque", type: "Methodology", description: null },
    { key: "general/actualites/2026/11/a.md", title: "Banque du Canada", type: "News" },
    { key: "general/index.md", title: "Index de la base", type: "Index" },
    { key: "general/societes/atd.md", title: "Alimentation Couche-Tard", type: "Company Fundamentals" },
    { key: "general/autre.md", title: "Sans type", type: null },
  ];
  const keys = (query: string, locale: "fr" | "en") => matchingItems(items, query, locale).map((item) => item.key);

  it("finds a document by its translated type", () => {
    expect(keys("méthodologie", "fr")).toEqual(["general/methodologie/risque.md"]);
    expect(keys("Actualité", "fr")).toEqual(["general/actualites/2026/11/a.md"]);
    expect(keys("série de données", "fr")).toEqual(["general/donnees/xiu-to.md"]);
  });

  it("ignores accents and case", () => {
    expect(keys("SERIE DE", "fr")).toEqual(["general/donnees/xiu-to.md"]);
    expect(keys("actualite", "fr")).toEqual(["general/actualites/2026/11/a.md"]);
    // Typed with a straight apostrophe, the label has a typographic one.
    expect(keys("fondamentaux d'une", "fr")).toEqual(["general/societes/atd.md"]);
    expect(keys("Fondamentaux d’une société", "fr")).toEqual(["general/societes/atd.md"]);
  });

  it("still finds a document by its raw type, key, title or description", () => {
    expect(keys("Data Series", "fr")).toEqual(["general/donnees/xiu-to.md"]);
    expect(keys("news", "en")).toEqual(["general/actualites/2026/11/a.md"]);
    expect(keys("xiu-to", "fr")).toEqual(["general/donnees/xiu-to.md"]);
    expect(keys("banque du", "en")).toEqual(["general/actualites/2026/11/a.md"]);
    expect(keys("yahoo", "fr")).toEqual(["general/donnees/xiu-to.md"]);
  });

  it("searches the label of the current language only", () => {
    expect(keys("série de données", "en")).toEqual([]);
    expect(keys("data series", "en")).toEqual(["general/donnees/xiu-to.md"]);
  });

  it("returns every document for an empty query", () => {
    expect(keys("  ", "fr")).toHaveLength(items.length);
  });
});
