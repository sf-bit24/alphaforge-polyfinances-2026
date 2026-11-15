/**
 * Suite de #77 : le badge du code d'erreur suit la typographie de la langue
 * (« Code : guardrail_blocked » en français, "Code: guardrail_blocked" en anglais).
 */
import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ErrorNotice } from "@/components/ui/error-notice";
import type { Locale } from "@/lib/contract/schemas";
import { I18nProvider } from "@/lib/i18n/provider";

/** `createElement` takes the children as an argument (react/no-children-prop): they are optional in its props. */
const Provider = I18nProvider as (props: { initialLocale: Locale; children?: ReactNode }) => ReturnType<typeof I18nProvider>;

function badge(locale: Locale, code: string): string {
  const notice = createElement(ErrorNotice, { error: { code, message: "…", details: {} } });
  const html = renderToStaticMarkup(createElement(Provider, { initialLocale: locale }, notice));
  return html.match(/<span[^>]*font-mono[^>]*>([^<]*)<\/span>/)?.[1] ?? "";
}

describe("issue #77: separator of the error code badge", () => {
  it.each([
    ["fr", "guardrail_blocked", "Code : guardrail_blocked"],
    ["en", "guardrail_blocked", "Code: guardrail_blocked"],
    ["fr", "model_error", "Code : model_error"],
    ["en", "model_error", "Code: model_error"],
  ] as const)("%s, %s", (locale, code, expected) => {
    expect(badge(locale, code)).toBe(expected);
  });
});
