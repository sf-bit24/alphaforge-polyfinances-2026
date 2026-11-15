---
type: Financial Concept
title: Diversification
description: Varier les expositions qui réagissent différemment, le rôle de la corrélation, comment AlphaForge AI la mesure et ses limites.
tags: [notion, diversification, correlation, portefeuille]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 9 (diversifier, c'est multiplier les sources de rendement et de risque) et diapositive 15 (idée 03)"
  - id: politique-risque
    title: "Niveaux de risque d'AlphaForge AI (risk_levels.yaml v0.2.0)"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml, sections 6 (composition) et 8 (limits_template)"
data:
  aliases: [diversification, diversifier, correlation, corrélation, tous mes oeufs dans le même panier]
  related: [concentration, expositions-consolidees, biais-domestique, fnb, volatilite, reequilibrage]
---

# Diversification

Diversifier, c'est répartir un portefeuille entre des expositions qui peuvent réagir différemment aux mêmes événements,
pas seulement posséder plus de titres (atelier BNCD, diapositive 9). Le principe qui la sous-tend est la corrélation :
deux placements qui ne bougent pas exactement ensemble réduisent la dépendance à un seul scénario.

## Comment l'expliquer selon le niveau

- **Débutant** : « Ne pas mettre tous ses œufs dans le même panier. Mais dix paniers posés sur la même table tombent
  ensemble : il faut des paniers qui ne dépendent pas des mêmes choses. »
- **Intermédiaire** : « On varie les classes d'actifs, les régions, les secteurs et les sources de risque. Dix actions
  technologiques dépendent souvent des mêmes moteurs : ce n'est pas une vraie diversification. »
- **Avancé** : « La réduction de risque vient des corrélations imparfaites entre expositions. On la lit avec le
  nombre effectif de positions, le ratio de diversification et les grappes de corrélation, pas avec le nombre de
  lignes. »

## Ce qu'il faut retenir

- On peut diversifier sur plusieurs dimensions : classes d'actifs, géographie, secteurs, style ou facteurs,
  instruments et sources de risque (taux, devise, crédit, inflation, liquidité) (atelier BNCD, diapositive 9).
- La corrélation n'est pas constante. L'or a parfois évolué dans un sens différent des actions en période de stress,
  mais pas toujours (atelier BNCD, diapositive 9).
- Diversifier réduit la dépendance à un scénario; cela n'élimine ni le risque de marché ni les pertes.
- Le nombre de titres compte moins que les secteurs, régions, actifs et facteurs qui les influencent (atelier BNCD,
  diapositive 15, idée 03).

## Comment AlphaForge AI la mesure

Le code calcule; le modèle explique. L'outil `portfolio.diversification_report` rend, à partir des rendements mensuels
de la fenêtre étudiée :

- le **nombre effectif de positions** selon les poids, 1 / Σ w², et selon les parts de risque;
- le **ratio de diversification**, la somme des volatilités pondérées divisée par la volatilité du portefeuille (plus
  il dépasse 1, plus les corrélations imparfaites réduisent le risque);
- des **grappes** d'actifs fortement corrélés, avec leur poids et leur corrélation moyenne (seuil par défaut 0,7).

Le compilateur de mandat ajoute des limites de composition pour éviter qu'un portefeuille repose sur un seul fonds :
plafond par FNB d'actions et par FNB obligataire, plafonds des titres individuels, et plafond d'exposition technologique
mesuré par transparence (voir [Expositions consolidées](expositions-consolidees.md)). Les formules sont dans
`risk_levels.yaml`, sections 6 et 8; ce sont des hypothèses de construction. Le Judge refuse une proposition qui dépasse
un plafond bloquant.

Pour un portefeuille existant, le code signale `few_holdings` quand il y a moins de cinq positions évaluées hors
encaisse et aucun FNB ni fonds (seuil à relire par le volet finance).

## Limites

- **Passé seulement** : corrélations et volatilités viennent de l'historique et peuvent changer, souvent à la hausse
  en crise, au moment où la diversification compterait le plus.
- **Fenêtre** : les mesures dépendent de la période et de la fréquence mensuelle retenues.
- **Transparence partielle** : le contenu réel des FNB n'est connu que pour certains thèmes; ailleurs, le code s'appuie
  sur des hypothèses déclarées.

## À ne pas confondre

- **Nombre de lignes** : posséder vingt titres du même secteur reste une [concentration](concentration.md).
- **Diversification et rendement** : diversifier ne vise pas le meilleur rendement passé; il vise à ne pas dépendre
  d'un seul scénario.
- **Corrélation et causalité** : deux actifs corrélés ne s'influencent pas forcément; ils peuvent dépendre d'un même
  moteur.
