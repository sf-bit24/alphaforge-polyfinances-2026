---
type: Methodology
title: Tolérance, capacité et risque effectif
description: Pourquoi la tolérance au risque et la capacité à prendre du risque sont mesurées séparément, et comment le code en tire le risque effectif.
tags: [methodologie, profil-investisseur, risque]
status: stable
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "team:larpathon", at: "2026-11-14T23:30:00Z" }
stale_after: "2027-02-14T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositives 7, 8 et 10"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, persona Amira (« risque élevé ne veut pas dire tout est acceptable », p. 5) et section Performance historique et risque (p. 18)"
data:
  rule: "effective_risk = min(tolerance, capacity)"
  scale: [low, low_medium, medium, medium_high, high]
  questionnaire_version: "2026-11-14.1"
---

# Tolérance, capacité et risque effectif

**Tolérance au risque ≠ capacité à prendre du risque** : vouloir accepter une baisse ne signifie pas pouvoir se
permettre ses conséquences (atelier BNCD, diapositive 8).

- **Tolérance** : la volonté de subir des fluctuations. Une simple déclaration peut la surestimer; la réaction à une
  baisse, réelle ou imaginée, en dit davantage.
- **Capacité** : la capacité financière à vivre les conséquences d'une perte sans changer ses projets. Elle dépend du
  coussin d'urgence, de la stabilité des revenus, de l'effet d'une perte sur les projets, de l'horizon et des besoins
  de liquidité.
- **Risque effectif** : le minimum des deux. Une tolérance élevée ne compense pas une capacité faible, et « risque
  élevé » ne veut pas dire « tout est acceptable » (énoncé officiel, persona Amira).

## Règle appliquée par le code

Les barèmes sont dans `questionnaire.yaml` (version 2026-11-14.1), à relire par le volet finance de l'équipe. L'échelle
compte cinq niveaux : faible, faible à moyen, moyen, moyen à élevé, élevé (0 à 4).

1. **Tolérance** = partie entière de la moyenne des points de la réaction à une baisse de 20 % (tout vendre 0,
   vendre une partie 1, ne rien changer 3, investir davantage 4) et de l'attitude face aux variations (éviter les
   baisses 0, petites 1, moyennes 2, fortes 4). Le comportement lors d'une baisse réelle s'y ajoute quand A1 l'a
   appris et que l'investisseur l'a vécue (a vendu 0, a conservé 3, a investi davantage 4).
2. **Capacité** = partie entière de la moyenne de trois composantes : fonds d'urgence (0 mois 0, moins de 3 mois 1,
   de 3 à moins de 6 mois 3, 6 mois et plus 4), stabilité des revenus (très stables 4, plutôt stables 3, variables 1,
   aucun revenu régulier 0) et effet d'une perte du quart du placement (changer des projets importants 0, quelques
   ajustements 2, aucun effet 4). Elle est ensuite plafonnée : horizon de moins de 3 ans à 1, de 3 à 10 ans à 3;
   retrait d'une petite partie sous 12 mois à 3, d'une part importante à 1; effet majeur d'une perte à 1; dette à
   taux élevé à 2.
3. **Risque effectif** = min(tolérance, capacité). Si une composante requise manque, le risque effectif reste
   inconnu : le code ne devine aucune valeur.

## Limites

- La volatilité n'est qu'un indicateur de risque parmi d'autres; l'horizon, la diversification et les préférences
  comptent aussi (énoncé officiel, p. 18).
- Le barème décrit un profil fictif pour une simulation; il ne remplace pas l'évaluation de convenance d'un conseiller.
