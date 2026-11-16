---
type: Financial Concept
title: Risque de change
description: Comment le taux USD/CAD change le résultat d'un placement étranger, comment AlphaForge AI convertit les rendements, et comment l'expliquer à chaque niveau.
tags: [notion, risque, devise, taux-de-change]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositives 6 (la devise change la comparaison), 8 (risque de devise) et 13 (XSP, couverture CAD)"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, p. 11 (famille de données Devises) et p. 12 (fx_usdcad_daily.csv, Banque du Canada)"
  - id: jeu-de-depart
    title: "Jeu de départ AlphaForge AI : taux de change USD/CAD quotidien"
    resource: "starter:fx_usdcad_daily.csv (Banque du Canada, série FXUSDCAD)"
data:
  aliases: [risque de change, devise, taux de change, dollar américain, USD, couverture, couvert en CAD]
  related: [biais-domestique, fnb, rendement-total, volatilite, types-de-risque]
---

# Risque de change

Le risque de change est la possibilité que le taux de change modifie le résultat d'un placement libellé dans une
autre devise (atelier BNCD, diapositive 8). Pour un investisseur canadien, un placement en dollars américains dépend
de deux choses : le prix du placement et le taux USD/CAD.

## Comment l'expliquer selon le niveau

Les chiffres, les sources et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « Si vous achetez une action américaine, vous achetez aussi des dollars américains. Si le dollar
  américain baisse face au dollar canadien, votre placement vaut moins en dollars canadiens, même si l'action n'a pas
  bougé. »
- **Intermédiaire** : « Le rendement en CAD combine le rendement en USD et la variation du taux USD/CAD. Un FNB
  « couvert en CAD » cherche à retirer cette seconde partie. »
- **Avancé** : « (1 + r_CAD) = (1 + r_USD) × (1 + variation USD/CAD). Le change ajoute sa propre volatilité, mais
  sa corrélation avec les actions peut aussi amortir une baisse vue en CAD. »

## Ce qu'il faut retenir

- Le rendement en CAD n'est pas le rendement en USD : la formule est (1 + r_USD) × (1 + variation USD/CAD) − 1.
  Par exemple, +10 % en USD et −5 % sur le dollar américain donnent 1,10 × 0,95 − 1 = +4,5 % en CAD.
- Le change peut jouer dans les deux sens : un dollar américain qui monte augmente la valeur en CAD.
- Comparer deux placements exige la même devise; la devise fait partie des conditions qui changent une comparaison
  (atelier BNCD, diapositive 6).
- La couverture de change a un coût et retire aussi les gains de change; elle se compare, elle ne s'impose pas.

## Comment AlphaForge AI la calcule

AlphaForge AI fait toutes les conversions selon des règles fixes. Yan les explique; les chiffres sont calculés,
jamais inventés.

- **Simulateur et vérification finale** : les rendements mensuels sont calculés dans la devise du mandat (CAD par
  défaut), donc taux de change compris. Avant le début des données USD/CAD (1971-02), aucun rendement en CAD n'est produit.
- **Lecture de votre portefeuille existant** : quand Yan lit votre portefeuille, une position en USD est convertie en
  CAD au dernier taux publié par la Banque du Canada, avec sa source et sa date. AlphaForge AI en tire l'exposition par
  devise, selon des règles fixes.
- **Signal** : si vous préférez rester en CAD et que plus de 20 % de votre portefeuille existant est en USD,
  AlphaForge AI relève la tension pour que Yan vous l'explique.

## Limites

- **Dernier taux** : la valeur en CAD d'un portefeuille existant utilise un seul taux, celui du dernier jour
  disponible.
- **Couverture** : le simulateur ne modélise pas le mécanisme de couverture; un FNB couvert est traité à partir de ses
  propres rendements.
- **Deux devises** : le simulateur ne gère que le CAD et l'USD.
- **Passé** : les variations passées du taux ne prédisent pas les suivantes.

## À ne pas confondre

- **Biais domestique** : préférer les placements de son pays réduit le risque de change, mais augmente la
  concentration (voir [Biais domestique](biais-domestique.md)).
- **Devise de cotation et exposition** : un FNB coté en CAD peut détenir des actions américaines et rester exposé au
  dollar américain s'il n'est pas couvert (voir [FNB](fnb.md)).
- **Volatilité de l'actif** : celle du change s'y ajoute en CAD, sans s'additionner simplement.
