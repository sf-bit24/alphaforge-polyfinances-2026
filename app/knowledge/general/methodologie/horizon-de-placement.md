---
type: Methodology
title: Horizon de placement
description: Définition de l'horizon, bandes de moins de 3 ans, 3 à 10 ans et 10 ans et plus, et ce dont il ne se déduit pas.
tags: [methodologie, profil-investisseur, horizon]
status: stable
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "team:larpathon", at: "2026-11-14T23:30:00Z" }
stale_after: "2027-02-14T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositives 7 et 8"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, personas (horizons de 15 ans ou plus, de 8 à 12 ans et de 3 à 5 ans, p. 5 à 7)"
data:
  bands:
    lt3: "moins de 3 ans"
    3to10: "de 3 à 10 ans"
    gt10: "10 ans et plus"
---

# Horizon de placement

L'horizon est le temps avant d'avoir besoin d'une part importante de l'argent investi (atelier BNCD, diapositive 7).

| Bande | Durée | Exemple | Conséquence |
| --- | --- | --- | --- |
| Court | moins de 3 ans | mise de fonds prochaine | peu de temps pour absorber une baisse avant un retrait |
| Moyen | de 3 à 10 ans | projet à moyen terme | plus de flexibilité, mais la date du besoin compte encore |
| Long | 10 ans et plus | retraite lointaine | davantage de temps pour traverser des cycles de marché |

- **Horizon ≠ âge** : deux personnes du même âge peuvent avoir des échéances très différentes.
- **Horizon ≠ tolérance** : aimer le risque ne donne pas plus de temps pour récupérer avant un besoin de liquidités.
- **Un portefeuille peut avoir plusieurs horizons** : urgences, projet, retraite; chaque objectif peut avoir sa propre
  échéance.

## Application dans AlphaForge AI

- La question de base demande la bande d'horizon, sans jamais la déduire de l'âge ni de la tolérance. A1 précise
  ensuite le nombre d'années avant le premier retrait important et la façon de retirer l'argent (en une fois, par
  étapes, en revenu régulier).
- Le code vérifie la cohérence entre la bande et le nombre d'années; une contradiction donne une question de
  clarification plutôt qu'une correction silencieuse.
- L'horizon plafonne la capacité à prendre du risque : moins de 3 ans la limite au niveau « faible à moyen », de 3 à
  10 ans au niveau « moyen à élevé » (voir « Tolérance, capacité et risque effectif »).
