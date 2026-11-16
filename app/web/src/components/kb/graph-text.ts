"use client";

import type { GraphNode } from "@/lib/kb/graph";
import { okfTypeLabel } from "@/lib/i18n/okf-types";
import { useI18n } from "@/lib/i18n/provider";

/** What a node is, in words: its OKF type (or "listed security"), its link count, and both for screen readers. */
export function useNodeText(node: GraphNode) {
  const { t, locale } = useI18n();
  const g = t.kb.graph;
  if (node.kind === "ticker") {
    const degree = g.documentCount(node.degree);
    return { kind: g.ticker, degree, accessible: `${node.label}, ${g.ticker}, ${degree}` };
  }
  // The OKF type is the most precise word (a data series, a fact, a concept); the colour already says the family.
  const kind = node.item.type ? okfTypeLabel(node.item.type, locale) : (t.kb.groups[node.group] ?? node.group);
  const degree = g.degree(node.degree);
  return { kind, degree, accessible: `${node.label}, ${kind}, ${degree}` };
}
