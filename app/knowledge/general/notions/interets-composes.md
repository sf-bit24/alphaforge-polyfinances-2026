---
type: Financial Concept
title: Intérêts composés
description: Des gains qui produisent à leur tour des gains, comment AlphaForge AI l'illustre, ses limites et comment l'expliquer à chaque niveau.
tags: [notion, rendement, interets-composes, horizon]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 6 (période, frais, distributions réinvesties) et diapositive 7 (le temps disponible change la décision)"
  - id: atelier-aws
    title: "Atelier AWS : aide-mémoire, pièges classiques des données financières"
    resource: "Atelier AWS du Datathon PolyFinances 2026, section 3 (rendement passé)"
data:
  catalog_id: interets_composes
  aliases: [intérêts composés, composition, boule de neige, intérêt sur intérêt, effet composé]
  related: [rendement-total, frais, horizon, inflation, fonds-urgence]
---

# Intérêts composés

Les intérêts composés, ce sont des gains qui produisent à leur tour des gains. Quand les intérêts, dividendes ou gains
restent investis, le rendement de l'année suivante s'applique au montant de départ **et** aux gains déjà accumulés. La
croissance n'est donc pas une ligne droite : elle s'accélère avec le temps.

## Comment l'expliquer selon le niveau

Les chiffres, les sources et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « C'est l'effet boule de neige : vos gains restent placés et rapportent eux aussi. Plus vous laissez
  le temps faire, plus la boule grossit. »
- **Intermédiaire** : « Le rendement s'applique chaque année à un montant qui a déjà grandi. Sur une longue période,
  les gains sur les gains finissent par dépasser les gains sur le montant de départ. »
- **Avancé** : « Valeur finale = V₀ × (1 + r)ⁿ, plus la valeur capitalisée des versements. Un écart de taux, de frais
  ou de durée se compose aussi; le rendement annualisé géométrique tient compte de cet effet. »

## Ce qu'il faut retenir

- Le temps est le moteur principal : plus l'horizon est long, plus l'effet est fort (atelier BNCD, diapositive 7).
- Un exemple d'arithmétique : 1 000 $ à 5 % par année donnent 1 050 $ après un an, mais environ 1 629 $ après dix ans,
  et non 1 500 $. Les 129 $ d'écart sont des gains sur des gains.
- La composition joue dans les deux sens. Les frais se composent aussi et réduisent l'écart chaque année (voir
  [Frais](frais.md)). Une dette à intérêt élevé, comme un solde de carte de crédit, grossit de la même façon.
- Pour que l'effet joue, les revenus doivent rester investis : un rendement « distributions réinvesties » et un
  rendement « distributions retirées » ne se comparent pas (atelier BNCD, diapositive 6).

## Comment AlphaForge AI l'illustre

Le code fait le calcul; le modèle ne l'estime jamais.

- L'outil `compound_growth` des faits tldoole simule un montant initial et des versements mensuels à un taux annuel
  constant, converti en taux mensuel équivalent, sur 1 à 50 ans. Il renvoie la valeur finale, le total versé et la
  croissance, avec une courbe.
- Chaque résultat porte son hypothèse en clair : « rendement constant, sans frais ni impôt : une illustration, pas une
  prévision ». Le taux est un paramètre choisi, pas un rendement attendu.
- Les rendements historiques calculés à partir de `adj_close` (dividendes réinvestis) intègrent déjà l'effet composé
  (voir [Rendement total](rendement-total.md)).

## Limites

- **Taux constant** : un vrai placement ne rapporte jamais le même taux chaque année. La volatilité et les baisses
  changent le parcours, et une perte en début de période pèse plus longtemps.
- **Sans frais ni impôt** : l'illustration les ignore; un vrai résultat serait plus bas.
- **Nominal** : la valeur finale est en dollars futurs; l'inflation en réduit le pouvoir d'achat (voir
  [Inflation](inflation.md)).
- **Hypothèse, pas promesse** : le rendement passé ne garantit pas le rendement futur (atelier AWS, section 3).

## À ne pas confondre

- **Intérêt simple** : l'intérêt ne s'applique qu'au montant de départ; il croît en ligne droite.
- **Rendement moyen arithmétique** : la moyenne simple des rendements annuels surestime la croissance réelle quand les
  rendements varient; le rendement géométrique est celui qui compose.
- **Rendement total** : le résultat mesuré sur une période passée; les intérêts composés décrivent le mécanisme.
