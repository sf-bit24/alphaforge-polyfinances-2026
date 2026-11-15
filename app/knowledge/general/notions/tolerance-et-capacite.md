---
type: Financial Concept
title: Tolérance et capacité
description: Vouloir ou pouvoir prendre du risque, pourquoi AlphaForge AI retient le plus prudent des deux et comment l'expliquer à chaque niveau.
tags: [notion, risque, tolerance, capacite, profil-investisseur]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 8 (tolérance au risque ≠ capacité à prendre du risque)"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, persona Amira (risque élevé, p. 5) et Encadrement responsable (p. 17)"
  - id: politique-risque
    title: "Niveaux de risque d'AlphaForge AI (risk_levels.yaml v0.2.0)"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml, sections capacity, tolerance, R, biases et status"
data:
  catalog_id: tolerance_capacite
  aliases: [tolérance au risque, capacité de risque, profil de risque, tolérance, capacité]
  related: [horizon, fonds-urgence, baisse-maximale, volatilite]
---

# Tolérance et capacité

La **tolérance** est ce que l'investisseur accepte de vivre comme baisses; la **capacité** est ce qu'il peut se
permettre de perdre sans changer ses projets. Vouloir accepter une baisse ne signifie pas pouvoir en assumer les
conséquences (atelier BNCD, diapositive 8). Les barèmes du questionnaire sont dans
[Tolérance, capacité et risque effectif](../methodologie/tolerance-capacite-risque-effectif.md).

## Comment l'expliquer selon le niveau

- **Débutant** : « Il y a deux questions : est-ce que vous dormiriez bien si votre placement baissait? Et est-ce que
  vos projets tiendraient quand même? On suit la réponse la plus prudente. »
- **Intermédiaire** : « La tolérance vient de vos réactions; la capacité, de votre situation : horizon, revenus,
  fonds d'urgence, dettes. Le risque retenu est le minimum des deux. »
- **Avancé** : « Tolérance déclarée ou testée, pondérée par la confiance; capacité multiplicative sur l'horizon, la
  perte absorbable, le coussin, les retraits, les revenus et la liquidité, puis plafonnée. Le score de risque part du
  minimum. »

## Ce qu'il faut retenir

- Une tolérance élevée ne compense pas une capacité faible; « risque élevé » ne veut pas dire « tout est acceptable »
  (énoncé, persona Amira).
- Ce qu'on fait pendant une vraie baisse en dit plus qu'une déclaration.
- La capacité dépend de l'[horizon](horizon.md), des revenus, du [fonds d'urgence](fonds-urgence.md) et des dettes.

## Comment AlphaForge AI l'utilise

- Le questionnaire calcule tolérance, capacité et risque effectif = min des deux; une réponse manquante laisse le risque
  inconnu plutôt que deviné.
- Le compilateur de mandat (`risk_levels.yaml`) refait ce calcul pour fixer le niveau N0 à N5 : capacité plafonnée par
  un coussin très faible ou une dette coûteuse, tolérance resserrée par les biais détectés (par exemple l'aversion aux
  pertes ajoute une limite de CDaR). Les biais ne peuvent que resserrer, jamais relâcher.
- Un profil incomplet est plafonné au niveau N2; un profil en protection reçoit N0 et un renvoi vers un humain.
- Un écart entre l'attitude déclarée et la réaction à une baisse peut déclencher une vidéo tldoole.

## Limites

- Les paramètres de tolérance ne sont pas calibrés psychométriquement (hypothèse notée dans `risk_levels.yaml`).
- Le calcul décrit un profil fictif; il ne remplace pas l'évaluation de convenance d'un conseiller (énoncé, p. 17).

## À ne pas confondre

- **Tolérance et horizon** : aimer le risque ne donne pas plus de temps pour récupérer.
- **Capacité et richesse** : un gros patrimoine avec un besoin d'argent proche peut avoir peu de capacité.
