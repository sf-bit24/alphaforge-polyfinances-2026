---
type: Financial Concept
title: Rééquilibrage
description: Ramener un portefeuille à ses poids cibles, pourquoi il dérive, comment AlphaForge AI le simule, et ses coûts et limites.
tags: [notion, portefeuille, reequilibrage, rebalancing]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 9 (diversifier sur plusieurs dimensions) et diapositive 15 (idée 02 : rendement, risque et horizon sont indissociables)"
  - id: politique-risque
    title: "Niveaux de risque d'AlphaForge AI (risk_levels.yaml v0.2.0)"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml, reference_portfolios et measurement (séries rééquilibrées chaque mois)"
data:
  aliases: [rééquilibrage, rééquilibrer, rebalancing, rebalancement, dérive des poids, revenir à la cible]
  related: [diversification, frais, volatilite, expositions-consolidees, baisse-maximale]
---

# Rééquilibrage

Rééquilibrer, c'est vendre une partie de ce qui a pris du poids et racheter ce qui en a perdu, pour ramener le
portefeuille à sa répartition cible. Sans rééquilibrage, les poids dérivent avec les marchés : la part qui monte le
plus grossit, et le portefeuille devient plus risqué ou plus concentré que prévu.

## Comment l'expliquer selon le niveau

- **Débutant** : « Vous aviez décidé moitié actions, moitié obligations. Si les actions montent beaucoup, elles
  prennent plus de place que prévu. Rééquilibrer, c'est revenir à votre moitié-moitié. »
- **Intermédiaire** : « On rééquilibre selon un calendrier (chaque mois, trimestre ou année) ou quand un poids
  s'écarte trop de sa cible. Chaque échange a un coût, et il peut avoir un effet fiscal hors des comptes enregistrés. »
- **Avancé** : « Entre deux décisions, le poids d'un actif suit wᵢ × (1 + rᵢ) / (1 + r_p). La rotation mesure la part
  échangée; la fréquence arbitre entre l'écart à la cible et les coûts de transaction. »

## Ce qu'il faut retenir

- Le rééquilibrage maintient le niveau de risque choisi; il ne cherche pas à prévoir le marché.
- Il conduit à vendre ce qui a monté et à acheter ce qui a baissé, ce qui peut sembler contre-intuitif.
- Une répartition n'a de sens qu'avec le risque et l'horizon qui l'ont justifiée (atelier BNCD, diapositive 15, idée
  02); laisser les poids dériver change ce risque sans décision.
- Plus on rééquilibre souvent, plus on paie de frais d'opération.

## Comment AlphaForge AI le simule

Le code simule; le modèle explique. Aucune transaction réelle n'est passée.

- **Mesures de risque** : les rendements d'un portefeuille proposé sont calculés comme s'il était ramené à ses poids
  **chaque mois** (`portfolio_returns`). C'est le cas des mesures du Judge, du stress test 2022 et des portefeuilles de
  référence qui calibrent les niveaux de risque (`risk_levels.yaml`).
- **Moteur de backtest** : il simule aussi un rééquilibrage mensuel, trimestriel, annuel, jamais, ou par bandes (on
  n'échange que si un poids s'écarte de la cible de plus que la bande, 5 points par défaut). Entre deux décisions, les
  poids dérivent avec les rendements. Il compte la rotation (moitié de la somme des écarts de poids) et retire un coût
  proportionnel aux échanges quand un coût en points de base est fourni.
- **Optimiseur** : face à un portefeuille existant, il compte la rotation nécessaire, y compris la vente forcée des
  titres hors de l'univers, peut la plafonner (`max_turnover`) et la pénaliser par un coût de transaction (zéro par
  défaut).

## Limites

- **Rééquilibrage mensuel supposé** : les mesures de risque supposent un rééquilibrage chaque mois, sans coût par
  défaut. Un investisseur qui ne rééquilibre jamais aura un risque différent.
- **Fiscalité** : la simulation ne calcule pas l'impôt sur les gains réalisés en vendant dans un compte non enregistré.
- **Coûts simplifiés** : le coût est proportionnel aux échanges; il ne modélise ni l'écart acheteur-vendeur réel ni
  les montants minimaux.
- **Passé seulement** : l'avantage d'une fréquence sur une autre dépend de la période simulée.

## À ne pas confondre

- **Changer de stratégie** : rééquilibrer revient à la même cible; modifier la cible est une autre décision, liée au
  profil.
- **Anticiper le marché** : vendre parce qu'on craint une baisse n'est pas un rééquilibrage.
- **[Diversification](diversification.md)** : elle fixe la répartition; le rééquilibrage la maintient.
