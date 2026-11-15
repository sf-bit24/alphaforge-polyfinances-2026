---
type: Financial Concept
title: Noyau et satellites
description: Un noyau diversifié de FNB et de petites positions plafonnées en titres individuels, pourquoi les satellites restent petits et comment AlphaForge AI les plafonne.
tags: [notion, portefeuille, noyau-satellites, diversification, concentration]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T04:30:00Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositives 5 (qu'achète-t-on vraiment?) et 9 (diversifier, c'est multiplier les sources de rendement et de risque)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: bessembinder-2018
    title: "Bessembinder, H. (2018). Do stocks outperform Treasury bills? Journal of Financial Economics, 129(3), 440-457"
    resource: "https://doi.org/10.1016/j.jfineco.2018.06.004 (cité par le rapport d'équipe brain:references/recherche-profil-investisseur.md)"
    retrieved_at: "2026-11-14"
  - id: rapport-profilage
    title: "Rapport de recherche de l'équipe : Investor profiling for portfolio construction (2026-11-14)"
    resource: "brain:references/recherche-profil-investisseur.md, section « A published ladder turns the profile into limits » (version française : brain:product/criteres-profil-investisseur.md, poche satellite)"
    retrieved_at: "2026-11-14"
  - id: politique-risque
    title: "Niveaux de risque d'AlphaForge AI (risk_levels.yaml v0.2.0)"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml (v0.2.0), sections satellites (single_name, sandbox), knowledge (debutant) et status"
    retrieved_at: "2026-11-15T04:20:00Z"
data:
  aliases: [noyau et satellites, noyau, satellite, cœur-satellite, core-satellite, poche satellite, titres individuels]
  related: [fnb, diversification, concentration, expositions-consolidees, style-de-portefeuille, selection-par-regles, biais-du-survivant]
---

# Noyau et satellites

Un portefeuille « noyau et satellites » repose sur un **noyau** de FNB larges, actions et obligations, qui porte
l'essentiel du capital et du risque. Autour, de petits **satellites** en titres individuels, chacun plafonné, dont le
total est plafonné aussi. Le noyau diversifie; les satellites restent assez petits pour qu'une erreur sur un titre
ne change pas le sort du portefeuille.

## Comment l'expliquer selon le niveau

Les faits et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « L'essentiel de l'argent va dans des paniers qui contiennent des centaines de sociétés. Quelques
  petites parts peuvent aller dans des sociétés choisies une à une, mais jamais assez pour tout faire basculer. »
- **Intermédiaire** : « Le noyau en FNB apporte la diversification. Chaque satellite a un plafond de poids, et leur
  somme aussi. Les plafonds sont calculés pour qu'une très forte baisse d'un titre ne consomme qu'une petite part de
  la perte acceptée. »
- **Avancé** : « Le poids d'un satellite est borné par φ × l* / δ, où l* est la perte acceptable du profil, δ une
  baisse de planification d'un titre seul et φ la part du budget de perte qu'il peut consommer; un plafond absolu et
  un plafond total s'ajoutent. »

## Ce qu'il faut retenir

- Un FNB est un panier : une part donne un petit morceau de tout ce qu'il contient (atelier BNCD, diapositive 5). Un
  titre seul porte en plus un risque propre à l'entreprise, que le panier dilue (voir [FNB](fnb.md)).
- **La plupart des titres font moins bien que des bons du Trésor.** Sur les actions ordinaires américaines de la
  base CRSP depuis 1926, environ quatre sur sept ont eu, sur toute leur vie cotée, un rendement inférieur à celui des
  bons du Trésor à un mois; environ 4 % des sociétés expliquent à elles seules le gain net de tout le marché
  (Bessembinder, 2018). Choisir quelques titres expose surtout au risque de manquer ces rares sociétés; un FNB large
  les détient par construction.
- **Aucune source revue par les pairs ne fixe la taille d'une poche satellite** (rapport d'équipe). Les plafonds
  d'AlphaForge AI sont donc des choix de conception, dits comme tels.
- Un satellite ne donne pas droit à plus de risque : il reste sous les mêmes budgets de pertes que le noyau.

## Comment AlphaForge AI les plafonne

Le code calcule les plafonds; le modèle les explique. Les règles sont dans `risk_levels.yaml`, section `satellites`.

- **Chaque titre** : poids ≤ min(5 %, φ × l* / δ), arrondi au 0,25 % inférieur, avec δ = 0,80 (un titre seul peut
  perdre 80 % de sa valeur) et φ = 0,10. Exemple de calcul, pas un profil : avec une perte acceptable l* de 20 %, un
  titre est plafonné à 0,10 × 0,20 / 0,80 = 2,5 %; s'il perdait 80 %, il coûterait 2 % du portefeuille, soit un
  dixième de la perte acceptée.
- **Total des titres** : ≤ 0,25 × l* / δ, soit 6,25 % dans le même exemple.
- **Profils plus fragiles** : pas de titres individuels au niveau N0; plafond de 2 % par titre pour un débutant;
  aucun titre individuel pour un profil incomplet ou en protection.
- **Étape 0** (voir [Étape 0 : style et score des titres](../methodologie/scoring-par-style.md)) :
  - **nombre de titres K** : 2 par défaut, 3 pour l'approche « titres individuels », et jamais plus que le plafond
    total divisé par le plafond par titre; K = 0 au niveau N0, pour un profil incomplet, pour un débutant ou en cas
    de faible littératie, et pour l'approche « fonds indiciels »;
  - **choix** : au plus un titre par secteur, par des règles publiées (voir
    [Sélection de titres par règles](selection-par-regles.md)); les titres non retenus sortent de l'univers;
  - **plancher** de chaque titre retenu : φ × la place disponible (le plus petit du plafond par titre et du plafond
    total partagé entre les titres retenus), avec φ = 0,5 en défensive et en dynamique, 0,75 en offensive, et au plus
    3 %. Le [style](style-de-portefeuille.md) change le choix et le plancher, jamais le plafond;
  - **excès de confiance** : un titre de moins (K − 1) et des planchers divisés par deux.
- **Contrôle** : le Judge vérifie les plafonds par titre et total (`conc.single_each`, `conc.single_total`) et
  refuse une proposition qui les dépasse (voir [Concentration](concentration.md)).

Ces valeurs sont des hypothèses de conception, à valider par l'équipe.

## Limites

- **Choix de conception** : 5 %, φ = 0,10 et 0,25 ne viennent d'aucune norme.
- **δ = 0,80 n'est pas un pire cas** : δ part du 75e centile des baisses maximales mensuelles longues des 16 actions
  du jeu de départ, plus une marge pour les baisses quotidiennes. Une faillite fait perdre 100 %, et un univers choisi en 2026 sous-estime
  ce risque (voir [Biais du survivant](biais-du-survivant.md)).
- **Le noyau a ses propres concentrations** : un FNB peut être lourd en technologie ou en banques (voir
  [Expositions consolidées](expositions-consolidees.md)).

## À ne pas confondre

- **Bac à sable** : une petite poche d'essai à part, avec un délai de réflexion; un titre du bac à sable respecte
  aussi les plafonds des titres individuels.
- **Noyau sans risque** : un noyau de FNB larges baisse avec le marché; il réduit la dépendance à une seule société,
  pas le risque de marché (voir [Diversification](diversification.md)).
- **Conviction** : une préférence forte pour un titre n'agrandit pas son plafond.
