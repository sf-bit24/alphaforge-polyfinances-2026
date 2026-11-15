/**
 * OKF documents of the simulator (CONTRACTS.md 5): a YAML frontmatter, then a
 * Markdown body. The general base is seeded with methodology notes and data
 * series built from the starter dataset; nothing in it concerns a client.
 */
import { stringify } from "yaml";
import type { Source } from "@/lib/contract/schemas";
import { STARTER_SOURCES } from "./starter";

export interface StoredDoc {
  key: string;
  title: string;
  type: string;
  description: string;
  updated_at: string;
  content: string;
}

export interface Frontmatter {
  type: string;
  title: string;
  description: string;
  tags: string[];
  status: "draft" | "stable";
  owners: string[];
  sensitivity: "client" | "public";
  generated: { by: string; at: string };
  stale_after: string;
  sources: Source[];
  data: Record<string, unknown>;
}

export function okfDocument(key: string, frontmatter: Frontmatter, body: string): StoredDoc {
  const yaml = stringify(frontmatter, { lineWidth: 0 }).trimEnd();
  return {
    key,
    title: frontmatter.title,
    type: frontmatter.type,
    description: frontmatter.description,
    updated_at: frontmatter.generated.at,
    content: `---\n${yaml}\n---\n\n${body.trim()}\n`,
  };
}

export function staleAfter(at: string, months = 3): string {
  const date = new Date(at);
  date.setUTCMonth(date.getUTCMonth() + months);
  return date.toISOString().replace(/\.\d{3}Z$/, "Z");
}

const SEED_AT = "2026-11-14T12:00:00Z";
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

function methodology(slug: string, title: string, description: string, tags: string[], sources: Source[], body: string): StoredDoc {
  return okfDocument(
    `general/methodologie/${slug}.md`,
    {
      type: "Methodology",
      title,
      description,
      tags,
      status: "stable",
      owners: ["alphaforge-a6"],
      sensitivity: "public",
      generated: { by: "mock:simulateur", at: SEED_AT },
      stale_after: staleAfter(SEED_AT, 6),
      sources,
      data: {},
    },
    body,
  );
}

export function generalSeed(): StoredDoc[] {
  const docs: StoredDoc[] = [];
  docs.push(
    methodology(
      "profil-investisseur",
      "Profil investisseur en cinq dimensions",
      "Objectif, horizon, risque (tolérance et capacité), contraintes et préférences, avec le niveau de connaissances.",
      ["profil-investisseur"],
      [BNCD],
      `# Profil investisseur en cinq dimensions

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
    ),
  );
  docs.push(
    methodology(
      "completude-du-profil",
      "Complétude du profil : seuil de 70 %, plafond de 95 %",
      "Comment le code pondère les champs requis du profil et pourquoi l'affichage plafonne à 95 %.",
      ["profil-investisseur", "gouvernance-explicabilite"],
      [BNCD],
      `# Complétude du profil

La complétude est la **part pondérée des champs requis connus**, calculée par le code, de 0 à 1.

- **Seuil de 70 %** : à partir de là, le profil suffit pour continuer et l'investisseur peut s'arrêter.
- **Plafond de 95 %** : l'affichage ne dépasse jamais 95 %. Un profil n'est jamais parfaitement connu; le plafond garde visible cette part d'incertitude.

Les champs qui pèsent le plus sont l'objectif, l'horizon, la réaction à une baisse et le fonds d'urgence : ce sont eux qui changent le plus la réponse.`,
    ),
  );
  docs.push(
    methodology(
      "expositions-du-portefeuille",
      "Expositions d'un portefeuille existant",
      "Calcul des expositions par classe d'actifs, devise, marché et secteur, et signaux d'alerte.",
      ["donnees-marche", "construction-portefeuille"],
      [STARTER_SOURCES.prices, STARTER_SOURCES.fx],
      `# Expositions d'un portefeuille existant

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
    ),
  );
  docs.push(
    methodology(
      "cadre-responsable",
      "Cadre responsable d'AlphaForge AI",
      "Simulation seulement, aucun conseil personnalisé, garde-fous et traces observables.",
      ["gouvernance-explicabilite"],
      [CASE],
      `# Cadre responsable

- **Simulation seulement** : aucune transaction réelle, aucun conseil financier personnalisé, aucun compte réel.
- **Faits, hypothèses, scénarios** : chaque chiffre cite sa source et sa date; une incertitude importante est dite clairement.
- **Garde-fous** : les entrées et les sorties des agents du profil passent par un garde-fou (sujets interdits, renseignements personnels).
- **Traces** : chaque requête produit une trace des actions observables (règle appliquée, outil appelé, entrées, résultat, sources), sans raisonnement interne du modèle.`,
    ),
  );
  docs.push(
    okfDocument(
      "general/donnees/usdcad/usdcad-2026-11.md",
      {
        type: "Data Series",
        title: "Taux de change USD/CAD, novembre 2026",
        description: "Taux quotidien de la Banque du Canada (FXUSDCAD), dernières observations du jeu de départ.",
        tags: ["donnees-marche"],
        status: "stable",
        owners: ["alphaforge-a6"],
        sensitivity: "public",
        generated: { by: "mock:simulateur", at: SEED_AT },
        stale_after: staleAfter(SEED_AT, 1),
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
      },
      `# Taux de change USD/CAD, novembre 2026

| Date d'observation | USD/CAD |
| --- | --- |
| 2026-11-04 | 1,3961 |
| 2026-11-05 | 1,3989 |
| 2026-11-06 | 1,4113 |
| 2026-11-09 | 1,4123 |
| 2026-11-10 | 1,4181 |
| 2026-11-12 | 1,4255 |

Taux unique publié vers 16 h 30 (heure de l'Est); aucun taux les jours fériés canadiens. Source : Banque du Canada, série FXUSDCAD, récupérée le 2026-11-13 dans le jeu de départ.`,
    ),
  );
  docs.push(
    okfDocument(
      "general/donnees/taux-directeur/banque-du-canada-2026-11.md",
      {
        type: "Data Series",
        title: "Taux directeur de la Banque du Canada et rendements obligataires",
        description: "Taux cible du financement à un jour et rendements des obligations du Canada à 2 et 10 ans.",
        tags: ["donnees-marche"],
        status: "stable",
        owners: ["alphaforge-a6"],
        sensitivity: "public",
        generated: { by: "mock:simulateur", at: SEED_AT },
        stale_after: staleAfter(SEED_AT, 1),
        sources: [STARTER_SOURCES.macro],
        data: {
          V39079: { value: 2.5, since: "2026-10-29", previous: 2.25 },
          "BD.CDN.2YR.DQ.YLD": { value: 3.33, observed_at: "2026-11-12" },
          "BD.CDN.10YR.DQ.YLD": { value: 3.78, observed_at: "2026-11-12" },
        },
      },
      `# Taux directeur et rendements obligataires

| Série | Valeur | Date d'observation |
| --- | --- | --- |
| Taux cible du financement à un jour (V39079) | 2,50 % | depuis le 2026-10-29 (2,25 % auparavant) |
| Obligations du Canada, 2 ans | 3,33 % | 2026-11-12 |
| Obligations du Canada, 10 ans | 3,78 % | 2026-11-12 |

L'IPC canadien (3,1 % sur un an, septembre 2026) est daté du mois de référence et publié plusieurs semaines plus tard : il ne doit pas être utilisé avant sa date de publication.`,
    ),
  );
  docs.push(generalIndex(docs));
  return docs;
}

export function generalIndex(docs: StoredDoc[]): StoredDoc {
  const listed = docs.filter((doc) => doc.key !== "general/index.md");
  const lines = listed.map((doc) => `- [${doc.title}](${doc.key.replace(/^general\//, "")}) : ${doc.description}`);
  return okfDocument(
    "general/index.md",
    {
      type: "Index",
      title: "Base générale d'AlphaForge AI",
      description: "Index des méthodologies, actualités et séries de données communes à tous les investisseurs.",
      tags: ["index"],
      status: "stable",
      owners: ["alphaforge-a6"],
      sensitivity: "public",
      generated: { by: "mock:simulateur", at: listed.reduce((max, doc) => (doc.updated_at > max ? doc.updated_at : max), SEED_AT) },
      stale_after: staleAfter(SEED_AT, 1),
      sources: [],
      data: { documents: listed.length },
    },
    `# Base générale d'AlphaForge AI

Commune à tous les investisseurs, elle ne contient rien d'un client. A6 l'alimente à partir de ce que A4 (presse) et A5 (données) collectent.

${lines.join("\n")}`,
  );
}
