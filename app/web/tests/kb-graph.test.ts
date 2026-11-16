import { describe, expect, it } from "vitest";
import { AgentRequest } from "@/lib/contract/requests";
import { KbListResponse, type KbItem } from "@/lib/contract/schemas";
import { buildKnowledgeGraph, nodeRelations, tickerId, visibleGraph, GRAPH_FAMILIES, type GraphFamily } from "@/lib/kb/graph";
import { labelText, placeLabels } from "@/lib/kb/labels";
import { fitTransform, layoutGraph, zoomAt } from "@/lib/kb/layout";
import { okfDocument, type Frontmatter } from "@/lib/mock/documents";
import { canonicalTicker, kbItemsWithRelations } from "@/lib/mock/kb-relations";
import { MockRuntime } from "@/lib/mock/runtime";
import { okfBaseRoot, resolveOkfLink } from "@/lib/okf";

const KNOWN = new Set([
  "general/notions/beta.md",
  "general/notions/volatilite.md",
  "general/methodologie/niveaux.md",
  "general/faits/bankofcanada-ca/2026-11-09-abc.md",
]);

const ALL: ReadonlySet<GraphFamily> = new Set(GRAPH_FAMILIES);

function item(key: string, links: string[] = [], tickers: string[] = []): KbItem {
  return { key, title: key.split("/").pop() ?? key, type: null, description: null, updated_at: null, links, tickers };
}

describe("resolveOkfLink (same rule as kb.list links, CONTRACTS.md 3.2)", () => {
  it("reads a link relative to the document's folder, then to the root of its base", () => {
    expect(resolveOkfLink("general/notions/beta.md", "volatilite.md", KNOWN)).toBe("general/notions/volatilite.md");
    expect(resolveOkfLink("general/notions/beta.md", "../methodologie/niveaux.md", KNOWN)).toBe("general/methodologie/niveaux.md");
    expect(resolveOkfLink("general/recherches/2026/11/x.md", "faits/bankofcanada-ca/2026-11-09-abc.md", KNOWN)).toBe(
      "general/faits/bankofcanada-ca/2026-11-09-abc.md",
    );
    expect(resolveOkfLink("general/notions/beta.md", "volatilite.md#calcul", KNOWN)).toBe("general/notions/volatilite.md");
    expect(resolveOkfLink("general/notions/beta.md", "../methodologie/niveaux%2Emd", KNOWN)).toBe("general/methodologie/niveaux.md");
  });

  it("ignores external, absolute, anchor-only and missing targets, and never leaves the base", () => {
    for (const href of ["https://www.bankofcanada.ca/x.md", "mailto:a@b.ca", "/general/notions/beta.md", "#calcul", "absent.md", "../../../x.md"]) {
      expect(resolveOkfLink("general/notions/beta.md", href, KNOWN)).toBeNull();
    }
    expect(resolveOkfLink("clients/c1/notes/a.md", "../../../general/notions/beta.md", KNOWN)).toBeNull();
    expect(okfBaseRoot("clients/8f0c/dimensions/horizon.md")).toBe("clients/8f0c/");
    expect(okfBaseRoot("general/notions/beta.md")).toBe("general/");
  });
});

describe("relations of the simulator's kb.list", () => {
  it("canonicalises symbols as the runtime does", () => {
    expect(canonicalTicker("shop.to")).toBe("SHOP.TO");
    expect(canonicalTicker("shop-to")).toBe("SHOP.TO");
    expect(canonicalTicker("BTC-USD")).toBe("BTC-USD");
    expect(canonicalTicker("apple inc.")).toBeNull();
  });

  it("keeps a tag as a symbol only when another document declares it", () => {
    const base: Omit<Frontmatter, "type" | "title" | "tags" | "data"> = {
      description: "d",
      status: "stable",
      owners: ["x"],
      sensitivity: "public",
      generated: { by: "x", at: "2026-11-14T00:00:00Z" },
      stale_after: "2027-01-01T00:00:00Z",
      sources: [],
    };
    const docs = [
      okfDocument("general/societes/aapl.md", { ...base, type: "Company Fundamentals", title: "Apple", tags: ["societes"], data: { ticker: "AAPL" } }, "Voir [le fait](../faits/y/f.md)."),
      okfDocument("general/faits/y/f.md", { ...base, type: "Fact", title: "Fait", tags: ["faits", "e2"], data: { tags: ["aapl", "cloture"] } }, "Aucun lien."),
    ];
    const [company, fact] = kbItemsWithRelations(docs);
    expect(company).toMatchObject({ key: "general/faits/y/f.md", tickers: ["AAPL"], links: [] });
    expect(fact).toMatchObject({ key: "general/societes/aapl.md", tickers: ["AAPL"], links: ["general/faits/y/f.md"] });
  });

  it("serves links and tickers through kb.list, with the seed's cross-links", async () => {
    const runtime = new MockRuntime({ delayScale: 0 });
    const list = KbListResponse.parse(await runtime.handle(AgentRequest.parse({ action: "kb.list", prefix: "general/" })));
    const byKey = new Map(list.items.map((entry) => [entry.key, entry]));
    expect(byKey.get("general/methodologie/profil-investisseur.md")?.links).toEqual([
      "general/methodologie/completude-du-profil.md",
      "general/methodologie/cadre-responsable.md",
    ]);
    expect(byKey.get("general/methodologie/expositions-du-portefeuille.md")?.links).toEqual(["general/donnees/usdcad/usdcad-2026-11.md"]);
    expect(list.items.every((entry) => Array.isArray(entry.links) && Array.isArray(entry.tickers))).toBe(true);
  });

  it("accepts items from a runtime release without links nor tickers", () => {
    const parsed = KbListResponse.parse({ ok: true, release: "old", items: [{ key: "general/notions/beta.md", title: "Bêta" }] });
    expect(parsed.items[0]?.links).toBeUndefined();
    expect(buildKnowledgeGraph(parsed.items).hasRelations).toBe(false);
  });
});

describe("knowledge graph", () => {
  const items = [
    item("general/index.md", ["general/notions/beta.md", "general/notions/volatilite.md"]),
    item("general/notions/beta.md", ["general/notions/volatilite.md", "general/absent.md", "general/notions/beta.md"]),
    item("general/notions/volatilite.md", ["general/notions/beta.md"]),
    item("general/societes/aapl.md", [], ["AAPL"]),
    item("general/actualites/2026/11/a.md", [], ["AAPL", "AAPL"]),
    item("general/actualites/2026/11/seule.md"),
  ];
  const graph = buildKnowledgeGraph(items);

  it("leaves the index out, merges mutual links and adds one node per symbol", () => {
    expect(graph.nodes.map((node) => node.id)).not.toContain("general/index.md");
    expect(graph.edges.filter((edge) => edge.kind === "link")).toHaveLength(1);
    expect(graph.edges.filter((edge) => edge.kind === "ticker")).toHaveLength(2);
    expect(graph.nodes.find((node) => node.id === tickerId("AAPL"))?.degree).toBe(2);
    expect(graph.nodes.find((node) => node.id === "general/actualites/2026/11/seule.md")?.degree).toBe(0);
    expect(graph.hasRelations).toBe(true);
  });

  it("filters by family, symbols and unlinked documents, never repainting a family", () => {
    const concepts = visibleGraph(graph, { families: new Set<GraphFamily>(["concepts"]), tickers: true, isolated: true });
    expect([...concepts.ids].sort()).toEqual(["general/notions/beta.md", "general/notions/volatilite.md"]);
    const linked = visibleGraph(graph, { families: ALL, tickers: true, isolated: false });
    expect(linked.ids.has("general/actualites/2026/11/seule.md")).toBe(false);
    const noTickers = visibleGraph(graph, { families: ALL, tickers: false, isolated: true });
    expect(noTickers.edges.every((edge) => edge.kind === "link")).toBe(true);
  });

  it("lists a document's links both ways, and a symbol's documents", () => {
    const beta = nodeRelations(graph, "general/notions/beta.md");
    expect(beta.linksTo.map((node) => node.id)).toEqual(["general/notions/volatilite.md"]);
    expect(beta.linkedFrom.map((node) => node.id)).toEqual(["general/notions/volatilite.md"]);
    expect(nodeRelations(graph, "general/societes/aapl.md").tickers.map((node) => node.label)).toEqual(["AAPL"]);
    expect(nodeRelations(graph, tickerId("AAPL")).documents.map((node) => node.id).sort()).toEqual([
      "general/actualites/2026/11/a.md",
      "general/societes/aapl.md",
    ]);
  });
});

describe("layout", () => {
  it("is deterministic, finite and places every node", () => {
    const items = Array.from({ length: 60 }, (_, index) =>
      item(`general/${["notions", "societes", "actualites"][index % 3]}/doc-${index}.md`, index > 0 ? [`general/notions/doc-${(index * 7) % index}.md`] : [], index % 5 === 0 ? ["AAPL"] : []),
    );
    const graph = buildKnowledgeGraph(items);
    const first = layoutGraph(graph);
    const second = layoutGraph(graph);
    expect([...first.positions.entries()]).toEqual([...second.positions.entries()]);
    expect(first.positions.size).toBe(graph.nodes.length);
    for (const { x, y } of first.positions.values()) {
      expect(Number.isFinite(x) && Number.isFinite(y)).toBe(true);
      expect(x).toBeGreaterThanOrEqual(first.bounds.minX);
      expect(y).toBeLessThanOrEqual(first.bounds.maxY);
    }
  });

  it("lays out the size of the real base quickly", () => {
    const items = Array.from({ length: 230 }, (_, index) => item(`general/actualites/doc-${index}.md`, [`general/actualites/doc-${(index * 13) % 230}.md`], [`T${index % 30}`]));
    const started = performance.now();
    layoutGraph(buildKnowledgeGraph(items));
    expect(performance.now() - started).toBeLessThan(1500);
  });

  it("fits the layout in the view, and zooms around a fixed point within limits", () => {
    const bounds = { minX: -100, minY: -50, maxX: 100, maxY: 50 };
    const fit = fitTransform(bounds, 500, 300, 50);
    expect(fit.k).toBeCloseTo(2);
    expect(fit.x).toBeCloseTo(250);
    expect(fit.y).toBeCloseTo(150);
    const zoomed = zoomAt(fit, 2, { x: 100, y: 100 }, { min: 1, max: 3 });
    expect(zoomed.k).toBe(3);
    expect((100 - zoomed.x) / zoomed.k).toBeCloseTo((100 - fit.x) / fit.k);
  });
});

describe("labels", () => {
  const items = Array.from({ length: 40 }, (_, index) =>
    item(`general/notions/doc-${index}.md`, [`general/notions/doc-${(index + 1) % 40}.md`, `general/notions/doc-${(index + 7) % 40}.md`], index % 4 === 0 ? [`T${index % 3}`] : []),
  );
  const graph = buildKnowledgeGraph(items);
  const layout = layoutGraph(graph);
  const visible = visibleGraph(graph, { families: ALL, tickers: true, isolated: true });
  const size = { width: 900, height: 600 };
  const view = fitTransform(layout.bounds, size.width, size.height);
  const context = { graph, visible, layout, view, active: null, selected: null, radiusOf: () => 6, gap: 5, size };

  it("labels every symbol it can and never overlaps two labels nor leaves the canvas", () => {
    const sides = placeLabels(context);
    expect(sides.has(tickerId("T0"))).toBe(true);
    const boxes = [...sides].map(([id, side]) => {
      const point = layout.positions.get(id)!;
      const width = labelText(graph.nodes.find((node) => node.id === id)!.label).length * 6.3;
      const x = view.k * point.x + view.x;
      const y = view.k * point.y + view.y;
      const left = { right: x + 11, left: x - 11 - width, above: x - width / 2, below: x - width / 2 }[side];
      const top = { right: y - 7.5, left: y - 7.5, above: y - 11 - 15, below: y + 11 }[side];
      return { left, top, right: left + width, bottom: top + 15 };
    });
    for (const [index, a] of boxes.entries()) {
      expect(a.left >= 0 && a.top >= 0 && a.right <= size.width && a.bottom <= size.height).toBe(true);
      for (const b of boxes.slice(index + 1)) expect(a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom).toBe(false);
    }
  });

  it("always labels the pointed and the selected node", () => {
    const sides = placeLabels({ ...context, active: "general/notions/doc-3.md", selected: "general/notions/doc-21.md" });
    expect(sides.has("general/notions/doc-3.md") && sides.has("general/notions/doc-21.md")).toBe(true);
  });
});
