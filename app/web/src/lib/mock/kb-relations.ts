/**
 * `links` and `tickers` of the simulator's `kb.list` items, by the runtime's rules
 * (CONTRACTS.md, section 3.2; `alphaforge.profile.kb_links`).
 */
import type { KbItem } from "@/lib/contract/schemas";
import { parseOkf, resolveOkfLink } from "@/lib/okf";
import type { StoredDoc } from "./documents";

const MARKDOWN_LINK = /\]\(\s*<?([^)\s>]+)/g;
const EXCHANGE_SLUG = /^([A-Z0-9][A-Z0-9-]*)-(TO|V|NE|CN)$/;
const TICKER = /^[A-Z0-9^][A-Z0-9.=^-]{0,19}$/;

/** Canonical form of a symbol, as `okf.canonical_ticker`: `shop.to` and `shop-to` give `SHOP.TO`. */
export function canonicalTicker(value: unknown): string | null {
  if (typeof value !== "string") return null;
  let text = value.trim().toUpperCase();
  const slug = text.includes(".") ? null : EXCHANGE_SLUG.exec(text);
  if (slug) text = `${slug[1]}.${slug[2]}`;
  return TICKER.test(text) ? text : null;
}

const asList = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);

function canonical(values: unknown[]): string[] {
  return [...new Set(values.map(canonicalTicker).filter((ticker): ticker is string => ticker !== null))];
}

function documentLinks(key: string, body: string, known: ReadonlySet<string>): string[] {
  const targets = [...body.matchAll(MARKDOWN_LINK)].map((match) => resolveOkfLink(key, match[1] ?? "", known));
  return [...new Set(targets.filter((target): target is string => target !== null && target !== key))];
}

interface Relations {
  links: string[];
  declared: string[];
  candidates: string[];
}

function relationsOf(doc: StoredDoc, known: ReadonlySet<string>): Relations {
  const { frontmatter, body } = parseOkf(doc.content);
  const front = frontmatter ?? {};
  const data = (front.data && typeof front.data === "object" ? front.data : {}) as Record<string, unknown>;
  return {
    links: documentLinks(doc.key, body, known),
    declared: canonical([data.ticker, data.symbol, ...asList(data.tickers)]),
    candidates: canonical([...asList(front.tags), ...asList(data.tags)]),
  };
}

/** `kb.list` items: links to the listed documents, and tags kept as symbols only when another document declares them. */
export function kbItemsWithRelations(docs: StoredDoc[]): KbItem[] {
  const sorted = [...docs].sort((left, right) => left.key.localeCompare(right.key));
  const known = new Set(sorted.map((doc) => doc.key));
  const relations = sorted.map((doc) => relationsOf(doc, known));
  const declared = new Set(relations.flatMap((found) => found.declared));
  return sorted.map((doc, index) => {
    const found = relations[index]!;
    const confirmed = found.candidates.filter((ticker) => declared.has(ticker) && !found.declared.includes(ticker));
    return {
      key: doc.key,
      title: doc.title,
      type: doc.type,
      description: doc.description,
      updated_at: doc.updated_at,
      links: found.links,
      tickers: [...found.declared, ...confirmed],
    };
  });
}
