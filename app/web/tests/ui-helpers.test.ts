import { describe, expect, it } from "vitest";
import { niceTicks } from "@/lib/chart/ticks";
import { curly, formatCompactMoney, formatSignedPoints, formatTime } from "@/lib/i18n/locale";
import { NARROW, sceneLayout, stopX, WORLD } from "@/lib/journey/geometry";

const nbsp = (text: string) => text.replace(/[  ]/g, " ");

describe("niceTicks", () => {
  it("picks round values inside the range", () => {
    expect(niceTicks(392_000, 533_443)).toEqual([400_000, 450_000, 500_000]);
    expect(niceTicks(0, 10)).toEqual([0, 2.5, 5, 7.5, 10].map(Math.round));
  });

  it("returns nothing for an empty range", () => {
    expect(niceTicks(5, 5)).toEqual([]);
    expect(niceTicks(10, 2)).toEqual([]);
  });

  it("keeps three to five ticks across magnitudes", () => {
    for (const [lo, hi] of [
      [12, 97],
      [380_000, 420_000],
      [1_000_000, 2_400_000],
    ] as const) {
      const ticks = niceTicks(lo, hi);
      expect(ticks.length).toBeGreaterThanOrEqual(3);
      expect(ticks.length).toBeLessThanOrEqual(5);
      expect(ticks.every((tick) => tick >= lo && tick <= hi)).toBe(true);
    }
  });
});

describe("number formats of the details page", () => {
  it("writes a difference of returns in points, with a true minus", () => {
    expect(nbsp(formatSignedPoints(-0.355, "fr"))).toBe("−35,5 pts");
    expect(formatSignedPoints(0.021, "en")).toBe("+2.1 pts");
  });

  it("writes axis values in thousands or millions", () => {
    expect(nbsp(formatCompactMoney(450_000, "fr"))).toBe("450 k$");
    expect(formatCompactMoney(450_000, "en")).toBe("$450k");
    expect(nbsp(formatCompactMoney(1_250_000, "fr"))).toBe("1,3 M$");
  });

  it("writes trace times as a clock, not a duration", () => {
    const at = new Date(2026, 10, 14, 21, 4, 8).toISOString();
    expect(formatTime(at, "fr")).toBe("21:04:08");
    expect(formatTime(at, "en")).toBe("21:04:08");
  });
});

describe("curly", () => {
  it("turns apostrophes between letters into typographic ones", () => {
    expect(curly("Quel est l'objectif d'un placement ?")).toBe("Quel est l’objectif d’un placement ?");
    expect(curly("don't 'quoted'")).toBe("don’t 'quoted'");
  });
});

describe("sceneLayout", () => {
  it("fills the window height on wide screens, as the draft", () => {
    const layout = sceneLayout(1440, 900);
    expect(layout.narrow).toBe(false);
    expect(layout.scale).toBe(1);
    expect(layout.ground).toBe(WORLD.ground);
  });

  it("draws a strip along the bottom on a phone, with the walker on screen", () => {
    const layout = sceneLayout(390, 844);
    expect(layout.narrow).toBe(true);
    expect(layout.ground).toBeLessThan(844);
    expect(layout.ground).toBeGreaterThan(844 * 0.8);
    const manX = layout.x + WORLD.manX * layout.scale;
    expect(manX).toBeGreaterThan(20);
    expect(manX).toBeLessThan(390 / 2);
    expect(layout.manTop).toBeLessThan(layout.ground);
    expect(layout.y + WORLD.ground * layout.scale).toBeCloseTo(layout.ground);
  });

  it("switches at the phone breakpoint", () => {
    expect(sceneLayout(NARROW - 1, 800).narrow).toBe(true);
    expect(sceneLayout(NARROW, 800).narrow).toBe(false);
  });

  it("spaces the stops evenly", () => {
    expect(stopX(-1)).toBe(0);
    expect(stopX(3) - stopX(2)).toBe(WORLD.gap);
  });
});
