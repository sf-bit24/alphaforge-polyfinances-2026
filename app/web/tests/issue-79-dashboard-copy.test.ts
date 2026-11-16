import { createElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ClientState, type Locale } from "@/lib/contract/schemas";
import { composeHints, introCopy, offersFollowups, startsFollowups } from "@/components/dashboard/assistant-offer";
import { ProfileBento } from "@/components/dashboard/bento";
import { dictionaries } from "@/lib/i18n/dictionary";
import { I18nProvider } from "@/lib/i18n/provider";
import { screensEn, screensFr } from "@/lib/i18n/screens";
import { clientState, portfolioView } from "./fixtures/contract-examples";

const nbsp = (text: string) => text.replace(/[  ]/g, " ");

// `children` is required by I18nProvider's props; createElement passes it as an argument.
const Provider = I18nProvider as (props: { initialLocale: Locale; children?: ReactNode }) => ReactElement;

function render(element: ReactElement, locale: Locale): string {
  return renderToStaticMarkup(createElement(Provider, { initialLocale: locale }, element));
}

function completeness(score: number, threshold = 0.7, cap = 0.95): ClientState["completeness"] {
  return { score, displayed: Math.min(score, cap), threshold, cap, ready: score >= threshold, missing: [] };
}

describe("hint under Yan's input (#79)", () => {
  it("says only that no transaction is placed outside the follow-ups", () => {
    expect(composeHints(dictionaries.fr, "fr", false, completeness(0.66))).toEqual(["Aucune transaction n’est passée."]);
  });

  it("puts the stop condition in a sentence of its own, never read as a condition on transactions", () => {
    for (const locale of ["fr", "en"] as const) {
      const t = dictionaries[locale];
      const [transactions, stop, ...rest] = composeHints(t, locale, true, completeness(0.66));
      expect(rest).toEqual([]);
      expect(transactions).toBe(t.assistant.hint);
      expect(stop).not.toMatch(/^(Possible|Available)/);
      expect(nbsp(stop!)).toContain(locale === "fr" ? "70 %" : "70%");
      expect(nbsp(stop!)).toContain(locale === "fr" ? "66 %" : "66%");
    }
    expect(nbsp(composeHints(dictionaries.fr, "fr", true, completeness(0.66))[1]!)).toBe(
      "Vous pourrez arrêter les questions dès 70 % de complétude (actuellement 66 %).",
    );
    expect(composeHints(dictionaries.en, "en", true, completeness(0.66))[1]).toBe("You can stop the questions from 70% completeness (currently 66%).");
  });

  it("names the threshold of the contract, and says the questions can stop once it is reached", () => {
    const [, locked] = composeHints(dictionaries.en, "en", true, completeness(0.5, 0.6));
    expect(locked).toBe("You can stop the questions from 60% completeness (currently 50%).");
    const [, ready] = composeHints(dictionaries.fr, "fr", true, completeness(1));
    expect(nbsp(ready!)).toBe("Votre profil atteint le seuil de 70 % : vous pouvez arrêter les questions.");
  });
});

describe("follow-ups chip of Yan's assistant (#79)", () => {
  const waiting = { followups: true, replying: false, started: true, questionCount: 2 };

  it("is offered in the intro while A1's questions, asked in the journey, wait for an answer", () => {
    expect(offersFollowups("intro", waiting)).toBe(true);
    // Being written (Yan started them in the journey): offered, disabled until they arrive.
    expect(offersFollowups("intro", { ...waiting, replying: true, questionCount: 0 })).toBe(true);
    expect(offersFollowups("intro", { ...waiting, started: false, questionCount: 0 })).toBe(true);
  });

  it("is not offered once A1 has nothing more to ask, nor outside the follow-ups", () => {
    expect(offersFollowups("intro", { ...waiting, questionCount: 0 })).toBe(false);
    expect(offersFollowups("intro", { ...waiting, followups: false })).toBe(false);
    expect(offersFollowups("thread", { ...waiting, followups: false, started: false })).toBe(false);
  });

  it("is offered under the thread only before A1 has asked anything: its questions show in the thread", () => {
    expect(offersFollowups("thread", waiting)).toBe(false);
    expect(offersFollowups("thread", { ...waiting, started: false, questionCount: 0 })).toBe(true);
    expect(offersFollowups("thread", { ...waiting, started: false, replying: true, questionCount: 0 })).toBe(false);
  });

  it("never asks A1 again once its questions are asked: picking it only shows them in the thread", () => {
    expect(startsFollowups(waiting)).toBe(false);
    const answeredAll = { ...waiting, questionCount: 0 };
    expect(startsFollowups(answeredAll)).toBe(false);
    for (const replying of [false, true])
      for (const questionCount of [0, 2]) {
        const status = { ...waiting, replying, questionCount };
        if (offersFollowups("intro", status)) expect(startsFollowups(status)).toBe(false);
      }
  });

  it("asks A1 for its first follow-ups only before it has spoken, and never while it writes", () => {
    expect(startsFollowups({ started: false, replying: false })).toBe(true);
    expect(startsFollowups({ started: false, replying: true })).toBe(false);
  });

  it("is promised by the intro's lead only when it is offered", () => {
    for (const t of [dictionaries.fr, dictionaries.en]) {
      expect(introCopy(t, true, true)).toEqual({ heading: t.assistant.introFollowups, lead: t.assistant.leadFollowups });
      const write = introCopy(t, true, false);
      expect(write.heading).toBe(t.assistant.introFollowups);
      expect(write.lead).not.toBe(t.assistant.leadFollowups);
      expect(write.lead).not.toMatch(/questions/i);
      expect(introCopy(t, false, false)).toEqual({ heading: t.assistant.introComplete, lead: t.assistant.leadComplete });
    }
  });
});

describe("the simulated portfolio, outside the simulator (#79)", () => {
  const followups = ClientState.parse({ ...clientState, stage: "followups", questions: [] });
  const withExisting = ClientState.parse({ ...clientState, stage: "followups", questions: [], portfolio: { ...portfolioView, status: "confirmed" } });

  it("is no longer announced for a version 2 on the dashboard", () => {
    for (const screens of [screensFr, screensEn]) {
      expect(JSON.stringify(screens.dash)).not.toMatch(/version [12]|guidé|guided/i);
    }
    for (const locale of ["fr", "en"] as const) {
      expect(render(createElement(ProfileBento, { state: followups }), locale)).not.toMatch(/version [12]/i);
    }
  });

  it("is reached from the dashboard tile, which names the tab and the « My profile » choice", () => {
    for (const locale of ["fr", "en"] as const) {
      const t = dictionaries[locale];
      const html = render(createElement(ProfileBento, { state: followups }), locale);
      expect(html).toContain('href="/portfolio"');
      expect(html).toContain(t.dash.real.simulated.cta);
      expect(html).toContain(t.appNav.portfolio);
      expect(html).toContain(t.portfolioView.personas.self.name);
    }
  });

  it("leaves the tile to the confirmed existing portfolio when there is one", () => {
    const html = render(createElement(ProfileBento, { state: withExisting }), "fr");
    expect(html).toContain(dictionaries.fr.dash.real.portfolio);
    expect(html).not.toContain('href="/portfolio"');
  });
});
