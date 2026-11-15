/**
 * Question catalogs of the simulator: the deterministic base questions (same for
 * everyone, with a few rule-based branches) and the follow-ups the fake A1 picks
 * from. Texts are localized here, as the real runtime does: the UI translates none.
 */
import type {
  AnswerValue,
  Dimension,
  KnowledgeLevel,
  Locale,
  Question,
  QuestionKind,
} from "@/lib/contract/schemas";

export interface L {
  fr: string;
  en: string;
}

export const tr = (text: L, locale: Locale): string => text[locale];

export interface OptionDef {
  value: string;
  label: L;
}

export interface QuestionDef {
  id: string;
  source: "deterministic" | "a1";
  dimension: Dimension;
  kind: QuestionKind;
  /** Profile field written by the answer, `<dimension>.<name>`. */
  field: string;
  prompt: L;
  help?: L | { beginner: L; other: L };
  options?: OptionDef[];
  min?: number;
  max?: number;
  unit?: L;
  required?: boolean;
}

const CAD: L = { fr: "CAD", en: "CAD" };

export const BASE_QUESTIONS: QuestionDef[] = [
  {
    id: "q_invest_frequency",
    source: "deterministic",
    dimension: "knowledge",
    kind: "single_choice",
    field: "knowledge.invest_frequency",
    prompt: {
      fr: "Au cours des trois dernières années, à quelle fréquence avez-vous placé de l'argent (actions, fonds, FNB, CPG…) ?",
      en: "Over the past three years, how often have you invested money (stocks, funds, ETFs, GICs…)?",
    },
    help: {
      fr: "Il n'y a pas de mauvaise réponse : votre niveau sert seulement à adapter les explications.",
      en: "There is no wrong answer: your level is only used to adapt the explanations.",
    },
    options: [
      { value: "never", label: { fr: "Jamais", en: "Never" } },
      { value: "few", label: { fr: "Une ou deux fois", en: "Once or twice" } },
      { value: "yearly", label: { fr: "Quelques fois par année", en: "A few times a year" } },
      { value: "monthly", label: { fr: "Chaque mois ou plus", en: "Every month or more" } },
    ],
  },
  {
    id: "q_news_follow",
    source: "deterministic",
    dimension: "knowledge",
    kind: "single_choice",
    field: "knowledge.news_follow",
    prompt: {
      fr: "À quelle fréquence suivez-vous l'actualité financière ou économique ?",
      en: "How often do you follow financial or economic news?",
    },
    help: {
      fr: "Journaux, balados, infolettres ou applications : tout compte.",
      en: "Newspapers, podcasts, newsletters or apps all count.",
    },
    options: [
      { value: "rarely", label: { fr: "Rarement ou jamais", en: "Rarely or never" } },
      { value: "monthly", label: { fr: "Quelques fois par mois", en: "A few times a month" } },
      { value: "weekly", label: { fr: "Chaque semaine", en: "Every week" } },
      { value: "daily", label: { fr: "Tous les jours", en: "Every day" } },
    ],
  },
  {
    id: "q_self_assessment",
    source: "deterministic",
    dimension: "knowledge",
    kind: "single_choice",
    field: "knowledge.self_assessment",
    prompt: {
      fr: "Comment évaluez-vous vos connaissances en placement ?",
      en: "How would you rate your investment knowledge?",
    },
    help: {
      fr: "Vous pourrez le changer à tout moment dans les réglages.",
      en: "You can change it at any time in the settings.",
    },
    options: [
      { value: "beginner", label: { fr: "Débutant : je découvre les placements", en: "Beginner: I am new to investing" } },
      { value: "intermediate", label: { fr: "Intermédiaire : je connais les actions, les obligations et les FNB", en: "Intermediate: I know stocks, bonds and ETFs" } },
      { value: "advanced", label: { fr: "Avancé : je compare des frais, des indicateurs de risque et des stratégies", en: "Advanced: I compare fees, risk metrics and strategies" } },
    ],
  },
  {
    id: "q_goal",
    source: "deterministic",
    dimension: "objective",
    kind: "single_choice",
    field: "objective.goal",
    prompt: { fr: "Quel est l'objectif principal de cet argent ?", en: "What is the main goal for this money?" },
    help: {
      fr: "Si vous avez plusieurs objectifs, choisissez le plus important pour cet argent.",
      en: "If you have several goals, pick the most important one for this money.",
    },
    options: [
      { value: "preserve", label: { fr: "Préserver mon capital", en: "Preserve my capital" } },
      { value: "income", label: { fr: "Obtenir un revenu régulier", en: "Earn a regular income" } },
      { value: "balanced", label: { fr: "Faire croître mon capital de façon équilibrée", en: "Grow my capital in a balanced way" } },
      { value: "growth", label: { fr: "Faire croître mon capital à long terme", en: "Grow my capital over the long term" } },
    ],
  },
  {
    id: "q_income_need",
    source: "deterministic",
    dimension: "objective",
    kind: "money",
    field: "objective.income_need",
    prompt: {
      fr: "Quel revenu annuel aimeriez-vous tirer de ce placement ?",
      en: "How much yearly income would you like this investment to provide?",
    },
    help: {
      fr: "Un ordre de grandeur suffit; il sert à vérifier la cohérence avec le montant placé.",
      en: "A rough figure is enough; it is used to check consistency with the amount invested.",
    },
    min: 0,
    max: 10_000_000,
    unit: CAD,
  },
  {
    id: "q_amount",
    source: "deterministic",
    dimension: "objective",
    kind: "money",
    field: "objective.amount",
    prompt: { fr: "Quel montant envisagez-vous de placer ?", en: "How much are you considering investing?" },
    help: {
      fr: "Un ordre de grandeur suffit. Tout reste fictif : aucune transaction n'est effectuée.",
      en: "A rough figure is enough. Everything stays fictitious: no transaction is made.",
    },
    min: 0,
    max: 100_000_000,
    unit: CAD,
  },
  {
    id: "q_horizon",
    source: "deterministic",
    dimension: "horizon",
    kind: "single_choice",
    field: "horizon.horizon_band",
    prompt: {
      fr: "Dans combien de temps aurez-vous besoin d'une part importante de cet argent ?",
      en: "When will you need a significant part of this money?",
    },
    help: {
      fr: "L'horizon ne se déduit ni de l'âge ni de la tolérance au risque.",
      en: "Your horizon cannot be inferred from your age or your risk tolerance.",
    },
    options: [
      { value: "lt3", label: { fr: "Moins de 3 ans", en: "Less than 3 years" } },
      { value: "3to10", label: { fr: "De 3 à 10 ans", en: "3 to 10 years" } },
      { value: "gt10", label: { fr: "10 ans et plus", en: "10 years or more" } },
    ],
  },
  {
    id: "q_liquidity",
    source: "deterministic",
    dimension: "constraints",
    kind: "boolean",
    field: "constraints.liquidity_need",
    prompt: {
      fr: "Pourriez-vous avoir besoin d'une partie de cet argent à tout moment, sans préavis ?",
      en: "Could you need part of this money at any time, without notice?",
    },
    help: {
      fr: "Un besoin de liquidité limite les placements qui peuvent baisser au mauvais moment.",
      en: "A liquidity need limits investments that could fall at the wrong time.",
    },
  },
  {
    id: "q_drawdown_reaction",
    source: "deterministic",
    dimension: "risk_tolerance",
    kind: "single_choice",
    field: "risk_tolerance.drawdown_reaction",
    prompt: {
      fr: "Imaginez que la valeur de votre placement baisse de 20 % en quelques mois. Que feriez-vous ?",
      en: "Imagine your investment loses 20% of its value within a few months. What would you do?",
    },
    help: {
      fr: "Répondez selon ce que vous feriez vraiment, pas selon ce qu'il faudrait faire.",
      en: "Answer with what you would actually do, not what you think you should do.",
    },
    options: [
      { value: "sell_all", label: { fr: "Je vendrais tout pour éviter d'autres pertes", en: "Sell everything to avoid further losses" } },
      { value: "sell_some", label: { fr: "Je vendrais une partie", en: "Sell part of it" } },
      { value: "hold", label: { fr: "Je ne changerais rien", en: "Change nothing" } },
      { value: "buy_more", label: { fr: "J'en profiterais pour investir davantage", en: "Take the opportunity to invest more" } },
    ],
  },
  {
    id: "q_risk_scale",
    source: "deterministic",
    dimension: "risk_tolerance",
    kind: "scale",
    field: "risk_tolerance.risk_scale",
    prompt: {
      fr: "Sur une échelle de 1 à 10, quelles variations de valeur êtes-vous prêt à accepter ?",
      en: "On a scale of 1 to 10, how much fluctuation in value are you willing to accept?",
    },
    help: {
      fr: "1 : aucune baisse acceptée. 10 : de fortes baisses acceptées dans l'espoir d'un rendement plus élevé.",
      en: "1: no decline accepted. 10: large declines accepted in the hope of a higher return.",
    },
    min: 1,
    max: 10,
  },
  {
    id: "q_income_stability",
    source: "deterministic",
    dimension: "risk_capacity",
    kind: "single_choice",
    field: "risk_capacity.income_stability",
    prompt: { fr: "Vos revenus sont-ils stables ?", en: "How stable is your income?" },
    help: {
      fr: "La capacité de risque dépend de votre situation, pas seulement de votre tempérament.",
      en: "Risk capacity depends on your situation, not only on your temperament.",
    },
    options: [
      { value: "very_stable", label: { fr: "Très stables (salaire, pension)", en: "Very stable (salary, pension)" } },
      { value: "stable", label: { fr: "Plutôt stables", en: "Fairly stable" } },
      { value: "variable", label: { fr: "Variables (travail autonome, commissions)", en: "Variable (self-employed, commissions)" } },
      { value: "none", label: { fr: "Aucun revenu d'emploi en ce moment", en: "No employment income at the moment" } },
    ],
  },
  {
    id: "q_savings_share",
    source: "deterministic",
    dimension: "risk_capacity",
    kind: "percent",
    field: "risk_capacity.savings_share",
    prompt: {
      fr: "Quelle part de votre épargne totale ce montant représente-t-il ?",
      en: "What share of your total savings does this amount represent?",
    },
    help: {
      fr: "Plus la part est grande, moins vous pouvez absorber une baisse.",
      en: "The larger the share, the less you can absorb a decline.",
    },
    min: 0,
    max: 100,
  },
  {
    id: "q_accounts",
    source: "deterministic",
    dimension: "constraints",
    kind: "multi_choice",
    field: "constraints.accounts",
    prompt: { fr: "Dans quels comptes ce placement pourrait-il se faire ?", en: "Which accounts could hold this investment?" },
    help: {
      fr: "Chaque compte enregistré a ses propres règles fiscales et plafonds de cotisation.",
      en: "Each registered account has its own tax rules and contribution limits.",
    },
    options: [
      { value: "tfsa", label: { fr: "CELI", en: "TFSA" } },
      { value: "rrsp", label: { fr: "REER", en: "RRSP" } },
      { value: "resp", label: { fr: "REEE", en: "RESP" } },
      { value: "rrif", label: { fr: "FERR", en: "RRIF" } },
      { value: "non_registered", label: { fr: "Compte non enregistré", en: "Non-registered account" } },
      { value: "unknown", label: { fr: "Je ne sais pas", en: "I don't know" } },
    ],
  },
  {
    id: "q_exclusions",
    source: "deterministic",
    dimension: "preferences",
    kind: "multi_choice",
    field: "preferences.exclusions",
    prompt: {
      fr: "Souhaitez-vous exclure certains secteurs ou types d'actifs ?",
      en: "Would you like to exclude certain sectors or asset types?",
    },
    help: {
      fr: "Les préférences orientent les choix à l'intérieur des limites fixées par vos contraintes.",
      en: "Preferences guide choices within the limits set by your constraints.",
    },
    options: [
      { value: "tobacco", label: { fr: "Tabac", en: "Tobacco" } },
      { value: "weapons", label: { fr: "Armement", en: "Weapons" } },
      { value: "fossil_fuels", label: { fr: "Énergies fossiles", en: "Fossil fuels" } },
      { value: "gambling", label: { fr: "Jeux de hasard", en: "Gambling" } },
      { value: "crypto", label: { fr: "Cryptoactifs", en: "Crypto-assets" } },
      { value: "none", label: { fr: "Aucune exclusion", en: "No exclusion" } },
      { value: "other", label: { fr: "Autre", en: "Other" } },
    ],
  },
  {
    id: "q_exclusions_other",
    source: "deterministic",
    dimension: "preferences",
    kind: "text",
    field: "preferences.exclusions_other",
    prompt: { fr: "Précisez ce que vous souhaitez exclure.", en: "Tell us what you want to exclude." },
    help: {
      fr: "Par exemple : une entreprise précise, un pays, une pratique.",
      en: "For example: a specific company, a country, a practice.",
    },
  },
  {
    id: "q_has_portfolio",
    source: "deterministic",
    dimension: "context",
    kind: "boolean",
    field: "context.has_portfolio",
    prompt: {
      fr: "Avez-vous déjà des placements (un portefeuille existant) ?",
      en: "Do you already have investments (an existing portfolio)?",
    },
    help: {
      fr: "Si oui, vous pourrez le transmettre sous n'importe quelle forme : texte collé, CSV, tableur, PDF ou image.",
      en: "If so, you can share it in any form: pasted text, CSV, spreadsheet, PDF or image.",
    },
  },
];

/** Branches of the questionnaire: a question listed here is asked only if its rule holds. */
const BRANCHES: Record<string, { trigger: string; when: (answers: Record<string, AnswerValue>) => boolean; why: L }> = {
  q_income_need: {
    trigger: "q_goal",
    when: (answers) => answers.q_goal === "income",
    why: { fr: "objectif = revenu régulier", en: "goal = regular income" },
  },
  q_liquidity: {
    trigger: "q_horizon",
    when: (answers) => answers.q_horizon === "lt3",
    why: { fr: "horizon de moins de 3 ans", en: "horizon under 3 years" },
  },
  q_exclusions_other: {
    trigger: "q_exclusions",
    when: (answers) => Array.isArray(answers.q_exclusions) && answers.q_exclusions.includes("other"),
    why: { fr: "exclusion « Autre » cochée", en: "\"Other\" exclusion selected" },
  },
};

const BASE_BY_ID = new Map(BASE_QUESTIONS.map((question) => [question.id, question]));

export function baseQuestion(id: string): QuestionDef | undefined {
  return BASE_BY_ID.get(id);
}

/** Next base question by the rules, or null when the questionnaire is done. */
export function nextBaseQuestion(answers: Record<string, AnswerValue>): {
  id: string;
  branch: L | null;
} | null {
  for (const question of BASE_QUESTIONS) {
    if (question.id in answers) continue;
    const branch = BRANCHES[question.id];
    if (branch && !branch.when(answers)) continue;
    return { id: question.id, branch: branch?.why ?? null };
  }
  return null;
}

/** Branch rules decided by the answer to `questionId`, for the trace. */
export function branchesTriggeredBy(
  questionId: string,
  answers: Record<string, AnswerValue>,
): Array<{ question: string; active: boolean; rule: L }> {
  return Object.entries(BRANCHES)
    .filter(([, branch]) => branch.trigger === questionId)
    .map(([id, branch]) => ({ question: id, active: branch.when(answers), rule: branch.why }));
}

export const A1_QUESTIONS: QuestionDef[] = [
  {
    id: "a1_emergency_fund",
    source: "a1",
    dimension: "risk_capacity",
    kind: "number",
    field: "risk_capacity.emergency_fund",
    prompt: {
      fr: "Combien de mois de dépenses votre épargne de précaution couvre-t-elle, hors de ce placement ?",
      en: "How many months of expenses does your emergency savings cover, outside this investment?",
    },
    help: {
      beginner: {
        fr: "C'est l'argent mis de côté pour les imprévus (perte d'emploi, réparation). Il évite de vendre vos placements au mauvais moment.",
        en: "This is money set aside for emergencies (job loss, repairs). It keeps you from selling investments at the wrong time.",
      },
      other: {
        fr: "Un coussin suffisant permet de traverser une baisse sans vendre.",
        en: "A sufficient cushion lets you ride out a decline without selling.",
      },
    },
    min: 0,
    max: 60,
    unit: { fr: "mois", en: "months" },
  },
  {
    id: "a1_purpose",
    source: "a1",
    dimension: "objective",
    kind: "text",
    field: "objective.purpose",
    prompt: { fr: "En quelques mots, à quoi servira cet argent ?", en: "In a few words, what will this money be used for?" },
    help: {
      fr: "Par exemple : la retraite, la mise de fonds d'une maison, les études des enfants.",
      en: "For example: retirement, a home down payment, your children's education.",
    },
  },
  {
    id: "a1_withdrawals",
    source: "a1",
    dimension: "horizon",
    kind: "single_choice",
    field: "horizon.withdrawal_pattern",
    prompt: { fr: "Comment prévoyez-vous retirer cet argent ?", en: "How do you plan to withdraw this money?" },
    help: {
      beginner: {
        fr: "Un portefeuille peut avoir plusieurs horizons : tout retirer d'un coup ou peu à peu ne demande pas la même prudence.",
        en: "A portfolio can have several horizons: withdrawing all at once or bit by bit calls for different caution.",
      },
      other: {
        fr: "Le profil de décaissement change la part à garder en actifs peu volatils.",
        en: "The withdrawal pattern changes how much to keep in low-volatility assets.",
      },
    },
    options: [
      { value: "lump_sum", label: { fr: "En une seule fois", en: "All at once" } },
      { value: "gradual", label: { fr: "Progressivement, sur plusieurs années", en: "Gradually, over several years" } },
      { value: "none", label: { fr: "Aucun retrait prévu", en: "No withdrawal planned" } },
      { value: "unsure", label: { fr: "Je ne sais pas encore", en: "Not sure yet" } },
    ],
  },
  {
    id: "a1_debt",
    source: "a1",
    dimension: "risk_capacity",
    kind: "boolean",
    field: "risk_capacity.high_interest_debt",
    prompt: {
      fr: "Avez-vous des dettes à taux élevé, par exemple un solde de carte de crédit reporté ?",
      en: "Do you carry high-interest debt, such as a credit card balance?",
    },
    help: {
      beginner: {
        fr: "Rembourser une dette chère passe souvent avant le placement : les intérêts payés peuvent dépasser le rendement espéré.",
        en: "Paying off expensive debt often comes before investing: the interest paid can exceed the expected return.",
      },
      other: {
        fr: "Une dette coûteuse réduit la capacité à prendre du risque.",
        en: "Expensive debt reduces your capacity to take risk.",
      },
    },
  },
  {
    id: "a1_liquidity",
    source: "a1",
    dimension: "constraints",
    kind: "boolean",
    field: "constraints.liquidity_need",
    prompt: {
      fr: "Pourriez-vous avoir besoin d'une partie de cet argent à court terme, sans préavis ?",
      en: "Could you need part of this money at short notice?",
    },
    help: {
      fr: "Cela indique la part à garder facilement disponible.",
      en: "This indicates how much to keep readily available.",
    },
  },
  {
    id: "a1_themes",
    source: "a1",
    dimension: "preferences",
    kind: "multi_choice",
    field: "preferences.themes",
    prompt: { fr: "Certains thèmes vous intéressent-ils particulièrement ?", en: "Are you particularly interested in some themes?" },
    help: {
      fr: "Un intérêt n'est pas une contrainte : il oriente les choix sans dépasser vos limites.",
      en: "An interest is not a constraint: it guides choices without exceeding your limits.",
    },
    options: [
      { value: "technology", label: { fr: "Technologie et IA", en: "Technology and AI" } },
      { value: "clean_energy", label: { fr: "Énergie propre", en: "Clean energy" } },
      { value: "dividends", label: { fr: "Entreprises qui versent des dividendes", en: "Dividend-paying companies" } },
      { value: "health", label: { fr: "Santé", en: "Health care" } },
      { value: "none", label: { fr: "Aucun en particulier", en: "None in particular" } },
    ],
  },
];

const A1_BY_ID = new Map(A1_QUESTIONS.map((question) => [question.id, question]));

export function a1Question(id: string): QuestionDef | undefined {
  return A1_BY_ID.get(id);
}

export function questionByField(field: string): QuestionDef | undefined {
  return [...BASE_QUESTIONS, ...A1_QUESTIONS].find((question) => question.field === field);
}

/** Render a catalog entry as a contract `Question` in the given locale and level. */
export function renderQuestion(def: QuestionDef, locale: Locale, level: KnowledgeLevel | null): Question {
  let help: string | null = null;
  if (def.help) {
    if ("beginner" in def.help) {
      help = tr(level === "beginner" || level === null ? def.help.beginner : def.help.other, locale);
    } else {
      help = tr(def.help, locale);
    }
  }
  return {
    id: def.id,
    source: def.source,
    dimension: def.dimension,
    kind: def.kind,
    prompt: tr(def.prompt, locale),
    help,
    options: def.options ? def.options.map((option) => ({ value: option.value, label: tr(option.label, locale) })) : null,
    min: def.min ?? (def.kind === "percent" ? 0 : null),
    max: def.max ?? (def.kind === "percent" ? 100 : null),
    unit: def.unit ? tr(def.unit, locale) : def.kind === "money" ? "CAD" : null,
    required: def.required ?? true,
    // Short name, as in the CONTRACTS.md 3.3 example (`horizon_band`).
    field: def.field.slice(def.field.indexOf(".") + 1),
  };
}

/** Label of an option value, for summaries. */
export function optionLabel(field: string, value: unknown, locale: Locale): string | null {
  const def = questionByField(field);
  const option = def?.options?.find((candidate) => candidate.value === value);
  return option ? tr(option.label, locale) : null;
}

export type ValidationResult = { ok: true; value: AnswerValue } | { ok: false; reason: L; details: Record<string, unknown> };

/** Validate a value against a question, by kind (CONTRACTS.md 3.3). */
export function validateAnswer(question: Question, value: unknown): ValidationResult {
  const fail = (reason: L, details: Record<string, unknown> = {}): ValidationResult => ({
    ok: false,
    reason,
    details: { question_id: question.id, kind: question.kind, ...details },
  });
  const allowed = question.options?.map((option) => option.value) ?? [];
  const min = question.min ?? null;
  const max = question.max ?? null;
  const inBounds = (number: number) => (min === null || number >= min) && (max === null || number <= max);
  switch (question.kind) {
    case "single_choice":
      if (typeof value !== "string" || !allowed.includes(value)) {
        return fail({ fr: "Choisissez une des options proposées.", en: "Choose one of the options." }, { allowed });
      }
      return { ok: true, value };
    case "multi_choice": {
      if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
        return fail({ fr: "Une liste d'options est attendue.", en: "A list of options is expected." }, { allowed });
      }
      const unique = [...new Set(value as string[])];
      const unknown = unique.filter((item) => !allowed.includes(item));
      if (unknown.length > 0) {
        return fail({ fr: "Certaines options sont inconnues.", en: "Some options are unknown." }, { allowed, unknown });
      }
      if (question.required && unique.length === 0) {
        return fail({ fr: "Cochez au moins une option.", en: "Select at least one option." }, { allowed });
      }
      return { ok: true, value: unique };
    }
    case "boolean":
      if (typeof value !== "boolean") return fail({ fr: "Répondez par oui ou par non.", en: "Answer yes or no." });
      return { ok: true, value };
    case "number":
    case "money":
      if (typeof value !== "number" || !Number.isFinite(value) || !inBounds(value) || (question.kind === "money" && value < 0)) {
        return fail(
          { fr: "Entrez un nombre dans les bornes permises.", en: "Enter a number within the allowed range." },
          { min, max },
        );
      }
      return { ok: true, value };
    case "percent":
      if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 100) {
        return fail({ fr: "Entrez un pourcentage de 0 à 100.", en: "Enter a percentage from 0 to 100." }, { min: 0, max: 100 });
      }
      return { ok: true, value };
    case "scale":
      if (typeof value !== "number" || !Number.isInteger(value) || !inBounds(value)) {
        return fail({ fr: "Choisissez un entier de l'échelle.", en: "Choose a whole number on the scale." }, { min, max });
      }
      return { ok: true, value };
    case "text": {
      if (typeof value !== "string") return fail({ fr: "Un texte est attendu.", en: "Text is expected." });
      const text = value.trim();
      if (text.length < 1 || text.length > 2000) {
        return fail({ fr: "Le texte doit compter de 1 à 2 000 caractères.", en: "Text must be 1 to 2,000 characters long." }, { min: 1, max: 2000 });
      }
      return { ok: true, value: text };
    }
  }
}
