---
type: Financial Concept
title: Style de portefeuille
description: Défensive, dynamique ou offensive, un choix de composition à risque égal, comment AlphaForge AI le fixe à partir du niveau de risque et comment l'expliquer à chaque niveau.
tags: [notion, portefeuille, style, strategie]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T04:30:00Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 10 (les contraintes établissent les limites; les préférences orientent les choix à l'intérieur de ces limites)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, persona Amira (« profil offensif » sans interpréter « risque élevé » comme « tout est acceptable », p. 5) et Encadrement responsable (p. 17)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: politique-risque
    title: "Niveaux de risque d'AlphaForge AI (risk_levels.yaml v0.2.0)"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml (v0.2.0), section levels (N0 à N5, bandes d'actions et budgets de pertes)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: bnc-profil
    title: "Banque Nationale, Votre profil d'investisseur (7 profils, de Liquidités à Actions)"
    resource: "https://www.bnc.ca/particuliers/epargne-placements/profil-investisseur.html"
    retrieved_at: "2026-11-15T04:25:00Z"
  - id: amf-profil
    title: "AMF, outil « Votre profil d'investisseur »"
    resource: "https://lautorite.qc.ca/en/general-public/calculators-and-tools/calculators/your-investor-profile/"
    retrieved_at: "2026-11-14"
data:
  aliases: [style de portefeuille, stratégie, défensive, dynamique, offensive, défensif, offensif, agressif, audacieux]
  related: [tolerance-et-capacite, diversification, concentration, baisse-maximale, noyau-et-satellites, selection-par-regles]
---

# Style de portefeuille

Le style décrit **comment** un portefeuille est composé à l'intérieur de ses limites de risque : défensive, dynamique
ou offensive. Il ne décide pas **combien** de risque est pris. Ce sont la tolérance et la capacité qui fixent le
niveau de risque (voir [Tolérance et capacité](tolerance-et-capacite.md)); le style choisit ensuite une composition, à
risque égal.

## Comment l'expliquer selon le niveau

Les faits et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « Votre profil fixe jusqu'où votre portefeuille peut baisser. Le style, c'est la façon de le remplir
  sans dépasser cette limite : plutôt des sociétés stables qui versent des dividendes, ou plutôt des sociétés qui
  suivent davantage la bourse. »
- **Intermédiaire** : « Défensive, dynamique et offensive sont trois façons de composer un portefeuille au même
  niveau de risque. Le style change le choix des titres et leurs inclinaisons; il ne change ni la part maximale
  d'actions ni les pertes acceptées. »
- **Avancé** : « Le style est un vecteur d'inclinaisons appliqué à la sélection de titres, sous des budgets de pertes
  (CVaR, baisse maximale) et des plafonds de concentration inchangés. Il peut resserrer une limite, jamais en relâcher
  une. »

## Ce qu'il faut retenir

- **À risque égal** : le niveau (N0 à N5), sa bande d'actions et ses budgets de pertes ne bougent pas avec le style.
- **Offensive ≠ tout est permis** : l'énoncé parle du « profil offensif » d'Amira, qu'il ne faut pas lire comme
  « tout est acceptable » (énoncé, p. 5). Un portefeuille offensif reste diversifié et respecte les mêmes plafonds.
- **Les contraintes fixent les limites; les préférences orientent les choix à l'intérieur** (atelier BNCD,
  diapositive 10). Le style est une préférence de composition, jamais une contrainte relâchée.

## Comment AlphaForge AI le fixe

Le code fixe le style à l'étape 0 du moteur, désactivée par défaut; le modèle l'explique. Le compilateur de mandat
fixe d'abord le niveau de risque N0 à N5 (`risk_levels.yaml`); le code en tire un **style par défaut** :

| Niveau | Style par défaut | Repères publics rapprochés par l'équipe |
| --- | --- | --- |
| N0 Préservation, N1 Prudent, N2 Prudent-modéré | Défensive | Profils Liquidités, Prudent et Conservateur de la Banque Nationale |
| N3 Équilibré, N4 Croissance | Dynamique | Profils Pondéré, Équilibré et Croissance de la Banque Nationale |
| N5 Croissance élevée | Offensive | Profil Actions de la Banque Nationale |

**HYPOTHÈSE** : cette correspondance est une convention d'équipe, alignée sur les échelles de profils publiées par la
Banque Nationale et par l'outil de profil de l'AMF. Ces échelles classent le risque d'un investisseur; elles ne
définissent pas de style de composition. À valider par l'équipe.

1. Une **préférence** de l'investisseur, par exemple un objectif de croissance, peut déplacer le style d'un cran au
   plus vers l'offensive. Une descente vers plus de prudence est toujours admise. Seule la composition change.
2. Aucune montée n'a lieu en présence d'un **blocage** : profil incomplet, niveau N0, signal FOMO, signal d'attention
   (actualité suivie chaque jour et envie d'un titre médiatisé), faible sang-froid ou aversion aux pertes, capacité
   qui limite le niveau, ou contradiction du profil (par exemple un horizon de moins de 3 ans ou une tolérance
   faible avec une préférence offensive).
3. Pour un débutant ou en cas de faible littératie, le style est plafonné à **dynamique**.
4. Le style oriente ensuite la [sélection de titres par règles](selection-par-regles.md) : poids des critères du
   score, bonus de style, taille visée des satellites sous leur plafond (planchers à 50 % de la place disponible en
   défensive et en dynamique, à 75 % en offensive), et un plafond sectoriel plus serré pour la technologie et
   l'énergie en défensive (voir [Noyau et satellites](noyau-et-satellites.md)).
5. La trace garde le style par défaut, la préférence, le style retenu et chaque blocage (Facts `strat.style`,
   `strat.preference`, `strat.preference_refused.*`).

Le style ne change jamais le niveau, la bande d'actions, la perte acceptable ni les budgets que le Judge contrôle
(CVaR, [baisse maximale](baisse-maximale.md), stress 2022). Toutes les limites de l'étape 0 sont non bloquantes. Les
règles exactes et leurs formules sont dans [Étape 0 : style et score des titres](../methodologie/scoring-par-style.md);
ce sont des hypothèses de conception, à valider par l'équipe.

## Limites

- **Convention** : les mots « défensive », « dynamique » et « offensive » n'ont pas de définition commune dans
  l'industrie; la correspondance avec les niveaux est un choix de l'équipe.
- **À risque égal sur l'historique** : deux compositions qui respectent les mêmes budgets sur le passé peuvent se
  comporter différemment dans une crise nouvelle.
- **Portée** : le style agit surtout sur la poche d'actions individuelles; il ne décrit pas la part obligataire.
- **Simulation** : le style décrit un profil fictif; il ne remplace pas l'évaluation de convenance d'un conseiller
  (énoncé, p. 17).

## À ne pas confondre

- **Niveau de risque** : combien de risque le profil permet, fixé par la tolérance et la capacité. Le style dit
  comment le composer.
- **Profil d'une institution** : les échelles de la Banque Nationale ou de l'AMF classent le risque d'un
  investisseur; le style d'AlphaForge AI ne classe pas le risque.
- **Style de gestion valeur ou croissance** : une approche de gestion fondée sur des ratios comptables, que l'étape 0
  n'utilise pas.
- **Agressivité** : un style offensif n'autorise pas plus de pertes qu'un style défensif au même niveau (voir
  [Concentration](concentration.md) et [Diversification](diversification.md)).
