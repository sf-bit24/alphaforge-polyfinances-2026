---
type: Financial Concept
title: Pire rendement sur 12 mois
description: La pire année glissante de l'historique, comment AlphaForge AI la calcule et l'affiche, ses limites et comment l'expliquer à chaque niveau.
tags: [notion, risque, pire-rendement-12-mois, horizon]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositives 6 (un rendement dépend de la période) et 7 (le temps disponible change la décision)"
  - id: moteur-metriques
    title: "Moteur de backtest AlphaForge AI : métriques sur rendements mensuels"
    resource: "research/backtest/engine/metrics.py (worst_window_return) et app/agents/src/alphaforge/finance/portfolio/analysis.py (risk_report)"
  - id: politique-risque
    title: "Politique de risque d'AlphaForge AI, niveaux N0 à N5"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml (v0.2.0), section measurement (CVAR12M)"
data:
  aliases: [pire année, pire rendement sur 12 mois, pire 12 mois, pire année glissante, worst 12 months]
  related: [baisse-maximale, var-cvar, horizon, stress-test-2022, volatilite]
---

# Pire rendement sur 12 mois

Le pire rendement sur 12 mois est le plus mauvais résultat obtenu sur n'importe quelle période de 12 mois consécutifs
de l'historique, par exemple de mars à février de l'année suivante. Il répond à la question : « Si j'avais investi au
pire moment et regardé mon relevé un an plus tard, qu'aurais-je vu? »

## Comment l'expliquer selon le niveau

Les chiffres, les sources et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « C'est la pire année qu'aurait connue ce portefeuille dans le passé, peu importe le mois où l'année
  commence. »
- **Intermédiaire** : « Le rendement composé le plus faible parmi toutes les fenêtres de 12 mois consécutifs. Il se
  lit avec l'horizon : sur un horizon court, une seule mauvaise année pèse lourd. »
- **Avancé** : « Minimum, sur toutes les fenêtres glissantes chevauchantes de 12 mois, de exp(Σ ln(1 + rₜ)) − 1, sur
  les rendements mensuels du portefeuille rééquilibré. Il s'agit d'un seul point de la distribution, sans moyenne de
  queue. »

## Ce qu'il faut retenir

- Le point de départ compte : un rendement n'a pas le même sens selon la période (atelier BNCD, diapositive 6). Les
  fenêtres glissantes testent tous les points de départ, pas seulement les années civiles.
- Le pire rendement sur 12 mois est en général moins profond que la baisse maximale, parce qu'une année fixe ne tombe
  pas forcément pile du sommet au creux.
- Plus l'horizon est court, plus ce chiffre est parlant : l'argent requis dans un an subit la pire année entière
  (voir [Horizon](horizon.md) et [Horizon de placement](../methodologie/horizon-de-placement.md)).

## Comment AlphaForge AI le calcule

Le code calcule ce chiffre; le modèle ne l'estime jamais.

- Le rapport de risque du moteur (`risk_report`) calcule le pire rendement composé sur 12 mois consécutifs, à partir
  des rendements mensuels du portefeuille rééquilibré chaque mois, en CAD par défaut, sur la fenêtre de la politique.
- Le chiffre est **affiché**, pas plafonné : l'angle « risque » de l'analyse le cite comme fait sourcé (« pire
  rendement sur 12 mois, historique »), avec la fenêtre et le nombre de mois, à côté de la CVaR, de la baisse maximale
  et de la volatilité.
- Le contrôle bloquant du Judge sur les années de 12 mois porte sur une autre mesure : la CVaR des rendements composés
  sur 12 mois glissants (`CVAR12M`), mesurée sur la série longue raccordée aux proxys (voir [VaR et CVaR](var-cvar.md)).
- Le moteur rend ce chiffre comme un rendement (négatif en cas de perte), et non comme une perte positive.

## Limites

- **Un seul épisode** : il décrit le pire cas observé, qui dépend d'une seule crise de la fenêtre.
- **Fenêtre** : sur une fenêtre sans crise, il paraît rassurant à tort; il faut au moins 12 mois de données.
- **Passé seulement** : une année pire que la pire année observée reste possible.
- **Mensuel** : les fenêtres commencent et finissent en fin de mois; le pire point quotidien n'y est pas.

## À ne pas confondre

- **Baisse maximale** : d'un sommet au creux, quelle que soit la durée (voir [Baisse maximale](baisse-maximale.md)).
- **Stress test 2022** : une année civile précise, de janvier à décembre 2022 (voir
  [Stress test 2022](stress-test-2022.md)).
- **CVaR sur 12 mois** : la moyenne des 5 % pires années glissantes, et non la seule pire.
