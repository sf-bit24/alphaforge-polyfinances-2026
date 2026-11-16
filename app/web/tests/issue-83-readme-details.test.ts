import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { screensFr } from "@/lib/i18n/screens";
import { portfolioFr } from "@/lib/i18n/portfolio";

const README = readFileSync(new URL("../README.md", import.meta.url), "utf8");

/** The README line on the `local` and `aws` modes, under « Données d'exemple ». */
const realModesLine = README.split("\n").find((line) => line.startsWith("- en modes `local` et `aws`")) ?? "";

describe("issue #83 (suite): the README describes the screens as they are, without the Details page", () => {
  it("no longer says anything announces version 2", () => {
    expect(README).not.toMatch(/version 2/);
  });

  it("no longer lists the Details page, its route or its components", () => {
    expect(README).not.toMatch(/`\/details`|page Détails|components\/details|dashboard, details/);
  });

  it("names the dashboard tile and the way to the simulated portfolio, as the screen writes them", () => {
    expect(realModesLine).toContain(`« ${screensFr.dash.real.simulated.title} »`);
    expect(realModesLine).toContain(`« ${portfolioFr.personas.self.name} »`);
    expect(realModesLine).toContain("`/portfolio`");
  });
});
