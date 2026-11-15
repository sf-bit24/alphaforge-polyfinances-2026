/**
 * Fake A2 of the simulator: reads pasted text or text-like files, resolves lines
 * against the starter universe, prices them with the starter's last close and
 * converts USD with the starter's USD/CAD rate. Exposures are computed by code.
 */
import type { PositionInput } from "@/lib/contract/requests";
import type { AccountType, Exposures, FxRate, Locale, Position, Source, UnresolvedItem } from "@/lib/contract/schemas";
import { findAssetByTicker, findAssetInText, PRICE_DATE, STARTER_SOURCES, USDCAD, type StarterAsset } from "./starter";

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

export interface Extraction {
  positions: Position[];
  unresolved: UnresolvedItem[];
  files: FileReport[];
  lines: number;
}

const ACCOUNT_PATTERNS: Array<[RegExp, AccountType]> = [
  [/\b(celi|tfsa)\b/i, "tfsa"],
  [/\b(reer|rrsp)\b/i, "rrsp"],
  [/\b(reee|resp)\b/i, "resp"],
  [/\b(ferr|rrif)\b/i, "rrif"],
  [/(non[ -]?enregistr|non[ -]?registered|\bmarge\b|\bmargin\b|\bcash account\b)/i, "non_registered"],
];

const MAX_RAW_CHARS = 200;

const HEADER_WORDS = /\b(ticker|symbole|symbol|titre|security|quantit[ée]|quantity|qty|compte|account|valeur|value|devise|currency)\b/i;

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
  if (text.includes("\u0000") || /�/.test(text.slice(0, 2000))) return null;
  return text;
}

function parseNumber(token: string): number | null {
  const cleaned = token.replace(/[\s  $€£]/g, "").replace(/(\d),(\d{3})(?!\d)/g, "$1$2").replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(cleaned)) return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

function round(value: number, digits = 2): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

/** Value in the listing currency: quantity times price when both are known, else the declared market value. */
function nativeValue(
  quantity: number | null | undefined,
  price: number | null | undefined,
  marketValue: number | null | undefined,
): number | null {
  if (typeof quantity === "number" && typeof price === "number") return quantity * price;
  return typeof marketValue === "number" ? marketValue : null;
}

/** Value in CAD of a quantity or a declared market value, in the given currency. */
export function valueInCad(
  quantity: number | null | undefined,
  price: number | null | undefined,
  marketValue: number | null | undefined,
  currency: string | null | undefined,
): number | null {
  const native = nativeValue(quantity, price, marketValue);
  if (native === null) return null;
  if (currency === "USD") return round(native * USDCAD);
  if (currency === "CAD" || currency === null || currency === undefined) return round(native);
  return null;
}

const NOTES = {
  value_declared: {
    fr: "Quantité absente : valeur déclarée utilisée.",
    en: "No quantity: declared value used.",
  },
  quantity_missing: {
    fr: "Quantité absente : ajoutez-la pour calculer la valeur.",
    en: "No quantity: add it to compute the value.",
  },
  not_in_universe: {
    fr: "Titre absent du jeu de départ : valeur déclarée utilisée, sans cours.",
    en: "Security not in the starter universe: declared value used, no price.",
  },
} as const;

const UNRESOLVED_REASONS = {
  unread_file: {
    fr: "contenu non lu par le simulateur (PDF, image ou tableur); en mode AWS, A2 le lit avec le modèle",
    en: "content not read by the simulator (PDF, image or spreadsheet); in AWS mode, A2 reads it with the model",
  },
  not_in_universe: {
    fr: "titre introuvable dans l'univers du jeu de départ",
    en: "security not found in the starter universe",
  },
} as const;

/** What a line says about a holding, before any price. */
interface Holding {
  quantity: number | null;
  marketValue: number | null;
  account: AccountType | null;
}

/** A row of the portfolio as read from a line, or as sent back by the investor. */
interface PositionRow extends Holding {
  id: string;
  raw: string | null;
}

function positionFromAsset(row: PositionRow, asset: StarterAsset, locale: Locale): Position {
  const { quantity, marketValue } = row;
  const value = valueInCad(quantity, asset.close, quantity === null ? marketValue : null, asset.currency);
  let notes: string | null = null;
  if (quantity === null && marketValue !== null) notes = NOTES.value_declared[locale];
  if (quantity === null && marketValue === null) notes = NOTES.quantity_missing[locale];
  return {
    id: row.id,
    raw: row.raw,
    ticker: asset.ticker,
    name: asset.name,
    asset_class: asset.asset_class,
    sector: asset.sector,
    market: asset.market,
    currency: asset.currency,
    quantity,
    market_value: marketValue,
    account_type: row.account ?? "unknown",
    price: asset.close,
    price_date: PRICE_DATE,
    price_source: STARTER_SOURCES.prices.resource,
    value_cad: value,
    resolved: true,
    notes,
  };
}

function unresolvedPosition(row: PositionRow, reason: string): Position {
  const { marketValue } = row;
  return {
    id: row.id,
    raw: row.raw,
    ticker: null,
    name: null,
    asset_class: null,
    sector: null,
    market: null,
    currency: marketValue !== null ? "CAD" : null,
    quantity: row.quantity,
    market_value: marketValue,
    account_type: row.account,
    price: null,
    price_date: null,
    price_source: null,
    value_cad: marketValue !== null ? valueInCad(null, null, marketValue, "CAD") : null,
    resolved: false,
    notes: reason,
  };
}

/** On a line that is not comma-delimited, "0,05" is a decimal and "1,234" a thousands group. */
function normalizeCommas(line: string): string {
  if ((line.match(/,/g) ?? []).length > 1) return line;
  return line.replace(/(\d),(\d{3})(?!\d)/g, "$1$2").replace(/(\d),(\d+)/g, "$1.$2");
}

function parseLine(rawLine: string): Holding & { asset: StarterAsset | null } {
  const line = normalizeCommas(rawLine);
  const tokens = line.split(/[\s,;\t|]+/).filter(Boolean);
  let asset: StarterAsset | null = null;
  let tickerToken = -1;
  tokens.forEach((token, index) => {
    if (asset) return;
    const candidate = findAssetByTicker(token.replace(/^["'(]|["')]$/g, ""));
    if (candidate && /[A-Za-z]/.test(token)) {
      asset = candidate;
      tickerToken = index;
    }
  });
  asset ??= findAssetInText(line);

  let quantity: number | null = null;
  let marketValue: number | null = null;
  const money = /(\$\s?[\d\s.,]+|[\d\s.,]+\s?\$)/.exec(line);
  if (money) marketValue = parseNumber(money[0]);
  tokens.forEach((token, index) => {
    if (index === tickerToken || quantity !== null) return;
    if (money && money[0].includes(token)) return;
    const number = parseNumber(token);
    if (number !== null) quantity = number;
  });
  let account: AccountType | null = null;
  for (const [pattern, type] of ACCOUNT_PATTERNS) {
    if (pattern.test(line)) {
      account = type;
      break;
    }
  }
  return { asset, quantity, marketValue, account };
}

interface InputLines {
  lines: string[];
  files: FileReport[];
  unread: UnresolvedItem[];
}

/** The lines of the pasted text and of the text-like files; a file without readable text is reported, not parsed. */
function readInput(input: ExtractionInput, locale: Locale): InputLines {
  const lines: string[] = input.text ? input.text.split(/\r?\n/) : [];
  const files: FileReport[] = [];
  const unread: UnresolvedItem[] = [];
  for (const file of input.files ?? []) {
    const bytes = Buffer.byteLength(file.data_base64, "base64");
    const text = isTextLike(file.media_type, file.name) ? decodeText(file.data_base64) : null;
    const fileLines = text ? text.split(/\r?\n/) : [];
    files.push({ name: file.name, media_type: file.media_type, bytes, readable: text !== null, lines: fileLines.length });
    lines.push(...fileLines);
    // Not a row: like the runtime's unparsed items, it has no `position_id`.
    if (!text) unread.push({ raw: file.name, reason: UNRESOLVED_REASONS.unread_file[locale] });
  }
  return { lines, files, unread };
}

/** A line that names no security and is only a header row, or has no letter at all. */
function isNoise(line: string): boolean {
  return (HEADER_WORDS.test(line) && !/\d/.test(line)) || !/[A-Za-zÀ-ÿ]/.test(line);
}

/** Extract positions from pasted text and text-like files. */
export function extractPositions(input: ExtractionInput, locale: Locale): Extraction {
  const { lines, files, unread } = readInput(input, locale);
  // Like the runtime, every line becomes a row; an unidentified one stays `resolved: false` and is listed in `unresolved`.
  const positions: Position[] = [];
  const unresolved: UnresolvedItem[] = [...unread];
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (line === "" || line.startsWith("#")) continue;
    const { asset, ...holding } = parseLine(line);
    if (!asset && isNoise(line)) continue;
    const row: PositionRow = { id: `p${positions.length + 1}`, raw: line.slice(0, MAX_RAW_CHARS), ...holding };
    if (asset) {
      positions.push(positionFromAsset(row, asset, locale));
      continue;
    }
    const reason = UNRESOLVED_REASONS.not_in_universe[locale];
    positions.push(unresolvedPosition(row, reason));
    unresolved.push({ raw: line.slice(0, MAX_RAW_CHARS), reason, position_id: row.id });
  }
  return { positions, unresolved, files, lines: lines.length };
}

function rowOf(input: PositionInput): PositionRow {
  return {
    id: input.id,
    raw: input.raw ?? null,
    quantity: input.quantity ?? null,
    marketValue: input.market_value ?? null,
    account: input.account_type ?? null,
  };
}

/** A corrected row whose ticker is not in the starter universe: kept as declared, valued from its market value. */
function unlistedPosition(input: PositionInput, row: PositionRow, locale: Locale): Position {
  const currency = input.currency ?? "CAD";
  return {
    id: row.id,
    raw: row.raw,
    ticker: input.ticker ?? null,
    name: input.name ?? null,
    asset_class: input.asset_class ?? "other",
    sector: input.sector ?? null,
    market: input.market ?? null,
    currency,
    quantity: row.quantity,
    market_value: row.marketValue,
    account_type: row.account ?? "unknown",
    price: null,
    price_date: null,
    price_source: null,
    value_cad: valueInCad(null, null, row.marketValue, currency),
    resolved: false,
    notes: NOTES.not_in_universe[locale],
  };
}

/** Re-resolve a position corrected by the investor (`portfolio.confirm`). */
export function normalizeConfirmed(input: PositionInput, locale: Locale): Position {
  const row = rowOf(input);
  const asset = findAssetByTicker(input.ticker ?? null);
  return asset ? positionFromAsset(row, asset, locale) : unlistedPosition(input, row, locale);
}

const SHARE_DIGITS = 4;
const TOP_POSITIONS = 5;

/** A position counts in the exposures once it has a positive value in CAD. */
export function isValued(position: Position): boolean {
  return typeof position.value_cad === "number" && position.value_cad > 0;
}

const valueOf = (position: Position) => position.value_cad ?? 0;
const sumValues = (positions: Position[]) => positions.reduce((sum, position) => sum + valueOf(position), 0);
const shareOf = (value: number, total: number) => (total > 0 ? round(value / total, SHARE_DIGITS) : 0);

function shares(positions: Position[], key: (position: Position) => string, total: number): Record<string, number> {
  const sums: Record<string, number> = {};
  for (const position of positions) {
    if (!position.value_cad) continue;
    const name = key(position);
    sums[name] = (sums[name] ?? 0) + position.value_cad;
  }
  return Object.fromEntries(
    Object.entries(sums)
      .sort((left, right) => right[1] - left[1])
      .map(([name, sum]) => [name, shareOf(sum, total)]),
  );
}

function topPositions(valued: Position[], total: number): Exposures["top_positions"] {
  return valued
    .map((position) => ({ id: position.id, weight: shareOf(valueOf(position), total) }))
    .sort((left, right) => right.weight - left.weight)
    .slice(0, TOP_POSITIONS);
}

/** Thresholds of app/agents/src/alphaforge/profile/portfolio.py (THRESHOLDS), so the mock raises the same flags. */
export const FLAG_THRESHOLDS = {
  concentration_single_position: 0.2,
  concentration_sector: 0.4,
  home_bias_canada: 0.6,
  crypto_exposure_high: 0.1,
  cash_heavy: 0.3,
  few_holdings: 5,
} as const;

const SINGLE_LINE = ["equity", "bond", "crypto", "other"];
const DIVERSIFIED = ["etf_equity", "etf_bond", "etf_commodity", "fund"];

const nonCashOf = (positions: Position[]) => positions.filter((position) => position.asset_class !== "cash");

function classShare(valued: Position[], assetClass: string, total: number): number {
  return sumValues(valued.filter((position) => position.asset_class === assetClass)) / total;
}

function hasConcentratedPosition(valued: Position[], total: number): boolean {
  return valued.some(
    (position) =>
      SINGLE_LINE.includes(position.asset_class ?? "other") && valueOf(position) / total > FLAG_THRESHOLDS.concentration_single_position,
  );
}

/** One sector above the threshold among the stocks held directly, when there are at least two of them. */
function hasConcentratedSector(valued: Position[]): boolean {
  const equities = valued.filter((position) => position.asset_class === "equity");
  const equityTotal = sumValues(equities);
  if (!(equityTotal > 0 && equities.length > 1)) return false;
  const sectors: Record<string, number> = {};
  for (const position of equities) {
    const sector = position.sector ?? "Unknown";
    sectors[sector] = (sectors[sector] ?? 0) + valueOf(position);
  }
  return Math.max(...Object.values(sectors)) / equityTotal > FLAG_THRESHOLDS.concentration_sector;
}

function hasHomeBias(valued: Position[]): boolean {
  const nonCash = nonCashOf(valued);
  const nonCashTotal = sumValues(nonCash);
  if (!(nonCashTotal > 0)) return false;
  const canada = sumValues(nonCash.filter((position) => position.market === "TSX" || position.currency === "CAD"));
  return canada / nonCashTotal >= FLAG_THRESHOLDS.home_bias_canada;
}

function hasFewHoldings(valued: Position[]): boolean {
  const nonCash = nonCashOf(valued);
  return nonCash.length < FLAG_THRESHOLDS.few_holdings && !nonCash.some((position) => DIVERSIFIED.includes(position.asset_class ?? ""));
}

/** The flags of a valued portfolio, in the order the Python runtime raises them. */
const FLAG_RULES: Array<[flag: string, isRaised: (valued: Position[], total: number) => boolean]> = [
  ["concentration_single_position", hasConcentratedPosition],
  ["concentration_sector", hasConcentratedSector],
  ["home_bias_canada", hasHomeBias],
  ["crypto_exposure_high", (valued, total) => classShare(valued, "crypto", total) > FLAG_THRESHOLDS.crypto_exposure_high],
  ["cash_heavy", (valued, total) => classShare(valued, "cash", total) > FLAG_THRESHOLDS.cash_heavy],
  ["few_holdings", hasFewHoldings],
];

function exposureFlags(valued: Position[], total: number, unvalued: number): string[] {
  const flags = total > 0 ? FLAG_RULES.filter(([, isRaised]) => isRaised(valued, total)).map(([flag]) => flag) : [];
  if (unvalued > 0) flags.push("unvalued_positions");
  return flags;
}

/**
 * Exposures as shares of `total_value_cad` (CONTRACTS.md 3.3), computed by code on valued positions.
 * `extraUnvalued` counts items that are not rows (files the simulator cannot read).
 */
export function computeExposures(positions: Position[], extraUnvalued = 0): Exposures {
  const valued = positions.filter(isValued);
  const unvalued = positions.length - valued.length + extraUnvalued;
  const total = round(sumValues(valued));
  return {
    total_value_cad: total,
    by_asset_class: shares(valued, (position) => position.asset_class ?? "other", total),
    by_currency: shares(valued, (position) => position.currency ?? "CAD", total),
    by_market: shares(valued, (position) => position.market ?? "other", total),
    by_sector: shares(valued, (position) => position.sector ?? "other", total),
    top_positions: topPositions(valued, total),
    flags: exposureFlags(valued, total, unvalued),
  };
}

/** `PortfolioView.fx`: the USD/CAD rate of the starter dataset. */
export function fxRate(): FxRate {
  return { pair: "USDCAD", rate: USDCAD, date: PRICE_DATE, source: "starter:fx_usdcad_daily.csv" };
}

export function portfolioSources(positions: Position[]): Source[] {
  const sources: Source[] = [STARTER_SOURCES.universe, STARTER_SOURCES.prices];
  if (positions.some((position) => position.currency === "USD")) sources.push(STARTER_SOURCES.fx);
  return sources;
}
