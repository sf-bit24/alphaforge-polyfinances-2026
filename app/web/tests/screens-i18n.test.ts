import { describe, expect, it } from "vitest";
import { DIMENSIONS } from "@/lib/contract/schemas";
import { dictionaries } from "@/lib/i18n/dictionary";
import { screensEn, screensFr } from "@/lib/i18n/screens";

type Tree = { [key: string]: unknown };

/** Same keys, same array lengths and same kinds of leaves in both languages. */
function shape(value: unknown, path = ""): string[] {
  if (Array.isArray(value)) return [`${path}[${value.length}]`, ...value.flatMap((item, index) => shape(item, `${path}[${index}]`))];
  if (typeof value === "function") return [`${path}()`];
  if (value && typeof value === "object") return Object.keys(value as Tree).sort().flatMap((key) => shape((value as Tree)[key], `${path}.${key}`));
  return [`${path}:${typeof value}`];
}

function strings(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(strings);
  if (value && typeof value === "object") return Object.values(value as Tree).flatMap(strings);
  return [];
}

describe("screen strings", () => {
  it("have the same structure in French and English", () => {
    expect(shape(screensEn)).toEqual(shape(screensFr));
  });

  it("are merged into both dictionaries", () => {
    expect(dictionaries.fr.journey).toBe(screensFr.journey);
    expect(dictionaries.en.journey).toBe(screensEn.journey);
    expect(dictionaries.fr.dash.hello).toBe("Bonjour");
    expect(dictionaries.en.dash.hello).toBe("Hello");
  });

  it("have a line for every dimension, and no empty text", () => {
    for (const screens of [screensFr, screensEn]) {
      for (const dimension of DIMENSIONS) expect(screens.journey.say.dimension[dimension].length).toBeGreaterThan(0);
      expect(strings(screens).every((text) => text.trim().length > 0)).toBe(true);
    }
  });

  it("format their parameters", () => {
    expect(screensFr.assistant.profilePill("64 %")).toBe("Profil : 64 %");
    expect(screensFr.assistant.how(1)).toBe("Comment j’ai répondu (1 étape)");
    expect(screensEn.assistant.how(4)).toBe("How I answered (4 steps)");
  });
});
