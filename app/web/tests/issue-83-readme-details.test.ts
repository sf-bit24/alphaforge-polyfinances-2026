import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { screensFr } from "@/lib/i18n/screens";
import { portfolioFr } from "@/lib/i18n/portfolio";

const README = readFileSync(new URL("../README.md", import.meta.url), "utf8");

/** The README line on the `local` and `aws` modes, under « Données d'exemple ». */
const realModesLine = README.split("\n").find((line) => line.startsWith("- en modes `local` et `aws`")) ?? "";

describe("issue #83 (suite): the README describes the Details page as it is since #79", () => {
  it("no longer says the Details page announces version 2", () => {
    expect(README).not.toMatch(/version 2/);
  });

  it("names the two tiles of the Details page and the way to the simulated portfolio, as the screen writes them", () => {
    const { simulated, existing } = screensFr.details;
    expect(realModesLine).toContain(`« ${simulated.title} »`);
    expect(realModesLine).toContain(`« ${existing.title} »`);
    expect(realModesLine).toContain(`« ${portfolioFr.personas.self.name} »`);
    expect(realModesLine).toContain("`/portfolio`");
  });
});
