/**
 * Line reading of the simulator's fake A2: what each line of the pasted text and of the text-like files
 * says about a holding. After a header row (a broker export), lines are read by column name; other lines
 * are read as free text. portfolio.ts then resolves, prices and values what was read.
 */
import type { AccountType } from "@/lib/contract/schemas";
import { findAssetByTicker, findAssetInText, type StarterAsset } from "./starter";

export interface ExtractionInput {
  text?: string;
  files?: Array<{ name: string; media_type: string; data_base64: string }>;
}

export interface FileReport {
  name: string;
  media_type: string;
  bytes: number;
  readable: boolean;
  lines: number;
}

/** What a line says about a holding, before any price. */
export interface Holding {
  quantity: number | null;
  marketValue: number | null;
  account: AccountType | null;
  /** Currency of the declared value, when the line gives it (a currency column). */
  currency: string | null;
}

/** The security a line names. */
interface Security {
  asset: StarterAsset | null;
  /** An explicit symbol absent from the starter universe: kept as is, never replaced by a name match. */
  symbol: string | null;
  cash: boolean;
}

/** A line read by the simulator. */
export interface ReadLine extends Holding, Security {
  line: string;
  name: string | null;
}

const ACCOUNT_PATTERNS: Array<[RegExp, AccountType]> = [
  [/\b(celi|tfsa)\b/i, "tfsa"],
  [/\b(reer|rrsp)\b/i, "rrsp"],
  [/\b(reee|resp)\b/i, "resp"],
  [/\b(ferr|rrif)\b/i, "rrif"],
  [/(non[ -]?enregistr|non[ -]?registered|\bmarge\b|\bmargin\b|\bcash account\b)/i, "non_registered"],
];

const HEADER_WORDS = /\b(ticker|symbole|symbol|titre|security|quantit[ée]|quantity|qty|compte|account|valeur|value|devise|currency)\b/i;

/** Cash, like `_CASH_NAME` of the Python runtime (portfolio.py). */
export const CASH_NAME = /\b(cash|encaisse|liquidit|comptant)/i;

/** A symbol with its Canadian listing: `RY.TO`, `VFV.TO`, `REI.UN.TO`, `ABC.V`. */
const LISTED_SYMBOL = /^[A-Z][A-Z0-9.]{0,7}\.(TO|V|NE|CN)$/i;

/** A cell that holds a symbol rather than a name: no space, no accent. */
const SYMBOL_CELL = /^[A-Za-z0-9][A-Za-z0-9.:-]{0,15}$/;

/** A total or subtotal line of a statement: not a holding. */
const TOTAL_LINE = /^"?(sous-total|subtotal|grand total|total)\b/i;

type Column = "symbol" | "name" | "quantity" | "price" | "value" | "currency";

/** Column names of broker exports, matched on the start of a header cell (lowercase, without accents). */
const COLUMNS: Array<[Column, RegExp]> = [
  ["symbol", /^(symbole|symbol|ticker|code)\b/],
  ["name", /^(description|nom|name|titre|security|libelle)\b/],
  ["quantity", /^(quantite|quantity|qty|nombre|parts|units|shares)\b/],
  ["price", /^(prix|price|cours)\b/],
  ["value", /^(valeur|value|market value|montant|amount)\b/],
  ["currency", /^(devise|currency|monnaie)\b/],
];

/** Book cost and average price are neither the market value nor the price. */
const COST_WORDS = /comptable|achat|book|cost|cout|moyen|average/;

const DELIMITERS = [",", ";", "\t", "|"];

interface Columns {
  delimiter: string;
  index: Partial<Record<Column, number>>;
}

export function round(value: number, digits = 2): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function isTextLike(mediaType: string, name: string): boolean {
  return (
    mediaType.startsWith("text/") ||
    /json|csv|xml|yaml|markdown/.test(mediaType) ||
    /\.(csv|tsv|txt|md|json|ya?ml)$/i.test(name)
  );
}

function decodeText(base64: string): string | null {
  const bytes = Buffer.from(base64, "base64");
  const text = bytes.toString("utf8");
  // Binary content (PDF, image, spreadsheet) is not readable without a model.
  if (text.includes("\u0000") || /\ufffd/.test(text.slice(0, 2000))) return null;
  return text;
}

function parseNumber(token: string): number | null {
  const cleaned = token.replace(/[\s\u00a0\u202f$€£]/g, "").replace(/(\d),(\d{3})(?!\d)/g, "$1$2").replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(cleaned)) return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

/** On a line that is not comma-delimited, "0,05" is a decimal and "1,234" a thousands group. */
function normalizeCommas(line: string): string {
  if ((line.match(/,/g) ?? []).length > 1) return line;
  return line.replace(/(\d),(\d{3})(?!\d)/g, "$1$2").replace(/(\d),(\d+)/g, "$1.$2");
}

function accountOf(line: string): AccountType | null {
  return ACCOUNT_PATTERNS.find(([pattern]) => pattern.test(line))?.[1] ?? null;
}

const unquote = (token: string) => token.replace(/^["'(]|["')]$/g, "");

/**
 * The security of a free-text line, and the index of its token: a listed symbol first, kept as is when it
 * is not in the universe; else a ticker of the universe; else a name or alias of the universe, or cash.
 */
function identifyTokens(tokens: string[], text: string): Security & { token: number } {
  const listed = tokens.findIndex((token) => LISTED_SYMBOL.test(unquote(token)));
  if (listed >= 0) {
    const symbol = unquote(tokens[listed] ?? "").toUpperCase();
    const asset = findAssetByTicker(symbol);
    return { asset, symbol: asset ? null : symbol, cash: false, token: listed };
  }
  const ticker = tokens.findIndex((token) => /[A-Za-z]/.test(token) && findAssetByTicker(unquote(token)) !== null);
  if (ticker >= 0) return { asset: findAssetByTicker(unquote(tokens[ticker] ?? "")), symbol: null, cash: false, token: ticker };
  const asset = findAssetInText(text);
  return { asset, symbol: null, cash: !asset && CASH_NAME.test(text), token: -1 };
}

/** A free-text line: the first number that is neither the symbol nor an amount in dollars is the quantity. */
function readText(line: string): ReadLine {
  const normalized = normalizeCommas(line);
  const tokens = normalized.split(/[\s,;\t|]+/).filter(Boolean);
  const { token, ...security } = identifyTokens(tokens, normalized);
  const money = /(\$\s?[\d\s.,]+|[\d\s.,]+\s?\$)/.exec(normalized)?.[0] ?? null;
  const marketValue = money ? parseNumber(money) : null;
  const numbers = tokens.map((text, index) => (index === token || money?.includes(text) ? null : parseNumber(text)));
  const quantity = numbers.find((number) => number !== null) ?? null;
  // Cash in free text needs an amount: "5 000 $ en encaisse", not "Mon compte cash".
  const cash = security.cash && (marketValue ?? quantity) !== null;
  return { line, ...security, cash, name: null, quantity, marketValue, account: accountOf(normalized), currency: null };
}

/** Cells of a delimited line; a quoted cell may hold the delimiter. */
function splitCells(line: string, delimiter: string): string[] {
  const cells: string[] = [];
  let cell = "";
  let quoted = false;
  for (const char of line) {
    if (char === '"') quoted = !quoted;
    else if (char === delimiter && !quoted) {
      cells.push(cell.trim());
      cell = "";
    } else cell += char;
  }
  cells.push(cell.trim());
  return cells;
}

const columnName = (cell: string) =>
  cell
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim();

function columnOf(cell: string): Column | null {
  const name = columnName(cell);
  if (COST_WORDS.test(name)) return null;
  return COLUMNS.find(([, pattern]) => pattern.test(name))?.[0] ?? null;
}

/** The columns of a header row: a delimited line of words that names a security column and an amount column. */
function readHeader(line: string): Columns | null {
  if (!HEADER_WORDS.test(line) || /\d/.test(line)) return null;
  const delimiter = DELIMITERS.reduce((best, candidate) => (line.split(candidate).length > line.split(best).length ? candidate : best));
  const index: Columns["index"] = {};
  splitCells(line, delimiter).forEach((cell, position) => {
    const column = columnOf(cell);
    if (column && index[column] === undefined) index[column] = position;
  });
  const namesSecurity = index.symbol !== undefined || index.name !== undefined;
  const givesAmount = index.quantity !== undefined || index.value !== undefined;
  return namesSecurity && givesAmount ? { delimiter, index } : null;
}

/** The security of a row: its symbol cell, explicit even when absent from the universe; else its name cell, read as text. */
function identifyRow(symbol: string, name: string): Security {
  if (!SYMBOL_CELL.test(symbol)) {
    const text = `${symbol} ${name}`.trim();
    const { asset, symbol: listed, cash } = identifyTokens(text.split(/\s+/), text);
    return { asset, symbol: listed, cash };
  }
  const asset = findAssetByTicker(symbol);
  if (asset) return { asset, symbol: null, cash: false };
  if (CASH_NAME.test(symbol)) return { asset: null, symbol: null, cash: true };
  return { asset: null, symbol: symbol.toUpperCase(), cash: false };
}

/** A row under a header, read by column name; a row without a value is valued at its quantity times its price. */
function readRow(line: string, columns: Columns): ReadLine {
  const cells = splitCells(line, columns.delimiter);
  const cell = (column: Column) => cells[columns.index[column] ?? -1] ?? "";
  const quantity = parseNumber(cell("quantity"));
  const price = parseNumber(cell("price"));
  const priced = quantity !== null && price !== null ? round(quantity * price) : null;
  const currency = cell("currency").toUpperCase();
  return {
    line: line.trim(),
    ...identifyRow(cell("symbol"), cell("name")),
    name: cell("name") || null,
    quantity,
    marketValue: parseNumber(cell("value")) ?? priced,
    account: accountOf(line),
    currency: /^[A-Z]{3}$/.test(currency) ? currency : null,
  };
}

/** A line that names no security and is only a header row, or has no letter at all. */
function isNoise(line: string): boolean {
  return (HEADER_WORDS.test(line) && !/\d/.test(line)) || !/[A-Za-zÀ-ÿ]/.test(line);
}

/** The lines of one source (the text or a file): a header row gives the columns of the next lines, up to a blank line. */
function readSource(lines: string[]): ReadLine[] {
  const read: ReadLine[] = [];
  let columns: Columns | null = null;
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (line === "") columns = null;
    if (line === "" || line.startsWith("#") || TOTAL_LINE.test(line)) continue;
    const header = readHeader(rawLine);
    if (header) {
      columns = header;
      continue;
    }
    const isRow = columns !== null && splitCells(rawLine, columns.delimiter).length > 1;
    const holding = columns && isRow ? readRow(rawLine, columns) : readText(line);
    if (holding.asset || holding.symbol || holding.cash || !isNoise(line)) read.push(holding);
  }
  return read;
}

export interface InputLines {
  holdings: ReadLine[];
  files: FileReport[];
  lines: number;
}

/** What the pasted text and the text-like files say; a file without readable text is reported, not read. */
export function readInput(input: ExtractionInput): InputLines {
  const sources: string[][] = input.text ? [input.text.split(/\r?\n/)] : [];
  const files: FileReport[] = [];
  for (const file of input.files ?? []) {
    const bytes = Buffer.byteLength(file.data_base64, "base64");
    const text = isTextLike(file.media_type, file.name) ? decodeText(file.data_base64) : null;
    const fileLines = text ? text.split(/\r?\n/) : [];
    files.push({ name: file.name, media_type: file.media_type, bytes, readable: text !== null, lines: fileLines.length });
    sources.push(fileLines);
  }
  const lines = sources.reduce((count, source) => count + source.length, 0);
  return { holdings: sources.flatMap((source) => readSource(source)), files, lines };
}
