---
type: Financial Concept
title: Rendement total
description: Gain en capital plus revenus reçus, sur une période, comment AlphaForge AI le calcule à partir des prix ajustés, ses limites et comment l'expliquer à chaque niveau.
tags: [notion, rendement, rendement-total]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 6 (un rendement n'est jamais qu'un chiffre)"
  - id: atelier-aws
    title: "Atelier AWS : aide-mémoire, pièges classiques des données financières"
    resource: "Atelier AWS du Datathon PolyFinances 2026, section 3 (prix brut ou ajusté, rendement sans risque, rendement passé)"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, p. 3 (l'objectif n'est pas le meilleur rendement passé) et p. 12 (clôture ajustée des dividendes et fractionnements)"
  - id: jeu-de-depart
    title: "Jeu de départ AlphaForge AI : prix quotidiens ajustés"
    resource: "starter:prices_daily.csv (colonne adj_close)"
data:
  catalog_id: rendement_total
  aliases: [rendement, rendement total, dividende, distribution, ça rapporte, rendement annuel]
  related: [interets-composes, inflation, frais, volatilite, baisse-maximale]
---

# Rendement total

Le rendement total est ce qu'un placement a rapporté sur une période : la variation de son prix (gain ou perte en
capital) **plus** les revenus reçus (intérêts, dividendes, distributions), en pourcentage du montant de départ. Exemple
de l'atelier BNCD : 100 $ devenus 108 $, plus 2 $ de dividendes, donnent (108 + 2 − 100) / 100 = 10 % (diapositive 6).

## Comment l'expliquer selon le niveau

Les chiffres, les sources et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « C'est tout ce que le placement vous a rapporté : la hausse de son prix, plus l'argent qu'il vous a
  versé en chemin. »
- **Intermédiaire** : « Gain en capital plus revenus, sur une période précise. Pour comparer des périodes de durées
  différentes, on le ramène à un rendement annuel moyen. »
- **Avancé** : « Rendement calculé sur `adj_close`, donc dividendes réinvestis; rendement annualisé géométrique (TCAC).
  Nominal, en devise de cotation sauf conversion explicite, avant impôt. »

## Ce qu'il faut retenir

- Un rendement n'a de sens qu'avec sa période : +10 % sur un mois ou sur dix ans, ce n'est pas pareil, et le point de
  départ compte (atelier BNCD, diapositive 6).
- Un rendement seul ne dit rien : il se lit avec la volatilité et la baisse maximale (atelier AWS, section 3).
- Le rendement passé décrit le passé; il ne garantit pas le rendement futur. AlphaForge AI ne cherche pas le
  placement au meilleur rendement passé (énoncé officiel, p. 3).
- Comparer des rendements exige des choses comparables : même période, même devise, mêmes frais, distributions
  réinvesties ou non (atelier BNCD, diapositive 6).

## Comment AlphaForge AI le calcule

Le code calcule le rendement; le modèle ne l'estime jamais.

| Où | Données | Résultat |
| --- | --- | --- |
| Faits d'un actif (vidéos tldoole) | Prix quotidiens ajustés (`adj_close`) du jeu de départ | Rendement total (dernier prix / premier prix − 1), rendement annuel moyen et valeur de 100 $ investis |
| Risque d'un portefeuille (moteur) | Rendements mensuels d'un portefeuille rééquilibré chaque mois | Rendement historique annualisé, marqué « passé, pas une prévision » |

- `adj_close` est ajusté des dividendes et des fractionnements (énoncé officiel, p. 12) : le rendement calculé inclut
  donc les dividendes, comme s'ils étaient réinvestis.
- Le rendement annuel moyen est géométrique : il tient compte de l'effet composé, contrairement à une simple moyenne
  des rendements annuels.

## Limites

- **Nominal** : le rendement calculé ne retire pas l'inflation (voir [Inflation](inflation.md)).
- **Avant impôt** : l'impôt sur les dividendes et les gains n'est pas déduit.
- **Frais** : les frais d'un FNB sont déjà reflétés dans son prix; les frais de courtage et de conseil ne le sont pas
  (voir [Frais](frais.md)).
- **Devise** : le rendement d'un actif américain diffère en dollars américains et en dollars canadiens.
- **Fenêtre** : le jeu de départ couvre cinq ans; un autre point de départ donnerait un autre chiffre.

## À ne pas confondre

- **Rendement de prix** : la seule variation du cours, sans les revenus. Il sous-estime le rendement d'un placement
  qui verse des dividendes.
- **Taux de dividende** : le dividende annuel divisé par le prix; une seule partie du rendement total.
- **Rendement réel** : le rendement après inflation.
- **Rendement espéré** : une hypothèse sur l'avenir, jamais un résultat mesuré.
