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

/** Group of a general/ key: methodologie, actualites, donnees, index or other. */
export function generalGroup(key: string): string {
  const parts = key.split("/");
  if (parts.length === 2 && parts[1] === "index.md") return "index";
  const folder = parts[1] ?? "";
  return ["methodologie", "actualites", "donnees"].includes(folder) ? folder : "other";
}
