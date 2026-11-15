---
type: Financial Concept
title: Stress test 2022
description: Ce qu'un portefeuille aurait perdu en 2022, quand actions et obligations ont baissé ensemble, comment le Judge le contrôle et ses limites.
tags: [notion, risque, stress-test, scenario-historique]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, p. 14 (le jeu de départ inclut 2022, quand actions et obligations ont reculé en même temps)"
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 8 (risque de taux et d'inflation)"
  - id: jeu-de-depart
    title: "Jeu de départ AlphaForge AI : prix quotidiens ajustés"
    resource: "starter:prices_daily.csv (colonne adj_close)"
data:
  aliases: [stress test, test de résistance, scénario 2022, année 2022, pire scénario]
  related: [baisse-maximale, obligations-et-taux, diversification, inflation, var-cvar]
---

# Stress test 2022

Un stress test rejoue un épisode difficile du passé sur un portefeuille d'aujourd'hui : « Avec ces poids, qu'aurais-je
perdu pendant cette crise? » AlphaForge AI utilise surtout l'année civile 2022. Cette année-là, la hausse rapide des
taux a fait reculer les actions **et** les obligations en même temps (énoncé officiel, p. 14) : les obligations n'ont
pas joué leur rôle habituel d'amortisseur.

## Comment l'expliquer selon le niveau

Les chiffres, les sources et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « On regarde ce que ce portefeuille aurait perdu en 2022, une année où presque tout a baissé en même
  temps. C'est un exemple réel de mauvaise année, pas une prédiction. »
- **Intermédiaire** : « Le rendement composé du portefeuille de janvier à décembre 2022, rééquilibré chaque mois. En
  2022, la hausse des taux a fait baisser actions et obligations ensemble, ce qui teste la diversification. »
- **Avancé** : « Perte composée sur 2022-01 → 2022-12, rendements mensuels des tickers réels, en CAD,
  rééquilibrage mensuel. Mesure de contrôle seulement, hors optimisation; corrélation actions-obligations positive
  sur l'épisode. »

## Ce qu'il faut retenir

- Un stress test répond à « et si ça recommençait? », pas à « que va-t-il se passer? ».
- 2022 est utile parce qu'il casse une idée reçue : les obligations ne montent pas toujours quand les actions baissent.
  Quand les taux montent vite, les deux peuvent baisser (atelier BNCD, diapositive 8).
- La perte d'une année civile n'est pas la pire baisse : le creux peut tomber au milieu de l'année (voir
  [Baisse maximale](baisse-maximale.md)).

## Comment AlphaForge AI le calcule

Le code calcule la perte; le modèle ne l'estime jamais.

| Outil | Ce qu'il fait |
| --- | --- |
| `portfolio.loss_2022` (Judge) | Rendement composé de janvier à décembre 2022, sur les tickers réels, rééquilibrage mensuel, en dollars canadiens; renvoie une perte positive (0 si l'année est positive) |
| `portfolio.stress_report` | Rejoue plusieurs épisodes (2022, COVID-19, crise de 2008, bulle technologique, choc pétrolier) : rendement de l'épisode, baisse maximale et perte pour 100 000 $ CAD |

- La règle `risk.stress_2022` est **bloquante** et propre au Judge : l'optimiseur ne la vise pas. Les pertes sont
  des fractions positives (0,145 = −14,5 %), en dollars canadiens, sur des rendements mensuels.
- Chacun des six niveaux de risque (N0 à N5) a son budget `s2022`, fixé dans
  `app/agents/src/alphaforge/finance/policy/risk_levels.yaml`. Il vient de la perte 2022 de portefeuilles de
  référence (actions et obligations du Canada) au haut de la bande d'actions du niveau, arrondie au-dessus.
- Le stress 2022 ne sert pas à choisir le niveau : sur l'historique long, 2022 sépare mal les profils prudents et
  audacieux. Il contrôle seulement le portefeuille proposé.
- Si 2022 n'est pas couvert pour ce portefeuille (moins de 12 mois de données), le Judge ne peut pas vérifier et
  refuse par prudence plutôt que de supposer.

## Limites

- **Un seul scénario** : 2022 est une crise de taux et d'inflation. Il ne dit rien d'une crise de crédit, d'un krach
  boursier rapide ou d'une crise de change.
- **Le passé ne se répète pas à l'identique** : la prochaine crise aura d'autres causes et d'autres gagnants.
- **Données mensuelles** : les variations à l'intérieur d'un mois n'apparaissent pas.
- **Devise** : la perte se mesure en dollars canadiens; le change a pu amortir ou amplifier la baisse d'un actif
  américain par rapport à sa baisse en dollars américains.

## À ne pas confondre

- **Baisse maximale** : la pire chute d'un sommet à un creux, sur toute la fenêtre; le stress test regarde une période
  fixe.
- **VaR et CVaR** : des mesures statistiques sur de nombreux mois (voir [VaR et CVaR](var-cvar.md)); le stress test
  rejoue un épisode réel.
