import { describe, expect, it } from "vitest";
import { DEMO, DEMO_CHIPS } from "@/lib/sample/assistant-demo";
import { GROUPS, SAMPLE_FACTS, annualizedVol, drawdown2022, groupWeight, noise, samplePortfolio, tradingDays } from "@/lib/sample/portfolio";

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

  it("allocates 100 % across the five pockets, 48 % of it in bonds and gold", () => {
    expect(GROUPS.reduce((sum, group) => sum + groupWeight(group), 0)).toBe(100);
    expect(groupWeight(GROUPS[0]!) + groupWeight(GROUPS[3]!)).toBe(48);
    expect(new Set(GROUPS.map((group) => group.color)).size).toBe(5);
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
      for (const action of reply.actions) expect(action.key === "noop" || action.key === "simulatedPortfolio" || action.key in DEMO).toBe(true);
    }
    expect(texts.every((text) => text.trim().length > 0)).toBe(true);
    expect(DEMO_CHIPS.map((chip) => chip.key)).toEqual(["trap", "gold", "nvda"]);
    expect(DEMO.trap.verdict?.ok).toBe(false);
    expect(DEMO.sandbox.verdict?.ok).toBe(true);
  });
});
