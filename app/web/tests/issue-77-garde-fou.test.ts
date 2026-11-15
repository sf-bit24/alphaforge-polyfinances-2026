/**
 * Issue #77 : un NAS refusé par le garde-fou (`guardrail_blocked`, `details.reason` = `personal_data`)
 * reçoit un indice qui parle de renseignement personnel, pas d'ordres ni de conseils.
 */
import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { calmNoticeOf, ErrorNotice } from "@/components/ui/error-notice";
import type { Locale } from "@/lib/contract/schemas";
import { dictionaries } from "@/lib/i18n/dictionary";
import { I18nProvider } from "@/lib/i18n/provider";

const SIN_ERROR = {
  code: "guardrail_blocked",
  message: "Votre message contient un renseignement personnel (NAS) : retirez-le, puis renvoyez-le.",
  details: { reason: "personal_data", entity: "CA_SIN" },
};
const TOPIC_ERROR = {
  code: "guardrail_blocked",
  message: "Cette demande sort du cadre du prototype (simulation seulement, aucun conseil personnalisé).",
  details: {},
};

/** `createElement` takes the children as an argument (react/no-children-prop): they are optional in its props. */
const Provider = I18nProvider as (props: { initialLocale: Locale; children?: ReactNode }) => ReturnType<typeof I18nProvider>;

function render(error: typeof SIN_ERROR | typeof TOPIC_ERROR, locale: Locale = "fr"): string {
  const notice = createElement(ErrorNotice, { error, onRetry: () => {} });
  return renderToStaticMarkup(createElement(Provider, { initialLocale: locale }, notice))
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"');
}

describe("guardrail notice for personal data (#77)", () => {
  it("shows the personal-data hint, without orders or advice", () => {
    const html = render(SIN_ERROR);
    const notice = dictionaries.fr.errors.calm.guardrail_blocked?.reasons?.personal_data;
    expect(notice).toBeDefined();
    expect(html).toContain(notice!.title);
    expect(html).toContain(notice!.hint);
    expect(html).toContain(SIN_ERROR.message);
    expect(html).toContain("le modèle ne les reçoit pas");
    expect(html).not.toMatch(/\b(ordres?|conseils?)\b/i);
    // Renvoyer le même texte serait refusé à nouveau : pas de bouton Réessayer.
    expect(html).not.toContain(dictionaries.fr.common.retry);
  });

  it("speaks English in English", () => {
    const html = render({ ...SIN_ERROR, message: "Your message contains personal information (SIN): remove it, then send it again." }, "en");
    expect(html).toContain(dictionaries.en.errors.calm.guardrail_blocked!.reasons!.personal_data!.hint);
    expect(html).toContain("the model does not receive them");
    expect(html).not.toMatch(/\b(orders?|advice)\b/i);
  });

  it("keeps the current hint for the other guardrail interventions", () => {
    const html = render(TOPIC_ERROR);
    expect(html).toContain(dictionaries.fr.errors.calm.guardrail_blocked!.hint);
    expect(html).toContain("aucun ordre");
    for (const details of [undefined, null, {}, { reason: 42 }, { reason: "unknown_reason" }, "personal_data"]) {
      expect(calmNoticeOf(dictionaries.fr, { code: "guardrail_blocked", details })).toBe(dictionaries.fr.errors.calm.guardrail_blocked);
    }
    expect(calmNoticeOf(dictionaries.fr, { code: "model_error", details: { reason: "personal_data" } })).toBe(dictionaries.fr.errors.calm.model_error);
  });
});

describe("A2 card promise (#77)", () => {
  it("says a SIN is refused and other personal details are masked", () => {
    const fr = dictionaries.fr.portfolioInput.privacy;
    expect(fr).toContain("Un NAS est refusé");
    expect(fr).toContain("courriels");
    expect(fr).not.toContain("masque les renseignements personnels détectés");
    const en = dictionaries.en.portfolioInput.privacy;
    expect(en).toContain("A SIN is refused");
    expect(en).toContain("email addresses");
  });
});
