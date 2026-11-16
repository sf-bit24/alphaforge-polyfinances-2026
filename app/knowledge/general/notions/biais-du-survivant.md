---
type: Financial Concept
title: Biais du survivant
description: Pourquoi un univers choisi en 2026 flatte le passé, ses effets sur la momentum et sur toute simulation sur l'historique, et comment AlphaForge AI le limite.
tags: [notion, donnees-marche, biais, backtest, jeu-de-depart]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T04:30:00Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: starter-readme
    title: "Guide du jeu de départ AlphaForge AI"
    resource: "alphaforge_starter/README.md, section « Things to know before using the data » (Survivorship bias : univers choisi en 2026 parmi des noms importants aujourd'hui)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, section Période, qualité et règles d'utilisation (comparabilité : tenir compte des biais de sélection, p. 14) et p. 18 (les performances passées ne prédisent pas les résultats futurs)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 6 (le rendement passé décrit le passé) et diapositive 11 (source, date, définition et limites d'une donnée)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: bessembinder-2018
    title: "Bessembinder, H. (2018). Do stocks outperform Treasury bills? Journal of Financial Economics, 129(3), 440-457"
    resource: "https://doi.org/10.1016/j.jfineco.2018.06.004 (cité par le rapport d'équipe brain:references/recherche-profil-investisseur.md)"
    retrieved_at: "2026-11-14"
  - id: politique-risque
    title: "Niveaux de risque d'AlphaForge AI"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml (v0.2.0), section measurement (historique mensuel raccordé aux history_proxies) et satellites.single_name (δ)"
    retrieved_at: "2026-11-15T04:20:00Z"
data:
  aliases: [biais du survivant, biais de survie, survivorship bias, biais de sélection, gagnants d'aujourd'hui]
  related: [baisse-maximale, selection-par-regles, noyau-et-satellites, rendement-total, volatilite, stress-test-2022]
---

# Biais du survivant

Le biais du survivant apparaît quand on étudie seulement ce qui existe encore aujourd'hui. Les sociétés disparues,
rachetées ou tombées hors des grands indices manquent à l'analyse, et le passé paraît meilleur qu'il ne l'a été. Le
jeu de départ en est un exemple : ses 31 actifs ont été choisis en 2026 parmi des noms importants aujourd'hui
(guide du jeu de départ).

## Comment l'expliquer selon le niveau

Les faits et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « Si on ne regarde que les entreprises qui ont réussi, on oublie toutes celles qui ont échoué en
  chemin. Le passé a l'air plus facile qu'il ne l'était vraiment. »
- **Intermédiaire** : « Une liste choisie aujourd'hui contient les gagnants d'hier. Tester une stratégie sur cette
  liste revient à connaître la fin de l'histoire : le résultat paraît meilleur que celui d'une stratégie choisie en
  2021. »
- **Avancé** : « Biais de sélection de l'univers : l'échantillon est conditionné à la survie et au succès jusqu'en
  2026. Il surestime les rendements, sous-estime les baisses et rend les signaux fondés sur le rendement passé, comme
  la momentum, artificiellement forts. »

## Ce qu'il faut retenir

- **Une simulation sur l'historique du jeu de départ paraît meilleure** qu'une stratégie choisie en 2021 ne l'aurait
  été (guide du jeu de départ). L'énoncé demande de tenir compte des biais de sélection (p. 14).
- **Les survivants sont rares** : sur les actions ordinaires américaines de la base CRSP depuis 1926, environ quatre
  sur sept ont eu, sur leur vie cotée, un rendement inférieur aux bons du Trésor à un mois, et environ 4 % des
  sociétés expliquent le gain net de tout le marché (Bessembinder, 2018). Un univers de grandes sociétés
  d'aujourd'hui est très loin d'un tirage au hasard.
- **Effet sur la momentum** : classer par rendement passé dans un univers de survivants revient à classer selon la
  raison même de leur présence. Le signal paraît fort sans rien dire de l'avenir.
- **Effet sur les risques** : les faillites et les longues descentes des sociétés disparues manquent, donc les
  baisses et les volatilités mesurées sont trop rassurantes.
- Le rendement passé décrit le passé (atelier BNCD, diapositive 6).

## Comment AlphaForge AI le limite

Le biais ne peut pas être supprimé avec ce jeu de données. AlphaForge AI le réduit selon des règles fixes et le dit.

- **La momentum n'est qu'une sensibilité** : elle est affichée, jamais utilisée dans le score de la
  [sélection de titres par règles](selection-par-regles.md).
- **Un long historique raccordé** : les budgets de pertes et la baisse maximale longue se mesurent sur un historique
  mensuel où chaque actif est raccordé à un proxy, un indice de marché ou d'industrie, pour inclure des crises comme
  1973-1974, 2000-2002 et 2008 (voir [Baisse maximale](baisse-maximale.md)).
  Un indice large comptait, à chaque date, les sociétés alors cotées, y compris celles disparues depuis.
- **Une baisse forte est supposée possible** : un titre seul est planifié comme s'il pouvait perdre 80 %, et un titre
  au-delà de ce seuil sur le long historique n'est pas éligible (voir [Noyau et satellites](noyau-et-satellites.md)).
- **Un noyau en FNB larges** : il dépend moins du choix de quelques survivants.
- **Le biais est noté** : la liste des actifs le signale pour chaque titre (« biais du survivant : univers choisi
  en 2026 »).

## Limites

- **Le proxy n'est pas le titre** : raccorder une action à son industrie avant sa cotation décrit l'industrie, pas
  la société; c'est pourquoi cette baisse longue est marquée HYPOTHÈSE.
- **Repli sur la fenêtre courte** : si l'historique long manque, le choix des titres selon le style prend la baisse
  maximale des cinq ans du jeu de départ, marquée HYPOTHÈSE « fenêtre courte »; elle est alors encore plus flattée par
  la survie (voir
  [Choix et score des titres selon le style](../methodologie/scoring-par-style.md)).
- **Le choix des 31 actifs reste biaisé**, FNB compris : un FNB thématique lancé récemment a lui aussi survécu.
- **Sans univers « à la date »**, la liste des titres réellement disponibles chaque année, le biais ne peut pas être
  mesuré, seulement signalé.

## À ne pas confondre

- **Biais d'anticipation** : utiliser une donnée avant sa date de publication (voir
  [Pièges du jeu de départ](../methodologie/pieges-du-jeu-de-depart.md)).
- **Choix de la fenêtre** : une période sans crise flatte aussi les chiffres, même sans biais du survivant (voir
  [Stress test 2022](stress-test-2022.md)).
- **Rendement total** : un biais de l'univers ne se corrige pas en ajoutant les dividendes (voir
  [Rendement total](rendement-total.md)).
