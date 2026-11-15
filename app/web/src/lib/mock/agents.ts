/**
 * Fake A1 and A2 language of the simulator: guardrail screening, rule-based fact
 * extraction from free text, and Markdown messages adapted to the knowledge level.
 * Messages are produced in both languages at once, so a locale change re-renders them.
 */
import type { Exposures, KnowledgeLevel, Locale } from "@/lib/contract/schemas";
import { formatMoney, formatPercent } from "./profile";
import type { L, QuestionDef } from "./questions";
import { PRICE_DATE } from "./starter";

const LOCALES: Locale[] = ["fr", "en"];

function both(build: (locale: Locale) => string): L {
  return { fr: build("fr"), en: build("en") };
}

export interface Screening {
  text: string;
  masked: number;
  adviceRequest: boolean;
  transactionRequest: boolean;
  offTopic: boolean;
}

const PII_PATTERNS: RegExp[] = [
  /[\w.+-]+@[\w-]+\.[\w.]+/g,
  /\b\d{3}[ -]?\d{3}[ -]?\d{3}\b/g,
  /\b\d{3}[ .-]?\d{3}[ .-]?\d{4}\b/g,
  /\b\d{7,}\b/g,
];

const ADVICE = /(dois-je|devrais-je|est-ce que je (dois|devrais)|faut-il (que j'|acheter|vendre)|recommandez|conseillez|should i|do you recommend|would you recommend|tell me (what|which) to)[^.?!]{0,80}(achet|vend|invest|plac|buy|sell|invest)/i;
const TRANSACTION = /(passe[rz]? (un |l'|des )?ordres?|ex[ée]cute[rz]? (la |une )?transaction|ach[eè]te[rz]?[^.?!]{0,30}pour moi|vend[sz]?[^.?!]{0,30}pour moi|place (an |the )?order|execute (a |the )?trade|buy [^.?!]{0,30}for me|sell [^.?!]{0,30}for me)/i;
const ON_TOPIC = /(argent|placement|investi|épargne|epargne|retraite|maison|risque|bourse|action|fonds|dette|revenu|urgence|compte|celi|reer|money|invest|saving|retire|house|home|risk|stock|fund|debt|income|emergency|account|tfsa|rrsp|portfolio|portefeuille)/i;
const OFF_TOPIC = /(météo|meteo|weather|recette|recipe|blague|joke|sport|hockey|film|movie|série télé|tv show)/i;

/** Guardrail on the investor's free text: mask personal data, flag advice requests. */
export function screenMessage(message: string): Screening {
  let text = message;
  let masked = 0;
  for (const pattern of PII_PATTERNS) {
    text = text.replace(pattern, () => {
      masked += 1;
      return "[masqué]";
    });
  }
  return {
    text,
    masked,
    adviceRequest: ADVICE.test(message),
    transactionRequest: TRANSACTION.test(message),
    offTopic: OFF_TOPIC.test(message) && !ON_TOPIC.test(message),
  };
}

export interface ExtractedFact {
  field: string;
  value: unknown;
  note: L;
}

/** Rule-based reading of a free-text message (what A1's update-KB tool would store). */
export function extractFacts(message: string, current: Map<string, unknown>): ExtractedFact[] {
  const facts: ExtractedFact[] = [];
  const lower = message.toLowerCase();

  const months = /(\d{1,2})\s*(mois|months?)/.exec(lower);
  if (months && /(urgence|emergency|coussin|cushion|précaution|precaution|côté|aside|épargne|savings)/.test(lower)) {
    const value = Number(months[1]);
    facts.push({
      field: "risk_capacity.emergency_fund",
      value,
      note: { fr: `fonds d'urgence de ${value} mois`, en: `${value}-month emergency fund` },
    });
  }

  if (/(pas|aucune?|no|zero|zéro|sans)\s+(de\s+|d')?(dettes?|debts?)/.test(lower)) {
    facts.push({ field: "risk_capacity.high_interest_debt", value: false, note: { fr: "aucune dette à taux élevé", en: "no high-interest debt" } });
  } else if (/(dettes?|debts?|carte de crédit|credit card)/.test(lower)) {
    facts.push({ field: "risk_capacity.high_interest_debt", value: true, note: { fr: "une dette à taux élevé", en: "high-interest debt" } });
  }

  if (/(pas besoin|no need|aucun besoin)[^.]{0,40}(retir|withdraw|liquid|disponible|available)/.test(lower)) {
    facts.push({ field: "constraints.liquidity_need", value: false, note: { fr: "pas de besoin de liquidité", en: "no liquidity need" } });
  } else if (/(n'importe quand|à tout moment|anytime|any time|short notice|court terme)/.test(lower)) {
    facts.push({ field: "constraints.liquidity_need", value: true, note: { fr: "un besoin de liquidité", en: "a liquidity need" } });
  }

  if (/(progressivement|petit à petit|peu à peu|gradually|bit by bit|over several years)/.test(lower)) {
    facts.push({ field: "horizon.withdrawal_pattern", value: "gradual", note: { fr: "retraits progressifs", en: "gradual withdrawals" } });
  } else if (/(en une (seule )?fois|d'un coup|all at once|lump sum)/.test(lower)) {
    facts.push({ field: "horizon.withdrawal_pattern", value: "lump_sum", note: { fr: "retrait en une fois", en: "one-time withdrawal" } });
  }

  const purpose = /(retraite|retirement|maison|house|home|mise de fonds|down payment|études|education|école|school|voyage|travel)/.exec(lower);
  if (purpose) {
    const text = message.trim().slice(0, 200);
    facts.push({ field: "objective.purpose", value: text, note: { fr: `finalité : ${purpose[1]}`, en: `purpose: ${purpose[1]}` } });
  }

  const themes = new Set<string>(Array.isArray(current.get("preferences.themes")) ? (current.get("preferences.themes") as string[]) : []);
  const before = themes.size;
  if (/(tech|technolog|\bia\b|\bai\b|intelligence artificielle|artificial intelligence)/.test(lower)) themes.add("technology");
  if (/(énergie propre|energie propre|clean energy|renouvelable|renewable)/.test(lower)) themes.add("clean_energy");
  if (/(dividende|dividend)/.test(lower)) themes.add("dividends");
  if (/(santé|sante|health)/.test(lower)) themes.add("health");
  if (themes.size > before) {
    themes.delete("none");
    facts.push({ field: "preferences.themes", value: [...themes], note: { fr: "vos thèmes d'intérêt", en: "your themes of interest" } });
  }

  if (/(exclu|évit|evit|exclude|avoid|pas de|no |sans)/.test(lower)) {
    const exclusions = new Set<string>(
      Array.isArray(current.get("preferences.exclusions")) ? (current.get("preferences.exclusions") as string[]) : [],
    );
    const size = exclusions.size;
    if (/(tabac|tobacco)/.test(lower)) exclusions.add("tobacco");
    if (/(armes?\b|armement|weapons?)/.test(lower)) exclusions.add("weapons");
    if (/(pétrol|petrol|fossile|fossil|\boil\b)/.test(lower)) exclusions.add("fossil_fuels");
    if (/(crypto)/.test(lower)) exclusions.add("crypto");
    if (exclusions.size > size) {
      exclusions.delete("none");
      facts.push({ field: "preferences.exclusions", value: [...exclusions], note: { fr: "vos exclusions", en: "your exclusions" } });
    }
  }
  return facts;
}

const DIMENSION_WORDS: Record<string, L> = {
  objective: { fr: "votre objectif", en: "your goal" },
  horizon: { fr: "votre horizon", en: "your horizon" },
  risk_capacity: { fr: "votre capacité de risque", en: "your risk capacity" },
  risk_tolerance: { fr: "votre tolérance au risque", en: "your risk tolerance" },
  constraints: { fr: "vos contraintes", en: "your constraints" },
  preferences: { fr: "vos préférences", en: "your preferences" },
};

const BEGINNER_EXPLAINERS: Record<string, L> = {
  risk_capacity: {
    fr: "La **capacité de risque**, c'est ce que votre situation vous permet de perdre temporairement sans changer vos projets.",
    en: "Your **risk capacity** is what your situation lets you lose temporarily without changing your plans.",
  },
  horizon: {
    fr: "L'**horizon**, c'est le moment où vous aurez besoin de l'argent, et la façon de le retirer.",
    en: "Your **horizon** is when you will need the money, and how you will withdraw it.",
  },
  objective: {
    fr: "Connaître la **finalité** de l'argent aide à choisir le bon niveau de prudence.",
    en: "Knowing what the money is **for** helps choose the right level of caution.",
  },
  constraints: {
    fr: "Les **contraintes** fixent les limites à respecter, par exemple garder de l'argent disponible.",
    en: "**Constraints** set the limits to respect, such as keeping money available.",
  },
  preferences: {
    fr: "Les **préférences** orientent les choix à l'intérieur de ces limites.",
    en: "**Preferences** guide choices within those limits.",
  },
};

function joinList(items: string[], locale: Locale): string {
  if (items.length <= 1) return items.join("");
  const last = items[items.length - 1];
  return `${items.slice(0, -1).join(", ")} ${locale === "fr" ? "et" : "and"} ${last}`;
}

export interface A1MessageInput {
  level: KnowledgeLevel | null;
  notes: L[];
  score: number;
  displayed: number;
  ready: boolean;
  questions: QuestionDef[];
  missingLabels: L[];
  adviceRequest: boolean;
  offTopic: boolean;
  outcome: "ask" | "complete" | "stopped" | "idle";
  firstTurn: boolean;
}

/** A1's reply, in Markdown, at the investor's knowledge level. */
export function composeA1Message(input: A1MessageInput): L {
  return both((locale) => {
    const fr = locale === "fr";
    const pct = formatPercent(input.displayed, locale);
    const level = input.level ?? "beginner";
    const parts: string[] = [];

    if (input.adviceRequest) {
      parts.push(
        fr
          ? "Je ne peux pas vous dire quoi acheter ou vendre : AlphaForge AI est une simulation et ne donne aucun conseil financier personnalisé. Je peux en revanche compléter votre profil, pour que les explications qui suivront tiennent compte de votre situation."
          : "I cannot tell you what to buy or sell: AlphaForge AI is a simulation and gives no personalized financial advice. I can, however, complete your profile so that the explanations that follow reflect your situation.",
      );
    } else if (input.offTopic) {
      parts.push(fr ? "Je reste centré sur votre profil d'investisseur." : "Let's stay focused on your investor profile.");
    }

    if (input.notes.length > 0) {
      const notes = joinList(input.notes.map((note) => note[locale]), locale);
      parts.push(fr ? `C'est noté : ${notes}.` : `Noted: ${notes}.`);
    } else if (input.firstTurn) {
      parts.push(
        fr
          ? "Merci pour vos réponses aux questions de base. Je vais préciser ce qui manque encore à votre profil."
          : "Thank you for answering the base questions. I will now clarify what your profile is still missing.",
      );
    }

    if (input.outcome === "stopped") {
      parts.push(
        fr
          ? `On s'arrête ici. Votre profil est enregistré à **${pct}**, au-dessus du seuil de 70 %. Vous pourrez le compléter à tout moment.`
          : `We'll stop here. Your profile is saved at **${pct}**, above the 70% threshold. You can complete it at any time.`,
      );
      return parts.join("\n\n");
    }
    if (input.outcome === "complete") {
      parts.push(
        level === "advanced"
          ? fr
            ? `Profil complet : **${pct}** affichés (plafond de 95 %, score calculé ${formatPercent(input.score, locale)}). Je n'ai plus de relance utile.`
            : `Profile complete: **${pct}** displayed (95% cap, computed score ${formatPercent(input.score, locale)}). I have no further useful follow-up.`
          : fr
            ? `Votre profil est complet à **${pct}**. L'affichage plafonne à 95 % : un profil n'est jamais parfaitement connu, et cette marge le rappelle. Vous pourrez le mettre à jour à tout moment.`
            : `Your profile is **${pct}** complete. The display is capped at 95%: a profile is never perfectly known, and this margin is a reminder. You can update it at any time.`,
      );
      return parts.join("\n\n");
    }

    if (level === "beginner") {
      parts.push(
        fr
          ? `Votre profil est rempli à **${pct}**.${input.ready ? " C'est assez pour continuer : vous pouvez vous arrêter quand vous voulez, ou répondre à quelques questions de plus pour des explications encore plus justes." : " Dès **70 %**, vous pourrez vous arrêter quand vous le voudrez."}`
          : `Your profile is **${pct}** complete.${input.ready ? " That is enough to continue: you can stop whenever you like, or answer a few more questions for even better explanations." : " From **70%**, you can stop whenever you like."}`,
      );
    } else if (level === "intermediate") {
      parts.push(
        fr
          ? `Complétude du profil : **${pct}**${input.ready ? " (seuil de 70 % atteint, vous pouvez vous arrêter)." : " (seuil de 70 %)."}`
          : `Profile completeness: **${pct}**${input.ready ? " (70% threshold reached, you may stop)." : " (70% threshold)."}`,
      );
    } else {
      parts.push(
        fr
          ? `Complétude : **${pct}** (seuil 70 %, plafond 95 %)${input.ready ? "; arrêt possible." : "."}`
          : `Completeness: **${pct}** (70% threshold, 95% cap)${input.ready ? "; you may stop." : "."}`,
      );
    }

    if (input.outcome === "idle" || input.questions.length === 0) {
      parts.push(
        fr
          ? "Si un élément de votre situation a changé, écrivez-le-moi; sinon, vous pouvez vous arrêter ici."
          : "If anything in your situation has changed, tell me; otherwise you can stop here.",
      );
      return parts.join("\n\n");
    }

    const dims = [...new Set(input.questions.map((question) => question.dimension))];
    if (level === "beginner") {
      const words = dims.map((dim) => DIMENSION_WORDS[dim]?.[locale] ?? dim);
      parts.push(fr ? `Il me reste à mieux comprendre ${joinList(words, locale)}.` : `I still need to better understand ${joinList(words, locale)}.`);
      const explainer = BEGINNER_EXPLAINERS[dims[0] ?? ""];
      if (explainer) parts.push(explainer[locale]);
    } else if (level === "intermediate") {
      const words = dims.map((dim) => DIMENSION_WORDS[dim]?.[locale] ?? dim);
      parts.push(fr ? `Les questions ci-dessous portent sur ${joinList(words, locale)}.` : `The questions below are about ${joinList(words, locale)}.`);
    } else {
      const labels = input.missingLabels.slice(0, input.questions.length).map((label) => label[locale].toLowerCase());
      parts.push(fr ? `Champs prioritaires : ${labels.join(", ")}.` : `Priority fields: ${labels.join(", ")}.`);
    }
    parts.push(
      fr
        ? "Vous pouvez répondre aux questions, ou simplement m'écrire avec vos mots."
        : "You can answer the questions, or simply write to me in your own words.",
    );
    return parts.join("\n\n");
  });
}

/** Flags of app/agents/src/alphaforge/profile/portfolio.py, same names and thresholds. */
const FLAG_SENTENCES: Record<string, L> = {
  concentration_single_position: { fr: "un titre détenu en direct pèse plus de 20 % du total", en: "a security held directly weighs more than 20% of the total" },
  concentration_sector: { fr: "un secteur dépasse 40 % des actions", en: "one sector exceeds 40% of the stocks" },
  home_bias_canada: { fr: "au moins 60 % est coté au Canada ou en CAD", en: "at least 60% is listed in Canada or in CAD" },
  crypto_exposure_high: { fr: "plus de 10 % est en cryptoactifs", en: "more than 10% is in crypto-assets" },
  cash_heavy: { fr: "plus de 30 % est en encaisse", en: "more than 30% is in cash" },
  few_holdings: { fr: "il y a moins de cinq positions, sans FNB ni fonds", en: "there are fewer than five positions, with no ETF or fund" },
};

export interface A2MessageInput {
  level: KnowledgeLevel | null;
  positions: number;
  unresolved: string[];
  exposures: Exposures;
  usesUsd: boolean;
}

/** A2's summary of the extraction, in Markdown. */
export function composeA2Message(input: A2MessageInput): L {
  return both((locale) => {
    const fr = locale === "fr";
    const level = input.level ?? "beginner";
    const parts: string[] = [];
    if (input.positions === 0) {
      parts.push(
        fr
          ? "Je n'ai reconnu aucun titre du jeu de départ dans ce que vous avez fourni. Ajoutez vos positions à la main dans le tableau, ou passez cette étape."
          : "I did not recognize any security from the starter universe in what you provided. Add your positions by hand in the table, or skip this step.",
      );
      return parts.join("\n\n");
    }
    const total = formatMoney(input.exposures.total_value_cad, locale);
    const fx = input.usesUsd ? (fr ? ", USD convertis à 1,4255 $ CA selon la Banque du Canada" : ", USD converted at 1.4255 CAD per the Bank of Canada") : "";
    parts.push(
      fr
        ? `J'ai repéré **${input.positions} position${input.positions > 1 ? "s" : ""}** pour une valeur estimée de **${total}** (cours de clôture du ${PRICE_DATE}, jeu de départ${fx}).`
        : `I found **${input.positions} position${input.positions > 1 ? "s" : ""}** worth an estimated **${total}** (closing prices of ${PRICE_DATE}, starter dataset${fx}).`,
    );
    if (level === "beginner") {
      parts.push(
        fr
          ? "Une **position**, c'est un titre que vous détenez, par exemple 100 actions d'une banque. Les pourcentages plus bas montrent la part de chaque catégorie dans le total."
          : "A **position** is a security you hold, for example 100 shares of a bank. The percentages below show each category's share of the total.",
      );
    }
    if (input.unresolved.length > 0) {
      const quoted = input.unresolved.slice(0, 3).map((raw) => (fr ? `« ${raw} »` : `"${raw}"`)).join(", ");
      parts.push(
        fr
          ? `${input.unresolved.length > 1 ? `${input.unresolved.length} éléments n'ont` : "Un élément n'a"} pas pu être identifié${input.unresolved.length > 1 ? "s" : ""} : ${quoted}.`
          : `${input.unresolved.length > 1 ? `${input.unresolved.length} items` : "One item"} could not be identified: ${quoted}.`,
      );
    }
    const flags = input.exposures.flags.map((flag) => FLAG_SENTENCES[flag]?.[locale]).filter((text): text is string => Boolean(text));
    if (flags.length > 0) {
      parts.push(fr ? `**À noter** : ${joinList(flags, locale)}.` : `**Worth noting**: ${joinList(flags, locale)}.`);
    }
    if (level === "advanced") {
      parts.push(
        fr
          ? "Les expositions sont calculées par le code sur la valeur en CAD; aucune n'est estimée par le modèle."
          : "Exposures are computed by code on the CAD value; none is estimated by the model.",
      );
    }
    parts.push(
      fr
        ? "Vérifiez les quantités et les comptes, corrigez au besoin, puis confirmez."
        : "Check the quantities and accounts, correct them if needed, then confirm.",
    );
    return parts.join("\n\n");
  });
}

export function localized(text: L, locale: Locale): string {
  return LOCALES.includes(locale) ? text[locale] : text.fr;
}
