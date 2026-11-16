---
type: Financial Concept
title: Biais domestique
description: Investir surtout dans son propre pays, ce qu'AlphaForge AI repère dans un portefeuille existant, et les limites de ce constat.
tags: [notion, diversification, biais-domestique, geographie]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 9 (dimensions de la diversification) et diapositive 13 (que m'apporterait XSP?)"
  - id: jeu-de-depart
    title: "Jeu de départ AlphaForge AI : univers d'actifs et prix quotidiens"
    resource: "starter:assets_universe.csv et starter:prices_daily.csv"
data:
  aliases: [biais domestique, trop canadien, seulement canadien, home bias, portefeuille canadien]
  related: [diversification, risque-de-change, concentration, expositions-consolidees, fnb]
---

# Biais domestique

Le biais domestique (*home bias*) est la tendance à investir surtout dans son propre pays. Pour un investisseur
canadien, c'est un portefeuille composé en grande partie d'actions et de fonds canadiens. Ce n'est pas une erreur en
soi : c'est une concentration géographique qu'il faut voir et comprendre.

## Comment l'expliquer selon le niveau

- **Débutant** : « Votre argent dépend surtout de l'économie d'un seul pays. Si ce pays traverse une mauvaise période,
  presque tout votre portefeuille la traverse avec lui. »
- **Intermédiaire** : « La bourse canadienne pèse lourd dans quelques secteurs, comme la finance et l'énergie. Un
  portefeuille très canadien hérite de ces concentrations. Ajouter d'autres régions multiplie les sources de rendement
  et de risque, avec un risque de change en plus. »
- **Avancé** : « Concentration géographique et sectorielle par construction de l'indice local. À juger avec la devise
  des dépenses futures, le chevauchement entre fonds et les corrélations, plutôt que contre une pondération mondiale
  théorique. »

## Ce qu'il faut retenir

- Une décision commence par « qu'est-ce que j'essaie d'améliorer? », pas par « qu'est-ce que j'achète? ». L'exemple de
  l'atelier : un portefeuille très canadien se demande si un FNB du S&P 500 améliorerait sa diversification, en
  regardant le chevauchement avec ses autres fonds et l'effet sur la concentration géographique (atelier BNCD,
  diapositive 13).
- La géographie est une des dimensions de la diversification, à côté des classes d'actifs et des secteurs (atelier
  BNCD, diapositive 9).
- Investir hors du Canada ajoute un [risque de change](risque-de-change.md) : la valeur en dollars canadiens dépend
  aussi du taux de change.
- Il y a des raisons de garder une part locale, par exemple des dépenses futures en dollars canadiens. Le constat
  ouvre une explication; il ne dicte pas une répartition.

## Comment AlphaForge AI le repère

Quand Yan lit votre portefeuille existant, AlphaForge AI l'analyse selon des règles fixes. Yan explique; les chiffres
sont calculés, jamais inventés. Le constat de biais domestique apparaît quand au moins 60 % de la valeur hors encaisse
est cotée à la Bourse de Toronto ou libellée en dollars canadiens. Les prix viennent du jeu de départ ou de Yahoo
Finance, et les positions en dollars américains sont converties au dernier taux USD/CAD du jeu de départ.

Pour un portefeuille proposé, le barème ne pose pas de plafond géographique. Ses portefeuilles de référence, qui servent
à calibrer les niveaux de risque, répartissent le plus souvent la part actions à parts égales entre le Canada et les
États-Unis.

## Limites

- **Cotation, pas contenu** : le constat regarde où une position est cotée et sa devise, pas ce qu'elle détient. Un FNB
  coté à Toronto qui détient des actions américaines compte comme canadien. Il faut le lire avec les
  [expositions consolidées](expositions-consolidees.md).
- **Positions évaluées seulement** : une ligne sans prix n'entre pas dans le calcul, et AlphaForge AI le signale.
- **Un seul compte** : le portefeuille saisi ne montre pas les autres comptes ou actifs de l'investisseur (atelier BNCD,
  diapositive 14).

## À ne pas confondre

- **Risque de change** : il apparaît en sortant du pays; ce n'est pas le biais lui-même.
- **Concentration sectorielle** : un portefeuille mondial peut aussi être concentré dans un secteur.
- **Préférence assumée** : vouloir rester au Canada est une préférence légitime, à expliquer avec ses conséquences.
