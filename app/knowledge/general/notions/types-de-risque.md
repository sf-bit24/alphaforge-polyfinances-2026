---
type: Financial Concept
title: Types de risque
description: Les six visages du risque (marché, crédit, liquidité, taux et inflation, devise, concentration), ce qu'AlphaForge AI en mesure et ce qu'il ne mesure pas.
tags: [notion, risque, types-de-risque]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 8 (types de risque et risque pertinent; FINRA, CIRO)"
  - id: politique-risque
    title: "Politique de risque d'AlphaForge AI, niveaux N0 à N5"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml (v0.2.0), sections measurement, composition et limits_template"
data:
  catalog_id: types_risque
  aliases: [risque, risque de marché, risque de crédit, risque de liquidité, risque de taux, risque de défaut]
  related: [volatilite, concentration, risque-de-change, obligations-et-taux, inflation, tolerance-et-capacite]
---

# Types de risque

Le risque ne se résume pas à « ça peut baisser ». C'est la possibilité qu'un résultat négatif important pour
l'investisseur se produise (atelier BNCD, diapositive 8). Chaque placement combine plusieurs types de risque.

| Type | Question | Exemple |
| --- | --- | --- |
| Marché | La valeur peut-elle chuter? | Baisse générale des actions |
| Crédit | L'émetteur peut-il ne pas payer? | Défaut d'une société |
| Liquidité | Peut-on vendre au moment voulu? | Peu d'acheteurs disponibles |
| Taux et inflation | Le contexte économique réduit-il la valeur? | Obligation qui baisse quand les taux montent |
| Devise | Le taux de change peut-il modifier le résultat? | Placement américain détenu en CAD |
| Concentration | Le résultat dépend-il trop d'une seule exposition? | Un titre, un secteur ou un pays dominant |

## Comment l'expliquer selon le niveau

Les faits et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « Un placement peut mal tourner de plusieurs façons : il peut baisser, l'emprunteur peut ne pas
  rembourser, on peut avoir du mal à le vendre, ou le dollar peut jouer contre nous. »
- **Intermédiaire** : « Six familles de risque, que l'on regarde ensemble. Le risque qui compte pour vous dépend de
  votre objectif, de votre horizon et de votre capacité à absorber une perte. »
- **Avancé** : « Les mesures de perte (volatilité, CVaR, baisse maximale) captent surtout le risque de marché tel
  qu'observé dans l'historique; crédit et liquidité y apparaissent seulement s'ils se sont matérialisés dans les prix. »

## Ce qu'il faut retenir

- Le risque pertinent dépend de l'objectif, de l'horizon et de la capacité à absorber une perte (atelier BNCD,
  diapositive 8).
- Vouloir accepter une baisse ne signifie pas pouvoir se permettre ses conséquences : la tolérance n'est pas la
  capacité (voir [Tolérance et capacité](tolerance-et-capacite.md)).
- Un placement réputé « sûr » porte quand même des risques : une obligation porte le risque de taux, l'encaisse porte
  le risque d'inflation.

## Comment AlphaForge AI l'utilise

| Type | Ce que le code mesure ou limite |
| --- | --- |
| Marché | CVaR mensuelle, CVaR sur 12 mois, baisse maximale et stress 2022, bloquants au Judge; volatilité, non bloquante |
| Taux et inflation | Un plafond de poids pour les obligations à longue durée (`alloc.long_duration`); le stress 2022 capte une année de hausse des taux |
| Devise | Rendements calculés en devise du mandat (CAD par défaut), donc taux de change inclus |
| Concentration | Plafonds par titre, par FNB d'actions et d'exposition à la technologie (`conc.*`, `exp.tech`) |
| Crédit | Pas de mesure propre : la poche crédit d'un FNB obligataire est ignorée dans son proxy d'historique |
| Liquidité | Pas de mesure propre dans le moteur |

Les budgets par niveau sont dans `finance/policy/risk_levels.yaml`. Les liens détaillés :
[Volatilité](volatilite.md), [VaR et CVaR](var-cvar.md), [Baisse maximale](baisse-maximale.md),
[Stress test 2022](stress-test-2022.md), [Concentration](concentration.md), [Risque de change](risque-de-change.md).

## Limites

- **Historique** : les mesures du code reposent sur des rendements passés; un risque qui ne s'est pas encore
  matérialisé (un défaut, un marché qui se fige) n'y apparaît pas.
- **Crédit et liquidité** : le moteur ne les chiffre pas; l'explication doit le dire plutôt que de les supposer
  nuls.
- **Interactions** : les risques se cumulent; une action américaine porte à la fois un risque de marché, de devise et
  parfois de concentration.

## À ne pas confondre

- **Volatilité** : une mesure du risque de marché, pas le risque en entier.
- **Perte sur papier et perte réalisée** : la seconde n'arrive que si l'on vend.
- **Incertitude et risque** : on chiffre un risque à partir de l'historique; ce qui n'y figure pas reste une
  incertitude.
