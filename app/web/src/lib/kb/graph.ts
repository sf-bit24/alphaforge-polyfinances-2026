/**
 * Graph of the general base: its documents and the symbols they are about, joined by the
 * `links` and `tickers` of `kb.list` (CONTRACTS.md, section 3.2). Pure functions, no layout.
 *
 * The index (`general/index.md`) is left out: it links to every document, so it would tie
 * everything to one hub and hide the links the documents make themselves.
 */
import type { KbItem } from "@/lib/contract/schemas";
import { generalGroup } from "@/lib/okf";

/** Colour families: three categorical slots at most, because any two nodes can sit side by side. */
export const GRAPH_FAMILIES = ["concepts", "markets", "news", "other"] as const;
export type GraphFamily = (typeof GRAPH_FAMILIES)[number];

const FAMILY_OF_GROUP: Record<string, GraphFamily> = {
  methodologie: "concepts",
  notions: "concepts",
  societes: "markets",
  donnees: "markets",
  faits: "markets",
  signaux: "markets",
  depots: "markets",
  actualites: "news",
  recherches: "news",
};

export function familyOf(key: string): GraphFamily {
  return FAMILY_OF_GROUP[generalGroup(key)] ?? "other";
}

export interface DocumentNode {
  id: string;
  kind: "document";
  label: string;
  family: GraphFamily;
  group: string;
  item: KbItem;
  degree: number;
}

export interface TickerNode {
  id: string;
  kind: "ticker";
  label: string;
  degree: number;
}

export type GraphNode = DocumentNode | TickerNode;

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: "link" | "ticker";
}

export interface KnowledgeGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** Ids of each node's neighbours. */
  neighbours: ReadonlyMap<string, ReadonlySet<string>>;
  /** False when the runtime sent neither `links` nor `tickers` (a release older than the graph). */
  hasRelations: boolean;
}

export const tickerId = (ticker: string) => `ticker:${ticker}`;

function linkEdges(documents: KbItem[], keys: ReadonlySet<string>): GraphEdge[] {
  const edges = new Map<string, GraphEdge>();
  for (const item of documents) {
    for (const target of item.links ?? []) {
      if (target === item.key || !keys.has(target)) continue;
      const pair = item.key < target ? `${item.key}|${target}` : `${target}|${item.key}`;
      if (!edges.has(pair)) edges.set(pair, { id: `link:${pair}`, source: item.key, target, kind: "link" });
    }
  }
  return [...edges.values()];
}

function tickerEdges(documents: KbItem[]): GraphEdge[] {
  return documents.flatMap((item) =>
    [...new Set(item.tickers ?? [])].map((ticker) => ({ id: `ticker:${item.key}|${ticker}`, source: item.key, target: tickerId(ticker), kind: "ticker" as const })),
  );
}

function neighbourMap(edges: GraphEdge[]): Map<string, Set<string>> {
  const map = new Map<string, Set<string>>();
  const add = (from: string, to: string) => map.set(from, (map.get(from) ?? new Set()).add(to));
  for (const edge of edges) {
    add(edge.source, edge.target);
    add(edge.target, edge.source);
  }
  return map;
}

export function buildKnowledgeGraph(items: KbItem[]): KnowledgeGraph {
  const documents = items.filter((item) => generalGroup(item.key) !== "index");
  const keys = new Set(documents.map((item) => item.key));
  const edges = [...linkEdges(documents, keys), ...tickerEdges(documents)];
  const neighbours = neighbourMap(edges);
  const degree = (id: string) => neighbours.get(id)?.size ?? 0;
  const tickers = [...new Set(documents.flatMap((item) => item.tickers ?? []))].sort();
  const nodes: GraphNode[] = [
    ...documents.map((item): DocumentNode => {
      const group = generalGroup(item.key);
      return { id: item.key, kind: "document", label: item.title || item.key, family: familyOf(item.key), group, item, degree: degree(item.key) };
    }),
    ...tickers.map((ticker): TickerNode => ({ id: tickerId(ticker), kind: "ticker", label: ticker, degree: degree(tickerId(ticker)) })),
  ];
  return { nodes, edges, neighbours, hasRelations: items.some((item) => item.links !== undefined || item.tickers !== undefined) };
}

export interface GraphFilter {
  families: ReadonlySet<GraphFamily>;
  tickers: boolean;
  isolated: boolean;
}

export interface VisibleGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  ids: ReadonlySet<string>;
}

/** The nodes and edges the filters keep; a symbol stays only while one of its documents is shown. */
export function visibleGraph(graph: KnowledgeGraph, filter: GraphFilter): VisibleGraph {
  const documents = graph.nodes.filter(
    (node): node is DocumentNode => node.kind === "document" && filter.families.has(node.family) && (filter.isolated || node.degree > 0),
  );
  const shown = new Set<string>(documents.map((node) => node.id));
  const tickers = filter.tickers
    ? graph.nodes.filter((node) => node.kind === "ticker" && [...(graph.neighbours.get(node.id) ?? [])].some((id) => shown.has(id)))
    : [];
  for (const node of tickers) shown.add(node.id);
  const edges = graph.edges.filter((edge) => shown.has(edge.source) && shown.has(edge.target));
  return { nodes: [...documents, ...tickers], edges, ids: shown };
}

export interface NodeRelations {
  linksTo: DocumentNode[];
  linkedFrom: DocumentNode[];
  tickers: TickerNode[];
  documents: DocumentNode[];
}

/** What the details panel lists for a node: the documents it links to and those that cite it, or a symbol's documents. */
export function nodeRelations(graph: KnowledgeGraph, id: string): NodeRelations {
  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  const documentsOf = (ids: Iterable<string>) =>
    [...ids].map((key) => byId.get(key)).filter((node): node is DocumentNode => node?.kind === "document");
  const node = byId.get(id);
  if (node?.kind !== "document") {
    return { linksTo: [], linkedFrom: [], tickers: [], documents: documentsOf(graph.neighbours.get(id) ?? []) };
  }
  const linkedFrom = graph.nodes.filter(
    (other): other is DocumentNode => other.kind === "document" && other.id !== id && (other.item.links ?? []).includes(id),
  );
  const tickers = [...new Set(node.item.tickers ?? [])].map((ticker) => byId.get(tickerId(ticker))).filter((other): other is TickerNode => other?.kind === "ticker");
  const linksTo = documentsOf(new Set((node.item.links ?? []).filter((key) => key !== id)));
  return { linksTo, linkedFrom, tickers, documents: [] };
}
