/**
 * Deterministic force-directed layout of the knowledge graph (Fruchterman–Reingold), computed once.
 * Every pair of nodes pushes apart, linked nodes pull together, and each node drifts toward the
 * anchor of its family, so the three families read as regions while links still cross between them.
 * Symbols sit in the middle, between the documents that cite them.
 *
 * The same documents always give the same picture: each node starts from a position drawn by a
 * generator seeded with its own id, so a new document does not reshuffle the others.
 */
import type { GraphFamily, GraphNode, KnowledgeGraph } from "./graph";

export interface Point {
  x: number;
  y: number;
}

export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export interface GraphLayout {
  positions: ReadonlyMap<string, Point>;
  bounds: Bounds;
}

/** Ideal distance between two linked nodes, in layout units. */
const SPACING = 30;
const ITERATIONS = 300;
const GRAVITY = 0.06;
const ANCHOR_ANGLE: Record<GraphFamily, number> = {
  concepts: (-5 * Math.PI) / 6,
  markets: -Math.PI / 6,
  news: Math.PI / 2,
  other: 0,
};

interface Body {
  x: number;
  y: number;
  dx: number;
  dy: number;
  anchor: Point;
}

/** FNV-1a: a stable 32-bit seed for a node id. */
function seedOf(text: string): number {
  let hash = 2166136261;
  for (let index = 0; index < text.length; index++) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

/** mulberry32: a small seeded generator, uniform on [0, 1). */
function generator(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let value = Math.imul(state ^ (state >>> 15), 1 | state);
    value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value;
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function anchorOf(node: GraphNode, ring: number): Point {
  if (node.kind === "ticker" || node.family === "other") return { x: 0, y: 0 };
  const angle = ANCHOR_ANGLE[node.family];
  return { x: Math.cos(angle) * ring, y: Math.sin(angle) * ring };
}

function initialBodies(nodes: GraphNode[], ring: number): Body[] {
  return nodes.map((node) => {
    const anchor = anchorOf(node, ring);
    const random = generator(seedOf(node.id));
    const angle = random() * 2 * Math.PI;
    const distance = Math.sqrt(random()) * ring * 0.6;
    return { x: anchor.x + Math.cos(angle) * distance, y: anchor.y + Math.sin(angle) * distance, dx: 0, dy: 0, anchor };
  });
}

function repel(bodies: Body[]): void {
  const strength = SPACING * SPACING;
  for (let i = 0; i < bodies.length; i++) {
    const a = bodies[i]!;
    for (let j = i + 1; j < bodies.length; j++) {
      const b = bodies[j]!;
      const ddx = a.x - b.x;
      const ddy = a.y - b.y;
      const force = strength / (ddx * ddx + ddy * ddy || 0.01);
      a.dx += ddx * force;
      a.dy += ddy * force;
      b.dx -= ddx * force;
      b.dy -= ddy * force;
    }
  }
}

/** A link between two well-linked nodes pulls less (as d3-force does): a dense cluster spreads instead of collapsing. */
interface Link {
  a: Body;
  b: Body;
  weight: number;
}

function attract(links: Link[]): void {
  for (const { a, b, weight } of links) {
    const ddx = a.x - b.x;
    const ddy = a.y - b.y;
    const force = (Math.hypot(ddx, ddy) / SPACING) * weight;
    a.dx -= ddx * force;
    a.dy -= ddy * force;
    b.dx += ddx * force;
    b.dy += ddy * force;
  }
}

function settle(bodies: Body[], temperature: number): void {
  for (const body of bodies) {
    body.dx += (body.anchor.x - body.x) * GRAVITY * SPACING;
    body.dy += (body.anchor.y - body.y) * GRAVITY * SPACING;
    const length = Math.hypot(body.dx, body.dy);
    if (length > 0) {
      const step = Math.min(length, temperature) / length;
      body.x += body.dx * step;
      body.y += body.dy * step;
    }
    body.dx = 0;
    body.dy = 0;
  }
}

/** Bounds of the points; a zero box at the origin when there are none. */
export function boundsOf(points: Iterable<Point>): Bounds {
  const bounds = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
  for (const { x, y } of points) {
    bounds.minX = Math.min(bounds.minX, x);
    bounds.minY = Math.min(bounds.minY, y);
    bounds.maxX = Math.max(bounds.maxX, x);
    bounds.maxY = Math.max(bounds.maxY, y);
  }
  return Number.isFinite(bounds.minX) ? bounds : { minX: 0, minY: 0, maxX: 0, maxY: 0 };
}

function linksOf(graph: KnowledgeGraph, byId: ReadonlyMap<string, Body>): Link[] {
  const degree = (id: string) => graph.neighbours.get(id)?.size ?? 1;
  return graph.edges.flatMap((edge) => {
    const a = byId.get(edge.source);
    const b = byId.get(edge.target);
    return a && b ? [{ a, b, weight: 1 / Math.min(degree(edge.source), degree(edge.target)) }] : [];
  });
}

export function layoutGraph(graph: KnowledgeGraph): GraphLayout {
  const ring = SPACING * Math.sqrt(graph.nodes.length) * 0.75;
  const bodies = initialBodies(graph.nodes, ring);
  const links = linksOf(graph, new Map(graph.nodes.map((node, index) => [node.id, bodies[index]!])));
  let temperature = ring / 3;
  const cooling = Math.pow(0.02, 1 / ITERATIONS);
  for (let step = 0; step < ITERATIONS; step++) {
    repel(bodies);
    attract(links);
    settle(bodies, temperature);
    temperature *= cooling;
  }
  const positions = new Map(graph.nodes.map((node, index) => [node.id, { x: bodies[index]!.x, y: bodies[index]!.y }]));
  return { positions, bounds: boundsOf(positions.values()) };
}

/** Screen transform of the layout: `screen = k * point + (x, y)`. */
export interface ViewTransform {
  k: number;
  x: number;
  y: number;
}

/** The transform that centres the layout in a `width` × `height` view, with `padding` pixels around it. */
export function fitTransform(bounds: Bounds, width: number, height: number, padding = 48): ViewTransform {
  const spanX = Math.max(bounds.maxX - bounds.minX, 1);
  const spanY = Math.max(bounds.maxY - bounds.minY, 1);
  const k = Math.max(Math.min((width - 2 * padding) / spanX, (height - 2 * padding) / spanY, 2), 0.05);
  return { k, x: width / 2 - (k * (bounds.minX + bounds.maxX)) / 2, y: height / 2 - (k * (bounds.minY + bounds.maxY)) / 2 };
}

/** Zoom by `factor` around the screen point (`cx`, `cy`), the scale kept within [`min`, `max`]. */
export function zoomAt(view: ViewTransform, factor: number, center: Point, limits: { min: number; max: number }): ViewTransform {
  const k = Math.min(Math.max(view.k * factor, limits.min), limits.max);
  const ratio = k / view.k;
  return { k, x: center.x - (center.x - view.x) * ratio, y: center.y - (center.y - view.y) * ratio };
}
