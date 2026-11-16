---
type: Financial Concept
title: Volatilité
description: L'ampleur des variations de prix, comment AlphaForge AI la calcule, pourquoi son plafond n'est pas bloquant, et comment l'expliquer à chaque niveau.
tags: [notion, risque, volatilite]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 8 (le risque ne se résume pas à « ça peut baisser »)"
  - id: atelier-aws
    title: "Atelier du Datathon PolyFinances 2026 : aide-mémoire, pièges classiques des données financières"
    resource: "Atelier AWS du Datathon PolyFinances 2026, section 3 (rendement sans risque, rendement passé)"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, p. 18 (la volatilité est un indicateur de risque parmi d'autres)"
  - id: jeu-de-depart
    title: "Jeu de départ AlphaForge AI : prix quotidiens ajustés"
    resource: "starter:prices_daily.csv (colonne adj_close)"
  - id: politique-risque
    title: "Niveaux de risque d'AlphaForge AI"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml (v0.2.0), section measurement"
data:
  aliases: [volatilité, fluctuations, écart-type, ça bouge, montagnes russes, yo-yo]
  related: [baisse-maximale, var-cvar, diversification, horizon, tolerance-et-capacite]
---

# Volatilité

La volatilité mesure l'ampleur des variations de prix d'un placement, à la hausse comme à la baisse. Plus elle est
élevée, plus la valeur peut s'écarter de son point de départ en peu de temps. Elle s'exprime en pourcentage par an.

## Comment l'expliquer selon le niveau

Les chiffres, les sources et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « La volatilité, c'est à quel point le prix fait des montagnes russes. Une volatilité forte veut dire
  de grands hauts et de grands bas, souvent sans prévenir. »
- **Intermédiaire** : « L'écart-type des rendements, ramené à l'année. Une volatilité de 15 % décrit des variations
  annuelles typiques de cet ordre autour de la moyenne, dans les deux sens. »
- **Avancé** : « Écart-type d'échantillon annualisé des rendements, quotidiens ou mensuels selon le calcul. Mesure
  symétrique, qui ne distingue pas les hausses des baisses et sous-estime les queues épaisses. »

## Ce qu'il faut retenir

- La volatilité compte les hausses autant que les baisses : elle mesure l'incertitude, pas la perte.
- Une action seule est en général plus volatile qu'un panier diversifié, parce que les variations des titres d'un
  panier se compensent en partie (voir [Diversification](diversification.md)).
- Un rendement seul ne dit rien : il se lit avec la volatilité et la baisse maximale (aide-mémoire du Datathon, section 3).
- La volatilité est un indicateur de risque parmi d'autres; l'horizon, la diversification et les préférences de
  l'investisseur comptent aussi (énoncé officiel, p. 18).
- La volatilité passée ne garantit pas la volatilité future.

## Comment AlphaForge AI la calcule

AlphaForge AI calcule la volatilité selon des règles fixes. Yan l'explique; les chiffres sont calculés, jamais
inventés.

| Où | Données | Calcul |
| --- | --- | --- |
| Risque d'un portefeuille (simulateur, vérification finale) | Rendements mensuels d'un portefeuille rééquilibré chaque mois, en devise du mandat | Écart-type d'échantillon multiplié par √12 |

- Chaque niveau de risque (N0 à N5) porte un plafond de volatilité.
- Ce plafond **n'est pas bloquant** : la vérification finale l'affiche et vérifie la cohérence, mais elle ne refuse
  pas une proposition pour ce seul motif. Les contrôles bloquants portent sur les pertes : CVaR mensuelle, CVaR sur 12 mois,
  baisse maximale et stress 2022 (voir [VaR et CVaR](var-cvar.md) et [Baisse maximale](baisse-maximale.md)).
- Quand une limite de volatilité s'applique, le simulateur utilise la même covariance empirique que la vérification
  finale.

## Limites

- **Symétrique** : une hausse brutale augmente la volatilité autant qu'une baisse brutale.
- **Queues** : elle décrit mal les rares très mauvais mois, d'où le recours à la CVaR et à la baisse maximale.
- **Fenêtre** : elle dépend de la période choisie; une période calme donne un chiffre rassurant.
- **Fréquence** : une volatilité tirée de prix quotidiens et une volatilité tirée de rendements mensuels ne se
  comparent pas directement.
- **Devise** : un actif américain n'a pas la même volatilité en dollars américains et en dollars canadiens (voir
  [Risque de change](risque-de-change.md)).

## À ne pas confondre

- **Baisse maximale** : le pire épisode d'un sommet à un creux, pas la variation typique.
- **Risque** : la volatilité n'en mesure qu'une facette; le crédit, la liquidité ou la concentration ne s'y voient pas
  toujours (voir [Types de risque](types-de-risque.md)).
- **Tolérance au risque** : ce que l'investisseur accepte de vivre, et non une propriété du placement (voir
  [Tolérance et capacité](tolerance-et-capacite.md)).
