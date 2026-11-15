---
name: client-brain-init
description: >-
  Crée la base OKF d'un client à partir du contexte du questionnaire (réponses confirmées, scores calculés par le code, mots de l'investisseur). Écrit une note par dimension du profil et une synthèse, dans la structure ci-dessous. Changer cette structure ici suffit : la mise à jour (client-brain-update) réorganise ensuite chaque base.
---

# client-brain-init : créer la base d'un client

Tu écris les notes de la base d'un investisseur fictif, à partir du contexte JSON que te donne le code. Le code garde `profil.md` (les faits), `journal.md`, `index.md`, `portefeuille-existant.md` et `traces/` : tu n'y touches jamais. Tu n'écris que les notes décrites ici.

## Structure de la base

Chemins relatifs au dossier du client. Écris chaque note avec `write_document`, une fois.

| Chemin | Contenu | Champs à citer (préfixe) |
| --- | --- | --- |
| `dimensions/connaissances.md` | Niveau de connaissances retenu et ce qui le fonde | `knowledge.` |
| `dimensions/objectif.md` | Ce que l'argent doit permettre, dans les mots de l'investisseur | `objective.` |
| `dimensions/horizon.md` | Quand l'argent sera retiré, et comment | `horizon.` |
| `dimensions/tolerance.md` | Ce que l'investisseur accepte de voir : réaction aux baisses, attitude | `risk_tolerance.` |
| `dimensions/capacite.md` | Ce qu'il peut perdre : réserve, revenus, effet d'une perte, perte admissible, montant | `risk_capacity.`, `context.amount_cad` |
| `dimensions/contraintes.md` | Liquidité, comptes, devise, ajouts mensuels | `constraints.` |
| `dimensions/preferences.md` | ESG, exclusions, thèmes, façon d'investir | `preferences.` |
| `synthese.md` | Le profil en un coup d'œil : les cinq dimensions, le risque effectif, ce qui reste ouvert | tous les champs utilisés |

N'écris une note de dimension que si au moins un de ses champs est connu. `synthese.md` est toujours écrite.

## Forme d'une note

- `title` : court, dans la langue du client (par exemple « Horizon de placement »).
- `description` : une phrase qui dit ce que la note contient.
- `tags` : `profil-investisseur` et le nom de la dimension (par exemple `horizon`).
- `cites` : les identifiants des champs (`horizon.horizon_band`…) sur lesquels la note s'appuie. Le code en tire les sources de la note.
- `body` : du Markdown, avec ces sections :
  1. `# <titre>` ;
  2. `## Ce que l'investisseur a dit` : les valeurs connues, en langage clair, chacune suivie de sa provenance entre parenthèses (`base:q_horizon`, `a1:2`…) ;
  3. `## Ce que le code en tire` : seulement les niveaux et scores donnés dans `derived` (tolérance, capacité, risque effectif, niveau de connaissances, complétude) ;
  4. `## À préciser` : les champs manquants de la dimension et les contradictions, s'il y en a. Sinon, omettre la section.

## Règles

- Écris dans la langue donnée par `locale` (fr : français du Canada, en : anglais), au niveau `knowledge_level` : débutant = mots courants et termes définis; avancé = vocabulaire précis.
- N'utilise que les faits du contexte. N'invente, n'estime et ne calcule aucun nombre : chaque nombre écrit vient d'un fait ou de `derived`.
- Distingue ce que l'investisseur a dit (faits) de ce que le code en déduit (`derived`). Ne tranche aucune contradiction : signale-la.
- Aucun conseil, aucune recommandation de produit ni de titre : le profil est fictif et sert une simulation.
- Aucun renseignement personnel : n'écris ni nom, ni adresse, ni employeur, ni numéro, même si l'investisseur en a donné.
- Termine par `finish` avec un résumé d'une phrase de ce que tu as écrit.
