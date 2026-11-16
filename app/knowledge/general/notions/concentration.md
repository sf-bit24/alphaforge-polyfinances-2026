---
type: Financial Concept
title: Concentration
description: Quand le résultat dépend trop d'un titre, d'un secteur ou d'un pays, comment AlphaForge AI le repère et le limite, et comment l'expliquer à chaque niveau.
tags: [notion, risque, concentration, diversification]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositives 8 (risque de concentration) et 9 (diversifier)"
  - id: politique-risque
    title: "Niveaux de risque d'AlphaForge AI"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml (v0.2.0), sections satellites et limits_template (conc.*, exp.tech)"
  - id: constats-portefeuille
    title: "Constats calculés sur un portefeuille existant"
    resource: "app/agents/src/alphaforge/profile/portfolio.py (THRESHOLDS, seuils à relire par le volet finance)"
data:
  aliases: [concentration, concentré, une seule action, un seul titre, tous mes oeufs]
  related: [diversification, expositions-consolidees, biais-domestique, types-de-risque, baisse-maximale]
---

# Concentration

Un portefeuille est concentré quand son résultat dépend trop d'une seule exposition : un titre, un secteur ou un
pays (atelier BNCD, diapositive 8). Une seule mauvaise nouvelle peut alors peser lourd sur l'ensemble.

## Comment l'expliquer selon le niveau

Les faits et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « Si une grosse part de votre argent est dans une seule entreprise, une mauvaise nouvelle pour elle
  devient une mauvaise nouvelle pour tout votre portefeuille. »
- **Intermédiaire** : « La concentration se mesure par poids : la part d'un titre, d'un secteur ou d'un pays dans le
  total. Plusieurs titres ne suffisent pas s'ils dépendent des mêmes moteurs. »
- **Avancé** : « Concentration par poids (1 / Σw², nombre effectif de positions) et par risque (part de risque de
  chaque actif, grappes de titres fortement corrélés), y compris l'exposition indirecte détenue par les FNB. »

## Ce qu'il faut retenir

- Dix actions technologiques dépendent souvent des mêmes moteurs : ce n'est pas une vraie diversification.
- La concentration se cache aussi dans les FNB : deux FNB différents peuvent détenir les mêmes grandes sociétés (voir
  [Expositions consolidées](expositions-consolidees.md)).
- Un portefeuille très canadien est concentré par pays et par secteur, même avec beaucoup de titres (voir
  [Biais domestique](biais-domestique.md)).
- Une position concentrée peut monter fort, mais elle peut aussi produire une baisse profonde sans que le reste du
  portefeuille compense (voir [Baisse maximale](baisse-maximale.md)).

## Comment AlphaForge AI la repère et la limite

AlphaForge AI calcule les poids et les constats selon des règles fixes. Yan les explique; les chiffres sont calculés,
jamais inventés.

- **Votre portefeuille existant** : quand Yan lit votre portefeuille, AlphaForge AI évalue chaque ligne en CAD et
  relève trois constats : un titre individuel au-delà de 20 % du total, un secteur au-delà de 40 % des actions
  individuelles, moins de cinq positions sans aucun FNB ni fonds.
- **Proposition** : les règles de votre profil fixent des plafonds de poids. Le simulateur les respecte, puis la
  vérification finale les contrôle :
  - chaque action individuelle et leur total, selon la perte acceptable du profil; le plafond est plus serré pour un
    débutant;
  - chaque FNB d'actions, selon le niveau de risque;
  - l'exposition consolidée à la technologie, FNB compris.
- **Diversification** : le simulateur calcule le nombre effectif de positions et regroupe les actifs dont la
  corrélation dépasse 0,7.

## Limites

- **Seuils** : les seuils des constats sont des choix de l'équipe, pas une norme réglementaire.
- **Exposition indirecte** : sans donnée de composition, l'exposition d'un FNB à un thème est une hypothèse déclarée
  dans les règles d'AlphaForge AI, ou comptée à zéro.
- **Corrélation passée** : des actifs peu corrélés hier peuvent chuter ensemble lors d'une crise.
- **Lignes non évaluées** : une position sans prix n'entre pas dans les poids, ce qui peut cacher une concentration.

## À ne pas confondre

- **Diversification** : l'inverse recherché, qui varie les sources de rendement et de risque.
- **Nombre de titres** : posséder beaucoup de titres n'élimine pas la concentration s'ils réagissent de la même façon.
- **Conviction** : une préférence forte pour un titre n'en réduit pas le risque.
