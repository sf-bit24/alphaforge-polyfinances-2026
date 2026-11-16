import { describe, expect, it } from "vitest";
import { curly, formatTime } from "@/lib/i18n/locale";
import { NARROW, sceneLayout, stopX, WORLD } from "@/lib/journey/geometry";

describe("formatTime", () => {
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
