---
type: Financial Concept
title: FNB (fonds négocié en bourse)
description: Ce qu'est un FNB, ce qu'on détient vraiment, comment AlphaForge AI traite les FNB du jeu de départ, et leurs limites.
tags: [notion, instrument, fnb, etf]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 5 (mais qu'achète-t-on vraiment? FINRA, Investor.gov)"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, p. 10 (exemples de FNB d'actions, obligataires et liés à l'or) et p. 11 (données des FNB)"
  - id: politique-risque
    title: "Niveaux de risque d'AlphaForge AI"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml, composition (etf_equity_each_max, etf_bond_each_max, forbidden_all)"
data:
  aliases: [fnb, fonds négocié en bourse, fonds indiciel, etf, exchange-traded fund, fonds coté]
  related: [diversification, frais, expositions-consolidees, obligations-et-taux, concentration]
---

# FNB (fonds négocié en bourse)

Un FNB (*exchange-traded fund*, ETF) est un panier de placements dont on achète des parts en bourse, au prix du marché,
comme une action. Une part donne un petit morceau de tout ce que le fonds contient. Son rendement est celui des actifs
qu'il détient, moins les frais (atelier BNCD, diapositive 5).

## Comment l'expliquer selon le niveau

- **Débutant** : « Au lieu d'acheter une action à la fois, vous achetez une part d'un panier qui en contient beaucoup.
  Le panier monte et baisse avec ce qu'il contient. »
- **Intermédiaire** : « Un FNB réplique souvent un indice. Il se négocie en bourse toute la journée, contrairement à un
  fonds commun racheté à sa valeur liquidative. On regarde ce qu'il détient, ses frais, sa liquidité et l'écart entre
  le prix acheteur et vendeur. »
- **Avancé** : « Véhicule collectif coté; rendement = rendement des actifs sous-jacents − frais − écart de suivi. Son
  risque est celui de son contenu : un FNB sectoriel ou à effet de levier n'a rien d'un panier diversifié. »

## Ce qu'il faut retenir

- Ce qu'on détient, c'est le contenu du panier; le risque est celui de ce contenu (actions, obligations, or, etc.).
- Deux FNB de la même catégorie peuvent fonctionner très différemment (atelier BNCD, diapositive 5).
- Risques à comprendre : les actifs détenus, les frais, la liquidité et l'écart acheteur-vendeur.
- Deux FNB différents peuvent détenir les mêmes sociétés : en ajouter un ne diversifie pas forcément (voir
  [Expositions consolidées](expositions-consolidees.md)).
- Les [frais](frais.md) se retirent chaque année, quel que soit le rendement.

## Comment AlphaForge AI l'utilise

Les chiffres sont calculés selon des règles fixes, jamais inventés; Yan les explique. Le jeu de départ contient
des FNB d'actions, obligataires et liés à l'or (par exemple XIU.TO, SPY, QQQ, XBB.TO, AGG, TLT, GLD), comme les
exemples de l'énoncé (p. 10).

- **Statistiques** : rendement, volatilité et [baisse maximale](baisse-maximale.md) d'un FNB se calculent sur ses prix
  quotidiens ajustés, comme pour une action.
- **Mandat** : le barème plafonne le poids de chaque FNB d'actions et de chaque FNB obligataire, pour qu'un portefeuille
  ne repose pas sur un seul fonds (ce plafond oblige en général à détenir au moins deux FNB d'actions). Les FNB à effet
  de levier et inversés sont exclus.
- **Votre portefeuille existant** : quand Yan lit votre portefeuille, un FNB ou un fonds n'est pas compté comme un
  titre individuel pour le constat de concentration sur une position. Sa présence évite aussi le constat « trop peu de
  positions ».
- **Historique long** : avant leur lancement, certains FNB sont prolongés par un indice proche déclaré (par exemple
  XIU.TO par les actions canadiennes, SPY par le marché américain); ce raccord est une hypothèse.

## Limites

- **Contenu approximé** : AlphaForge AI ne lit pas la liste complète des titres de chaque FNB; la transparence se
  limite à quelques thèmes et à des hypothèses déclarées.
- **Frais et écart de suivi** : les prix ajustés intègrent déjà les frais passés; AlphaForge AI ne ventile pas leur
  effet.
- **Liquidité** : le prix simulé est un prix de clôture, sans écart acheteur-vendeur.
- **Passé seulement** : le comportement passé d'un FNB ne garantit pas son comportement futur.

## À ne pas confondre

- **Fonds commun de placement** : même idée de portefeuille collectif, mais acheté et racheté à la valeur liquidative
  plutôt que négocié en bourse (atelier BNCD, diapositive 5).
- **Diversifié et sectoriel** : un FNB technologique est un panier concentré dans un secteur.
- **Indice et FNB** : l'indice est une mesure; le FNB est le produit qui tente de le suivre, avec des frais.
