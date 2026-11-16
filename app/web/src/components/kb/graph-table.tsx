"use client";

import type { DocumentNode, GraphNode } from "@/lib/kb/graph";
import { okfTypeLabel } from "@/lib/i18n/okf-types";
import { useI18n } from "@/lib/i18n/provider";
import { NodeSwatch } from "./graph-details";

function TableRow({ node, onOpenDoc }: { node: DocumentNode; onOpenDoc: (key: string) => void }) {
  const { t, locale } = useI18n();
  return (
    <tr className="border-b border-ink-150 align-top">
      <td className="py-2 pr-3 pl-5">
        <button
          type="button"
          onClick={() => onOpenDoc(node.id)}
          className="text-left font-medium text-navy underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-focus"
        >
          {node.label}
        </button>
      </td>
      <td className="py-2 pr-3 whitespace-nowrap text-ink-700">
        <span className="inline-flex items-center gap-2">
          <NodeSwatch tone={node.family} />
          {t.kb.graph.families[node.family]}
        </span>
      </td>
      <td className="py-2 pr-3 text-ink-700">{node.item.type ? okfTypeLabel(node.item.type, locale) : "—"}</td>
      <td className="py-2 pr-3 text-right text-ink-900 tabular-nums">{node.degree}</td>
      <td className="py-2 pr-5 font-mono text-xs text-ink-700">{node.item.tickers?.length ? node.item.tickers.join(", ") : "—"}</td>
    </tr>
  );
}

/** The table twin of the graph: every document the filters and the search keep, the most linked first. */
export function GraphTable({ nodes, onOpenDoc }: { nodes: GraphNode[]; onOpenDoc: (key: string) => void }) {
  const { t, locale } = useI18n();
  const g = t.kb.graph.table;
  const rows = nodes
    .filter((node): node is DocumentNode => node.kind === "document")
    .sort((a, b) => b.degree - a.degree || a.label.localeCompare(b.label, locale));
  return (
    <div className="max-h-[min(68vh,640px)] overflow-auto">
      <table className="w-full min-w-[760px] text-sm">
        <caption className="sr-only">{g.caption}</caption>
        <thead className="sticky top-0 bg-surface">
          <tr className="border-b border-ink-200 text-left text-xs text-ink-600">
            <th scope="col" className="py-2 pr-3 pl-5 font-semibold">
              {g.document}
            </th>
            <th scope="col" className="py-2 pr-3 font-semibold">
              {g.family}
            </th>
            <th scope="col" className="py-2 pr-3 font-semibold">
              {g.type}
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-semibold">
              {g.links}
            </th>
            <th scope="col" className="py-2 pr-5 font-semibold">
              {g.tickers}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((node) => (
            <TableRow key={node.id} node={node} onOpenDoc={onOpenDoc} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
