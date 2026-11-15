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

/** Value in CAD of a quantity or a declared market value, in the given currency. */
export function valueInCad(
  quantity: number | null | undefined,
  price: number | null | undefined,
  marketValue: number | null | undefined,
  currency: string | null | undefined,
): number | null {
  const native =
    typeof quantity === "number" && typeof price === "number"
      ? quantity * price
      : typeof marketValue === "number"
        ? marketValue
        : null;
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

function positionFromAsset(
  id: string,
  raw: string,
  asset: StarterAsset,
  quantity: number | null,
  marketValue: number | null,
  account: AccountType | null,
  locale: Locale,
): Position {
  const value = valueInCad(quantity, asset.close, quantity === null ? marketValue : null, asset.currency);
  let notes: string | null = null;
  if (quantity === null && marketValue !== null) notes = NOTES.value_declared[locale];
  if (quantity === null && marketValue === null) notes = NOTES.quantity_missing[locale];
  return {
    id,
    raw,
    ticker: asset.ticker,
    name: asset.name,
    asset_class: asset.asset_class,
    sector: asset.sector,
    market: asset.market,
    currency: asset.currency,
    quantity,
    market_value: marketValue,
    account_type: account ?? "unknown",
    price: asset.close,
    price_date: PRICE_DATE,
    price_source: STARTER_SOURCES.prices.resource,
    value_cad: value,
    resolved: true,
    notes,
  };
}

/** On a line that is not comma-delimited, "0,05" is a decimal and "1,234" a thousands group. */
function normalizeCommas(line: string): string {
  if ((line.match(/,/g) ?? []).length > 1) return line;
  return line.replace(/(\d),(\d{3})(?!\d)/g, "$1$2").replace(/(\d),(\d+)/g, "$1.$2");
}

function parseLine(rawLine: string): { asset: StarterAsset | null; quantity: number | null; marketValue: number | null; account: AccountType | null } {
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

/** Extract positions from pasted text and text-like files. */
export function extractPositions(input: ExtractionInput, locale: Locale): Extraction {
  const lines: string[] = [];
  const files: FileReport[] = [];
  const unresolved: UnresolvedItem[] = [];
  if (input.text) lines.push(...input.text.split(/\r?\n/));
  for (const file of input.files ?? []) {
    const bytes = Buffer.byteLength(file.data_base64, "base64");
    const text = isTextLike(file.media_type, file.name) ? decodeText(file.data_base64) : null;
    const fileLines = text ? text.split(/\r?\n/) : [];
    files.push({ name: file.name, media_type: file.media_type, bytes, readable: text !== null, lines: fileLines.length });
    if (text) lines.push(...fileLines);
    else {
      // Not a row: like the runtime's unparsed items, it has no `position_id`.
      unresolved.push({
        raw: file.name,
        reason:
          locale === "fr"
            ? "contenu non lu par le simulateur (PDF, image ou tableur); en mode AWS, A2 le lit avec le modèle"
            : "content not read by the simulator (PDF, image or spreadsheet); in AWS mode, A2 reads it with the model",
      });
    }
  }

  // Like the runtime, every line becomes a row; an unidentified one stays `resolved: false` and is listed in `unresolved`.
  const positions: Position[] = [];
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (line === "" || line.startsWith("#")) continue;
    const parsed = parseLine(line);
    const id = `p${positions.length + 1}`;
    if (!parsed.asset) {
      if (HEADER_WORDS.test(line) && !/\d/.test(line)) continue;
      if (!/[A-Za-zÀ-ÿ]/.test(line)) continue;
      const reason = locale === "fr" ? "titre introuvable dans l'univers du jeu de départ" : "security not found in the starter universe";
      positions.push(unresolvedPosition(id, line.slice(0, 200), parsed, reason));
      unresolved.push({ raw: line.slice(0, 200), reason, position_id: id });
      continue;
    }
    positions.push(positionFromAsset(id, line.slice(0, 200), parsed.asset, parsed.quantity, parsed.marketValue, parsed.account, locale));
  }
  return { positions, unresolved, files, lines: lines.length };
}

function unresolvedPosition(id: string, raw: string, parsed: ReturnType<typeof parseLine>, reason: string): Position {
  const currency = parsed.marketValue !== null ? "CAD" : null;
  return {
    id,
    raw,
    ticker: null,
    name: null,
    asset_class: null,
    sector: null,
    market: null,
    currency,
    quantity: parsed.quantity,
    market_value: parsed.marketValue,
    account_type: parsed.account,
    price: null,
    price_date: null,
    price_source: null,
    value_cad: parsed.marketValue !== null ? valueInCad(null, null, parsed.marketValue, "CAD") : null,
    resolved: false,
    notes: reason,
  };
}

/** Re-resolve a position corrected by the investor (`portfolio.confirm`). */
export function normalizeConfirmed(input: PositionInput, locale: Locale): Position {
  const asset = findAssetByTicker(input.ticker ?? null);
  const quantity = input.quantity ?? null;
  const marketValue = input.market_value ?? null;
  if (asset) {
    const position = positionFromAsset(
      input.id,
      input.raw ?? input.ticker ?? "",
      asset,
      quantity,
      marketValue,
      input.account_type ?? null,
      locale,
    );
    return { ...position, raw: input.raw ?? null, account_type: input.account_type ?? "unknown" };
  }
  const currency = input.currency ?? "CAD";
  return {
    id: input.id,
    raw: input.raw ?? null,
    ticker: input.ticker ?? null,
    name: input.name ?? null,
    asset_class: input.asset_class ?? "other",
    sector: input.sector ?? null,
    market: input.market ?? null,
    currency,
    quantity,
    market_value: marketValue,
    account_type: input.account_type ?? "unknown",
    price: null,
    price_date: null,
    price_source: null,
    value_cad: valueInCad(null, null, marketValue, currency),
    resolved: false,
    notes: NOTES.not_in_universe[locale],
  };
}

function shares(positions: Position[], key: (position: Position) => string, total: number): Record<string, number> {
  const sums: Record<string, number> = {};
  for (const position of positions) {
    if (!position.value_cad) continue;
    const name = key(position);
    sums[name] = (sums[name] ?? 0) + position.value_cad;
  }
  return Object.fromEntries(
    Object.entries(sums)
      .sort((a, b) => b[1] - a[1])
      .map(([name, sum]) => [name, total > 0 ? round(sum / total, 4) : 0]),
  );
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

/**
 * Exposures as shares of `total_value_cad` (CONTRACTS.md 3.3), computed by code on valued positions.
 * `extraUnvalued` counts items that are not rows (files the simulator cannot read).
 */
export function computeExposures(positions: Position[], extraUnvalued = 0): Exposures {
  const valued = positions.filter((position) => typeof position.value_cad === "number" && position.value_cad > 0);
  const unvalued = positions.length - valued.length + extraUnvalued;
  const total = round(valued.reduce((sum, position) => sum + (position.value_cad ?? 0), 0));
  const byAssetClass = shares(valued, (position) => position.asset_class ?? "other", total);
  const byCurrency = shares(valued, (position) => position.currency ?? "CAD", total);
  const byMarket = shares(valued, (position) => position.market ?? "other", total);
  const bySector = shares(valued, (position) => position.sector ?? "other", total);
  const top = valued
    .map((position) => ({ id: position.id, weight: total > 0 ? round((position.value_cad ?? 0) / total, 4) : 0 }))
    .sort((a, b) => b.weight - a.weight)
    .slice(0, 5);

  const flags: string[] = [];
  const value = (position: Position) => position.value_cad ?? 0;
  const sum = (list: Position[]) => list.reduce((acc, position) => acc + value(position), 0);
  if (total > 0) {
    const t = FLAG_THRESHOLDS;
    if (valued.some((position) => SINGLE_LINE.includes(position.asset_class ?? "other") && value(position) / total > t.concentration_single_position)) {
      flags.push("concentration_single_position");
    }
    const equities = valued.filter((position) => position.asset_class === "equity");
    const equityTotal = sum(equities);
    if (equityTotal > 0 && equities.length > 1) {
      const sectors: Record<string, number> = {};
      for (const position of equities) sectors[position.sector ?? "Unknown"] = (sectors[position.sector ?? "Unknown"] ?? 0) + value(position);
      if (Math.max(...Object.values(sectors)) / equityTotal > t.concentration_sector) flags.push("concentration_sector");
    }
    const nonCash = valued.filter((position) => position.asset_class !== "cash");
    const nonCashTotal = sum(nonCash);
    if (nonCashTotal > 0) {
      const canada = sum(nonCash.filter((position) => position.market === "TSX" || position.currency === "CAD"));
      if (canada / nonCashTotal >= t.home_bias_canada) flags.push("home_bias_canada");
    }
    if (sum(valued.filter((position) => position.asset_class === "crypto")) / total > t.crypto_exposure_high) flags.push("crypto_exposure_high");
    if (sum(valued.filter((position) => position.asset_class === "cash")) / total > t.cash_heavy) flags.push("cash_heavy");
    if (nonCash.length < t.few_holdings && !nonCash.some((position) => DIVERSIFIED.includes(position.asset_class ?? ""))) {
      flags.push("few_holdings");
    }
  }
  if (unvalued > 0) flags.push("unvalued_positions");

  return {
    total_value_cad: total,
    by_asset_class: byAssetClass,
    by_currency: byCurrency,
    by_market: byMarket,
    by_sector: bySector,
    top_positions: top,
    flags,
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
