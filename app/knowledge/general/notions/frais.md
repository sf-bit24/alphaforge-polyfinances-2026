---
type: Financial Concept
title: Frais
description: RFG, frais d'opération et frais de conseil, comment ils se composent, ce que AlphaForge AI en calcule, ses limites et comment l'expliquer à chaque niveau.
tags: [notion, rendement, frais, rfg]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 5 (fonds commun et FNB : rendement des actifs moins les frais) et diapositive 6 (les frais changent la comparaison)"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, p. 11 (données des FNB, dont les frais) et p. 12 (champs de assets_universe.csv)"
  - id: fp-canada-nhp-2026
    title: "2026 Projection Assumption Guidelines (FP Canada Standards Council et Institut de planification financière)"
    resource: "https://www.fpcanada.ca/docs/professionalsitelibraries/standards/projection-assumption-guidelines.pdf (section 5 : hypothèses brutes de frais, relevé dans rules/canada_2026.yaml, statut verified)"
data:
  aliases: [frais, rfg, frais de gestion, ratio des frais de gestion, commission, frais de courtage, mer]
  related: [fnb, interets-composes, rendement-total, reequilibrage]
---

# Frais

Les frais sont ce que coûte un placement, en plus de son prix. Pour un fonds commun ou un FNB, ils sont résumés par le
**ratio des frais de gestion (RFG)** : un pourcentage de la valeur investie, prélevé chaque année dans le fonds.
S'y ajoutent, selon le cas, les frais d'opération (commission, écart entre prix acheteur et vendeur) et les frais de
conseil. Le rendement d'un fonds est le rendement de ses actifs **moins** ses frais (atelier BNCD, diapositive 5).

## Comment l'expliquer selon le niveau

Les chiffres, les sources et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « Chaque année, le fonds garde un petit pourcentage de votre argent pour se payer. Ça paraît peu,
  mais ça se répète chaque année, et l'écart grossit avec le temps. »
- **Intermédiaire** : « Le RFG est retiré chaque année de la valeur du fonds; il est déjà inclus dans son rendement
  affiché. À rendement égal des actifs, un fonds à 2 % de frais et un fonds à 0,2 % finissent très loin l'un de
  l'autre après vingt ans. »
- **Avancé** : « Valeur ≈ V₀ × (1 + r − f)ⁿ : les frais réduisent le taux composé, pas seulement le résultat d'une
  année. S'y ajoutent les coûts de rotation (commissions, écart acheteur-vendeur) proportionnels au volume échangé. »

## Ce qu'il faut retenir

- Les frais se composent : ils réduisent le rendement chaque année, et l'écart s'accumule (voir
  [Intérêts composés](interets-composes.md)).
- Deux fonds semblables peuvent avoir des frais très différents; c'est l'un des rares éléments connus d'avance.
- Comparer des rendements exige des frais comparables : avant ou après frais, avec ou sans conseil (atelier BNCD,
  diapositive 6).
- Échanger souvent coûte aussi : chaque achat et chaque vente paie un écart et parfois une commission.

## Comment AlphaForge AI les calcule

Le code fait le calcul; le modèle ne l'estime jamais.

- Les rendements historiques viennent de `adj_close`. Pour un FNB, le RFG est déjà prélevé dans la valeur du fonds :
  ses rendements passés sont donc nets de ses frais de gestion.
- L'optimiseur peut compter des frais d'opération sur la rotation, avec `transaction_cost_bps` (zéro par défaut) et un
  plafond de rotation `max_turnover`. Les titres vendus parce qu'ils sortent de l'univers comptent dans la rotation.

## Limites

- **RFG inconnus** : le jeu de départ ne contient pas le RFG de ses FNB (énoncé officiel, p. 12). Les frais propres à
  chaque fonds ne sont donc pas comparés par l'application.
- **Frais de conseil et de courtage** : ils ne sont pas dans les prix; les rendements historiques ne les déduisent
  pas. Les hypothèses de projection de FP Canada sont aussi brutes de frais : il faut les retirer soi-même.
- **Frais d'opération à zéro par défaut** : sans paramètre explicite, la rotation d'un portefeuille paraît gratuite.

## À ne pas confondre

- **RFG** : frais annuels du fonds, déjà dans son rendement.
- **Commission et écart acheteur-vendeur** : coûts payés à chaque opération.
- **Frais de conseil** : rémunération d'un conseiller, en plus du RFG.
- **Impôt** : ce n'est pas un frais du placement, mais il réduit aussi le rendement net.
