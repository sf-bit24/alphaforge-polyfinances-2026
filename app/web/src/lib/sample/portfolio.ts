/**
 * The example portfolio of the approved drafts (dashboard and details), shown in
 * `mock` mode only and always labelled as an example. Nothing here is computed from
 * the investor’s profile: the guided portfolio (A3, analysis agents, Judge) is not
 * in version 1. The series are synthetic, seeded and calibrated like the draft:
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

export interface MonthlyReturn {
  /** Last trading day of the month. */
  at: number;
  /** Return of the month, as a share. */
  value: number;
}

/** Month-by-month returns of a value series. */
export function monthlyReturns(dates: number[], values: number[]): MonthlyReturn[] {
  const months: MonthlyReturn[] = [];
  let start = 0;
  for (let index = 1; index <= dates.length; index += 1) {
    const ends = index === dates.length || new Date(dates[index] ?? 0).getUTCMonth() !== new Date(dates[index - 1] ?? 0).getUTCMonth();
    if (!ends) continue;
    const base = values[Math.max(0, start - 1)] ?? 1;
    months.push({ at: dates[index - 1] ?? 0, value: (values[index - 1] ?? base) / base - 1 });
    start = index;
  }
  return months;
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

export interface GovernanceCheck {
  label: L;
  value: L;
  limit: L;
}

/** The seven limits of the example profile, all respected. */
export const GOVERNANCE: GovernanceCheck[] = [
  { label: { fr: "Poids d’un seul titre", en: "Weight of a single security" }, value: { fr: "5,0 %", en: "5.0%" }, limit: { fr: "≤ 5 %", en: "≤ 5%" } },
  { label: { fr: "Actions au total", en: "Equities in total" }, value: { fr: "44 %", en: "44%" }, limit: { fr: "≤ 45 %", en: "≤ 45%" } },
  { label: { fr: "Obligations et or", en: "Bonds and gold" }, value: { fr: "48 %", en: "48%" }, limit: { fr: "≥ 40 %", en: "≥ 40%" } },
  { label: { fr: "Cryptoactifs", en: "Crypto-assets" }, value: { fr: "0 %", en: "0%" }, limit: { fr: "= 0 %", en: "= 0%" } },
  { label: { fr: "Volatilité", en: "Volatility" }, value: { fr: "6,1 %", en: "6.1%" }, limit: { fr: "≤ 7 %", en: "≤ 7%" } },
  { label: { fr: "Encaisse de sécurité", en: "Safety cash" }, value: { fr: "8 mois", en: "8 months" }, limit: { fr: "≥ 6 mois", en: "≥ 6 months" } },
  {
    label: { fr: "Durée obligataire", en: "Bond duration" },
    value: { fr: "courte à moyenne", en: "short to medium" },
    limit: { fr: "pas de long terme", en: "no long term" },
  },
];

export type LogIcon = "stop" | "box" | "user" | "swap" | "data";
export type LogStatus = "stop" | "wait" | "ok" | "navy";

export interface LogEntry {
  icon: LogIcon;
  title: L;
  by: L;
  status: LogStatus;
  statusLabel: L;
  when: L;
}

export const DECISION_LOG: LogEntry[] = [
  {
    icon: "stop",
    title: { fr: "Refus provisoire · NVDA pour 50 000 $", en: "Provisional refusal · NVDA for $50,000" },
    by: { fr: "Judge · 3 plafonds dépassés", en: "Judge · 3 caps exceeded" },
    status: "stop",
    statusLabel: { fr: "Refusé", en: "Refused" },
    when: { fr: "aujourd’hui", en: "today" },
  },
  {
    icon: "box",
    title: { fr: "Bac à sable de 4 % proposé", en: "4% sandbox proposed" },
    by: { fr: "Agent du portefeuille · conforme", en: "Portfolio agent · compliant" },
    status: "wait",
    statusLabel: { fr: "À décider", en: "To decide" },
    when: { fr: "aujourd’hui", en: "today" },
  },
  {
    icon: "user",
    title: { fr: "Profil mis à jour · capacité de perte", en: "Profile updated · loss capacity" },
    by: { fr: "Agent du profil · votre réponse", en: "Profile agent · your answer" },
    status: "ok",
    statusLabel: { fr: "Confirmé", en: "Confirmed" },
    when: { fr: "hier", en: "yesterday" },
  },
  {
    icon: "swap",
    title: { fr: "Rééquilibrage simulé · or ramené à 6 %", en: "Simulated rebalancing · gold back to 6%" },
    by: { fr: "Agent du portefeuille · aucun ordre passé", en: "Portfolio agent · no order placed" },
    status: "navy",
    statusLabel: { fr: "Simulé", en: "Simulated" },
    when: { fr: "il y a 3 j", en: "3 days ago" },
  },
  {
    icon: "data",
    title: { fr: "Prix mis à jour au 12 nov. 2026", en: "Prices updated to Nov 12, 2026" },
    by: { fr: "Agent de données · Yahoo Finance", en: "Data agent · Yahoo Finance" },
    status: "ok",
    statusLabel: { fr: "Confirmé", en: "Confirmed" },
    when: { fr: "il y a 3 j", en: "3 days ago" },
  },
];

/** The four questions of the BNCD workshop, answered for the example portfolio. */
export const WHY: Array<{ title: L; text: L }> = [
  {
    title: { fr: "Quelles données", en: "Which data" },
    text: {
      fr: "Prix quotidiens de nov. 2021 à nov. 2026 (Yahoo Finance via le jeu de départ), taux de la Banque du Canada, votre profil.",
      en: "Daily prices from Nov 2021 to Nov 2026 (Yahoo Finance through the starter dataset), Bank of Canada rates, your profile.",
    },
  },
  {
    title: { fr: "Pourquoi ce choix", en: "Why this choice" },
    text: {
      fr: "Votre capacité à encaisser une perte est faible : vous aurez besoin de cet argent dès 2030. Près de la moitié est en obligations et en or pour amortir les baisses.",
      en: "Your capacity to absorb a loss is low: you will need this money from 2030. Almost half is in bonds and gold to cushion falls.",
    },
  },
  {
    title: { fr: "Quelles limites", en: "Which limits" },
    text: {
      fr: "Cinq ans d’historique seulement, et des titres choisis en 2026 : le passé paraît plus favorable qu’il ne l’était.",
      en: "Only five years of history, and securities picked in 2026: the past looks better than it was.",
    },
  },
  {
    title: { fr: "Ce qui changerait la réponse", en: "What would change the answer" },
    text: {
      fr: "Un départ à la retraite repoussé, ou un autre revenu stable, permettrait plus d’actions.",
      en: "A later retirement, or another stable income, would allow more equities.",
    },
  },
];

export const SAMPLE_FACTS = {
  capital: 400_000,
  volCap: 0.07,
  stressLimit: -0.12,
  stressScale: -0.2,
  retirement: { date: utc(2030, 6, 1), equityToday: 0.44, equityTarget: 0.32, glidePath: 0.28 },
  limits: { respected: 7, total: 7 },
} as const;

export interface SamplePortfolio {
  dates: number[];
  /** Portfolio value in CAD, ending at the capital. */
  value: number[];
  /** Daily returns of the portfolio. */
  returns: number[];
  /** XIU.TO alone, growth of 1 (rebased on the chart’s window). */
  benchmark: number[];
  /** 2022 worst drop of the portfolio, as a share (negative). */
  drop2022: number;
  /** Five-year annualized volatility, as a share. */
  vol5y: number;
  months: MonthlyReturn[];
}

let cached: SamplePortfolio | null = null;

/** Build (once) the example series: the 2022 drift is bisected until the 2022 drop is −9.8 %. */
export function samplePortfolio(): SamplePortfolio {
  if (cached) return cached;
  const dates = tradingDays();
  const shocksA = noise(7, dates.length);
  const shocksB = noise(11, dates.length);
  let low = -0.004;
  let high = 0;
  let portfolio = series(dates, shocksA, 0.061, (low + high) / 2);
  for (let step = 0; step < 30; step += 1) {
    const mid = (low + high) / 2;
    portfolio = series(dates, shocksA, 0.061, mid);
    if (drawdown2022(dates, portfolio.values) < -0.098) low = mid;
    else high = mid;
  }
  const last = portfolio.values[portfolio.values.length - 1] ?? 1;
  const value = portfolio.values.map((growth) => (growth * SAMPLE_FACTS.capital) / last);
  cached = {
    dates,
    value,
    returns: portfolio.returns,
    benchmark: series(dates, shocksB, 0.131, -0.0011).values,
    drop2022: drawdown2022(dates, value),
    vol5y: annualizedVol(portfolio.returns),
    months: monthlyReturns(dates, value).slice(-60),
  };
  return cached;
}

export type ChartRange = "1m" | "1y" | "5y";
export const CHART_RANGES: Record<ChartRange, { take: number | "all"; step: number }> = {
  "1m": { take: 22, step: 1 },
  "1y": { take: 252, step: 5 },
  "5y": { take: "all", step: 21 },
};

export interface ChartPoint {
  at: number;
  portfolio: number;
  /** XIU.TO alone, invested with the portfolio’s value at the window start. */
  benchmark: number;
}

/** Points of the comparison chart for a window, sampled every `step` trading days (last day always kept). */
export function chartPoints(sample: SamplePortfolio, range: ChartRange): ChartPoint[] {
  const { take, step } = CHART_RANGES[range];
  const count = sample.dates.length;
  const start = take === "all" ? 0 : count - take;
  const base = (sample.value[start] ?? 0) / (sample.benchmark[start] ?? 1);
  const points: ChartPoint[] = [];
  for (let index = start; index < count; index += 1) {
    if ((index - start) % step !== 0 && index !== count - 1) continue;
    points.push({ at: sample.dates[index] ?? 0, portfolio: sample.value[index] ?? 0, benchmark: (sample.benchmark[index] ?? 0) * base });
  }
  return points;
}

export type VolWindow = "1y" | "3y" | "5y";
export const VOL_WINDOWS: Record<VolWindow, number | "all"> = { "1y": 252, "3y": 756, "5y": "all" };

export function windowVol(sample: SamplePortfolio, window: VolWindow): number {
  const size = VOL_WINDOWS[window];
  return annualizedVol(sample.returns, size === "all" ? sample.returns.length : size);
}
