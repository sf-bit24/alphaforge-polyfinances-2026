---
type: Methodology
title: Les cinq dimensions du profil investisseur
description: Objectif, horizon, risque, contraintes et préférences, et ce qu'un portefeuille existant ne dit pas.
tags: [methodologie, profil-investisseur]
status: stable
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "team:larpathon", at: "2026-11-14T23:30:00Z" }
stale_after: "2027-02-14T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositives 3, 10, 14 et 15"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, sections Personas d'investisseurs (p. 4 à 7) et Encadrement responsable (p. 17)"
data:
  dimensions: [objective, horizon, risk, constraints, preferences]
---

# Les cinq dimensions du profil investisseur

Le portefeuille ne peut pas être séparé de l'investisseur : les mêmes marchés peuvent mener à des propositions
différentes selon le besoin, les limites et le contexte (atelier BNCD, diapositive 10).

| Dimension | Question | Ce qu'elle décrit |
| --- | --- | --- |
| Objectif | Pourquoi investir ? | Coussin de sécurité, projet important, retraite, revenu, patrimoine à transmettre ou croissance du capital. |
| Horizon | Quand l'argent sera-t-il requis ? | Le délai avant un retrait important (voir « Horizon de placement »). |
| Risque | Quelle perte peut être absorbée ? | La volonté de subir des fluctuations (tolérance) et la capacité financière d'en vivre les conséquences (capacité), mesurées séparément. |
| Contraintes | Qu'est-ce qui limite les choix ? | Liquidité, concentration existante, devise, fiscalité et types de comptes, connaissances, besoins particuliers. |
| Préférences | Qu'est-ce qui compte pour la personne ? | Critères ESG, secteurs privilégiés ou exclus, convictions et façon d'investir. |

- **Les contraintes établissent les limites; les préférences orientent les choix à l'intérieur de ces limites**
  (diapositive 10).
- **L'objectif vient avant le produit** : on ne choisit pas un placement sans comprendre ce que l'argent doit permettre
  de faire. Parfois, le bon choix est de ne pas exposer cet argent aux marchés (diapositives 3 et 15).
- Le niveau de connaissances fait partie des contraintes; AlphaForge AI le mesure en premier, car il règle le
  vocabulaire et la précision des explications (voir « Niveaux de connaissances »).

## Ce qu'un portefeuille existant ne dit pas

Un portefeuille montre ce que l'investisseur possède : positions, quantités, valeur, poids relatifs, liquidités,
concentrations apparentes. Il ne suffit pas à expliquer ce dont l'investisseur a besoin : objectif, horizon, capacité
et tolérance au risque, contraintes et préférences, autres comptes et actifs, raisons derrière les positions restent à
établir (diapositive 14).

## Application dans AlphaForge AI

- Les questions de base, déterministes et identiques pour tous, couvrent d'abord le niveau de connaissances, puis les
  cinq dimensions et le contexte (montant à investir), et enfin l'existence d'un portefeuille. Leur contenu est
  versionné dans `questionnaire.yaml`, à relire par le volet finance de l'équipe.
- L'agent A1 relance ensuite sur les champs manquants, sans s'écarter du profil; il ne devine aucune valeur.
- La complétude est la part pondérée des champs requis connus, calculée par le code. Le profil peut servir dès 70 %,
  et la complétude affichée plafonne à 95 % pour garder une part d'incertitude.
- Cadre responsable : profils et portefeuilles fictifs, simulation seulement, aucune transaction réelle ni conseil
  financier personnalisé (énoncé officiel, p. 17).
