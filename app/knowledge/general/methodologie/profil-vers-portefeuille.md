---
type: Methodology
title: Du profil au portefeuille
description: L'enchaînement fixe en sept étapes qui mène du profil investisseur aux limites du portefeuille, le rôle des signaux comportementaux et des règles de contradiction, et ce que le modèle de langage fait ou ne fait pas.
tags: [methodologie, profil-investisseur, construction-portefeuille, gouvernance]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T04:45:00Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: rapport-profilage
    title: "Rapport de recherche de l'équipe : Investor profiling for portfolio construction (2026-11-14)"
    resource: "brain:references/recherche-profil-investisseur.md, sections « A published ladder turns the profile into limits, stress-tested in dollars » et « Fixed rules score the profile; the LLM only asks, clarifies and explains » (version française : brain:product/criteres-profil-investisseur.md, section « Du profil aux limites du portefeuille »)"
    retrieved_at: "2026-11-14"
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositives 8 (tolérance au risque ≠ capacité à prendre du risque), 10 (les contraintes établissent les limites, les préférences orientent les choix) et 12 (une explication crédible répond à quatre questions)"
    retrieved_at: "2026-11-14"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, persona Amira (p. 5) et Encadrement responsable (p. 17)"
    retrieved_at: "2026-11-14"
  - id: cp-31-103
    title: "Instruction générale 31-103CP relative au Règlement 31-103, codification administrative de la CVMO"
    resource: "https://www.osc.ca/en/securities-law/instruments-rules-policies/3/31-103/unofficial-consolidation-companion-policy-31-103cp-registration-requirements-exemptions-and-1"
    retrieved_at: "2026-11-14"
  - id: avis-31-368
    title: "Avis conjoint 31-368 du personnel des ACVM et de l'OCRI, revue de la connaissance du client (10 décembre 2025)"
    resource: "https://www.osc.ca/en/securities-law/instruments-rules-policies/3/31-368/joint-csaciro-staff-notice-31-368-client-focused-reforms-review-registrants-know-your-client-know"
    retrieved_at: "2026-11-14"
  - id: ocri-26-0200
    title: "Bulletin 26-0200 de l'OCRI, indications ciblées sur les réformes axées sur le client (10 septembre 2026)"
    resource: "https://www.ciro.ca/newsroom/publications/client-focused-reforms-cfr-targeted-compliance-guidance-practical-steps-help-dealer-members-dealers"
    retrieved_at: "2026-11-14"
  - id: davies-2017
    title: "Davies, G. B. (2017). New Vistas in Risk Profiling. CFA Institute Research Foundation"
    resource: "https://rpc.cfainstitute.org/research/foundation/2017/new-vistas-in-risk-profiling"
    retrieved_at: "2026-11-14"
  - id: wealthsimple
    title: "Wealthsimple, Understanding the managed portfolio risk assessment (méthode d'évaluation du risque du portefeuille géré)"
    resource: "https://help.wealthsimple.com/hc/en-ca/articles/26129491261211-Understanding-the-managed-portfolio-risk-assessment"
    retrieved_at: "2026-11-14"
  - id: esma-2022
    title: "ESMA, Guidelines on certain aspects of the MiFID II suitability requirements (ESMA35-43-3172, 2022)"
    resource: "https://www.esma.europa.eu/sites/default/files/2023-04/ESMA35-43-3172_Guidelines_on_certain_aspects_of_the_MiFID_II_suitability_requirements.pdf"
    retrieved_at: "2026-11-14"
  - id: fp-canada-nhp-2026
    title: "2026 Projection Assumption Guidelines (FP Canada Standards Council et Institut de planification financière)"
    resource: "https://www.fpcanada.ca/docs/professionalsitelibraries/standards/projection-assumption-guidelines.pdf (section 5 : hypothèses nominales brutes de frais, relevées dans rules/canada_2026.yaml, statut verified)"
    retrieved_at: "2026-11-14"
  - id: ibbotson-2007
    title: "Ibbotson, R. G., Milevsky, M. A., Chen, P. et Zhu, K. X. (2007). Lifetime Financial Advice: Human Capital, Asset Allocation, and Insurance. CFA Institute Research Foundation"
    resource: "https://rpc.cfainstitute.org/sites/default/files/-/media/documents/book/rf-publication/2007/rf-v2007-n1-4580-pdf.pdf"
    retrieved_at: "2026-11-14"
  - id: politique-risque
    title: "Niveaux de risque d'AlphaForge AI (risk_levels.yaml v0.2.0)"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml (v0.2.0), sections horizon_cap, capacity, tolerance, R, dollar_rule, buckets, knowledge, status et biases"
    retrieved_at: "2026-11-15T04:20:00Z"
data:
  pipeline:
    - liquidite_d_abord
    - base_par_objectif_et_horizon
    - tolerance_dans_la_bande
    - capacite_plafond
    - capital_humain
    - besoin_de_rendement
    - preferences_puis_garde_fous
  rule: "niveau_effectif = min(tolerance, capacite)"
  contradictions: "la réponse la plus prudente l'emporte, jamais la moyenne"
  behavioural_flags: [exces_de_confiance, fomo_attention, sang_froid_faible, litteratie_faible]
---

# Du profil au portefeuille

AlphaForge AI passe du profil au portefeuille par un **enchaînement fixe** de sept étapes, que l'investisseur peut
suivre pas à pas : les mêmes réponses donnent toujours le même résultat. L'enchaînement vient du rapport de recherche
de l'équipe, « Investor profiling for portfolio construction » (2026-11-14,
`brain:references/recherche-profil-investisseur.md`). Le déterminisme compte : selon ce rapport, 53 robots-conseillers
proposaient de 0 % à 100 % d'actions au même investisseur « prudent » (Boreiko et Massarotti, 2020). Tout ceci reste
une simulation éducative, jamais un conseil personnalisé (énoncé, p. 17).

## Les sept étapes

1. **La liquidité d'abord.** Le fonds d'urgence et les dépenses prévues d'ici environ deux ans sortent du budget de
   risque et vont en épargne, en dépôts à court terme ou en CPG (rapport).
   - *Dans AlphaForge AI* : un objectif « besoin » à moins de 3 ans est plafonné à N0, à moins de 5 ans à N1
     (`risk_levels.yaml`, section `buckets`); un coussin d'urgence insuffisant abaisse la capacité (voir
     [Fonds d'urgence](../notions/fonds-urgence.md)).
2. **Une base par objectif et par horizon.** L'objectif et l'horizon posent la base (Wealthsimple).
   - *Dans AlphaForge AI* : un plafond d'horizon limite le niveau (moins de 1 an : N0; moins de 3 ans : N1; moins de
     5 ans : N2; moins de 10 ans : N4), et chaque niveau N0 à N5 porte une bande d'actions publiée (voir
     [Horizon de placement](horizon-de-placement.md)).
3. **La tolérance mesurée place le portefeuille dans sa bande.** La tolérance oriente la proposition, sous le
   plafond de la capacité (Wealthsimple).
   - *Dans AlphaForge AI* : l'étape 0 fixe un plancher d'actions dans la bande du niveau, selon la place du score de
     tolérance dans l'intervalle de ce niveau; quand la capacité est la limite, le plancher rejoint le plafond
     (hypothèse de conception, à valider par l'équipe).
4. **La capacité fixe le plafond.** Tolérance et capacité s'évaluent séparément, et le profil de risque retient la
   plus basse des deux (avis 31-368; atelier BNCD, diapositive 8). L'OCRI demande une capacité définie, comparable
   directement à la tolérance (bulletin 26-0200). Pour la plupart des investisseurs, la capacité compte bien plus que
   la tolérance (Davies, 2017); chez Wealthsimple, les vérifications de capacité agissent comme un plafond, pas comme
   une pénalité. Le niveau effectif est le plus bas des deux, **jamais la moyenne**.
   - *Dans AlphaForge AI* : score de risque = min(tolérance, capacité), moins des pénalités; la perte acceptable est
     la plus petite de la perte du niveau, de la perte déclarée et du plafond de capacité (`dollar_rule`; voir
     [Tolérance, capacité et risque effectif](tolerance-capacite-risque-effectif.md)).
5. **Le capital humain ajuste.** Un revenu stable, proche d'une obligation, laisse plus de place aux actions; un
   revenu lié aux marchés en laisse moins, avec des limites sectorielles (Ibbotson et al., 2007).
   - *Dans AlphaForge AI* : la stabilité du revenu entre dans la capacité; l'étape 0 plafonne le secteur d'emploi
     près de son poids de marché et n'en sélectionne aucun titre (voir [Capital humain](../notions/capital-humain.md)).
6. **Le besoin de rendement est vérifié, sans relever le risque.** On ne passe pas outre au risque qu'un client veut
   et peut accepter parce que ses attentes de rendement ne seraient pas atteintes; on explique plutôt d'autres
   leviers : épargner davantage, dépenser moins, prendre sa retraite plus tard (31-103CP). Un objectif inatteignable
   s'ajuste; le profil de risque, non (Davies, 2017). La vérification se fait avec les Normes d'hypothèses de
   projection 2026 de FP Canada et de l'IQPF, nettes de frais.
   - *Dans AlphaForge AI* : ces hypothèses sont relevées et vérifiées dans `canada_2026.yaml`, brutes de frais. Le
     calcul du rendement requis par objectif n'est pas encore relié au moteur.
7. **Les préférences en dernier, puis tous les garde-fous.** Les préférences de durabilité se demandent après
   l'évaluation de convenance; quand aucun produit ne convient, seules les préférences peuvent être adaptées, jamais
   le profil de risque (ESMA, 2022). Les contraintes établissent les limites; les préférences orientent les choix à
   l'intérieur (atelier BNCD, diapositive 10).
   - *Dans AlphaForge AI* : exclusions et préférences ESG s'appliquent après le niveau et le style, puis le Judge
     recontrôle chaque limite sur le portefeuille filtré : budgets de pertes, concentration et exposition
     technologique.

## Les signaux comportementaux règlent les garde-fous, pas l'allocation

Les attitudes comportementales raffinent la solution sans la définir (Davies, 2017). Un signal ne déplace pas
l'allocation de base vers plus de risque : il ajoute un garde-fou ou resserre une limite, jamais l'inverse.

| Signal | Garde-fou | Dans AlphaForge AI |
| --- | --- | --- |
| Excès de confiance | Poche satellite réduite, retour sur les coûts | La réponse testée pèse plus que la déclaration; taille visée des satellites réduite à l'étape 0 |
| Attention et FOMO | Délai de réflexion, contrôle de concentration sur les titres médiatisés | Délai de réflexion du bac à sable; plafonds par titre |
| Sang-froid faible | Entrée progressive, plan de baisse écrit, contact proactif | Limite de baisse conditionnelle (CDaR) ajoutée; position limitée dans la bande |
| Littératie faible | Choix diversifiés par défaut | Profil débutant : plafond de 2 % par titre, cryptoactifs par FNB seulement |

Les valeurs sont dans `risk_levels.yaml` (sections `tolerance`, `biases`, `knowledge`, `satellites`) et dans la
configuration de l'étape 0; ce sont des hypothèses de conception, à valider par l'équipe (voir
[Noyau et satellites](../notions/noyau-et-satellites.md)).

## Les contradictions : la réponse la plus prudente l'emporte

Une table fixe de paires contradictoires repère les réponses incohérentes (rapport) : connaissances testées faibles
avec une tolérance agressive; tolérance faible avec un objectif de croissance maximale; horizon court ou retrait
important proche avec une préférence pour beaucoup d'actions; expertise déclarée élevée avec un score de quiz faible.

- La contradiction est d'abord montrée à l'investisseur, qui peut corriger sa réponse.
- Si elle reste ouverte, la réponse la plus prudente l'emporte, jamais la moyenne, et le point est noté comme non
  résolu (rapport).
- *Dans AlphaForge AI* : quand la perte déclarée et la perte supportable divergent, la capacité l'emporte; à
  l'étape 0, une contradiction empêche le [style](../notions/style-de-portefeuille.md) de monter vers l'offensive.

## Le modèle de langage pose, clarifie et explique

Le rapport conclut que le modèle de langage est la composante la plus risquée du profilage : il doit être confiné à
poser les questions, clarifier et expliquer. Dans AlphaForge AI :

- les scores, la règle du minimum, les contradictions et les plafonds sont calculés par le code;
- un fait tiré d'un texte libre reste non confirmé, hors des scores, tant que l'investisseur ne l'a pas confirmé;
- la trace garde les entrées, la règle appliquée et le résultat, comme l'OCRI l'attend d'une approche algorithmique
  (bulletin 26-0200), pour répondre aux quatre questions d'une explication crédible : quelles données, pourquoi ce
  choix, quelles limites, qu'est-ce qui changerait la réponse (atelier BNCD, diapositive 12).

## Limites

- Les seuils sont des hypothèses de conception; les paramètres de tolérance ne sont pas calibrés
  psychométriquement (`risk_levels.yaml`).
- L'étape 6 n'est pas encore reliée au moteur : un manque de rendement n'est pas encore calculé par objectif.
- L'enchaînement décrit un profil fictif; il ne remplace pas l'évaluation de convenance d'un conseiller (énoncé,
  p. 17).
