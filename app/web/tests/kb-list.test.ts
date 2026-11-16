import { describe, expect, it } from "vitest";
import type { KbItem } from "@/lib/contract/schemas";
import { groupedItems } from "@/components/kb/document-list";
import { matchingNodes } from "@/components/kb/match";

function item(key: string, title: string, updated_at: string | null = null): KbItem {
  return { key, title, type: null, description: null, updated_at };
}

describe("document list", () => {
  it("orders folders as the base does, dated folders newest first and the others by title", () => {
    const groups = groupedItems(
      [
        item("general/actualites/2026/11/a.md", "Ancienne", "2026-11-02T10:00:00Z"),
        item("general/notions/volatilite.md", "Volatilité"),
        item("general/actualites/2026/11/b.md", "Récente", "2026-11-14T10:00:00Z"),
        item("general/notions/beta.md", "Bêta"),
        item("general/index.md", "Base générale"),
      ],
      "fr",
    );
    expect(groups.map(({ group }) => group)).toEqual(["index", "notions", "actualites"]);
    expect(groups[1]?.items.map((entry) => entry.title)).toEqual(["Bêta", "Volatilité"]);
    expect(groups[2]?.items.map((entry) => entry.title)).toEqual(["Récente", "Ancienne"]);
  });
});

describe("graph search", () => {
  const nodes = [
    { id: "general/notions/volatilite.md", label: "Volatilité implicite" },
    { id: "general/notions/beta.md", label: "Bêta d’un titre" },
    { id: "ticker:RY.TO", label: "RY.TO" },
    { id: "general/societes/ry-to.md", label: "Banque Royale" },
  ];

  it("finds names without accents, a name that starts with the query first, then keys", () => {
    expect(matchingNodes(nodes, "beta").map((node) => node.id)).toEqual(["general/notions/beta.md"]);
    expect(matchingNodes(nodes, "ry").map((node) => node.id)).toEqual(["ticker:RY.TO", "general/societes/ry-to.md"]);
    expect(matchingNodes(nodes, "titre").map((node) => node.label)).toEqual(["Bêta d’un titre"]);
    expect(matchingNodes(nodes, "  ")).toHaveLength(4);
  });
});
