---
type: Methodology
title: Niveaux de connaissances
description: Comment AlphaForge AI établit le niveau débutant, intermédiaire ou avancé, et ce qu'il change dans les explications.
tags: [methodologie, profil-investisseur, explicabilite]
status: stable
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "team:larpathon", at: "2026-11-14T23:30:00Z" }
stale_after: "2027-02-14T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 10 (les connaissances parmi les contraintes) et diapositive 12 (les quatre questions d'une explication crédible)"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, personas (expérience en investissement intermédiaire ou avancée, p. 5 à 7) et Encadrement responsable (p. 17)"
data:
  levels: [beginner, intermediate, advanced]
  rule: "min(auto-évaluation, niveau mesuré + 1 cran)"
  questionnaire_version: "2026-11-14.1"
---

# Niveaux de connaissances

Le niveau de connaissances fait partie des contraintes de l'investisseur (atelier BNCD, diapositive 10). AlphaForge AI
l'établit en premier, avant les cinq dimensions du profil, parce qu'il règle la façon d'expliquer.

## Mesure

Quatre questions rapides, notées selon des règles fixes :

1. la fréquence des placements au cours des trois dernières années (0 à 3 points);
2. la fréquence du suivi de l'actualité financière ou économique (0 à 3 points);
3. les produits connus assez bien pour en expliquer le fonctionnement (0 produit de base : 0 point; 1 ou 2 : 1 point;
   3 ou 4 : 2 points; 3 ou plus et un produit avancé, comme les options : 3 points);
4. une auto-évaluation : débutant, intermédiaire ou avancé.

Le niveau mesuré est débutant de 0 à 2 points, intermédiaire de 3 à 5, avancé de 6 à 9. Le niveau retenu est
**min(auto-évaluation, niveau mesuré + 1 cran)** : l'auto-évaluation peut dépasser le niveau mesuré d'un cran au plus,
et une auto-évaluation plus modeste est respectée. L'investisseur peut changer son niveau dans les réglages; ce choix
remplace alors le calcul.

## Ce que le niveau change, et ce qu'il ne change pas

- **Change** : le vocabulaire et la précision. Débutant : mots de tous les jours, une idée par phrase, tout terme
  financier défini simplement. Intermédiaire : termes courants brièvement expliqués. Avancé : vocabulaire précis et
  concis.
- **Ne change pas** : les faits, les chiffres, les sources ni les limites. Les chiffres sont calculés, jamais
  inventés, et citent leur source.
- Une explication crédible répond aux mêmes quatre questions à tous les niveaux : quelles données, pourquoi ce choix,
  quelles limites, qu'est-ce qui changerait la réponse (atelier BNCD, diapositive 12).
- Quel que soit le niveau, AlphaForge AI reste une simulation et ne donne aucun conseil financier personnalisé
  (énoncé officiel, p. 17).
