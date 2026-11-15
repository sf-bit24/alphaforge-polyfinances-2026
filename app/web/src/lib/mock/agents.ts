/**
 * Fake A1 and A2 language of the simulator: guardrail screening, rule-based fact
 * extraction from free text, and Markdown messages adapted to the knowledge level.
 * Messages are produced in both languages at once, so a locale change re-renders them.
 */
import type { Exposures, KnowledgeLevel, Locale } from "@/lib/contract/schemas";
import { formatMoney, formatPercent } from "./profile";
import type { L, QuestionDef } from "./questions";
import { PRICE_DATE } from "./starter";

/** Model the fake A1 and A2 name in their `model` trace steps. */
export const MODEL_ID = "us.anthropic.claude-opus-5-5";

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

/** Numbers in words, one to twelve, as investors write a number of months. */
const NUMBER_WORDS: Record<string, number> = Object.fromEntries(
  [
    ["un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze"],
    ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"],
  ].flatMap((words) => words.map((word, index) => [word, index + 1])),
);

/** A number of months, in digits or in words; « dix-huit » or "twenty-four" is not read as « huit » or "four". */
const MONTHS = new RegExp(`(?:\\b(\\d{1,2})|(?<![\\w-])(${Object.keys(NUMBER_WORDS).join("|")}))\\s*(?:mois|months?)\\b`);

function emergencyFundFact(lower: string): ExtractedFact | null {
  const months = MONTHS.exec(lower);
  if (!months || !/(urgence|emergency|coussin|cushion|précaution|precaution|côté|aside|épargne|savings)/.test(lower)) return null;
  const [, digits, word = ""] = months;
  const value = Number(digits ?? NUMBER_WORDS[word]);
  return {
    field: "risk_capacity.emergency_fund",
    value,
    note: { fr: `fonds d'urgence de ${value} mois`, en: `${value}-month emergency fund` },
  };
}

function debtFact(lower: string): ExtractedFact | null {
  if (/(pas|aucune?|no|zero|zéro|sans)\s+(de\s+|d')?(dettes?|debts?)/.test(lower)) {
    return { field: "risk_capacity.high_interest_debt", value: false, note: { fr: "aucune dette à taux élevé", en: "no high-interest debt" } };
  }
  if (/(dettes?|debts?|carte de crédit|credit card)/.test(lower)) {
    return { field: "risk_capacity.high_interest_debt", value: true, note: { fr: "une dette à taux élevé", en: "high-interest debt" } };
  }
  return null;
}

function liquidityFact(lower: string): ExtractedFact | null {
  if (/(pas besoin|no need|aucun besoin)[^.]{0,40}(retir|withdraw|liquid|disponible|available)/.test(lower)) {
    return { field: "constraints.liquidity_need", value: false, note: { fr: "pas de besoin de liquidité", en: "no liquidity need" } };
  }
  if (/(n'importe quand|à tout moment|anytime|any time|short notice|court terme)/.test(lower)) {
    return { field: "constraints.liquidity_need", value: true, note: { fr: "un besoin de liquidité", en: "a liquidity need" } };
  }
  return null;
}

function withdrawalFact(lower: string): ExtractedFact | null {
  if (/(progressivement|petit à petit|peu à peu|gradually|bit by bit|over several years)/.test(lower)) {
    return { field: "horizon.withdrawal_pattern", value: "gradual", note: { fr: "retraits progressifs", en: "gradual withdrawals" } };
  }
  if (/(en une (seule )?fois|d'un coup|all at once|lump sum)/.test(lower)) {
    return { field: "horizon.withdrawal_pattern", value: "lump_sum", note: { fr: "retrait en une fois", en: "one-time withdrawal" } };
  }
  return null;
}

/** The purpose keeps the investor's own words, shortened; the note names the keyword found. */
function purposeFact(message: string, lower: string): ExtractedFact | null {
  const purpose = /(retraite|retirement|maison|house|home|mise de fonds|down payment|études|education|école|school|voyage|travel)/.exec(lower);
  if (!purpose) return null;
  const text = message.trim().slice(0, 200);
  return { field: "objective.purpose", value: text, note: { fr: `finalité : ${purpose[1]}`, en: `purpose: ${purpose[1]}` } };
}

type ChoicePattern = [pattern: RegExp, choice: string];

/**
 * Read on the investor's text, not lowered: "AI" counts in capitals only, since a lower-case
 * « ai » is the French verb (j'ai, j'en ai, ai-je), and so is "AI" after an apostrophe (J'AI).
 */
const THEME_PATTERNS: ChoicePattern[] = [
  [/(\btech\b|technolog|\bia\b|intelligence artificielle|artificial intelligence)/i, "technology"],
  [/(?<!')\bAI\b/, "technology"],
  [/(énergie propre|energie propre|clean energy|renouvelable|renewable)/i, "clean_energy"],
  [/(dividende|dividend)/i, "dividends"],
  // « santé », not the end of « suffisante » or « intéressante ».
  [/(\bsant[ée]|health)/i, "health"],
];

const EXCLUSION_PATTERNS: ChoicePattern[] = [
  [/(tabac|tobacco)/, "tobacco"],
  [/(\barmes?\b|armement|weapons?)/, "weapons"],
  [/(pétrol|petrol|fossile|fossil|\boil\b)/, "fossil_fuels"],
  [/(crypto)/, "crypto"],
];

/** The choices already made plus those the text mentions, or null when it mentions no new one. */
function withMentionedChoices(current: unknown, text: string, patterns: ChoicePattern[]): string[] | null {
  const choices = new Set<string>(Array.isArray(current) ? (current as string[]) : []);
  const before = choices.size;
  for (const [pattern, choice] of patterns) {
    if (pattern.test(text)) choices.add(choice);
  }
  if (choices.size === before) return null;
  choices.delete("none");
  return [...choices];
}

function themesFact(text: string, current: Map<string, unknown>): ExtractedFact | null {
  const themes = withMentionedChoices(current.get("preferences.themes"), text, THEME_PATTERNS);
  if (!themes) return null;
  return { field: "preferences.themes", value: themes, note: { fr: "vos thèmes d'intérêt", en: "your themes of interest" } };
}

function exclusionsFact(lower: string, current: Map<string, unknown>): ExtractedFact | null {
  if (!/(exclu|évit|evit|exclude|avoid|pas de|no |sans)/.test(lower)) return null;
  const exclusions = withMentionedChoices(current.get("preferences.exclusions"), lower, EXCLUSION_PATTERNS);
  if (!exclusions) return null;
  return { field: "preferences.exclusions", value: exclusions, note: { fr: "vos exclusions", en: "your exclusions" } };
}

/** Rule-based reading of a free-text message (what A1's update-KB tool would store). */
export function extractFacts(message: string, current: Map<string, unknown>): ExtractedFact[] {
  // The patterns use the straight apostrophe; keyboards often type the typographic one (j’ai).
  const text = message.replace(/’/g, "'");
  const lower = text.toLowerCase();
  const facts = [
    emergencyFundFact(lower),
    debtFact(lower),
    liquidityFact(lower),
    withdrawalFact(lower),
    purposeFact(message, lower),
    themesFact(text, current),
    exclusionsFact(lower, current),
  ];
  return facts.filter((fact) => fact !== null);
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

/** Paragraphs of a message; a null one is left out. */
function joinParagraphs(paragraphs: Array<string | null>): string {
  return paragraphs.filter((paragraph) => paragraph !== null).join("\n\n");
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

const NO_ADVICE: L = {
  fr: "Je ne peux pas vous dire quoi acheter ou vendre : AlphaForge AI est une simulation et ne donne aucun conseil financier personnalisé. Je peux en revanche compléter votre profil, pour que les explications qui suivront tiennent compte de votre situation.",
  en: "I cannot tell you what to buy or sell: AlphaForge AI is a simulation and gives no personalized financial advice. I can, however, complete your profile so that the explanations that follow reflect your situation.",
};
const BACK_TO_PROFILE: L = {
  fr: "Je reste centré sur votre profil d'investisseur.",
  en: "Let's stay focused on your investor profile.",
};
const FIRST_TURN_THANKS: L = {
  fr: "Merci pour vos réponses aux questions de base. Je vais préciser ce qui manque encore à votre profil.",
  en: "Thank you for answering the base questions. I will now clarify what your profile is still missing.",
};
const NOTHING_TO_ASK: L = {
  fr: "Si un élément de votre situation a changé, écrivez-le-moi; sinon, vous pouvez vous arrêter ici.",
  en: "If anything in your situation has changed, tell me; otherwise you can stop here.",
};
const ANSWER_OR_WRITE: L = {
  fr: "Vous pouvez répondre aux questions, ou simplement m'écrire avec vos mots.",
  en: "You can answer the questions, or simply write to me in your own words.",
};

/** A1's answer to a request it must not follow: personalized advice, or a subject outside the profile. */
function framing(input: A1MessageInput, locale: Locale): string | null {
  if (input.adviceRequest) return NO_ADVICE[locale];
  if (input.offTopic) return BACK_TO_PROFILE[locale];
  return null;
}

function acknowledgement(input: A1MessageInput, locale: Locale): string | null {
  if (input.notes.length > 0) {
    const notes = joinList(input.notes.map((note) => note[locale]), locale);
    return locale === "fr" ? `C'est noté : ${notes}.` : `Noted: ${notes}.`;
  }
  return input.firstTurn ? FIRST_TURN_THANKS[locale] : null;
}

function stoppedParagraph(percent: string, locale: Locale): string {
  return locale === "fr"
    ? `On s'arrête ici. Votre profil est enregistré à **${percent}**, au-dessus du seuil de 70 %. Vous pourrez le compléter à tout moment.`
    : `We'll stop here. Your profile is saved at **${percent}**, above the 70% threshold. You can complete it at any time.`;
}

function completeParagraph(input: A1MessageInput, percent: string, locale: Locale): string {
  const fr = locale === "fr";
  if (input.level === "advanced") {
    return fr
      ? `Profil complet : **${percent}** affichés (plafond de 95 %, score calculé ${formatPercent(input.score, locale)}). Je n'ai plus de relance utile.`
      : `Profile complete: **${percent}** displayed (95% cap, computed score ${formatPercent(input.score, locale)}). I have no further useful follow-up.`;
  }
  return fr
    ? `Votre profil est complet à **${percent}**. L'affichage plafonne à 95 % : un profil n'est jamais parfaitement connu, et cette marge le rappelle. Vous pourrez le mettre à jour à tout moment.`
    : `Your profile is **${percent}** complete. The display is capped at 95%: a profile is never perfectly known, and this margin is a reminder. You can update it at any time.`;
}

/** Where the profile stands, and whether the investor may stop, at the investor's level. */
function progressParagraph(input: A1MessageInput, percent: string, locale: Locale): string {
  const fr = locale === "fr";
  const { ready } = input;
  const level = input.level ?? "beginner";
  if (level === "beginner") {
    return fr
      ? `Votre profil est rempli à **${percent}**.${ready ? " C'est assez pour continuer : vous pouvez vous arrêter quand vous voulez, ou répondre à quelques questions de plus pour des explications encore plus justes." : " Dès **70 %**, vous pourrez vous arrêter quand vous le voudrez."}`
      : `Your profile is **${percent}** complete.${ready ? " That is enough to continue: you can stop whenever you like, or answer a few more questions for even better explanations." : " From **70%**, you can stop whenever you like."}`;
  }
  if (level === "intermediate") {
    return fr
      ? `Complétude du profil : **${percent}**${ready ? " (seuil de 70 % atteint, vous pouvez vous arrêter)." : " (seuil de 70 %)."}`
      : `Profile completeness: **${percent}**${ready ? " (70% threshold reached, you may stop)." : " (70% threshold)."}`;
  }
  return fr
    ? `Complétude : **${percent}** (seuil 70 %, plafond 95 %)${ready ? "; arrêt possible." : "."}`
    : `Completeness: **${percent}** (70% threshold, 95% cap)${ready ? "; you may stop." : "."}`;
}

/** What the next questions are about: in plain words for a beginner, by field name for an advanced investor. */
function topicParagraphs(input: A1MessageInput, locale: Locale): string[] {
  const fr = locale === "fr";
  const level = input.level ?? "beginner";
  if (level !== "beginner" && level !== "intermediate") {
    const labels = input.missingLabels.slice(0, input.questions.length).map((label) => label[locale].toLowerCase());
    return [fr ? `Champs prioritaires : ${labels.join(", ")}.` : `Priority fields: ${labels.join(", ")}.`];
  }
  const dimensions = [...new Set(input.questions.map((question) => question.dimension))];
  const topics = joinList(dimensions.map((dimension) => DIMENSION_WORDS[dimension]?.[locale] ?? dimension), locale);
  if (level === "intermediate") {
    return [fr ? `Les questions ci-dessous portent sur ${topics}.` : `The questions below are about ${topics}.`];
  }
  const sentence = fr ? `Il me reste à mieux comprendre ${topics}.` : `I still need to better understand ${topics}.`;
  const explainer = BEGINNER_EXPLAINERS[dimensions[0] ?? ""];
  return explainer ? [sentence, explainer[locale]] : [sentence];
}

function a1Paragraphs(input: A1MessageInput, locale: Locale): Array<string | null> {
  const percent = formatPercent(input.displayed, locale);
  const opening = [framing(input, locale), acknowledgement(input, locale)];
  if (input.outcome === "stopped") return [...opening, stoppedParagraph(percent, locale)];
  if (input.outcome === "complete") return [...opening, completeParagraph(input, percent, locale)];
  const progress = progressParagraph(input, percent, locale);
  if (input.outcome === "idle" || input.questions.length === 0) return [...opening, progress, NOTHING_TO_ASK[locale]];
  return [...opening, progress, ...topicParagraphs(input, locale), ANSWER_OR_WRITE[locale]];
}

/** A1's reply, in Markdown, at the investor's knowledge level. */
export function composeA1Message(input: A1MessageInput): L {
  return both((locale) => joinParagraphs(a1Paragraphs(input, locale)));
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

const NOTHING_RECOGNIZED: L = {
  fr: "Je n'ai reconnu aucun titre du jeu de départ dans ce que vous avez fourni. Ajoutez vos positions à la main dans le tableau, ou passez cette étape.",
  en: "I did not recognize any security from the starter universe in what you provided. Add your positions by hand in the table, or skip this step.",
};
const POSITION_EXPLAINER: L = {
  fr: "Une **position**, c'est un titre que vous détenez, par exemple 100 actions d'une banque. Les pourcentages plus bas montrent la part de chaque catégorie dans le total.",
  en: "A **position** is a security you hold, for example 100 shares of a bank. The percentages below show each category's share of the total.",
};
const EXPOSURES_BY_CODE: L = {
  fr: "Les expositions sont calculées par le code sur la valeur en CAD; aucune n'est estimée par le modèle.",
  en: "Exposures are computed by code on the CAD value; none is estimated by the model.",
};
const CHECK_AND_CONFIRM: L = {
  fr: "Vérifiez les quantités et les comptes, corrigez au besoin, puis confirmez.",
  en: "Check the quantities and accounts, correct them if needed, then confirm.",
};
const USD_CONVERSION: L = {
  fr: ", USD convertis à 1,4255 $ CA selon la Banque du Canada",
  en: ", USD converted at 1.4255 CAD per the Bank of Canada",
};

function positionsFound(input: A2MessageInput, locale: Locale): string {
  const total = formatMoney(input.exposures.total_value_cad, locale);
  const conversion = input.usesUsd ? USD_CONVERSION[locale] : "";
  const plural = input.positions > 1 ? "s" : "";
  return locale === "fr"
    ? `J'ai repéré **${input.positions} position${plural}** pour une valeur estimée de **${total}** (cours de clôture du ${PRICE_DATE}, jeu de départ${conversion}).`
    : `I found **${input.positions} position${plural}** worth an estimated **${total}** (closing prices of ${PRICE_DATE}, starter dataset${conversion}).`;
}

/** The items A2 could not identify: their number, and the first three as the investor wrote them. */
function unidentifiedItems(unresolved: string[], locale: Locale): string | null {
  if (unresolved.length === 0) return null;
  const fr = locale === "fr";
  const several = unresolved.length > 1;
  const quoted = unresolved.slice(0, 3).map((raw) => (fr ? `« ${raw} »` : `"${raw}"`)).join(", ");
  return fr
    ? `${several ? `${unresolved.length} éléments n'ont` : "Un élément n'a"} pas pu être identifié${several ? "s" : ""} : ${quoted}.`
    : `${several ? `${unresolved.length} items` : "One item"} could not be identified: ${quoted}.`;
}

function flagsParagraph(flags: string[], locale: Locale): string | null {
  const sentences = flags.map((flag) => FLAG_SENTENCES[flag]?.[locale]).filter((text): text is string => Boolean(text));
  if (sentences.length === 0) return null;
  return locale === "fr" ? `**À noter** : ${joinList(sentences, locale)}.` : `**Worth noting**: ${joinList(sentences, locale)}.`;
}

function a2Paragraphs(input: A2MessageInput, locale: Locale): Array<string | null> {
  if (input.positions === 0) return [NOTHING_RECOGNIZED[locale]];
  const level = input.level ?? "beginner";
  return [
    positionsFound(input, locale),
    level === "beginner" ? POSITION_EXPLAINER[locale] : null,
    unidentifiedItems(input.unresolved, locale),
    flagsParagraph(input.exposures.flags, locale),
    level === "advanced" ? EXPOSURES_BY_CODE[locale] : null,
    CHECK_AND_CONFIRM[locale],
  ];
}

/** A2's summary of the extraction, in Markdown. */
export function composeA2Message(input: A2MessageInput): L {
  return both((locale) => joinParagraphs(a2Paragraphs(input, locale)));
}
