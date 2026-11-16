---
type: Methodology
title: Pièges du jeu de données de départ
description: Clôture ajustée, dates d'observation et de publication, calendriers, biais du survivant et absence de cotes ESG dans le jeu de départ AlphaForge AI.
tags: [methodologie, donnees-marche, jeu-de-depart]
status: stable
owners: [alphaforge-a6]
sensitivity: public
generated: { by: "team:larpathon", at: "2026-11-14T23:30:00Z" }
stale_after: "2027-02-14T00:00:00Z"
sources:
  - id: starter-readme
    title: "Guide du jeu de départ AlphaForge AI"
    resource: "alphaforge_starter/README.md, section « Things to know before using the data » (extraction du 2026-11-13)"
  - id: starter-metadata
    title: "Description des sources du jeu de départ AlphaForge AI"
    resource: "alphaforge_starter/sources_metadata.csv"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, section Période, qualité et règles d'utilisation (p. 14)"
data:
  window: { start: "2021-11-12", end: "2026-11-12", retrieved: "2026-11-13" }
  assets: 31
---

# Pièges du jeu de données de départ

Le jeu de départ des organisateurs couvre 31 actifs du 12 novembre 2021 au 12 novembre 2026 (extraction du
13 novembre 2026), ce qui inclut 2022, quand actions et obligations ont reculé ensemble. Il est facultatif et sert à la
simulation; rien n'y constitue un conseil en placement (guide du jeu de départ).

## Prix

- **La clôture ajustée pour les rendements, la clôture non ajustée pour la valeur** : la clôture ajustée tient compte
  des fractionnements et des dividendes (méthode de Yahoo, recalculée depuis la dernière date); ses valeurs passées
  changent à chaque nouvelle extraction. La clôture non ajustée ne tient compte que des fractionnements. AlphaForge AI
  évalue un portefeuille existant à la dernière clôture non ajustée et réserve la clôture ajustée aux rendements.
- **Fractionnements déjà appliqués** : les fractionnements listés parmi les opérations sur titres du jeu de départ
  sont des références; il ne faut pas les appliquer de nouveau. Le « fractionnement » de 1,021 de CNQ.TO le
  2022-08-22 reflète probablement une distribution spéciale.
- **Devise de cotation** : les titres cotés à Toronto sont en CAD, les autres en USD. La conversion utilise le taux
  de change quotidien USD/CAD de la Banque du Canada, qui n'est pas publié les jours fériés canadiens. AlphaForge AI
  convertit au dernier taux disponible et le cite avec sa date.
- **Aucun remplissage ni alignement de calendrier** : un prix n'existe que les jours où Yahoo en fournit un. Les
  jours fériés diffèrent entre la TSX et les marchés américains, et les cryptoactifs se négocient 7 jours sur 7, en
  jours civils du temps universel (UTC), sans clôture de marché.

## Dates

- **Date d'observation et date de publication** : les données macro mensuelles (IPC du Canada et des États-Unis,
  chômage américain) sont datées au mois de référence et publiées des semaines plus tard. Une simulation ne doit pas
  utiliser une valeur avant sa publication (énoncé officiel, p. 14). Les valeurs FRED sont les dernières révisées, pas
  celles d'abord publiées.
- La base de connaissances garde les deux dates pour chaque donnée et chaque actualité; quand une source ne donne pas la date
  de publication, la date de récupération en sert de borne supérieure.

## Sélection et contenu

- **Biais du survivant** : l'univers a été choisi en 2026 parmi des titres aujourd'hui importants. Une simulation sur
  l'historique y paraît donc meilleure qu'une stratégie réellement choisie en 2021.
- **Aucune cote ESG, nouvelle ou donnée fondamentale** : les organisateurs n'ont pas voulu distribuer de cotes ESG
  sans pouvoir les sourcer et les licencier. Le jeu de départ ne dit pas si une société est liée à une controverse
  environnementale ou sociale; il faut des preuves externes documentées (rapports de durabilité, pages
  méthodologiques des émetteurs de FNB, SEDAR+, EDGAR).
- Les secteurs de la liste des actifs du jeu de départ sont attribués par les organisateurs et simplifiés; pour un FNB, le « secteur »
  décrit l'exposition.

## Conditions d'utilisation

Yahoo Finance pour les prix et les opérations sur titres, la Banque du Canada (service Valet) pour le change, les taux
et l'IPC canadien, FRED pour les données américaines. La description des sources du jeu de départ donne les
conditions de chaque source.
