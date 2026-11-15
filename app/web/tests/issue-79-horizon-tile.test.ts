import { createElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ClientState, type Locale } from "@/lib/contract/schemas";
import { horizonTileText } from "@/components/dashboard/bento-text";
import { ProfileBento } from "@/components/dashboard/bento";
import { I18nProvider } from "@/lib/i18n/provider";
import { clientState, profileView } from "./fixtures/contract-examples";

// Summaries of the horizon refined by ranges (#75), as the profile runtime wrote them in the e2e check (verif-yan).
const REFINED = {
  fr: "De 3 à 10 ans · Années avant le premier retrait important : de 5 à moins de 7 ans (5 ans retenus par prudence) · Par étapes, sur quelques années",
  frLong: "10 ans et plus · Années avant le premier retrait important : de 15 à moins de 20 ans (15 ans retenus par prudence) · Par étapes, sur quelques années",
  en: "3 to 10 years · Years before the first major withdrawal: 5 to less than 7 years (5 years used as a cautious figure) · In stages, over a few years",
};

// `children` is required by I18nProvider's props; createElement passes it as an argument.
const Provider = I18nProvider as (props: { initialLocale: Locale; children?: ReactNode }) => ReactElement;

function bento(horizon: string, objective: string, locale: Locale): string {
  const dimensions = { ...profileView.dimensions, horizon: { ...profileView.dimensions.horizon, summary: horizon }, objective: { ...profileView.dimensions.objective, summary: objective } };
  const state = ClientState.parse({ ...clientState, stage: "followups", questions: [], profile: { ...profileView, dimensions } });
  return renderToStaticMarkup(createElement(Provider, { initialLocale: locale }, createElement(ProfileBento, { state })));
}

describe("text of the horizon tile (#79, after #75)", () => {
  it("keeps the horizon band alone as the figure, and the other facts under the label", () => {
    expect(horizonTileText(REFINED.fr)).toEqual({
      figure: "De 3 à 10 ans",
      details: "Années avant le premier retrait important : de 5 à moins de 7 ans (5 ans retenus par prudence) · Par étapes, sur quelques années",
    });
    expect(horizonTileText(REFINED.en)).toEqual({
      figure: "3 to 10 years",
      details: "Years before the first major withdrawal: 5 to less than 7 years (5 years used as a cautious figure) · In stages, over a few years",
    });
  });

  it("drops and rewrites nothing: the figure and the details give back the summary", () => {
    for (const summary of Object.values(REFINED)) {
      const { figure, details } = horizonTileText(summary);
      expect([figure, details].join(" · ")).toBe(summary);
    }
  });

  it("shows a summary of one fact as the figure alone, and a dash without summary", () => {
    expect(horizonTileText("10 ans et plus")).toEqual({ figure: "10 ans et plus", details: null });
    expect(horizonTileText(null)).toEqual({ figure: "—", details: null });
    expect(horizonTileText(undefined)).toEqual({ figure: "—", details: null });
  });
});

describe("horizon tile of the dashboard, with a horizon refined by ranges (#79)", () => {
  it("renders the band as the figure, then the label, the other facts and the objective, in French and English", () => {
    const cases = [
      { locale: "fr" as const, summary: REFINED.fr, label: "Horizon de placement", objective: "Préparer la retraite" },
      { locale: "en" as const, summary: REFINED.en, label: "Investment horizon", objective: "Prepare for retirement" },
    ];
    for (const { locale, summary, label, objective } of cases) {
      const html = bento(summary, objective, locale);
      const { figure, details } = horizonTileText(summary);
      // The figure holds the band only, no longer the whole seven-line summary.
      expect(html).toMatch(new RegExp(`<span class="[^"]*" title="${figure}">${figure}</span>`));
      expect(html).not.toContain(`>${summary}<`);
      const order = [figure, label, details!, objective].map((text) => html.indexOf(`>${text}<`));
      expect(order.every((index) => index >= 0)).toBe(true);
      expect([...order].sort((first, second) => first - second)).toEqual(order);
    }
  });

  it("keeps a short horizon as it was: the band, the label and the objective", () => {
    const html = bento("10 ans et plus", "Croissance à long terme", "fr");
    expect(html).toMatch(/<span class="[^"]*" title="10 ans et plus">10 ans et plus<\/span>/);
    expect(html).toContain(">Croissance à long terme<");
  });
});
