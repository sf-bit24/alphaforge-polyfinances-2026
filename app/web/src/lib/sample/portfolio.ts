/**
 * The example portfolio of the approved dashboard draft, shown in `mock` mode only
 * and always labelled as an example. Nothing here is computed from the investor’s
 * profile. The series are synthetic, seeded and calibrated like the draft:
 * a 6.1 % five-year volatility, a −9.8 % worst drop in 2022, a 400 000 $ capital.
 */
import type { Locale } from "@/lib/contract/schemas";

export interface L {
  fr: string;
  en: string;
}

export const tr = (text: L, locale: Locale): string => text[locale];

const DAY = 86_400_000;
const utc = (year: number, month: number, day: number) => Date.UTC(year, month - 1, day);

/** Trading days (weekdays) from 2021-11-12 to 2026-11-12, as UTC midnights. */
export function tradingDays(from = utc(2021, 11, 12), to = utc(2026, 11, 12)): number[] {
  const days: number[] = [];
  for (let at = from; at <= to; at += DAY) {
    const weekday = new Date(at).getUTCDay();
    if (weekday !== 0 && weekday !== 6) days.push(at);
  }
  return days;
}

/** Park-Miller generator, summed three times: a bell-shaped, seeded noise. */
export function noise(seed: number, count: number): number[] {
  let state = seed;
  const next = () => (state = (state * 16807) % 2147483647) / 2147483647;
  return Array.from({ length: count }, () => (next() + next() + next() - 1.5) / 0.5);
}

const IN_2022_DROP = [utc(2022, 1, 3), utc(2022, 10, 14)] as const;
const RECOVERY = [utc(2022, 10, 14), utc(2023, 3, 31)] as const;

export interface Series {
  /** Daily returns. */
  returns: number[];
  /** Growth of 1. */
  values: number[];
}

/** A daily series with a 2022 drift `drift2022`, rescaled to the annualized volatility `vol`. */
export function series(dates: number[], shocks: number[], vol: number, drift2022: number): Series {
  const raw = shocks.map((shock, index) => {
    const at = dates[index] ?? 0;
    const drop = at >= IN_2022_DROP[0] && at <= IN_2022_DROP[1] ? drift2022 : 0;
    const recovery = at > RECOVERY[0] && at <= RECOVERY[1] ? 0.0004 : 0;
    return 0.00022 + shock * 0.004 + drop + recovery;
  });
  const mean = raw.reduce((sum, value) => sum + value, 0) / raw.length;
  const sd = Math.sqrt(raw.reduce((sum, value) => sum + (value - mean) ** 2, 0) / raw.length) * Math.sqrt(252);
  const returns = raw.map((value) => mean + ((value - mean) * vol) / sd);
  const values: number[] = [];
  let growth = 1;
  for (const value of returns) {
    growth *= 1 + value;
    values.push(growth);
  }
  return { returns, values };
}

/** Worst peak-to-trough fall within calendar year 2022. */
export function drawdown2022(dates: number[], values: number[]): number {
  let peak = 0;
  let worst = 0;
  values.forEach((value, index) => {
    if (new Date(dates[index] ?? 0).getUTCFullYear() !== 2022) return;
    peak = Math.max(peak, value);
    worst = Math.min(worst, value / peak - 1);
  });
  return worst;
}

/** Annualized volatility of the last `window` daily returns. */
export function annualizedVol(returns: number[], window = returns.length): number {
  const slice = returns.slice(-window);
  const mean = slice.reduce((sum, value) => sum + value, 0) / slice.length;
  return Math.sqrt(slice.reduce((sum, value) => sum + (value - mean) ** 2, 0) / slice.length) * Math.sqrt(252);
}

export type GroupKey = "bonds" | "ca_equity" | "us_equity" | "gold" | "cash";

export interface Holding {
  ticker: string;
  name: L;
  /** Weight in percent of the portfolio. */
  weight: number;
  /** One-year volatility in percent, or null for cash. */
  vol1y: number | null;
}

export interface Group {
  key: GroupKey;
  name: L;
  color: string;
  holdings: Holding[];
}

/** Colors validated together (see globals.css, chart series). */
export const GROUP_COLORS: Record<GroupKey, string> = {
  bonds: "#0B2341",
  ca_equity: "#E41C23",
  us_equity: "#F08A8E",
  gold: "#A8831C",
  cash: "#8D9BAD",
};

export const GROUPS: Group[] = [
  {
    key: "bonds",
    name: { fr: "Obligations", en: "Bonds" },
    color: GROUP_COLORS.bonds,
    holdings: [
      { ticker: "XBB.TO", name: { fr: "iShares Core Canadian Universe Bond", en: "iShares Core Canadian Universe Bond" }, weight: 22, vol1y: 4.9 },
      { ticker: "ZST.TO", name: { fr: "BMO Ultra Short-Term Bond", en: "BMO Ultra Short-Term Bond" }, weight: 12, vol1y: 0.9 },
      { ticker: "AGG", name: { fr: "iShares Core U.S. Aggregate Bond", en: "iShares Core U.S. Aggregate Bond" }, weight: 8, vol1y: 5.8 },
    ],
  },
  {
    key: "ca_equity",
    name: { fr: "Actions canadiennes", en: "Canadian equities" },
    color: GROUP_COLORS.ca_equity,
    holdings: [
      { ticker: "XIU.TO", name: { fr: "iShares S&P/TSX 60", en: "iShares S&P/TSX 60" }, weight: 14, vol1y: 13.1 },
      { ticker: "RY.TO", name: { fr: "Banque Royale du Canada", en: "Royal Bank of Canada" }, weight: 5, vol1y: 17.2 },
      { ticker: "FTS.TO", name: { fr: "Fortis", en: "Fortis" }, weight: 5, vol1y: 14.0 },
      { ticker: "ENB.TO", name: { fr: "Enbridge", en: "Enbridge" }, weight: 4, vol1y: 16.5 },
    ],
  },
  {
    key: "us_equity",
    name: { fr: "Actions américaines", en: "U.S. equities" },
    color: GROUP_COLORS.us_equity,
    holdings: [
      { ticker: "SPY", name: { fr: "SPDR S&P 500", en: "SPDR S&P 500" }, weight: 8, vol1y: 15.4 },
      { ticker: "JNJ", name: { fr: "Johnson & Johnson", en: "Johnson & Johnson" }, weight: 4, vol1y: 15.9 },
      { ticker: "PG", name: { fr: "Procter & Gamble", en: "Procter & Gamble" }, weight: 4, vol1y: 16.3 },
    ],
  },
  {
    key: "gold",
    name: { fr: "Or", en: "Gold" },
    color: GROUP_COLORS.gold,
    holdings: [{ ticker: "GLD", name: { fr: "SPDR Gold Shares", en: "SPDR Gold Shares" }, weight: 6, vol1y: 14.6 }],
  },
  {
    key: "cash",
    name: { fr: "Encaisse", en: "Cash" },
    color: GROUP_COLORS.cash,
    holdings: [{ ticker: "CAD", name: { fr: "Encaisse", en: "Cash" }, weight: 8, vol1y: null }],
  },
];

export const groupWeight = (group: Group): number => group.holdings.reduce((sum, holding) => sum + holding.weight, 0);

export const SAMPLE_FACTS = {
  capital: 400_000,
  volCap: 0.07,
  limits: { respected: 7, total: 7 },
} as const;

export interface SamplePortfolio {
  dates: number[];
  /** Portfolio value in CAD, ending at the capital. */
  value: number[];
  /** Daily returns of the portfolio. */
  returns: number[];
  /** 2022 worst drop of the portfolio, as a share (negative). */
  drop2022: number;
  /** Five-year annualized volatility, as a share. */
  vol5y: number;
}

let cached: SamplePortfolio | null = null;

/** Build (once) the example series: the 2022 drift is bisected until the 2022 drop is −9.8 %. */
export function samplePortfolio(): SamplePortfolio {
  if (cached) return cached;
  const dates = tradingDays();
  const shocks = noise(7, dates.length);
  let low = -0.004;
  let high = 0;
  let portfolio = series(dates, shocks, 0.061, (low + high) / 2);
  for (let step = 0; step < 30; step += 1) {
    const mid = (low + high) / 2;
    portfolio = series(dates, shocks, 0.061, mid);
    if (drawdown2022(dates, portfolio.values) < -0.098) low = mid;
    else high = mid;
  }
  const last = portfolio.values[portfolio.values.length - 1] ?? 1;
  const value = portfolio.values.map((growth) => (growth * SAMPLE_FACTS.capital) / last);
  cached = {
    dates,
    value,
    returns: portfolio.returns,
    drop2022: drawdown2022(dates, value),
    vol5y: annualizedVol(portfolio.returns),
  };
  return cached;
}
