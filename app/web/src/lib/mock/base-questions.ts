/**
 * The deterministic base questions of the simulator, in the order they are asked: the same
 * for everyone, apart from the few rule-based branches of `questions.ts`. Texts are localized
 * here, as the real runtime does: the UI translates none.
 */
import type { L, QuestionDef } from "./questions";

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
