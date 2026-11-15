---
type: Financial Concept
title: Fonds d'urgence
description: La réserve d'argent disponible rapidement, pourquoi elle compte dans la capacité de risque, comment AlphaForge AI l'utilise et comment l'expliquer à chaque niveau.
tags: [notion, fonds-urgence, liquidite, capacite, profil-investisseur]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositives 7 (urgences, projet, retraite : plusieurs horizons) et 8 (capacité à absorber une perte)"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, Encadrement responsable (p. 17)"
  - id: regles-canada
    title: "Paramètres canadiens d'AlphaForge AI : protection SADC"
    resource: "app/agents/src/alphaforge/finance/rules/canada_2026.yaml, cdic.coverage_limit_per_category et cdic.insured_categories (vérifiés, 2026, https://www.cdic.ca/your-coverage/whats-covered/)"
  - id: risk-levels
    title: "Niveaux de risque d'AlphaForge AI (risk_levels.yaml v0.2.0)"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml, section capacity (emergency_req_months, hard_caps)"
data:
  catalog_id: fonds_urgence
  aliases: [fonds d'urgence, coussin, réserve d'urgence, imprévu, liquidité]
  related: [tolerance-et-capacite, horizon, baisse-maximale]
---

# Fonds d'urgence

Le fonds d'urgence est une réserve d'argent disponible rapidement pour faire face aux imprévus : perte d'emploi,
réparation, dépense de santé. AlphaForge AI le mesure en **mois de dépenses essentielles** qu'il couvre, hors du
montant à placer. Il fait partie de la capacité à prendre du risque (atelier BNCD, diapositive 8).

## Comment l'expliquer selon le niveau

Les chiffres, les sources et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « C'est l'argent de côté pour les coups durs. Sans lui, une grosse dépense pourrait vous obliger à
  vendre vos placements au pire moment, pendant une baisse. »
- **Intermédiaire** : « Une réserve liquide, exprimée en mois de dépenses, séparée du portefeuille. Plus elle est
  faible, plus une perte de marché risque de devenir une perte réelle. »
- **Avancé** : « Le coussin est une composante de la capacité, rapportée à un nombre de mois requis qui dépend de la
  stabilité des revenus; un coussin très faible plafonne la capacité, quelle que soit la tolérance. »

## Ce qu'il faut retenir

- Le fonds d'urgence a son propre horizon, très court : l'argent doit être disponible tout de suite, pas après une
  remontée des marchés (atelier BNCD, diapositive 7; voir [Horizon](horizon.md)).
- Il protège le reste du placement : il évite de vendre au creux d'une [baisse](baisse-maximale.md).
- Des revenus variables demandent un coussin plus grand que des revenus stables.
- Les dépôts admissibles (comptes d'épargne, CPG) sont protégés par la SADC jusqu'à 100 000 $ par catégorie et par
  institution membre; les actions, obligations, FNB et cryptoactifs ne le sont pas (`canada_2026.yaml`, vérifié en
  2026).

## Comment AlphaForge AI l'utilise

- **Questionnaire** : la question « Votre fonds d'urgence couvre combien de mois de dépenses essentielles? » alimente
  le score de capacité; moins de mois donne moins de points (voir
  [Tolérance, capacité et risque effectif](../methodologie/tolerance-capacite-risque-effectif.md)).
- **Mandat** : le compilateur compare les mois déclarés aux mois requis selon la stabilité des revenus, plus exigeants
  après 55 ans ou à la retraite. Un coussin de moins d'un mois plafonne la capacité; une réponse manquante est traitée
  comme aucune réserve, par prudence (`risk_levels.yaml`, section `capacity`).
- Un coussin insuffisant donne plus de poids à la lentille « risque » de l'explication, sans changer les limites.
- Un coussin de moins de trois mois peut déclencher une vidéo tldoole sur le fonds d'urgence.

## Limites

- Le montant est déclaré par l'investisseur; AlphaForge AI ne le vérifie pas.
- Le nombre de mois requis est un paramètre de simulation, à relire par le volet finance; ce n'est pas une règle
  universelle.
- AlphaForge AI ne dit pas où placer ce fonds : simulation seulement, sans conseil personnalisé (énoncé, p. 17).

## À ne pas confondre

- **Fonds d'urgence et épargne de projet** : un projet a une date connue; l'urgence, non.
- **Fonds d'urgence et encaisse du portefeuille** : l'encaisse détenue dans le portefeuille sert l'allocation; le
  coussin reste hors du montant placé.
