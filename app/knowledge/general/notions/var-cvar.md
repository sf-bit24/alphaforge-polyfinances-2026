---
type: Financial Concept
title: VaR et CVaR
description: La perte des mauvais mois (VaR) et la perte moyenne des pires mois (CVaR), le contrôle bloquant d'AlphaForge AI, et comment l'expliquer à chaque niveau.
tags: [notion, risque, var, cvar, perte-extreme]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 8 (le risque, possibilité d'un résultat négatif important)"
  - id: politique-risque
    title: "Niveaux de risque d'AlphaForge AI"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml (v0.2.0), sections measurement, levels et limits_template (risk.cvar_m, risk.cvar_12m)"
  - id: moteur-metriques
    title: "Simulateur d'AlphaForge AI : mesures sur rendements mensuels"
    resource: "app/agents/src/alphaforge/finance/backtest/metrics.py (var_cvar) et app/agents/src/alphaforge/finance/portfolio/analysis.py (cvar_rolling)"
data:
  aliases: [VaR, CVaR, valeur à risque, perte attendue extrême, expected shortfall, pire mois, perte en queue]
  related: [volatilite, baisse-maximale, pire-rendement-12-mois, stress-test-2022, cryptoactifs, types-de-risque]
---

# VaR et CVaR

La VaR (valeur à risque) à 95 % est la perte qu'un portefeuille n'a dépassée que lors des 5 % pires périodes de son
historique. La CVaR (*conditional value at risk*, ou *expected shortfall*) est la perte moyenne de ces 5 % pires
périodes. La VaR dit où commence la zone des mauvais mois; la CVaR dit combien on y perd en moyenne.

## Comment l'expliquer selon le niveau

Les chiffres, les sources et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « Sur 100 mois, prenez les 5 pires. La CVaR, c'est ce que le portefeuille a perdu en moyenne pendant
  ces 5 mois-là. C'est une façon de regarder les mauvais moments en face. »
- **Intermédiaire** : « La VaR à 95 % est le seuil des 5 % pires mois; la CVaR est la moyenne au-delà de ce seuil.
  La CVaR est plus prudente, parce qu'elle tient compte de la gravité des pires mois. »
- **Avancé** : « VaR et CVaR historiques à β = 0,95, quantile *lower* puis moyenne de la queue, sur rendements mensuels
  et sur rendements composés de 12 mois glissants chevauchants. La CVaR est cohérente et convexe, d'où son usage
  dans le simulateur (Rockafellar-Uryasev). »

## Ce qu'il faut retenir

- La CVaR est toujours au moins égale à la VaR au même niveau : elle regarde au-delà du seuil.
- Contrairement à la volatilité, la CVaR ne regarde que les pertes, et elle tient compte des mois extrêmes.
- La CVaR ne fixe pas la pire perte possible : une perte plus grande que la moyenne de la queue reste possible.
- Une CVaR mensuelle et une CVaR sur 12 mois ne se comparent pas : la seconde décrit une année entière de mauvaise
  conjoncture, pas un seul mauvais mois.

## Comment AlphaForge AI la calcule

AlphaForge AI calcule VaR et CVaR selon des règles fixes. Yan les explique; les chiffres sont calculés, jamais
inventés. Les pertes sont exprimées en fractions positives (0,05 = −5 %), en CAD par défaut.

| Mesure | Série | Utilisée par | Bloquante |
| --- | --- | --- | --- |
| CVaR mensuelle (β = 0,95) | Rendements mensuels du portefeuille sur la fenêtre d'historique retenue | Simulateur et vérification finale | Oui |
| CVaR sur 12 mois (β = 0,95) | Rendements composés sur 12 mois glissants, série longue raccordée aux proxys, depuis 1971 au plus tôt | Vérification finale seulement | Oui |

- Le simulateur minimise la CVaR sous les contraintes du profil. La vérification finale contrôle ensuite la CVaR
  mensuelle et la CVaR sur 12 mois face aux budgets du niveau de risque (N0 à N5).
- Un actif sans historique long (Bitcoin, Ether) est exclu de la série longue; AlphaForge AI ajoute une borne de perte
  prudente, son poids multiplié par 0,90, à la CVaR sur 12 mois. Le budget de CVaR mensuelle est réduit de même, du
  poids en cryptoactifs multiplié par 0,55.
- Le rapport de risque donne aussi la contribution de chaque actif à la CVaR.

## Limites

- **Historique** : la CVaR décrit les pires mois observés; une crise plus grave que celles de l'historique n'y figure
  pas.
- **Proxys** : avant le lancement d'un FNB, son historique est remplacé par celui d'un indice proche, ce qui reste une
  hypothèse déclarée.
- **Fréquence** : sur rendements mensuels, une chute brutale effacée dans le mois n'apparaît pas.
- **Échantillon** : 5 % d'un historique court ne représente que quelques mois; le chiffre est alors fragile.

## À ne pas confondre

- **Volatilité** : variation typique dans les deux sens, pas la perte des pires périodes (voir
  [Volatilité](volatilite.md)).
- **Baisse maximale** : le pire épisode cumulé d'un sommet à un creux, et non une moyenne de mois (voir
  [Baisse maximale](baisse-maximale.md)).
- **Pire rendement sur 12 mois** : le seul pire cas, et non la moyenne des 5 % pires (voir
  [Pire rendement sur 12 mois](pire-rendement-12-mois.md)).
