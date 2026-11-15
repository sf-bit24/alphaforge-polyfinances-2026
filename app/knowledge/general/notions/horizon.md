---
type: Financial Concept
title: Horizon
description: Le temps avant d'avoir besoin de l'argent, pourquoi il limite le risque possible et comment l'expliquer à chaque niveau.
tags: [notion, horizon, profil-investisseur]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 7 (le temps disponible change la décision)"
  - id: risk-levels
    title: "Niveaux de risque d'AlphaForge AI (risk_levels.yaml v0.2.0)"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml, sections horizon_cap, capacity et satellites.rules"
data:
  catalog_id: horizon
  aliases: [horizon, horizon de placement, long terme, court terme, moyen terme]
  related: [tolerance-et-capacite, baisse-maximale, fonds-urgence, volatilite]
---

# Horizon

L'horizon est le temps avant d'avoir besoin d'une part importante de l'argent investi (atelier BNCD, diapositive 7).
Les bandes utilisées par AlphaForge AI et la façon de les demander sont dans
[Horizon de placement](../methodologie/horizon-de-placement.md).

## Comment l'expliquer selon le niveau

- **Débutant** : « Quand aurez-vous besoin de cet argent? Plus c'est loin, plus vous avez de temps pour attendre que
  les placements remontent après une baisse. »
- **Intermédiaire** : « L'horizon, c'est la date du premier retrait important. Il fixe le temps disponible pour
  traverser une baisse, donc la part de placements volatils qu'on peut raisonnablement envisager. »
- **Avancé** : « L'horizon borne le niveau de risque : plus la durée est courte, plus la probabilité de finir en perte
  nominale est élevée pour une même part d'actions; le plafond d'horizon en découle. »

## Ce qu'il faut retenir

- L'horizon n'est ni l'âge ni le goût du risque : aimer le risque ne donne pas plus de temps pour récupérer.
- Un même investisseur peut avoir plusieurs horizons : urgences, projet, retraite. Chaque objectif a son échéance.
- Une baisse se vit mal surtout quand il faut vendre pendant le creux (voir [Baisse maximale](baisse-maximale.md)).

## Comment AlphaForge AI l'utilise

- L'horizon est demandé, jamais déduit de l'âge.
- Il plafonne la capacité à prendre du risque (voir [Tolérance et capacité](tolerance-et-capacite.md)).
- Le compilateur de mandat retient le nombre d'années avant le premier retrait de la poche de risque. Plus cette durée
  est courte, plus le niveau de risque maximal est bas (`horizon_cap` dans `risk_levels.yaml`). Un retrait récurrent
  proche crée en plus une réserve prudente.
- Un horizon court combiné à une attitude très ouverte au risque peut déclencher une vidéo tldoole.

## Limites

- Un horizon déclaré peut changer : un imprévu peut rapprocher la date du besoin.
- Un long horizon ne garantit pas une récupération; il en augmente seulement les chances, selon le passé.

## À ne pas confondre

- **Horizon et âge** : deux personnes du même âge peuvent avoir des échéances très différentes.
- **Horizon et tolérance** : l'un mesure le temps disponible, l'autre ce qu'on accepte de vivre.
