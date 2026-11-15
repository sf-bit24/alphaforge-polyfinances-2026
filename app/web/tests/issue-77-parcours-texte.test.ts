/**
 * Suite de #77 : dans la carte de relance du parcours, un message écrit « avec mes mots » et refusé (un NAS, le
 * garde-fou) revient dans sa zone de saisie, comme au tableau de bord et dans la carte d'A2. Avant, la carte était
 * démontée pendant la requête : la question et le texte disparaissaient, et la zone rouverte était vide.
 */
import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FollowupStage, keepOwnWords, keptOwnWords, ownWordsKey } from "@/components/journey/followup-card";
import { ApiError } from "@/lib/client/api";
import { Question, type ClientState, type Locale } from "@/lib/contract/schemas";
import { dictionaries } from "@/lib/i18n/dictionary";
import { I18nProvider } from "@/lib/i18n/provider";
import { clientState, question } from "./fixtures/contract-examples";

const fake = vi.hoisted(() => ({ session: {} as Record<string, unknown> }));
vi.mock("@/lib/client/session", () => ({ useSession: () => fake.session }));

const CLIENT = clientState.client_id;
const QUESTIONS = [Question.parse({ ...question, id: "a1_1_1", source: "a1" })];
const STATE = { ...clientState, stage: "followups", questions: QUESTIONS } as unknown as ClientState;
const TEXT = "Mon NAS est 046454286 et 4 mois de dépenses de côté";
const REFUSAL = {
  fr: "Votre message contient un renseignement personnel (NAS) : retirez-le, puis renvoyez-le.",
  en: "Your message contains personal information (SIN): remove it, then send it again.",
};

/** `createElement` takes the children as an argument (react/no-children-prop): they are optional in its props. */
const Provider = I18nProvider as (props: { initialLocale: Locale; children?: ReactNode }) => ReturnType<typeof I18nProvider>;

function session(locale: Locale, overrides: Record<string, unknown>) {
  fake.session = {
    clientId: CLIENT,
    pending: null,
    error: null,
    errorAction: null,
    streamText: "",
    conversation: [{ id: "e1", role: "agent", message: "Une question.", questions: QUESTIONS, stage: "followups", runId: "r1" }],
    reply: async () => true,
    retry: async () => true,
    dismissError: () => {},
    locale,
    ...overrides,
  };
}

function render(locale: Locale): string {
  const card = createElement(FollowupStage, { state: STATE, visible: true, interacted: true, onRestart: () => {} });
  return renderToStaticMarkup(createElement(Provider, { initialLocale: locale }, card)).replace(/&#x27;/g, "'");
}

const refused = (locale: Locale) =>
  new ApiError("guardrail_blocked", REFUSAL[locale], { reason: "personal_data", entity: "CA_SIN" });

describe.each(["fr", "en"] as const)("issue #77: the journey keeps a refused own-words message (%s)", (locale) => {
  const t = dictionaries[locale];
  const key = ownWordsKey(CLIENT, QUESTIONS);

  beforeEach(() => {
    keepOwnWords(key, null);
    // The investor chose « Répondre avec mes mots » and typed the text, then sent it.
    keepOwnWords(key, { writing: true, text: TEXT });
  });

  it("makes way for Yan while the request runs", () => {
    session(locale, { pending: "followup.reply" });
    const html = render(locale);
    expect(html).toContain(t.journey.end.thinkingNext);
    expect(html).not.toContain("<textarea");
  });

  it("brings the text back in the box, under Yan's line, with the notice", () => {
    session(locale, { error: refused(locale), errorAction: "followup.reply" });
    const html = render(locale);
    expect(html).toMatch(new RegExp(`<textarea[^>]*aria-label="${t.journey.end.ownWordsLabel}"[^>]*>${TEXT}</textarea>`));
    expect(html).toContain(REFUSAL[locale]);
    expect(html).toContain(t.errors.calm.guardrail_blocked!.reasons!.personal_data!.hint);
    expect(html).not.toContain(t.journey.end.thinkingNext);
  });

  it("keeps the text once the notice is closed", () => {
    session(locale, { error: null, errorAction: null });
    expect(render(locale)).toMatch(new RegExp(`<textarea[^>]*>${TEXT}</textarea>`));
  });

  it("keeps the former notice when nothing was written in one's own words", () => {
    keepOwnWords(key, null);
    session(locale, { error: refused(locale), errorAction: "followup.reply" });
    const html = render(locale);
    expect(html).toContain(t.journey.end.thinkingNext);
    expect(html).toContain(REFUSAL[locale]);
    expect(html).not.toContain("<textarea");
  });

  it("keeps a draft per client and per batch, and drops it once sent", () => {
    expect(keptOwnWords(ownWordsKey("another-client", QUESTIONS))).toEqual({ writing: false, text: "" });
    expect(keptOwnWords(key)).toEqual({ writing: true, text: TEXT });
    keepOwnWords(key, null);
    expect(keptOwnWords(key)).toEqual({ writing: false, text: "" });
  });
});
