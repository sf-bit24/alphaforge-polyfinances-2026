"use client";

import { Network, Table2, Waypoints } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import type { KbItem } from "@/lib/contract/schemas";
import type { ApiError } from "@/lib/client/api";
import { buildKnowledgeGraph, GRAPH_FAMILIES, visibleGraph, type GraphFamily, type GraphFilter, type KnowledgeGraph, type VisibleGraph } from "@/lib/kb/graph";
import { layoutGraph } from "@/lib/kb/layout";
import { useI18n } from "@/lib/i18n/provider";
import { Card, CardHeader } from "@/components/ui/card";
import { cn } from "@/components/ui/cn";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Spinner } from "@/components/ui/spinner";
import { GraphCanvas } from "./graph-canvas";
import { GraphDetails, NodeSwatch } from "./graph-details";
import { GraphTable } from "./graph-table";

type GraphView = "graph" | "table";

const ALL_FAMILIES: ReadonlySet<GraphFamily> = new Set(GRAPH_FAMILIES);

function FilterToggle({ pressed, onToggle, swatch, label, count }: { pressed: boolean; onToggle: () => void; swatch: ReactNode; label: string; count: number }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onToggle}
      className={cn(
        "inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm ring-1 ring-inset transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
        pressed ? "bg-white text-ink-900 ring-ink-300 hover:bg-ink-50" : "bg-ink-50 text-ink-500 ring-ink-200 hover:text-ink-700",
      )}
    >
      {swatch}
      <span className={cn(!pressed && "line-through decoration-ink-300")}>{label}</span>
      <span className="text-ink-500 tabular-nums">{count}</span>
    </button>
  );
}

/** One row above the graph: the legend, whose entries also show or hide their nodes. */
function GraphFilters({ graph, filter, onChange }: { graph: KnowledgeGraph; filter: GraphFilter; onChange: (filter: GraphFilter) => void }) {
  const { t } = useI18n();
  const g = t.kb.graph;
  const counts = new Map<GraphFamily, number>();
  for (const node of graph.nodes) if (node.kind === "document") counts.set(node.family, (counts.get(node.family) ?? 0) + 1);
  const tickers = graph.nodes.filter((node) => node.kind === "ticker").length;
  const isolated = graph.nodes.filter((node) => node.kind === "document" && node.degree === 0).length;
  const toggleFamily = (family: GraphFamily) => {
    const families = new Set(filter.families);
    if (!families.delete(family)) families.add(family);
    onChange({ ...filter, families });
  };
  return (
    <div role="group" aria-label={g.filters} className="flex flex-wrap items-center gap-2">
      {GRAPH_FAMILIES.filter((family) => counts.has(family)).map((family) => (
        <FilterToggle
          key={family}
          pressed={filter.families.has(family)}
          onToggle={() => toggleFamily(family)}
          swatch={<NodeSwatch tone={family} muted={!filter.families.has(family)} />}
          label={g.families[family] ?? family}
          count={counts.get(family) ?? 0}
        />
      ))}
      {tickers ? (
        <FilterToggle pressed={filter.tickers} onToggle={() => onChange({ ...filter, tickers: !filter.tickers })} swatch={<NodeSwatch tone="ticker" muted={!filter.tickers} />} label={g.tickers} count={tickers} />
      ) : null}
      {isolated ? (
        <FilterToggle
          pressed={filter.isolated}
          onToggle={() => onChange({ ...filter, isolated: !filter.isolated })}
          swatch={<span aria-hidden className={cn("inline-block size-2.5 rounded-full ring-1 ring-ink-400 ring-inset", !filter.isolated && "opacity-30")} />}
          label={g.isolated}
          count={isolated}
        />
      ) : null}
    </div>
  );
}

function ViewToggle({ view, onChange }: { view: GraphView; onChange: (view: GraphView) => void }) {
  const { t } = useI18n();
  const options: Array<{ id: GraphView; label: string; icon: ReactNode }> = [
    { id: "graph", label: t.kb.graph.views.graph, icon: <Network aria-hidden className="size-4" /> },
    { id: "table", label: t.kb.graph.views.table, icon: <Table2 aria-hidden className="size-4" /> },
  ];
  return (
    <div role="group" aria-label={t.kb.graph.views.label} className="inline-flex rounded-lg bg-ink-100 p-0.5">
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          aria-pressed={view === option.id}
          onClick={() => onChange(option.id)}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-focus",
            view === option.id ? "bg-white text-ink-950 shadow-sm" : "text-ink-600 hover:text-ink-900",
          )}
        >
          {option.icon}
          {option.label}
        </button>
      ))}
    </div>
  );
}

interface GraphBodyProps {
  graph: KnowledgeGraph;
  visible: VisibleGraph;
  view: GraphView;
  selected: string | null;
  onSelect: (id: string | null) => void;
  onOpenDoc: (key: string) => void;
}

function GraphBody({ graph, visible, view, selected, onSelect, onOpenDoc }: GraphBodyProps) {
  const { t } = useI18n();
  const layout = useMemo(() => layoutGraph(graph), [graph]);
  if (visible.nodes.length === 0) return <p className="px-5 py-10 text-center text-sm text-ink-500">{t.kb.graph.empty}</p>;
  if (view === "table") return <GraphTable visible={visible} onOpenDoc={onOpenDoc} />;
  return (
    <div className="grid lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="min-w-0">
        <GraphCanvas graph={graph} visible={visible} layout={layout} selected={selected} onSelect={onSelect} />
      </div>
      <aside aria-label={t.kb.graph.details.label} className="border-t border-ink-150 px-5 py-4 lg:max-h-[min(68vh,640px)] lg:overflow-y-auto lg:border-t-0 lg:border-l">
        <GraphDetails graph={graph} selected={selected} onSelect={onSelect} onOpenDoc={onOpenDoc} />
      </aside>
    </div>
  );
}

interface KnowledgeGraphPanelProps {
  items: KbItem[];
  loaded: boolean;
  /** The list is reloading: the previous graph stays, dimmed, instead of a spinner. */
  stale: boolean;
  error: ApiError | null;
  onOpenDoc: (key: string) => void;
}

function PanelStatus({ error, loaded, empty, related }: { error: ApiError | null; loaded: boolean; empty: boolean; related: boolean }) {
  const { t } = useI18n();
  if (error) return <ErrorNotice className="m-5" error={error} />;
  if (!loaded) return <Spinner className="m-5" label={t.common.loading} />;
  if (empty) return <p className="px-5 py-10 text-center text-sm text-ink-500">{t.kb.emptyGeneral}</p>;
  if (!related) return <p className="px-5 py-10 text-center text-sm text-ink-600">{t.kb.graph.noRelations}</p>;
  return null;
}

/** The graph tab: documents of the general base and the symbols they cite, linked as the documents link them. */
export function KnowledgeGraphPanel({ items, loaded, stale, error, onOpenDoc }: KnowledgeGraphPanelProps) {
  const { t } = useI18n();
  const graph = useMemo(() => buildKnowledgeGraph(items), [items]);
  const [filter, setFilter] = useState<GraphFilter>({ families: ALL_FAMILIES, tickers: true, isolated: false });
  const [view, setView] = useState<GraphView>("graph");
  const [selected, setSelected] = useState<string | null>(null);
  const visible = useMemo(() => visibleGraph(graph, filter), [graph, filter]);
  const status = <PanelStatus error={error} loaded={loaded} empty={items.length === 0} related={graph.hasRelations} />;
  const ready = !error && loaded && items.length > 0 && graph.hasRelations;
  const shownTickers = visible.nodes.filter((node) => node.kind === "ticker").length;
  return (
    <div className="space-y-4">
      {ready ? <GraphFilters graph={graph} filter={filter} onChange={setFilter} /> : null}
      <Card className={cn("transition-opacity", stale && "opacity-60")}>
        <CardHeader
          title={t.kb.graph.title}
          subtitle={ready ? t.kb.graph.subtitle(visible.nodes.length - shownTickers, shownTickers, visible.edges.length) : t.kb.graph.lead}
          icon={<Waypoints aria-hidden className="size-4" />}
          actions={ready ? <ViewToggle view={view} onChange={setView} /> : null}
        />
        {ready ? <GraphBody graph={graph} visible={visible} view={view} selected={selected} onSelect={setSelected} onOpenDoc={onOpenDoc} /> : status}
        {ready ? <p className="border-t border-ink-150 px-5 py-3 text-xs text-ink-500">{t.kb.graph.caption}</p> : null}
      </Card>
    </div>
  );
}
