/**
 * Suite de #77 : le badge du code d'erreur suit la typographie de la langue
 * (« Code : guardrail_blocked » en français, "Code: guardrail_blocked" en anglais).
 * Le badge n'est que dans la vue équipe (LANGAGE.md) : l'avis d'un client ne montre aucun code.
 */
import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ErrorNotice } from "@/components/ui/error-notice";
import type { Locale } from "@/lib/contract/schemas";
import { dictionaries } from "@/lib/i18n/dictionary";
import { I18nProvider } from "@/lib/i18n/provider";

/** `createElement` takes the children as an argument (react/no-children-prop): they are optional in its props. */
const Provider = I18nProvider as (props: { initialLocale: Locale; children?: ReactNode }) => ReturnType<typeof I18nProvider>;

function render(locale: Locale, error: { code: string; message: string; details: unknown }): string {
  const notice = createElement(ErrorNotice, { error });
  return renderToStaticMarkup(createElement(Provider, { initialLocale: locale }, notice)).replace(/&#x27;/g, "'");
}

describe("issue #77: separator of the error code badge", () => {
  it.each([
    ["fr", "guardrail_blocked", "Code : guardrail_blocked"],
    ["en", "guardrail_blocked", "Code: guardrail_blocked"],
    ["fr", "model_error", "Code : model_error"],
    ["en", "model_error", "Code: model_error"],
  ] as const)("%s, %s", (locale, code, expected) => {
    expect(dictionaries[locale].errors.code(code)).toBe(expected);
  });
});

describe("a client's error notice (LANGAGE.md)", () => {
  const RUNTIME_DOWN = {
    code: "internal",
    message: "Runtime local injoignable à http://127.0.0.1:8080 (ECONNREFUSED).",
    details: { source: "gateway", request_id: "4f1c2d3e" },
  };

  it.each(["fr", "en"] as const)("shows no code, no raw message and no details (%s)", (locale) => {
    const html = render(locale, RUNTIME_DOWN);
    expect(html).toContain(dictionaries[locale].errors.hints.internal);
    expect(html).not.toMatch(/Code ?:|internal|Runtime|127\.0\.0\.1|ECONNREFUSED|4f1c2d3e|<details/);
  });

  it("keeps the message written for the investor", () => {
    const html = render("fr", { code: "invalid_answer", message: "Cinq fichiers au plus.", details: { max_files: 5 } });
    expect(html).toContain("Cinq fichiers au plus.");
    expect(html).toContain(dictionaries.fr.errors.hints.invalid_answer);
    expect(html).not.toMatch(/max_files|<details/);
  });
});
