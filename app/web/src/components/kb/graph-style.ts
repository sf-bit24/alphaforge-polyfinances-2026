import type { GraphFamily, GraphNode } from "@/lib/kb/graph";

/**
 * Family colours: the first three categorical slots of the chart palette, validated all-pairs
 * (any two nodes can be neighbours) on the white surface; symbols and "other" stay neutral.
 * Aqua sits below 3:1 on white, so the graph always ships its table view.
 */
export const FAMILY_FILL: Record<GraphFamily, string> = {
  concepts: "fill-kb-concepts",
  markets: "fill-kb-markets",
  news: "fill-kb-news",
  other: "fill-kb-other",
};

export const FAMILY_SWATCH: Record<GraphFamily, string> = {
  concepts: "bg-kb-concepts",
  markets: "bg-kb-markets",
  news: "bg-kb-news",
  other: "bg-kb-other",
};

/** Marker radius in pixels: at least 4 (an 8 px dot), a little larger for documents with many links. */
export function nodeRadius(node: GraphNode): number {
  return node.kind === "ticker" ? 5.5 : 4 + Math.min(5, 1.5 * Math.sqrt(node.degree));
}

export function shortLabel(label: string, max = 34): string {
  return label.length > max ? `${label.slice(0, max - 1).trimEnd()}…` : label;
}
