"use client";

import { Minus, Plus, Scan } from "lucide-react";
import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { GraphEdge, GraphNode, KnowledgeGraph, VisibleGraph } from "@/lib/kb/graph";
import { labelText, placeLabels, type LabelSide } from "@/lib/kb/labels";
import { boundsOf, type GraphLayout, type Point, type ViewTransform } from "@/lib/kb/layout";
import { useI18n } from "@/lib/i18n/provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/components/ui/cn";
import { FAMILY_FILL, nodeRadius, shortLabel } from "./graph-style";
import { useNodeText } from "./graph-text";
import { useGraphViewport, type GraphViewport } from "./use-graph-viewport";

/** Hover and focus area of a node, in pixels: 24 px across at least, more than the mark itself. */
const HIT_RADIUS = 12;
const LABEL_GAP = 5;

const NAV_STEP: Record<string, (index: number, count: number) => number> = {
  ArrowRight: (index, count) => (index + 1) % count,
  ArrowDown: (index, count) => (index + 1) % count,
  ArrowLeft: (index, count) => (index - 1 + count) % count,
  ArrowUp: (index, count) => (index - 1 + count) % count,
  Home: () => 0,
  End: (_index, count) => count - 1,
};

interface Highlight {
  active: string | null;
  related: ReadonlySet<string>;
}

function highlightOf(graph: KnowledgeGraph, active: string | null): Highlight {
  if (!active) return { active: null, related: new Set() };
  return { active, related: new Set([active, ...(graph.neighbours.get(active) ?? [])]) };
}

const dimmedIn = (highlight: Highlight, id: string) => highlight.active !== null && !highlight.related.has(id);

function EdgeLines({ edges, positions, highlight }: { edges: GraphEdge[]; positions: ReadonlyMap<string, Point>; highlight: Highlight }) {
  const incident = (edge: GraphEdge) => highlight.active !== null && (edge.source === highlight.active || edge.target === highlight.active);
  const ordered = [...edges].sort((a, b) => Number(incident(a)) - Number(incident(b)));
  return (
    <g aria-hidden>
      {ordered.map((edge) => {
        const from = positions.get(edge.source);
        const to = positions.get(edge.target);
        if (!from || !to) return null;
        const lit = incident(edge);
        const tone = edge.kind === "link" ? "stroke-ink-400" : "stroke-ink-300";
        return (
          <line
            key={edge.id}
            x1={from.x}
            y1={from.y}
            x2={to.x}
            y2={to.y}
            vectorEffect="non-scaling-stroke"
            strokeWidth={lit ? 1.5 : 1}
            className={cn(lit ? "stroke-ink-600" : tone, highlight.active && !lit ? "opacity-15" : "opacity-80")}
          />
        );
      })}
    </g>
  );
}

function Glyph({ node }: { node: GraphNode }) {
  const radius = nodeRadius(node);
  if (node.kind === "ticker") {
    return <rect x={-radius} y={-radius} width={radius * 2} height={radius * 2} rx={1} transform="rotate(45)" className="fill-ink-700 stroke-white" strokeWidth={2} />;
  }
  return <circle r={radius} className={cn(FAMILY_FILL[node.family], "stroke-white")} strokeWidth={2} />;
}

interface NodeHandlers {
  register: (id: string, element: SVGGElement | null) => void;
  hover: (id: string | null) => void;
  focus: (id: string | null, visible: boolean) => void;
  activate: (id: string) => void;
  keyDown: (event: KeyboardEvent<SVGGElement>, id: string) => void;
}

interface NodeMarkProps {
  node: GraphNode;
  point: Point;
  scale: number;
  status: { selected: boolean; dimmed: boolean; tabbable: boolean; focusRing: boolean };
  handlers: NodeHandlers;
}

function NodeMark({ node, point, scale, status, handlers }: NodeMarkProps) {
  const text = useNodeText(node);
  return (
    <g
      ref={(element) => handlers.register(node.id, element)}
      transform={`translate(${point.x} ${point.y}) scale(${1 / scale})`}
      role="button"
      tabIndex={status.tabbable ? 0 : -1}
      aria-label={text.accessible}
      aria-pressed={status.selected}
      className={cn("cursor-pointer outline-none transition-opacity", status.dimmed && "opacity-20")}
      onPointerEnter={() => handlers.hover(node.id)}
      onPointerLeave={() => handlers.hover(null)}
      onFocus={(event) => handlers.focus(node.id, event.currentTarget.matches(":focus-visible"))}
      onBlur={() => handlers.focus(null, false)}
      onClick={() => handlers.activate(node.id)}
      onKeyDown={(event) => handlers.keyDown(event, node.id)}
    >
      <circle r={HIT_RADIUS} fill="transparent" />
      {status.selected ? <circle r={nodeRadius(node) + 4} fill="none" className="stroke-navy" strokeWidth={2} /> : null}
      {status.focusRing ? <circle r={nodeRadius(node) + 8} fill="none" className="stroke-focus" strokeWidth={2} /> : null}
      <Glyph node={node} />
    </g>
  );
}

interface LayerProps {
  visible: VisibleGraph;
  layout: GraphLayout;
  scale: number;
  highlight: Highlight;
}

function NodeLayer({ visible, layout, scale, highlight, selected, canvas }: LayerProps & { selected: string | null; canvas: ReturnType<typeof useCanvasState> }) {
  return visible.nodes.map((node) => {
    const point = layout.positions.get(node.id);
    if (!point) return null;
    const status = {
      selected: node.id === selected,
      dimmed: dimmedIn(highlight, node.id),
      tabbable: node.id === canvas.tabStop,
      focusRing: node.id === canvas.focusRing,
    };
    return <NodeMark key={node.id} node={node} point={point} scale={scale} status={status} handlers={canvas.handlers} />;
  });
}

/** Where the text of a label sits, from its node's centre: `offset` is the marker radius plus the gap. */
const TEXT_AT: Record<LabelSide, (offset: number) => { x: number; y: number; textAnchor: "start" | "end" | "middle" }> = {
  right: (offset) => ({ x: offset, y: 4, textAnchor: "start" }),
  left: (offset) => ({ x: -offset, y: 4, textAnchor: "end" }),
  above: (offset) => ({ x: 0, y: -offset - 3, textAnchor: "middle" }),
  below: (offset) => ({ x: 0, y: offset + 11, textAnchor: "middle" }),
};

/** Direct labels, above every node; they never catch the pointer, so they cannot hide a node from it. */
function LabelLayer({ visible, layout, scale, highlight, labelled }: LayerProps & { labelled: ReadonlyMap<string, LabelSide> }) {
  return (
    <g aria-hidden className="pointer-events-none">
      {visible.nodes.map((node) => {
        const point = layout.positions.get(node.id);
        const side = labelled.get(node.id);
        if (!point || !side) return null;
        return (
          <g key={node.id} transform={`translate(${point.x} ${point.y}) scale(${1 / scale})`} className={cn(dimmedIn(highlight, node.id) && "opacity-20")}>
            <text {...TEXT_AT[side](nodeRadius(node) + LABEL_GAP)} className="fill-ink-900 stroke-white text-[11px] font-medium" strokeWidth={3} paintOrder="stroke">
              {labelText(node.label)}
            </text>
          </g>
        );
      })}
    </g>
  );
}

function Tooltip({ node, point, view, size }: { node: GraphNode; point: Point; view: ViewTransform; size: { width: number; height: number } }) {
  const text = useNodeText(node);
  const x = view.k * point.x + view.x;
  const y = view.k * point.y + view.y;
  const left = Math.max(8, Math.min(x + 16, size.width - 272));
  const top = y + 96 > size.height ? y - 88 : y + 16;
  return (
    <div role="presentation" className="pointer-events-none absolute z-10 w-64 rounded-lg bg-white px-3 py-2 shadow-card ring-1 ring-ink-200" style={{ left, top }}>
      <p className="text-sm leading-snug font-semibold text-ink-950">{shortLabel(node.label, 90)}</p>
      <p className="mt-0.5 text-xs text-ink-600">{text.kind}</p>
      <p className="mt-0.5 text-xs text-ink-500">{text.degree}</p>
    </div>
  );
}

function ZoomControls({ viewport }: { viewport: GraphViewport }) {
  const { t } = useI18n();
  const g = t.kb.graph;
  return (
    <div className="absolute top-3 right-3 flex flex-col gap-1 rounded-lg bg-white/90 p-1 shadow-card ring-1 ring-ink-200">
      <Button size="sm" variant="ghost" onClick={viewport.zoomIn} aria-label={g.zoomIn} title={g.zoomIn} icon={<Plus aria-hidden className="size-4" />} />
      <Button size="sm" variant="ghost" onClick={viewport.zoomOut} aria-label={g.zoomOut} title={g.zoomOut} icon={<Minus aria-hidden className="size-4" />} />
      <Button size="sm" variant="ghost" onClick={viewport.reset} disabled={!viewport.custom} aria-label={g.reset} title={g.reset} icon={<Scan aria-hidden className="size-4" />} />
    </div>
  );
}

/** A node to bring into view, found by the search; `nonce` tells two requests for the same node apart. */
export interface FocusRequest {
  id: string;
  nonce: number;
}

interface GraphCanvasProps {
  graph: KnowledgeGraph;
  visible: VisibleGraph;
  layout: GraphLayout;
  selected: string | null;
  onSelect: (id: string | null) => void;
  focus: FocusRequest | null;
}

/** Pointer, focus and keyboard state of the canvas: which node is hovered or focused, and the roving tab stop. */
function useCanvasState({ visible, selected, onSelect }: Pick<GraphCanvasProps, "visible" | "selected" | "onSelect">, dragging: () => boolean) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [focused, setFocused] = useState<{ id: string | null; visible: boolean }>({ id: null, visible: false });
  const elements = useRef(new Map<string, SVGGElement>());
  const order = visible.nodes.map((node) => node.id);
  const toggle = (id: string) => onSelect(selected === id ? null : id);
  const handlers: NodeHandlers = {
    register: (id, element) => {
      if (element) elements.current.set(id, element);
      else elements.current.delete(id);
    },
    hover: setHovered,
    focus: (id, visible) => setFocused({ id, visible }),
    activate: (id) => {
      if (!dragging()) toggle(id);
    },
    keyDown: (event, id) => {
      const step = NAV_STEP[event.key];
      if (step) elements.current.get(order[step(order.indexOf(id), order.length)] ?? id)?.focus();
      else if (event.key === "Enter" || event.key === " ") toggle(id);
      else if (event.key === "Escape") onSelect(null);
      else return;
      event.preventDefault();
    },
  };
  const live = (id: string | null) => (id && visible.ids.has(id) ? id : null);
  const focusedId = live(focused.id);
  return {
    hovered: live(hovered),
    focused: focusedId,
    /** Drawn only for keyboard focus: a click focuses the node too, and already shows the selection ring. */
    focusRing: focused.visible ? focusedId : null,
    tabStop: focusedId ?? live(selected) ?? order[0] ?? null,
    handlers,
  };
}

/** The graph itself: edges, nodes, then labels; hover or focus a node to light its links, click it to select it. */
export function GraphCanvas({ graph, visible, layout, selected, onSelect, focus }: GraphCanvasProps) {
  const { t } = useI18n();
  const hintId = useId();
  const bounds = useMemo(() => boundsOf(visible.nodes.flatMap((node) => layout.positions.get(node.id) ?? [])), [visible, layout]);
  const [containerRef, viewport] = useGraphViewport(bounds);
  const [centered, setCentered] = useState(focus);
  if (focus !== centered) {
    setCentered(focus);
    const point = focus ? layout.positions.get(focus.id) : undefined;
    if (point) viewport.centerOn(point);
  }
  const state = useCanvasState({ visible, selected, onSelect }, viewport.dragging);
  const active = state.hovered ?? state.focused ?? selected;
  const highlight = useMemo(() => highlightOf(graph, active), [graph, active]);
  const { view, size } = viewport;
  const labelled = useMemo(
    () => placeLabels({ graph, visible, layout, view, active, selected, radiusOf: nodeRadius, gap: LABEL_GAP, size }),
    [graph, visible, layout, view, active, selected, size],
  );
  const pointed = visible.nodes.find((node) => node.id === (state.hovered ?? state.focused));
  const pointedAt = pointed ? layout.positions.get(pointed.id) : undefined;
  const layer = { visible, layout, scale: view.k, highlight };
  return (
    <div ref={containerRef} className="relative h-[min(68vh,640px)] min-h-[420px] w-full overflow-hidden">
      <svg width={size.width} height={size.height} role="group" aria-label={t.kb.graph.canvasLabel} aria-describedby={hintId} className="block touch-pan-y select-none" {...viewport.pan}>
        <rect width="100%" height="100%" fill="transparent" onClick={() => (viewport.dragging() ? undefined : onSelect(null))} />
        <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
          <EdgeLines edges={visible.edges} positions={layout.positions} highlight={highlight} />
          <NodeLayer {...layer} selected={selected} canvas={state} />
          <LabelLayer {...layer} labelled={labelled} />
        </g>
      </svg>
      {pointed && pointedAt ? <Tooltip node={pointed} point={pointedAt} view={view} size={size} /> : null}
      <ZoomControls viewport={viewport} />
      <p id={hintId} className="pointer-events-none absolute bottom-2 left-3 rounded bg-white/80 px-1 text-xs text-ink-500">
        {t.kb.graph.hint}
      </p>
    </div>
  );
}
