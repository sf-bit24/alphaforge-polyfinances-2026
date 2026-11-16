---
type: Financial Concept
title: Bêta
description: La sensibilité d'un titre aux mouvements de son marché local, comment AlphaForge AI la calcule sur deux ans de rendements quotidiens, et pourquoi ce n'est pas une prévision.
tags: [notion, risque, beta, risque-de-marche]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T04:30:00Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: ftse-global-factor
    title: "FTSE Russell, FTSE Global Factor Index Series Ground Rules, v8.8 (juillet 2026)"
    resource: "https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-global-factor-index-series-ground-rules.pdf, §5.9 (bêta : covariance du rendement total du titre et de l'indice, divisée par la variance de l'indice, sur deux ans de données quotidiennes; devise locale pour un indice d'un seul pays)"
    retrieved_at: "2026-11-15T04:10:00Z"
  - id: jeu-de-depart
    title: "Jeu de départ AlphaForge AI : prix quotidiens ajustés"
    resource: "starter:prices_daily.csv (colonne adj_close) et starter:assets_universe.csv (XIU.TO, SPY)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 8 (types de risque, dont le risque de marché)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, p. 18 (le défi ne demande pas de prédire les rendements futurs à partir des performances passées)"
    retrieved_at: "2026-11-15T04:20:00Z"
data:
  aliases: [bêta, beta, sensibilité au marché, risque de marché, suit le marché, amplifie le marché]
  related: [volatilite, diversification, types-de-risque, risque-de-change, selection-par-regles, style-de-portefeuille]
---

# Bêta

Le bêta (β) mesure la sensibilité d'un titre aux mouvements de son marché. Un bêta de 1 indique qu'en moyenne, sur la
période étudiée, le titre a bougé comme le marché; un bêta de 1,5, qu'il a amplifié ses mouvements; un bêta de 0,5,
qu'il les a amortis. C'est une mesure du passé, pas une prévision.

## Comment l'expliquer selon le niveau

Les chiffres, les sources et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « Le bêta dit si un titre a eu tendance à suivre la bourse en exagérant ses mouvements ou en les
  adoucissant. Quand la bourse baissait de 1 %, un titre de bêta 1,5 baissait en moyenne d'environ 1,5 %. »
- **Intermédiaire** : « Le bêta compare les variations quotidiennes d'un titre à celles de son marché local. Il
  mesure la part du mouvement liée au marché, pas tout le risque du titre. »
- **Avancé** : « β = cov(rᵢ, rₘ) / var(rₘ) = ρ × σᵢ / σₘ, estimé sur deux ans de rendements quotidiens contre
  l'indice local. Estimation instable, sensible à la fenêtre et à l'indice retenus. »

## Ce qu'il faut retenir

- **Bêta et volatilité sont différents** : β = ρ × σᵢ / σₘ. Un titre très volatil mais peu corrélé au marché peut
  avoir un bêta faible; son risque est alors surtout propre à l'entreprise (voir [Volatilité](volatilite.md)).
- **Le bêta dépend de l'indice** : changer d'indice de référence change le bêta.
- **Le bêta change dans le temps** et peut grimper en crise, quand les titres baissent ensemble.
- **Le bêta d'un portefeuille** est la moyenne pondérée des bêtas de ses titres, s'ils sont mesurés contre le même
  indice.
- **Ce n'est pas une prévision** : le défi ne demande pas de prédire les rendements futurs à partir du passé
  (énoncé, p. 18).

## Comment AlphaForge AI le calcule

AlphaForge AI calcule le bêta selon des règles fixes. Yan l'explique; les chiffres sont calculés, jamais inventés.

- **Formule** : covariance des rendements quotidiens du titre et de l'indice, divisée par la variance des rendements
  de l'indice, sur les 504 dernières dates communes au titre et à son indice (environ deux ans), comme les règles des
  indices factoriels de FTSE Russell (§5.9). Sous 250 dates communes, le bêta reste inconnu plutôt que deviné.
- **Indice local** : XIU.TO (FNB du S&P/TSX 60) pour un titre coté en CAD, SPY (FNB du S&P 500) pour les autres. Le
  titre et son indice se négocient dans la même devise : aucune conversion de change n'entre dans le calcul, comme
  FTSE le prévoit pour un indice d'un seul pays.
- **Prix** : rendements tirés de la clôture ajustée, qui tient compte des dividendes et des fractionnements; FTSE
  utilise aussi des rendements totaux.
- **Usage** : le bêta est un des critères de la [sélection de titres par règles](selection-par-regles.md). Le
  [style](style-de-portefeuille.md) défensif favorise un bêta bas (poids 1), le style offensif un bêta plus élevé
  (poids 2), toujours sous les mêmes plafonds de satellites et budgets de pertes (voir
  [Choix et score des titres selon le style](../methodologie/scoring-par-style.md)).

## Limites

- **Passé seulement** : deux ans de données décrivent un seul régime de marché; un bêta mesuré en période calme peut
  sous-estimer la sensibilité en crise.
- **Erreur d'estimation** : sur deux ans, l'incertitude autour d'un bêta est grande; un écart de 0,1 entre deux titres
  ne veut pas dire grand-chose.
- **Titre lourd dans son indice** : une grande banque pèse beaucoup dans le S&P/TSX 60; elle entre dans le calcul de
  l'indice lui-même, ce qui rapproche mécaniquement son bêta de 1.
- **Pas de comparaison directe entre marchés** : un bêta contre XIU.TO et un bêta contre SPY ne se comparent pas.
- **Relation linéaire moyenne** : le bêta ne dit pas si un titre réagit plus fort aux baisses qu'aux hausses.
- **Prix ajustés** : les valeurs passées de la clôture ajustée changent à chaque mise à jour des données (voir
  [Pièges du jeu de départ](../methodologie/pieges-du-jeu-de-depart.md)).

## À ne pas confondre

- **Volatilité** : l'ampleur totale des variations, risque propre compris.
- **Corrélation** : le sens commun des mouvements, sans leur ampleur (voir [Diversification](diversification.md)).
- **Risque de change** : un titre américain détenu en dollars canadiens porte aussi le risque de la devise, que ce
  bêta en devise locale ne mesure pas (voir [Risque de change](risque-de-change.md)).
- **Risque total** : le risque de marché n'est qu'un type de risque parmi d'autres (voir
  [Types de risque](types-de-risque.md)).
