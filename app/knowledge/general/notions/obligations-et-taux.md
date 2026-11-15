---
type: Financial Concept
title: Obligations et taux d'intérêt
description: Ce qu'est une obligation, pourquoi son prix baisse quand les taux montent, comment AlphaForge AI traite les FNB obligataires, et ses limites.
tags: [notion, instrument, obligations, taux, duree]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 5 (obligation : intérêts + variation du prix; taux, crédit, liquidité) et diapositive 8 (obligation qui baisse lorsque les taux montent)"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, p. 10 (FNB obligataires) et p. 11 (obligations et taux : sensibilité aux taux, rôle des actifs défensifs)"
  - id: politique-risque
    title: "Niveaux de risque d'AlphaForge AI (risk_levels.yaml v0.2.0)"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml, composition (long_duration_max, etf_bond_each_max), history_proxies et reference_portfolios"
data:
  aliases: [obligation, obligations, taux d'intérêt, taux directeur, rendement obligataire, cpg, bond, durée]
  related: [inflation, types-de-risque, stress-test-2022, fnb, diversification, horizon]
---

# Obligations et taux d'intérêt

Une obligation est un titre de dette : on prête à un gouvernement ou à une société, qui verse des intérêts puis
rembourse le capital à l'échéance. Son rendement vient des intérêts et de la variation de son prix (atelier BNCD,
diapositive 5). Ce prix varie surtout avec les taux d'intérêt du marché.

## Comment l'expliquer selon le niveau

- **Débutant** : « Vous prêtez de l'argent et on vous paie des intérêts. Si de nouveaux prêts paient plus d'intérêts
  que le vôtre, le vôtre vaut moins pour quelqu'un qui voudrait vous l'acheter. »
- **Intermédiaire** : « Quand les taux montent, le prix des obligations déjà émises baisse, et inversement. Plus
  l'échéance est longue, plus le prix réagit. Il faut aussi regarder le crédit : l'émetteur peut ne pas payer. »
- **Avancé** : « Prix = valeur actualisée des coupons et du principal au taux du marché. La sensibilité du prix au taux
  croît avec la durée. Risques : taux, crédit, liquidité et inflation, qui réduit la valeur réelle des coupons fixes. »

## Ce qu'il faut retenir

- Une obligation n'est pas sans risque : son prix peut baisser, surtout quand les taux montent (atelier BNCD,
  diapositive 8).
- La durée compte : une obligation longue réagit beaucoup plus aux taux qu'une obligation courte.
- Les obligations jouent souvent un rôle défensif à côté des actions (énoncé, p. 11), mais ce rôle n'est pas garanti :
  actions et obligations peuvent baisser ensemble quand les taux montent vite (voir
  [Stress test 2022](stress-test-2022.md)).
- L'[inflation](inflation.md) érode la valeur réelle d'intérêts fixes.
- Un CPG ressemble à un dépôt à intérêt prévu au contrat; il n'a pas de prix de marché, mais il a ses propres limites
  de liquidité (atelier BNCD, diapositive 5).

## Comment AlphaForge AI les traite

Le code calcule; le modèle explique.

- **FNB obligataires du jeu de départ** : XBB.TO (obligations canadiennes), AGG (obligations américaines), TLT
  (obligations américaines longues) et ZST.TO (très court terme). Leurs statistiques se calculent sur les prix ajustés.
- **Mandat** : le barème plafonne la part d'obligations longues (`alloc.long_duration`, nulle au niveau le plus prudent)
  et le poids de chaque FNB obligataire (`conc.etf_bond_each`); ZST.TO compte parmi les quasi-liquidités
  (`alloc.cash_like`). Les valeurs par niveau sont dans `risk_levels.yaml`, section 6.
- **Historique long** : avant leur lancement, ces FNB sont prolongés par des séries de taux (XBB.TO par les obligations
  du Canada à 10 ans, AGG par celles des États-Unis à 5 ans, TLT à 20 ans, ZST.TO par les bons du Trésor). Le moteur
  reconstitue des rendements d'obligation à échéance constante à partir de ces taux. Ce raccord est une hypothèse.

## Limites

- **Proxy de XBB.TO** : la série de taux moyens mensuels qui le prolonge sous-estime sa volatilité, et sa corrélation
  avec le FNB est modeste; les mesures sur l'historique long sont donc plus optimistes pour ce fonds.
- **Crédit ignoré** : le proxy d'AGG est une série d'obligations d'État; la poche d'obligations de sociétés et son risque
  de crédit n'y sont pas.
- **Pas d'obligation individuelle** : la simulation ne modélise que des FNB, sans échéance ni remboursement propre.
- **Passé seulement** : les taux passés ne prédisent pas les taux futurs.

## À ne pas confondre

- **Taux et rendement d'un FNB** : le taux du marché n'est pas le rendement total du fonds, qui inclut la variation de
  prix.
- **Taux directeur** : fixé par la banque centrale; il influence les taux des obligations sans les fixer.
- **Sans risque** : seul un placement tenu jusqu'à l'échéance par un émetteur solide approche ce cas, et pas en valeur
  réelle.
