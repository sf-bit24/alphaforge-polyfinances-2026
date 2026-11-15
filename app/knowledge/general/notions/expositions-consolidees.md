---
type: Financial Concept
title: Expositions consolidées
description: Regarder à travers les fonds pour voir ce qu'un portefeuille détient vraiment, comment AlphaForge AI le calcule et ses limites.
tags: [notion, diversification, exposition, transparence, look-through]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T02:39:35Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 13 (chevauchement avec ZEQT) et diapositive 14 (concentrations apparentes)"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, p. 11 (FNB : titres détenus, pondérations, secteur, pays; expositions sous-jacentes)"
  - id: regles-composition
    title: "Barème des niveaux de risque d'AlphaForge AI (risk_levels.yaml v0.2.0)"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml, satellites.theme_tech, exposure_overrides et limits_template (exp.tech)"
data:
  aliases: [exposition consolidée, expositions consolidées, transparence, look-through, chevauchement, ce que je détiens vraiment]
  related: [diversification, concentration, fnb, biais-domestique, risque-de-change]
---

# Expositions consolidées

Les expositions consolidées décrivent ce qu'un portefeuille détient vraiment, une fois les fonds « ouverts » : la part
totale exposée à un secteur, un pays ou une devise, en additionnant les titres détenus directement et ceux détenus à
travers des FNB. On parle aussi de transparence (*look-through*).

## Comment l'expliquer selon le niveau

- **Débutant** : « Un FNB est une boîte qui contient d'autres placements. Pour savoir où va vraiment votre argent, il
  faut regarder dans les boîtes, pas seulement les étiquettes. »
- **Intermédiaire** : « Deux fonds différents peuvent détenir les mêmes grandes sociétés. Si vous avez déjà ces
  sociétés en direct, votre exposition réelle est plus grande que ce que montrent vos lignes. »
- **Avancé** : « Exposition consolidée à un thème = Σ poidsᵢ × part du thème dans l'actif i. Le résultat dépend de la
  qualité et de la date des compositions des fonds; une part inconnue comptée 0 sous-estime l'exposition. »

## Ce qu'il faut retenir

- Le portefeuille montre des concentrations *apparentes*; les vraies apparaissent en regardant le contenu des fonds
  (atelier BNCD, diapositive 14).
- Avant d'ajouter un fonds, on regarde son chevauchement avec ceux qu'on détient déjà (atelier BNCD, diapositive 13).
- La composition d'un FNB (titres, pondérations, secteur, pays) est une donnée publique utile justement pour mesurer
  ces expositions sous-jacentes (énoncé, p. 11).

## Comment AlphaForge AI les calcule

Le code calcule; le modèle explique. Deux calculs existent.

| Où | Méthode | Résultat |
| --- | --- | --- |
| Portefeuille proposé (moteur, Judge) | `portfolio.lookthrough_report` : pour chaque thème, vecteur d'exposition des actifs × poids | Part du portefeuille exposée au thème, détail par actif, actifs sans donnée, hypothèses |
| Portefeuille existant (A2) | Regroupement des positions évaluées en CAD | Parts par classe d'actifs, devise, marché et secteur, et cinq plus grosses positions |

- L'exposition d'un actif à un thème vient, dans l'ordre : d'une valeur déclarée dans le mandat (`exposure_overrides`),
  de la part du secteur dans le marché américain à la date étudiée (indices sectoriels de Kenneth French, utilisée pour
  le marché américain et les FNB qui le répliquent), de la colonne `exposures` du catalogue d'actifs, sinon de 1 ou 0
  selon l'étiquette de l'actif.
- Le mandat plafonne l'exposition technologique consolidée (`exp.tech`). Pour QQQ et XIU.TO, la part technologique est
  une **hypothèse déclarée**, en attente d'une fiche de l'émetteur datée; sans elle, ces fonds compteraient 0.
- Le Judge contrôle ce plafond sur les poids proposés et refuse la proposition en cas de dépassement.

## Limites

- **Thèmes limités** : la transparence ne couvre que quelques thèmes (technologie, énergie, finance, etc.), pas toute
  la composition des fonds.
- **Hypothèses** : les parts déclarées à la main sont marquées `HYPOTHESE` et doivent être remplacées par des fiches
  datées.
- **Inconnu compté 0** : un fonds large sans donnée compte 0 pour un thème; le code liste ces actifs pour le dire.
- **Portefeuille existant** : la vue d'A2 ne regarde pas dans les fonds. Un FNB coté à Toronto qui détient des actions
  américaines y compte comme canadien et en dollars canadiens.
- **Date** : la composition d'un fonds change; une exposition vaut à la date de sa donnée.

## À ne pas confondre

- **Poids d'une ligne** : le poids d'un FNB dans le portefeuille n'est pas l'exposition à ce qu'il contient.
- **[Concentration](concentration.md)** : les expositions consolidées sont l'outil qui la révèle; la concentration
  est le constat.
- **Corrélation** : deux fonds sans titre commun peuvent quand même bouger ensemble (voir
  [Diversification](diversification.md)).
