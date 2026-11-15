import { describe, expect, it } from "vitest";
import { DEMO, DEMO_CHIPS } from "@/lib/sample/assistant-demo";
import {
  CHART_RANGES,
  DECISION_LOG,
  GOVERNANCE,
  GROUPS,
  SAMPLE_FACTS,
  WHY,
  annualizedVol,
  chartPoints,
  drawdown2022,
  groupWeight,
  monthlyReturns,
  noise,
  samplePortfolio,
  tradingDays,
  windowVol,
  type ChartRange,
} from "@/lib/sample/portfolio";

const day = (iso: string) => Date.parse(`${iso}T00:00:00Z`);

describe("example portfolio of the drafts", () => {
  it("uses weekdays from 2021-11-12 to 2026-11-12", () => {
    const dates = tradingDays();
    expect(dates[0]).toBe(day("2021-11-12"));
    expect(dates[dates.length - 1]).toBe(day("2026-11-12"));
    expect(dates.every((at) => ![0, 6].includes(new Date(at).getUTCDay()))).toBe(true);
    expect(dates.length).toBe(1305);
  });

  it("is calibrated like the draft: 6.1 % volatility, −9.8 % in 2022, 400 000 $ today", () => {
    const sample = samplePortfolio();
    expect(sample.value[sample.value.length - 1]).toBeCloseTo(SAMPLE_FACTS.capital, 6);
    expect(sample.vol5y).toBeCloseTo(0.061, 3);
    expect(sample.drop2022).toBeCloseTo(-0.098, 3);
    expect(drawdown2022(sample.dates, sample.value)).toBeCloseTo(sample.drop2022, 10);
    expect(annualizedVol(sample.returns)).toBeCloseTo(sample.vol5y, 10);
  });

  it("is deterministic (seeded) and built once", () => {
    expect(noise(7, 5)).toEqual(noise(7, 5));
    expect(noise(7, 5)).not.toEqual(noise(11, 5));
    expect(samplePortfolio()).toBe(samplePortfolio());
  });

  it("gives sixty monthly returns ending in November 2026, chained back to the values", () => {
    const sample = samplePortfolio();
    expect(sample.months).toHaveLength(60);
    const last = sample.months[sample.months.length - 1]!;
    expect(new Date(last.at).toISOString().slice(0, 10)).toBe("2026-11-12");
    const all = monthlyReturns(sample.dates, sample.value);
    const growth = all.reduce((product, month) => product * (1 + month.value), 1);
    expect(growth).toBeCloseTo(sample.value[sample.value.length - 1]! / sample.value[0]!, 8);
  });

  it("samples each chart window from its start, keeps the last day, and rebases XIU.TO on the portfolio", () => {
    const sample = samplePortfolio();
    for (const range of Object.keys(CHART_RANGES) as ChartRange[]) {
      const points = chartPoints(sample, range);
      const first = points[0]!;
      const last = points[points.length - 1]!;
      expect(last.at).toBe(sample.dates[sample.dates.length - 1]);
      expect(first.benchmark).toBeCloseTo(first.portfolio, 6);
      expect(points.every((point, index) => index === 0 || point.at > points[index - 1]!.at)).toBe(true);
    }
    expect(chartPoints(sample, "1m")).toHaveLength(22);
  });

  it("reads the volatility over the three windows of the gauge", () => {
    const sample = samplePortfolio();
    expect(windowVol(sample, "5y")).toBeCloseTo(sample.vol5y, 10);
    for (const span of ["1y", "3y"] as const) {
      const vol = windowVol(sample, span);
      expect(vol).toBeGreaterThan(0.02);
      expect(vol).toBeLessThan(0.1);
    }
  });

  it("allocates 100 % across the five pockets, 48 % of it in bonds and gold", () => {
    expect(GROUPS.reduce((sum, group) => sum + groupWeight(group), 0)).toBe(100);
    expect(groupWeight(GROUPS[0]!) + groupWeight(GROUPS[3]!)).toBe(48);
    expect(new Set(GROUPS.map((group) => group.color)).size).toBe(5);
    expect(GOVERNANCE).toHaveLength(SAMPLE_FACTS.limits.total);
    expect(WHY).toHaveLength(4);
    expect(DECISION_LOG.length).toBeGreaterThan(0);
  });
});

describe("assistant demo script", () => {
  it("has every text in French and English, and actions that point to scripts", () => {
    const texts: string[] = [];
    for (const reply of Object.values(DEMO)) {
      const localized = [
        reply.user,
        ...reply.paragraphs,
        ...(reply.reasons?.flatMap((reason) => [reason.title, reason.text]) ?? []),
        ...(reply.verdict ? [reply.verdict.title, reply.verdict.by, ...reply.verdict.checks.flatMap((check) => [check.label, check.value, check.cap])] : []),
        ...(reply.closing ? [reply.closing] : []),
        ...reply.sources,
        ...reply.actions.map((action) => action.label),
        ...reply.trace.flatMap((step) => [step.title, step.detail]),
      ];
      for (const text of localized) texts.push(text.fr, text.en);
      for (const action of reply.actions) expect(action.key === "noop" || action.key === "dashboardDetails" || action.key in DEMO).toBe(true);
    }
    expect(texts.every((text) => text.trim().length > 0)).toBe(true);
    expect(DEMO_CHIPS.map((chip) => chip.key)).toEqual(["trap", "gold", "nvda"]);
    expect(DEMO.trap.verdict?.ok).toBe(false);
    expect(DEMO.sandbox.verdict?.ok).toBe(true);
  });
});
