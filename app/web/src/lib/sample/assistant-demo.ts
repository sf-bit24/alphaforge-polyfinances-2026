/**
 * Scripted portfolio answers of the approved dashboard draft, played in `mock` mode
 * only and tagged as examples in the thread. They show what the guided portfolio
 * (A3, analysis agents, Judge) will do; version 1 has no portfolio engine, so the
 * numbers below are the draft’s example values, not computations.
 */
import type { L } from "./portfolio";

export type DemoKey = "trap" | "sandbox" | "keep" | "gold" | "nvda";
export type DemoAction = { key: DemoKey | "simulatedPortfolio" | "noop"; label: L; primary?: boolean; href?: string };

export interface DemoCheck {
  label: L;
  value: L;
  cap: L;
  ok: boolean;
}

export interface DemoReply {
  /** What the investor says (chips) when this demo starts. */
  user: L;
  paragraphs: L[];
  verdict?: { ok: boolean; title: L; by: L; checks: DemoCheck[] };
  reasons?: Array<{ title: L; text: L }>;
  closing?: L;
  sources: L[];
  actions: DemoAction[];
  trace: Array<{ tone: "neutral" | "stop" | "ok"; title: L; detail: L }>;
}

const JUDGE: L = { fr: "Judge · contrôle par le code", en: "Judge · checked by code" };
const PRICES: L = { fr: "prices_daily.csv · Yahoo Finance · au 2026-11-12", en: "prices_daily.csv · Yahoo Finance · as of 2026-11-12" };

export const DEMO: Record<DemoKey, DemoReply> = {
  trap: {
    user: {
      fr: "Je veux acheter pour 50 000 $ de la société techno dont tout le monde parle.",
      en: "I want to buy $50,000 of the tech company everyone is talking about.",
    },
    paragraphs: [
      {
        fr: "Je comprends l’envie : NVDA fait beaucoup parler d’elle. Je ne peux pas l’ajouter telle quelle à votre portefeuille simulé, et je vous explique pourquoi.",
        en: "I understand the appeal: NVDA is in the news a lot. I can’t add it as is to your simulated portfolio, and here is why.",
      },
    ],
    verdict: {
      ok: false,
      title: { fr: "Refus provisoire de la gouvernance", en: "Provisional refusal by governance" },
      by: JUDGE,
      checks: [
        { label: { fr: "Poids d’un seul titre", en: "Weight of a single security" }, value: { fr: "12,5 %", en: "12.5%" }, cap: { fr: "plafond 5 %", en: "cap 5%" }, ok: false },
        { label: { fr: "Volatilité du portefeuille", en: "Portfolio volatility" }, value: { fr: "8,4 %", en: "8.4%" }, cap: { fr: "plafond 7 %", en: "cap 7%" }, ok: false },
        { label: { fr: "Technologie au total", en: "Technology in total" }, value: { fr: "15 %", en: "15%" }, cap: { fr: "plafond 10 %", en: "cap 10%" }, ok: false },
      ],
    },
    reasons: [
      {
        title: { fr: "Vos objectifs.", en: "Your goals." },
        text: {
          fr: "Vous prenez votre retraite en 2030 et voulez d’abord préserver votre capital.",
          en: "You retire in 2030 and want to preserve your capital first.",
        },
      },
      {
        title: { fr: "Les données.", en: "The data." },
        text: {
          fr: "Sur un an, NVDA a une volatilité d’environ 50 %, huit fois celle de votre portefeuille.",
          en: "Over one year, NVDA has a volatility of about 50%, eight times that of your portfolio.",
        },
      },
      {
        title: { fr: "En dollars.", en: "In dollars." },
        text: {
          fr: "Une baisse comme celle de NVDA en 2022 (environ −50 %) ferait perdre près de 25 000 $ sur ces 50 000 $.",
          en: "A fall like NVDA’s in 2022 (about −50%) would lose almost $25,000 of these $50,000.",
        },
      },
      {
        title: { fr: "Un compromis.", en: "A compromise." },
        text: {
          fr: "Une poche « bac à sable » plafonnée à 4 % du capital, soit 16 000 $, sans toucher à vos obligations.",
          en: "A \"sandbox\" pocket capped at 4% of the capital, that is $16,000, without touching your bonds.",
        },
      },
    ],
    sources: [PRICES, { fr: "adj_close · volatilité 252 j", en: "adj_close · 252-day volatility" }, { fr: "Votre profil · mis à jour le 2026-11-14", en: "Your profile · updated 2026-11-14" }],
    actions: [
      { key: "sandbox", label: { fr: "Voir le compromis", en: "See the compromise" }, primary: true },
      { key: "keep", label: { fr: "Garder mon portefeuille actuel", en: "Keep my current portfolio" } },
    ],
    trace: [
      { tone: "neutral", title: { fr: "A3 · agent du portefeuille", en: "A3 · portfolio agent" }, detail: { fr: "Simule l’ajout de 50 000 $ de NVDA.", en: "Simulates adding $50,000 of NVDA." } },
      { tone: "neutral", title: { fr: "Analyse du risque", en: "Risk analysis" }, detail: { fr: "Volatilité et baisse 2022 calculées sur adj_close.", en: "Volatility and 2022 fall computed on adj_close." } },
      {
        tone: "neutral",
        title: { fr: "Analyse de la diversification", en: "Diversification analysis" },
        detail: { fr: "Exposition technologique consolidée, FNB compris.", en: "Consolidated technology exposure, ETFs included." },
      },
      { tone: "stop", title: { fr: "Judge · gouvernance", en: "Judge · governance" }, detail: { fr: "3 plafonds dépassés : refus provisoire et compromis.", en: "3 caps exceeded: provisional refusal and a compromise." } },
    ],
  },
  sandbox: {
    user: { fr: "Montre-moi le compromis.", en: "Show me the compromise." },
    paragraphs: [
      {
        fr: "Voici une version encadrée : 4 % de NVDA dans une poche « bac à sable », financée en réduisant SPY de 8 % à 4 %. Vos obligations et votre encaisse ne bougent pas.",
        en: "Here is a framed version: 4% of NVDA in a \"sandbox\" pocket, funded by cutting SPY from 8% to 4%. Your bonds and cash do not move.",
      },
    ],
    verdict: {
      ok: true,
      title: { fr: "Proposition encadrée : conforme", en: "Framed proposal: compliant" },
      by: JUDGE,
      checks: [
        { label: { fr: "Poids d’un seul titre", en: "Weight of a single security" }, value: { fr: "4,0 %", en: "4.0%" }, cap: { fr: "plafond 5 %", en: "cap 5%" }, ok: true },
        { label: { fr: "Volatilité du portefeuille", en: "Portfolio volatility" }, value: { fr: "6,7 %", en: "6.7%" }, cap: { fr: "plafond 7 %", en: "cap 7%" }, ok: true },
        { label: { fr: "Technologie au total", en: "Technology in total" }, value: { fr: "5,6 %", en: "5.6%" }, cap: { fr: "plafond 10 %", en: "cap 10%" }, ok: true },
      ],
    },
    closing: {
      fr: "Le pire scénario de type 2022 sur cette poche coûterait environ 8 000 $. Le reste du portefeuille reste celui que vous connaissez.",
      en: "A 2022-type worst case on this pocket would cost about $8,000. The rest of the portfolio stays the one you know.",
    },
    sources: [PRICES, { fr: "Corrélations sur 5 ans", en: "5-year correlations" }],
    actions: [
      { key: "simulatedPortfolio", label: { fr: "Appliquer à ma simulation", en: "Apply to my simulation" }, primary: true, href: "/portfolio" },
      { key: "noop", label: { fr: "Ajuster le montant", en: "Adjust the amount" } },
    ],
    trace: [
      { tone: "neutral", title: { fr: "A3 · agent du portefeuille", en: "A3 · portfolio agent" }, detail: { fr: "Construit la poche bac à sable à 4 %.", en: "Builds the 4% sandbox pocket." } },
      {
        tone: "neutral",
        title: { fr: "Analyse du risque", en: "Risk analysis" },
        detail: { fr: "Volatilité recalculée avec les corrélations : 6,7 %.", en: "Volatility recomputed with correlations: 6.7%." },
      },
      { tone: "ok", title: { fr: "Judge · gouvernance", en: "Judge · governance" }, detail: { fr: "Tous les plafonds respectés : proposition encadrée.", en: "All caps respected: framed proposal." } },
    ],
  },
  keep: {
    user: { fr: "Je garde mon portefeuille actuel.", en: "I keep my current portfolio." },
    paragraphs: [
      {
        fr: "C’est noté. Votre portefeuille simulé ne change pas. Je garde votre intérêt pour NVDA en mémoire : si votre situation évolue, on pourra en reparler.",
        en: "Noted. Your simulated portfolio does not change. I keep your interest in NVDA in mind: if your situation changes, we can talk about it again.",
      },
    ],
    sources: [],
    actions: [],
    trace: [],
  },
  gold: {
    user: { fr: "Et si je retire l’or ?", en: "What if I remove the gold?" },
    paragraphs: [
      {
        fr: "Sans l’or, ces 6 % iraient en obligations canadiennes (XBB.TO). La volatilité passerait de 6,1 % à 5,9 %, mais votre portefeuille perdrait une protection utile quand actions et obligations baissent ensemble, comme en 2022.",
        en: "Without gold, these 6% would go to Canadian bonds (XBB.TO). Volatility would go from 6.1% to 5.9%, but your portfolio would lose a useful protection when stocks and bonds fall together, as in 2022.",
      },
      {
        fr: "C’est conforme à votre profil. Je vous le déconseille sans l’interdire : c’est votre décision.",
        en: "It fits your profile. I advise against it without forbidding it: it is your decision.",
      },
    ],
    sources: [{ fr: "prices_daily.csv · GLD, XBB.TO", en: "prices_daily.csv · GLD, XBB.TO" }, { fr: "Stress test 2022", en: "2022 stress test" }],
    actions: [{ key: "noop", label: { fr: "Voir la simulation sans or", en: "See the simulation without gold" } }],
    trace: [
      { tone: "neutral", title: { fr: "A3 · agent du portefeuille", en: "A3 · portfolio agent" }, detail: { fr: "Remplace GLD par XBB.TO.", en: "Replaces GLD with XBB.TO." } },
      { tone: "neutral", title: { fr: "Analyse du risque", en: "Risk analysis" }, detail: { fr: "Recalcule la volatilité et le stress test 2022.", en: "Recomputes volatility and the 2022 stress test." } },
      { tone: "ok", title: { fr: "Judge · gouvernance", en: "Judge · governance" }, detail: { fr: "Plafonds respectés.", en: "Caps respected." } },
    ],
  },
  nvda: {
    user: { fr: "Comment a évolué NVDA sur 14 jours ?", en: "How did NVDA do over 14 days?" },
    paragraphs: [
      {
        fr: "Sur les 14 derniers jours du jeu de données (au 12 novembre 2026), NVDA a varié de −6,2 %, avec des écarts quotidiens jusqu’à 4 %. C’est une observation, pas une prévision.",
        en: "Over the last 14 days of the dataset (as of November 12, 2026), NVDA moved −6.2%, with daily swings of up to 4%. This is an observation, not a forecast.",
      },
    ],
    sources: [{ fr: "prices_daily.csv · NVDA · 2026-10-29 au 2026-11-12", en: "prices_daily.csv · NVDA · 2026-10-29 to 2026-11-12" }, { fr: "adj_close · USD", en: "adj_close · USD" }],
    actions: [],
    trace: [
      { tone: "neutral", title: { fr: "Agent de données", en: "Data agent" }, detail: { fr: "Lit 10 séances de cotation NVDA.", en: "Reads 10 NVDA trading sessions." } },
      { tone: "ok", title: { fr: "Réponse", en: "Answer" }, detail: { fr: "Aucun conseil personnalisé : simple description.", en: "No personalized advice: a plain description." } },
    ],
  },
};

/** Suggested prompts of the draft, in its order; the first one is the "trap" request. */
export const DEMO_CHIPS: Array<{ key: Extract<DemoKey, "trap" | "gold" | "nvda">; trap: boolean }> = [
  { key: "trap", trap: true },
  { key: "gold", trap: false },
  { key: "nvda", trap: false },
];
