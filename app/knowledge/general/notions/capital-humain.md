---
type: Financial Concept
title: Capital humain
description: Les revenus de travail à venir se comportent comme un actif, et pourquoi AlphaForge AI évite d'ajouter au portefeuille l'exposition que le salaire porte déjà.
tags: [notion, profil-investisseur, capital-humain, concentration]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T04:30:00Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: ibbotson-2007
    title: "Ibbotson, R. G., Milevsky, M. A., Chen, P. et Zhu, K. X. (2007). Lifetime Financial Advice: Human Capital, Asset Allocation, and Insurance. CFA Institute Research Foundation"
    resource: "https://rpc.cfainstitute.org/sites/default/files/-/media/documents/book/rf-publication/2007/rf-v2007-n1-4580-pdf.pdf"
    retrieved_at: "2026-11-14"
  - id: rapport-profilage
    title: "Rapport de recherche de l'équipe : Investor profiling for portfolio construction (2026-11-14)"
    resource: "brain:references/recherche-profil-investisseur.md, sections « Canadian rules fix six elements » (capital humain) et « A published ladder turns the profile into limits » (cas de la personne qui travaille en technologie)"
    retrieved_at: "2026-11-14"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, persona Amira (ingénieure logicielle, « éviter de miser exclusivement sur les technologies », p. 5)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 9 (dix titres technologiques dépendent des mêmes moteurs) et diapositive 10 (concentration existante parmi les contraintes)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: politique-risque
    title: "Niveaux de risque d'AlphaForge AI (risk_levels.yaml v0.2.0)"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml (v0.2.0), sections capacity (income_stability, employer_equity_haircut), satellites.theme_tech et biases.familiarite"
    retrieved_at: "2026-11-15T04:20:00Z"
data:
  aliases: [capital humain, revenus futurs, salaire, emploi, secteur d'emploi, actions de l'employeur, je travaille en techno]
  related: [concentration, expositions-consolidees, diversification, tolerance-et-capacite, biais-domestique, selection-par-regles, noyau-et-satellites]
---

# Capital humain

Le capital humain est la valeur, aujourd'hui, des revenus de travail qu'une personne peut encore gagner. Pour une
personne jeune, c'est souvent son plus gros « actif », loin devant son épargne. Ibbotson et al. (2007) montrent qu'il
faut le regarder avec le portefeuille financier : la nature du revenu change ce qu'il est prudent de détenir à côté.

## Comment l'expliquer selon le niveau

Les faits et les limites sont les mêmes à tous les niveaux; seuls les mots changent (voir
[Niveaux de connaissances](../methodologie/niveaux-de-connaissances.md)).

- **Débutant** : « Votre salaire est déjà un placement dans le secteur où vous travaillez. Si ce secteur va mal,
  votre emploi et vos placements pourraient souffrir en même temps. On évite donc d'en rajouter. »
- **Intermédiaire** : « Un revenu stable ressemble à une obligation; un revenu qui suit les marchés ressemble à une
  action. Le portefeuille complète ce que le revenu expose déjà, au lieu de le doubler. »
- **Avancé** : « Le capital humain est la valeur actualisée des revenus futurs. Sa corrélation avec les marchés et
  avec un secteur détermine l'allocation financière qui le complète (Ibbotson et al., 2007). »

## Ce qu'il faut retenir

- **Revenu stable, revenu lié aux marchés** : les revenus futurs d'un professeur titulaire se comportent comme une
  obligation et laissent plus de place aux actions dans le portefeuille financier; ceux d'un courtier suivent les
  marchés et en laissent moins (Ibbotson et al., 2007).
- **Double exposition** : une crise sectorielle peut toucher en même temps l'emploi (mises à pied, primes en baisse)
  et les placements du même secteur.
- **Les actions de l'employeur cumulent les deux risques** : salaire et épargne dépendent alors d'une seule société.
- **Ne pas ajouter à ce que le salaire expose déjà** : une personne qui travaille en technologie y est déjà exposée par
  son salaire; la logique du capital humain plafonne la technologie près de son poids de marché plutôt que de
  l'augmenter (rapport d'équipe). L'énoncé fait dire à Amira, ingénieure logicielle, qu'elle veut éviter de miser
  exclusivement sur les technologies (p. 5).
- Dix titres technologiques dépendent souvent des mêmes moteurs (atelier BNCD, diapositive 9).

## Comment AlphaForge AI l'utilise

Le code applique des règles fixes; le modèle les explique.

- **Capacité** : la stabilité du revenu entre dans la capacité de risque, et les actions de l'employeur y comptent
  avec une décote (`risk_levels.yaml`, section `capacity`; voir [Tolérance et capacité](tolerance-et-capacite.md)).
- **Étape 0** : si le secteur d'emploi déclaré correspond à un secteur suivi (par exemple technologie, finance,
  énergie ou santé), deux règles s'ajoutent :
  - l'exposition consolidée à ce secteur, FNB compris, est plafonnée près de son poids dans le marché : part d'actions
    du portefeuille × part du secteur dans le marché de référence, sans la marge habituelle des satellites (voir
    [Expositions consolidées](expositions-consolidees.md));
  - aucun titre de ce secteur n'entre dans la [sélection de titres par règles](selection-par-regles.md).
- **Exemple** : pour une personne qui développe des logiciels, le moteur ne sélectionne aucune action du secteur
  Technologie de l'information du jeu de départ (AAPL, MSFT, NVDA, SHOP.TO, CSU.TO), et la technologie vue par
  transparence reste plafonnée près de son poids de marché. Le [noyau](noyau-et-satellites.md) en FNB larges en
  contient déjà sa part.
- La trace cite le secteur déclaré, la règle appliquée et les titres retirés.

Ces règles sont des hypothèses de conception, à valider par l'équipe.

## Limites

- **Secteur d'emploi ≠ exposition réelle** : une développeuse dans une banque dépend surtout de la finance; le profil
  ne demande que le secteur, pas l'employeur.
- **Classification** : l'exclusion suit le secteur du jeu de départ. AMZN y est classée Consommation discrétionnaire
  et GOOGL Services de communication : la règle d'exclusion ne les retire pas, même si leur activité touche à la
  technologie. Le plafond par transparence compte l'exposition attribuée à chaque actif dans le catalogue d'actifs :
  GOOGL y compte comme technologie, AMZN non.
- **Pas de valeur chiffrée** : AlphaForge AI ne calcule pas la valeur actualisée des revenus futurs ni leur
  corrélation avec les marchés; il applique des règles qualitatives.
- **Simulation** : ces règles décrivent un profil fictif et ne remplacent pas l'analyse d'un conseiller.

## À ne pas confondre

- **Capacité de risque** : le capital humain en est un ingrédient, pas un synonyme.
- **Préférence sectorielle** : aimer un secteur ne réduit pas l'exposition qu'on y a déjà.
- **Familiarité** : connaître un secteur ou un pays n'est pas une diversification (voir
  [Biais domestique](biais-domestique.md) et [Concentration](concentration.md)).
