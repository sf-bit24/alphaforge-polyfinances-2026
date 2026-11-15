/**
 * The follow-ups the fake A1 picks from, one per profile field the base questions leave open.
 * A help text can come in two versions: one for beginners, one for the other levels.
 */
import type { QuestionDef } from "./questions";

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
