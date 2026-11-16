/**
 * Which nodes carry a direct label, and on which side, placed greedily on screen so that a label
 * never covers another label or another node: the pointed and selected nodes first (always), then
 * the selected node's neighbours, the symbols by number of documents, and a few of the most linked
 * documents. Each label tries the right, the left, above and below its node; one that fits nowhere
 * is dropped, and zooming in makes room for it again. The tooltip and the table keep every name.
 */
import type { GraphNode, KnowledgeGraph, VisibleGraph } from "./graph";
import type { GraphLayout, ViewTransform } from "./layout";

/** Documents labelled without hovering: the most linked ones, for orientation. */
const HUB_LABELS = 8;
/** A selected node labels its neighbours when it has this many or fewer. */
const NEIGHBOUR_LABELS = 12;
/** Approximate advance of an 11 px medium character, and the label box height, in pixels. */
const CHAR_WIDTH = 6.3;
const LABEL_HEIGHT = 15;
export const LABEL_MAX = 34;

interface Box {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

const overlaps = (a: Box, b: Box) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;

export function labelText(label: string): string {
  return label.length > LABEL_MAX ? `${label.slice(0, LABEL_MAX - 1).trimEnd()}…` : label;
}

function byDegree(a: GraphNode, b: GraphNode): number {
  return b.degree - a.degree || a.label.localeCompare(b.label);
}

function candidates(graph: KnowledgeGraph, visible: VisibleGraph, active: string | null, selected: string | null): string[] {
  const near = selected ? [...(graph.neighbours.get(selected) ?? [])].filter((id) => visible.ids.has(id)) : [];
  const tickers = visible.nodes.filter((node) => node.kind === "ticker").sort(byDegree);
  const hubs = visible.nodes.filter((node) => node.kind === "document" && node.degree > 0).sort(byDegree).slice(0, HUB_LABELS);
  const ordered = [active, selected, ...(near.length <= NEIGHBOUR_LABELS ? near : []), ...tickers.map((node) => node.id), ...hubs.map((node) => node.id)];
  return [...new Set(ordered.filter((id): id is string => id !== null && visible.ids.has(id)))];
}

export type LabelSide = "right" | "left" | "above" | "below";

const SIDES: readonly LabelSide[] = ["right", "left", "above", "below"];

/** Screen box of a label of `width` on `side` of a node centred at (`x`, `y`), `offset` pixels away. */
const BOX_AT: Record<LabelSide, (x: number, y: number, offset: number, width: number) => Box> = {
  right: (x, y, offset, width) => ({ left: x + offset, top: y - LABEL_HEIGHT / 2, right: x + offset + width, bottom: y + LABEL_HEIGHT / 2 }),
  left: (x, y, offset, width) => ({ left: x - offset - width, top: y - LABEL_HEIGHT / 2, right: x - offset, bottom: y + LABEL_HEIGHT / 2 }),
  above: (x, y, offset, width) => ({ left: x - width / 2, top: y - offset - LABEL_HEIGHT, right: x + width / 2, bottom: y - offset }),
  below: (x, y, offset, width) => ({ left: x - width / 2, top: y + offset, right: x + width / 2, bottom: y + offset + LABEL_HEIGHT }),
};

export interface LabelContext {
  graph: KnowledgeGraph;
  visible: VisibleGraph;
  layout: GraphLayout;
  view: ViewTransform;
  active: string | null;
  selected: string | null;
  /** Marker radius of a node, in pixels. */
  radiusOf: (node: GraphNode) => number;
  /** Space between a marker and its label, in pixels. */
  gap: number;
  /** Size of the canvas: a label never runs off its edges. */
  size: { width: number; height: number };
}

interface Marker {
  id: string;
  box: Box;
}

function markersOf({ visible, layout, view, radiusOf }: LabelContext): Marker[] {
  return visible.nodes.flatMap((node) => {
    const point = layout.positions.get(node.id);
    if (!point) return [];
    const x = view.k * point.x + view.x;
    const y = view.k * point.y + view.y;
    const radius = radiusOf(node);
    return [{ id: node.id, box: { left: x - radius, top: y - radius, right: x + radius, bottom: y + radius } }];
  });
}

/**
 * The first side whose box stays inside the canvas, clear of every placed label and of the other markers; else
 * the first inside and clear of labels only (another label is a hard obstacle, a marker a soft one: in a dense cluster the halo keeps the
 * text legible); else, for a label that must show, the right side.
 */
interface Obstacles {
  placed: Box[];
  others: Box[];
  frame: Box;
}

function chooseSide(boxOf: (side: LabelSide) => Box, { placed, others, frame }: Obstacles, forced: boolean): LabelSide | null {
  const clearOf = (boxes: Box[]) => (side: LabelSide) => !boxes.some((box) => overlaps(boxOf(side), box));
  const inside = (side: LabelSide) => {
    const box = boxOf(side);
    return box.left >= frame.left && box.top >= frame.top && box.right <= frame.right && box.bottom <= frame.bottom;
  };
  const clearOfLabels = (side: LabelSide) => inside(side) && clearOf(placed)(side);
  const clearOfMarkers = clearOf(others);
  return SIDES.find((side) => clearOfLabels(side) && clearOfMarkers(side)) ?? SIDES.find(clearOfLabels) ?? (forced ? "right" : null);
}

export function placeLabels(context: LabelContext): Map<string, LabelSide> {
  const { graph, visible, layout, view, active, selected, radiusOf, gap, size } = context;
  const frame = { left: 0, top: 0, right: size.width, bottom: size.height };
  const nodes = new Map(visible.nodes.map((node) => [node.id, node]));
  const markers = markersOf(context);
  const placed: Box[] = [];
  const sides = new Map<string, LabelSide>();
  for (const id of candidates(graph, visible, active, selected)) {
    const node = nodes.get(id);
    const point = layout.positions.get(id);
    if (!node || !point) continue;
    const width = labelText(node.label).length * CHAR_WIDTH;
    const boxOf = (side: LabelSide) => BOX_AT[side](view.k * point.x + view.x, view.k * point.y + view.y, radiusOf(node) + gap, width);
    const others = markers.filter((marker) => marker.id !== id).map((marker) => marker.box);
    const side = chooseSide(boxOf, { placed, others, frame }, id === active || id === selected);
    if (side === null) continue;
    placed.push(boxOf(side));
    sides.set(id, side);
  }
  return sides;
}
