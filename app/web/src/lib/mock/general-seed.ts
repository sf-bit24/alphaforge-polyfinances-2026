/**
 * Seed of the general base (CONTRACTS.md 5): methodology notes and data series built from the
 * starter dataset. Nothing in it concerns a client.
 */
import type { Source } from "@/lib/contract/schemas";
import { STARTER_SOURCES } from "./starter";

export interface MethodologyNote {
  slug: string;
  title: string;
  description: string;
  tags: string[];
  sources: Source[];
  body: string;
}

export interface DataSeries {
  key: string;
  title: string;
  description: string;
  sources: Source[];
  data: Record<string, unknown>;
  body: string;
}

const BNCD: Source = {
  id: "atelier-bncd",
  title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution",
  resource: "docs/comprendre-investisseur-avant-solution.md",
  retrieved_at: "2026-11-14",
};
const CASE: Source = {
  id: "enonce-fr",
  title: "Énoncé officiel du défi AlphaForge AI (français)",
  resource: "docs/case-officiel-2026-fr.md",
  retrieved_at: "2026-11-14",
};

export const METHODOLOGY_NOTES: MethodologyNote[] = [
  {
    slug: "profil-investisseur",
    title: "Profil investisseur en cinq dimensions",
    description: "Objectif, horizon, risque (tolérance et capacité), contraintes et préférences, avec le niveau de connaissances.",
    tags: ["profil-investisseur"],
    sources: [BNCD],
    body: `# Profil investisseur en cinq dimensions

Un profil se décrit en cinq dimensions : **objectif**, **horizon**, **risque**, **contraintes** et **préférences** (atelier BNCD, diapositive 10).[^bncd]

| Dimension | Ce qu'elle mesure |
| --- | --- |
| Objectif | Ce que l'argent doit accomplir : préserver, procurer un revenu, croître. |
| Horizon | Quand l'argent sera nécessaire. Il ne se déduit ni de l'âge ni de la tolérance. |
| Tolérance au risque | Ce que l'investisseur accepte de vivre psychologiquement. |
| Capacité de risque | Ce que sa situation lui permet de perdre temporairement. |
| Contraintes | Les limites : comptes, liquidité, fiscalité, connaissances. |
| Préférences | Ce qui oriente les choix à l'intérieur de ces limites. |

## Risque effectif

Le risque effectif est le **minimum** de la tolérance et de la capacité, calculé par le code. Une tolérance élevée ne compense jamais une capacité faible.

## Niveau de connaissances

Trois questions rapides (fréquence des placements, suivi de l'actualité, auto-évaluation) donnent le niveau : débutant, intermédiaire ou avancé. Il change le langage des explications, jamais les chiffres.

[^bncd]: Atelier BNCD : comprendre l'investisseur avant de bâtir la solution`,
  },
  {
    slug: "completude-du-profil",
    title: "Complétude du profil : seuil de 70 %, plafond de 95 %",
    description: "Comment le code pondère les champs requis du profil et pourquoi l'affichage plafonne à 95 %.",
    tags: ["profil-investisseur", "gouvernance-explicabilite"],
    sources: [BNCD],
    body: `# Complétude du profil

La complétude est la **part pondérée des champs requis connus**, calculée par le code, de 0 à 1.

- **Seuil de 70 %** : à partir de là, le profil suffit pour continuer et l'investisseur peut s'arrêter.
- **Plafond de 95 %** : l'affichage ne dépasse jamais 95 %. Un profil n'est jamais parfaitement connu; le plafond garde visible cette part d'incertitude.

Les champs qui pèsent le plus sont l'objectif, l'horizon, la réaction à une baisse et le fonds d'urgence : ce sont eux qui changent le plus la réponse.`,
  },
  {
    slug: "expositions-du-portefeuille",
    title: "Expositions d'un portefeuille existant",
    description: "Calcul des expositions par classe d'actifs, devise, marché et secteur, et signaux d'alerte.",
    tags: ["donnees-marche", "construction-portefeuille"],
    sources: [STARTER_SOURCES.prices, STARTER_SOURCES.fx],
    body: `# Expositions d'un portefeuille existant

A2 propose des positions normalisées; l'investisseur les corrige puis les confirme. Le **code** calcule ensuite les expositions, jamais le modèle.

1. Valeur de chaque position = quantité × dernier cours de clôture du jeu de départ (ou valeur déclarée).
2. Les montants en USD sont convertis au dernier taux USD/CAD de la Banque du Canada.
3. Chaque exposition est une part de 0 à 1 de la valeur totale en CAD.

| Signal | Règle |
| --- | --- |
| Concentration sur une position | une position dépasse 20 % du total |
| Biais domestique (Canada) | 50 % ou plus en titres cotés à la TSX |
| Concentration sectorielle | un secteur dépasse 40 % |
| Cryptoactifs | une part, même petite, en cryptoactifs |
| Aucun revenu fixe | ni obligation, ni FNB obligataire, ni encaisse |

Un portefeuille existant montre ce que l'investisseur possède, pas ce dont il a besoin (atelier BNCD, diapositive 14).`,
  },
  {
    slug: "cadre-responsable",
    title: "Cadre responsable d'AlphaForge AI",
    description: "Simulation seulement, aucun conseil personnalisé, garde-fous et traces observables.",
    tags: ["gouvernance-explicabilite"],
    sources: [CASE],
    body: `# Cadre responsable

- **Simulation seulement** : aucune transaction réelle, aucun conseil financier personnalisé, aucun compte réel.
- **Faits, hypothèses, scénarios** : chaque chiffre cite sa source et sa date; une incertitude importante est dite clairement.
- **Garde-fous** : les entrées et les sorties des agents du profil passent par un garde-fou (sujets interdits, renseignements personnels).
- **Traces** : chaque requête produit une trace des actions observables (règle appliquée, outil appelé, entrées, résultat, sources), sans raisonnement interne du modèle.`,
  },
];

export const DATA_SERIES: DataSeries[] = [
  {
    key: "general/donnees/usdcad/usdcad-2026-11.md",
    title: "Taux de change USD/CAD, novembre 2026",
    description: "Taux quotidien de la Banque du Canada (FXUSDCAD), dernières observations du jeu de départ.",
    sources: [STARTER_SOURCES.fx],
    data: {
      series_id: "FXUSDCAD",
      unit: "CAD par USD",
      observations: [
        { date: "2026-11-04", value: 1.3961 },
        { date: "2026-11-05", value: 1.3989 },
        { date: "2026-11-06", value: 1.4113 },
        { date: "2026-11-09", value: 1.4123 },
        { date: "2026-11-10", value: 1.4181 },
        { date: "2026-11-12", value: 1.4255 },
      ],
    },
    body: `# Taux de change USD/CAD, novembre 2026

| Date d'observation | USD/CAD |
| --- | --- |
| 2026-11-04 | 1,3961 |
| 2026-11-05 | 1,3989 |
| 2026-11-06 | 1,4113 |
| 2026-11-09 | 1,4123 |
| 2026-11-10 | 1,4181 |
| 2026-11-12 | 1,4255 |

Taux unique publié vers 16 h 30 (heure de l'Est); aucun taux les jours fériés canadiens. Source : Banque du Canada, série FXUSDCAD, récupérée le 2026-11-13 dans le jeu de départ.`,
  },
  {
    key: "general/donnees/taux-directeur/banque-du-canada-2026-11.md",
    title: "Taux directeur de la Banque du Canada et rendements obligataires",
    description: "Taux cible du financement à un jour et rendements des obligations du Canada à 2 et 10 ans.",
    sources: [STARTER_SOURCES.macro],
    data: {
      V39079: { value: 2.5, since: "2026-10-29", previous: 2.25 },
      "BD.CDN.2YR.DQ.YLD": { value: 3.33, observed_at: "2026-11-12" },
      "BD.CDN.10YR.DQ.YLD": { value: 3.78, observed_at: "2026-11-12" },
    },
    body: `# Taux directeur et rendements obligataires

| Série | Valeur | Date d'observation |
| --- | --- | --- |
| Taux cible du financement à un jour (V39079) | 2,50 % | depuis le 2026-10-29 (2,25 % auparavant) |
| Obligations du Canada, 2 ans | 3,33 % | 2026-11-12 |
| Obligations du Canada, 10 ans | 3,78 % | 2026-11-12 |

L'IPC canadien (3,1 % sur un an, septembre 2026) est daté du mois de référence et publié plusieurs semaines plus tard : il ne doit pas être utilisé avant sa date de publication.`,
  },
];
