---
type: Financial Concept
title: Inflation
description: La hausse générale des prix et le rendement réel, ce que AlphaForge AI en montre, ses limites et comment l'expliquer à chaque niveau.
tags: [notion, rendement, inflation, pouvoir-d-achat]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 5 (risque d'inflation d'un CPG), diapositive 6 (l'inflation change la comparaison) et diapositive 8 (risque de taux et d'inflation)"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, p. 12 (macro_rates.csv : IPC du Canada et des États-Unis) et p. 14 (2022, actions et obligations en baisse)"
  - id: fp-canada-nhp-2026
    title: "2026 Projection Assumption Guidelines (FP Canada Standards Council et Institut de planification financière)"
    resource: "https://www.fpcanada.ca/docs/professionalsitelibraries/standards/projection-assumption-guidelines.pdf (section 5, relevé dans rules/canada_2026.yaml, statut verified)"
data:
  aliases: [inflation, pouvoir d'achat, ipc, coût de la vie, rendement réel, indice des prix]
  related: [rendement-total, interets-composes, obligations-et-taux, stress-test-2022, horizon]
---

# Inflation

L'inflation est la hausse générale des prix : avec le même argent, on achète moins. Au Canada, on la suit surtout avec
l'indice des prix à la consommation (IPC). Pour un investisseur, la question n'est pas seulement « combien ai-je
gagné? », mais « qu'est-ce que je peux acheter de plus avec ce que j'ai gagné? ». C'est le rendement réel.

## Comment l'expliquer selon le niveau

Les chiffres, les sources et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « Les prix montent avec le temps. Si votre argent rapporte moins que la hausse des prix, vous pourrez
  en acheter moins plus tard, même si le montant a grandi. »
- **Intermédiaire** : « Le rendement réel est à peu près le rendement moins l'inflation. Un placement qui rapporte
  3 % quand les prix montent de 4 % fait perdre du pouvoir d'achat. »
- **Avancé** : « Rendement réel = (1 + r) / (1 + π) − 1. L'inflation touche aussi les taux : une inflation qui
  surprend fait monter les taux et baisser le prix des obligations, comme en 2022. »

## Ce qu'il faut retenir

- Un rendement nominal positif peut cacher une perte réelle (atelier BNCD, diapositive 6).
- Même un placement « sûr » comme un CPG porte un risque d'inflation : son intérêt est fixé d'avance, pas les prix
  (atelier BNCD, diapositive 5).
- Plus l'horizon est long, plus l'inflation pèse, parce qu'elle se compose comme un rendement (voir
  [Intérêts composés](interets-composes.md)).
- L'inflation est liée aux taux : quand elle surprend à la hausse, les banques centrales relèvent leurs taux, ce qui
  peut faire baisser actions et obligations en même temps (énoncé officiel, p. 14; voir
  [Stress test 2022](stress-test-2022.md)).

## Comment AlphaForge AI l'utilise

- Le jeu de départ fournit l'IPC du Canada (variation sur un an, Banque du Canada) et l'IPC des États-Unis (FRED), dans
  `macro_rates.csv` (énoncé officiel, p. 12).
- A5 recueille aussi ces séries, avec leur date d'observation (le mois de l'IPC) et leur date de publication, pour la
  base générale.
- Le fichier `rules/canada_2026.yaml` reprend l'hypothèse d'inflation à long terme des normes de projection 2026 de
  FP Canada et de l'Institut de planification financière : 2,1 % par année. C'est une hypothèse de planification, pas
  une prévision.
- Les outils de l'application ne calculent pas aujourd'hui de rendement réel : les rendements affichés sont nominaux,
  et l'explication doit le dire.

## Limites

- **Moyenne nationale** : l'IPC mesure un panier moyen; l'inflation vécue par une personne dépend de ses dépenses.
- **Données publiées en retard** : l'IPC d'un mois est publié plusieurs semaines plus tard. Une simulation ne peut
  l'utiliser qu'à partir de sa date de publication.
- **Hypothèse à long terme** : l'inflation future est inconnue; 2,1 % est une hypothèse, pas une garantie.
- **Rendements nominaux** : tant que le rendement réel n'est pas calculé, une comparaison entre placements ne dit pas
  lequel protège le mieux le pouvoir d'achat.

## À ne pas confondre

- **Taux directeur** : le taux fixé par la Banque du Canada pour viser l'inflation; ce n'est pas l'inflation.
- **Rendement nominal** : le rendement affiché, avant inflation.
- **Hausse d'un prix** : un prix qui monte ne fait pas l'inflation; l'inflation est une hausse générale.
