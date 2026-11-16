/**
 * OKF documents (CONTRACTS.md 5): a YAML frontmatter between `---` lines, then a
 * Markdown body. Parsing never throws: an unreadable frontmatter is reported.
 */
import { parse } from "yaml";

export interface OkfDocument {
  frontmatter: Record<string, unknown> | null;
  body: string;
  error: string | null;
}

const FRONTMATTER = /^﻿?---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/;

export function parseOkf(content: string): OkfDocument {
  const match = FRONTMATTER.exec(content);
  if (!match) return { frontmatter: null, body: content, error: null };
  const body = content.slice(match[0].length).replace(/^\s*\n/, "");
  try {
    const data: unknown = parse(match[1] ?? "");
    if (data === null || data === undefined) return { frontmatter: {}, body, error: null };
    if (typeof data !== "object" || Array.isArray(data)) return { frontmatter: null, body: content, error: "frontmatter is not a mapping" };
    return { frontmatter: data as Record<string, unknown>, body, error: null };
  } catch (error) {
    return { frontmatter: null, body: content, error: error instanceof Error ? error.message : String(error) };
  }
}

/** The closed set of general/ folders (CONTRACTS.md, section 5), in display order. */
export const GENERAL_FOLDERS = [
  "methodologie",
  "notions",
  "societes",
  "actualites",
  "donnees",
  "recherches",
  "faits",
  "signaux",
  "depots",
] as const;

/** Group of a general/ key: one of GENERAL_FOLDERS, index or other. */
export function generalGroup(key: string): string {
  const parts = key.split("/");
  if (parts.length === 2 && parts[1] === "index.md") return "index";
  const folder = parts[1] ?? "";
  return (GENERAL_FOLDERS as readonly string[]).includes(folder) ? folder : "other";
}

/** Root of the base a key belongs to: `general/` or `clients/<client_id>/`. */
export function okfBaseRoot(key: string): string {
  const parts = key.split("/");
  return `${parts.slice(0, parts[0] === "clients" ? 2 : 1).join("/")}/`;
}

const SCHEME = /^[a-z][a-z0-9+.-]*:/i;

/** `.` and `..` segments resolved; null when the path climbs above its first segment. */
function normalizePath(path: string): string | null {
  const segments: string[] = [];
  for (const segment of path.split("/")) {
    if (segment === "" || segment === ".") continue;
    if (segment !== "..") segments.push(segment);
    else if (segments.pop() === undefined) return null;
  }
  return segments.join("/");
}

/** Path of a Markdown link, without anchor or query; null for an external or absolute address. */
function linkPath(href: string): string | null {
  const bare = href.split("#", 1)[0]?.split("?", 1)[0] ?? "";
  let path = bare.trim();
  try {
    path = decodeURIComponent(bare).trim();
  } catch {
    // a malformed escape stays as written
  }
  return !path || path.startsWith("/") || SCHEME.test(path) ? null : path;
}

/**
 * The key, among `known`, that a link of the document `fromKey` points to: relative to the document's folder
 * (`../methodologie/x.md`), else to the root of its base (`faits/<source>/<date>.md`). The runtime applies the
 * same rule to the `links` of `kb.list` (CONTRACTS.md, section 3.2).
 */
export function resolveOkfLink(fromKey: string, href: string, known: ReadonlySet<string>): string | null {
  const path = linkPath(href);
  if (path === null) return null;
  const root = okfBaseRoot(fromKey);
  const folder = fromKey.slice(0, fromKey.lastIndexOf("/") + 1);
  const candidates = [normalizePath(folder + path), normalizePath(root + path)];
  // A link never leaves its base: `../../../general/x.md` from a client's note points nowhere.
  return candidates.find((candidate): candidate is string => candidate !== null && candidate.startsWith(root) && known.has(candidate)) ?? null;
}
