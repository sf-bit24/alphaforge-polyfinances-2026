---
type: Financial Concept
title: Sélection de titres par règles
description: Comment AlphaForge AI classe des actions par des règles publiées et des rangs selon le style, pourquoi la momentum reste une sensibilité, et pourquoi ce classement n'est ni une prévision ni un conseil.
tags: [notion, portefeuille, selection, explicabilite, facteurs]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T04:30:00Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 6 (le piège à éviter : « Celui qui a le meilleur rendement historique est le meilleur placement. ») et diapositive 12 (les quatre questions d'une explication crédible)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, p. 3 (l'objectif n'est pas de sélectionner le portefeuille ayant affiché le meilleur rendement), p. 17 (simulation, aucun conseil personnalisé) et p. 18 (ne pas prédire les rendements futurs)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: ftse-global-factor
    title: "FTSE Russell, FTSE Global Factor Index Series Ground Rules, v8.8 (juillet 2026)"
    resource: "https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-global-factor-index-series-ground-rules.pdf, §5.3 (momentum), §5.7 (volatilité), §5.8 (rendement du dividende), §5.9 (bêta) et §6.1 (indices à inclinaisons multiples)"
    retrieved_at: "2026-11-15T04:10:00Z"
  - id: politique-risque
    title: "Niveaux de risque d'AlphaForge AI (risk_levels.yaml v0.2.0)"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml (v0.2.0), sections satellites.single_name (δ = 0,80) et reference_portfolios (noyau 50/50 CA/US)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: starter-readme
    title: "README du jeu de départ AlphaForge AI"
    resource: "alphaforge_starter/README.md, section « Things to know before using the data » (biais du survivant)"
    retrieved_at: "2026-11-15T04:20:00Z"
data:
  aliases: [sélection de titres, choix des titres, classement, score, palmarès, pourquoi ce titre, filtre]
  related: [style-de-portefeuille, noyau-et-satellites, beta, volatilite, baisse-maximale, rendement-du-dividende, diversification, capital-humain, biais-du-survivant]
---

# Sélection de titres par règles

À l'étape 0, AlphaForge AI classe les actions individuelles du jeu de départ par des **règles fixes et publiées** :
les mêmes données et le même profil donnent toujours le même classement. Ce classement sert à choisir quelques
[satellites](noyau-et-satellites.md); le noyau reste en FNB larges. Il décrit des caractéristiques passées mesurées;
ce n'est ni une prévision ni un conseil personnalisé.

## Comment l'expliquer selon le niveau

Les faits et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « On compare les sociétés sur quelques mesures simples de leur passé, comme leurs hauts et leurs bas
  ou les dividendes versés. On ne choisit pas celle qui a le plus monté : ce serait regarder dans le rétroviseur. »
- **Intermédiaire** : « Chaque titre reçoit un rang sur cinq critères. Le style du portefeuille donne plus de poids à
  certains critères. On garde au plus un titre par secteur, et tout le classement est affiché. »
- **Avancé** : « Score = moyenne pondérée de rangs centiles orientés, avec un vecteur d'inclinaisons propre au style,
  inspiré des indices à inclinaisons multiples de FTSE Russell (§6.1). Filtres d'éligibilité, contrainte d'un titre par
  secteur, momentum en analyse de sensibilité seulement. »

## Ce qu'il faut retenir

- **Le piège à éviter** : « Celui qui a le meilleur rendement historique est le meilleur placement. » Le rendement
  passé décrit le passé (atelier BNCD, diapositive 6). L'objectif du défi n'est pas de retenir ce qui a le plus
  rapporté (énoncé, p. 3).
- **Des règles, pas une opinion** : chaque critère, son sens et son poids sont publiés; le modèle ne classe rien, il
  explique un classement calculé par le code.
- **Tout est visible** : chaque titre, son rang par critère, son score et la raison d'une exclusion.
- **Ni prévision, ni conseil** : un bon rang décrit une caractéristique passée, dans une simulation (énoncé, p. 17
  et 18).

## Comment AlphaForge AI classe

**Éligibilité** : les actions individuelles du jeu de départ, sauf celles dont la baisse maximale sur le long
historique dépasse 80 %, le même δ que le plafond des satellites (`risk_levels.yaml`), celles exclues par le profil
et celles du secteur d'emploi (voir [Capital humain](capital-humain.md)).

**Critères**, chacun converti en rang centile parmi les titres éligibles :

| Critère | Mesure | Repère |
| --- | --- | --- |
| [Volatilité](volatilite.md) | Écart-type des rendements hebdomadaires sur cinq ans | FTSE §5.7 |
| [Bêta](beta.md) | Deux ans de rendements quotidiens contre l'indice local | FTSE §5.9 |
| [Baisse maximale](baisse-maximale.md) longue | Long historique mensuel | Même δ que les satellites |
| [Rendement du dividende](rendement-du-dividende.md) | Dividendes des 12 derniers mois / cours | FTSE §5.8 |
| Corrélation au noyau | Rendements hebdomadaires contre un noyau moitié XIU.TO, moitié SPY | `reference_portfolios` |

- **Score** : moyenne pondérée des rangs, orientés selon le [style](style-de-portefeuille.md). Le style défensif
  favorise une faible volatilité, un bêta bas, une baisse longue limitée et un dividende plus élevé; le style
  dynamique favorise d'abord une faible corrélation au noyau; le style offensif favorise un bêta plus élevé, mais
  pénalise toujours une baisse longue profonde. Une préférence déclarée ajoute un petit bonus, sans lever aucun
  plafond.
- **Choix** : les mieux classés, au plus un par secteur, en petit nombre, sous les plafonds des satellites.
- **Momentum** : le rendement cumulé sur 12 mois, hors dernier mois (comme FTSE §5.3), est calculé et affiché comme
  sensibilité : « le classement changerait-il si l'on en tenait compte? ». Elle n'entre jamais dans le score, parce
  que dans un univers choisi en 2026 elle mesure surtout la raison de la présence des titres (voir
  [Biais du survivant](biais-du-survivant.md)).

**Pourquoi des rangs** : FTSE Russell normalise par scores Z sur des milliers de titres. Sur une vingtaine de titres,
un rang résiste mieux à une valeur extrême, qui ne peut pas écraser les autres critères. Les poids par style sont
décrits dans la méthodologie du score par style; ce sont des hypothèses de conception, à valider par l'équipe.

## Limites

- **Petit univers** : une vingtaine d'actions, choisies en 2026, presque toutes de grandes sociétés.
- **Passé seulement** : chaque critère est mesuré sur une fenêtre passée et peut changer.
- **Rangs** : un rang perd l'écart réel; deux titres voisins peuvent être presque identiques.
- **Poids** : d'autres poids donneraient un autre classement, d'où l'affichage de tout le classement.
- **Aucune donnée fondamentale** : le jeu de départ ne contient ni bénéfices, ni dette, ni évaluation.

## À ne pas confondre

- **Prévision** : un classement par caractéristiques passées ne dit pas quel titre montera.
- **Indice factoriel** : FTSE Russell pondère des milliers de titres; ici, quelques satellites seulement, à côté d'un
  noyau de FNB.
- **Conseil personnalisé** : la sélection est une simulation éducative; aucune transaction n'est passée.
