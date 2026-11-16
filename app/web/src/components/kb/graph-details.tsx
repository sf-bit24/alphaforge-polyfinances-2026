"use client";

import { ArrowUpRight, X } from "lucide-react";
import { nodeRelations, type DocumentNode, type GraphFamily, type GraphNode, type KnowledgeGraph, type TickerNode } from "@/lib/kb/graph";
import { formatDate } from "@/lib/i18n/locale";
import { useI18n } from "@/lib/i18n/provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/components/ui/cn";
import { FAMILY_SWATCH } from "./graph-style";
import { useNodeText } from "./graph-text";

export const toneOf = (node: GraphNode): GraphFamily | "ticker" => (node.kind === "ticker" ? "ticker" : node.family);

/** The mark of a family (a dot) or of a symbol (a diamond), as drawn in the graph. */
export function NodeSwatch({ tone, muted = false }: { tone: GraphFamily | "ticker"; muted?: boolean }) {
  if (tone === "ticker") {
    return <span aria-hidden className={cn("inline-block size-2 shrink-0 rotate-45 rounded-[1px] bg-ink-700", muted && "opacity-30")} />;
  }
  return <span aria-hidden className={cn("inline-block size-2.5 shrink-0 rounded-full", FAMILY_SWATCH[tone], muted && "opacity-30")} />;
}

function NodeList({ title, nodes, onSelect }: { title: string; nodes: GraphNode[]; onSelect: (id: string) => void }) {
  const { t } = useI18n();
  return (
    <section className="mt-5">
      <h4 className="text-[0.7rem] font-semibold tracking-wide text-ink-500 uppercase">
        {title} <span className="font-normal tabular-nums">({nodes.length})</span>
      </h4>
      {nodes.length === 0 ? (
        <p className="mt-1 text-sm text-ink-500">{t.kb.graph.details.none}</p>
      ) : (
        <ul className="mt-1 max-h-52 space-y-0.5 overflow-y-auto">
          {nodes.map((node) => (
            <li key={node.id}>
              <button
                type="button"
                onClick={() => onSelect(node.id)}
                className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-sm text-ink-800 hover:bg-ink-50 focus-visible:outline-2 focus-visible:outline-focus"
              >
                <NodeSwatch tone={toneOf(node)} />
                <span className="min-w-0 flex-1 truncate">{node.label}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

interface DetailsProps<N extends GraphNode> {
  graph: KnowledgeGraph;
  node: N;
  onSelect: (id: string | null) => void;
  onOpenDoc: (key: string) => void;
}

function DocumentDetails({ graph, node, onSelect, onOpenDoc }: DetailsProps<DocumentNode>) {
  const { t, locale } = useI18n();
  const g = t.kb.graph.details;
  const text = useNodeText(node);
  const relations = nodeRelations(graph, node.id);
  return (
    <>
      <p className="flex items-center gap-2 text-xs text-ink-500">
        <NodeSwatch tone={toneOf(node)} />
        {text.kind}
      </p>
      <h3 className="mt-1.5 text-base leading-snug font-semibold text-ink-950">{node.label}</h3>
      {node.item.updated_at ? (
        <p className="mt-1 text-xs text-ink-500">
          {t.kb.updated} {formatDate(node.item.updated_at, locale)}
        </p>
      ) : null}
      {node.item.description ? <p className="mt-2 line-clamp-4 text-sm text-ink-600">{node.item.description}</p> : null}
      <Button className="mt-3" size="sm" variant="secondary" onClick={() => onOpenDoc(node.id)} icon={<ArrowUpRight aria-hidden className="size-4" />}>
        {g.open}
      </Button>
      <NodeList title={g.linksTo} nodes={relations.linksTo} onSelect={onSelect} />
      <NodeList title={g.linkedFrom} nodes={relations.linkedFrom} onSelect={onSelect} />
      {relations.tickers.length ? <NodeList title={g.tickers} nodes={relations.tickers} onSelect={onSelect} /> : null}
    </>
  );
}

function TickerDetails({ graph, node, onSelect }: DetailsProps<TickerNode>) {
  const { t } = useI18n();
  return (
    <>
      <p className="flex items-center gap-2 text-xs text-ink-500">
        <NodeSwatch tone={toneOf(node)} />
        {t.kb.graph.ticker}
      </p>
      <h3 className="mt-1.5 font-mono text-base font-semibold text-ink-950">{node.label}</h3>
      <NodeList title={t.kb.graph.details.documents} nodes={nodeRelations(graph, node.id).documents} onSelect={onSelect} />
    </>
  );
}

/** The selected node: what it is, the document to open, and its neighbours, each one a step further in the graph. */
export function GraphDetails({ graph, selected, onSelect, onOpenDoc }: Omit<DetailsProps<GraphNode>, "node"> & { selected: string | null }) {
  const { t } = useI18n();
  const node = selected ? graph.nodes.find((candidate) => candidate.id === selected) : undefined;
  if (!node) return <p className="text-sm text-ink-500">{t.kb.graph.details.pick}</p>;
  return (
    <div className="relative pr-8">
      <Button
        size="sm"
        variant="ghost"
        onClick={() => onSelect(null)}
        aria-label={t.kb.graph.details.clear}
        title={t.kb.graph.details.clear}
        icon={<X aria-hidden className="size-4" />}
        className="absolute -top-1 -right-2"
      />
      {node.kind === "document" ? (
        <DocumentDetails graph={graph} node={node} onSelect={onSelect} onOpenDoc={onOpenDoc} />
      ) : (
        <TickerDetails graph={graph} node={node} onSelect={onSelect} onOpenDoc={onOpenDoc} />
      )}
    </div>
  );
}
