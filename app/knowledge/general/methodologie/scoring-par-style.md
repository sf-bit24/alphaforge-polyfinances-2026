---
type: Methodology
title: "Étape 0 : style et score des titres"
description: Les règles exactes de l'étape 0 du moteur, telles que codées (style tiré du niveau, position dans la bande, plafonds sectoriels, indicateurs, score par rangs, éligibilité, nombre de titres, planchers et repli), avec leurs formules. Chaque Fact strat.* renvoie à ce document.
tags: [methodologie, construction-portefeuille, style, selection, explicabilite]
status: draft
owners: [alphaforge-a1]
sensitivity: public
generated: { by: "agent:claude-code", at: "2026-11-15T05:00:00Z" }
stale_after: "2027-02-15T00:00:00Z"
sources:
  - id: strategie-etape-0
    title: "Configuration de l'étape 0 d'AlphaForge AI (strategy.yaml v0.1.0)"
    resource: "app/agents/src/alphaforge/finance/strategy/strategy.yaml au commit 6f84b19 (v0.1.0, sha256 4136e34e2930240811c59daf12fabfdd108f4b3bfb7c34afd8395a6d8c7e88cb); code au même commit : finance/strategy/style.py, rules.py, features.py, scoring.py et select.py"
    retrieved_at: "2026-11-15T04:50:00Z"
  - id: politique-risque
    title: "Niveaux de risque d'AlphaForge AI (risk_levels.yaml v0.2.0)"
    resource: "app/agents/src/alphaforge/finance/policy/risk_levels.yaml (v0.2.0), sections levels, dollar_rule, satellites (single_name, theme_tech) et limits_template (alloc.growth, conc.single_each, conc.single_total, exp.*)"
    retrieved_at: "2026-11-15T04:50:00Z"
  - id: queues-sectorielles
    title: "Baisses maximales longues des industries (calibration de l'étape 0)"
    resource: "app/agents/scripts/calibration/tails_sectors.py et app/agents/tests/finance/fixtures/calibration/tails_sectors.csv au commit 6f84b19 (US_IND_UTILS 0,431; US_IND_HLTH 0,479), avec tails_monthly.csv (US_IND_ENRGY 0,588; US_IND_MONEY 0,693)"
    retrieved_at: "2026-11-15T04:50:00Z"
  - id: ftse-global-factor
    title: "FTSE Russell, FTSE Global Factor Index Series Ground Rules, v8.8 (juillet 2026)"
    resource: "https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-global-factor-index-series-ground-rules.pdf, §5.3 (momentum), §5.7 (volatilité), §5.8 (rendement du dividende), §5.9 (bêta) et §6.1 (indices à inclinaisons multiples)"
    retrieved_at: "2026-11-15T04:10:00Z"
  - id: jeu-de-depart
    title: "Jeu de départ AlphaForge AI : prix quotidiens, dividendes, change et univers"
    resource: "starter:prices_daily.csv (adj_close, close, volume), starter:corporate_actions.csv, starter:fx_usdcad_daily.csv et starter:assets_universe.csv (secteurs)"
    retrieved_at: "2026-11-15T04:50:00Z"
  - id: rapport-profilage
    title: "Rapport de recherche de l'équipe : Investor profiling for portfolio construction (2026-11-14)"
    resource: "brain:references/recherche-profil-investisseur.md (la tolérance place dans la bande, la capacité plafonne; signaux comportementaux en garde-fous; table de contradictions; poche satellite)"
    retrieved_at: "2026-11-14"
  - id: ibbotson-2007
    title: "Ibbotson, R. G., Milevsky, M. A., Chen, P. et Zhu, K. X. (2007). Lifetime Financial Advice: Human Capital, Asset Allocation, and Insurance. CFA Institute Research Foundation"
    resource: "https://rpc.cfainstitute.org/sites/default/files/-/media/documents/book/rf-publication/2007/rf-v2007-n1-4580-pdf.pdf"
    retrieved_at: "2026-11-14"
  - id: atelier-bncd
    title: "Atelier BNCD : comprendre l'investisseur avant de bâtir la solution"
    resource: "Atelier finance du Datathon PolyFinances 2026, diapositive 6 (le piège du meilleur rendement historique) et diapositive 10 (les contraintes établissent les limites, les préférences orientent les choix)"
    retrieved_at: "2026-11-15T04:20:00Z"
  - id: enonce-officiel
    title: "Énoncé officiel du défi AlphaForge AI (Datathon PolyFinances 2026)"
    resource: "Énoncé officiel, persona Amira (p. 5), Encadrement responsable (p. 17) et Performance historique et risque (p. 18)"
    retrieved_at: "2026-11-15T04:20:00Z"
data:
  strategy_yaml:
    path: "app/agents/src/alphaforge/finance/strategy/strategy.yaml"
    commit: "6f84b19"
    version: "0.1.0"
    sha256: "4136e34e2930240811c59daf12fabfdd108f4b3bfb7c34afd8395a6d8c7e88cb"
  fact_prefix: "strat."
  limits_blocking: false
  enabled_by_default: false
---

# Étape 0 : style et score des titres

L'étape 0 choisit un **style de composition** et quelques **titres satellites** avant l'optimisation. Ce document
décrit ses règles exactes, telles que codées au commit `6f84b19` : `strategy.yaml` v0.1.0, sha256
`4136e34e2930240811c59daf12fabfdd108f4b3bfb7c34afd8395a6d8c7e88cb`. Chaque Fact `strat.*` cite
`strategy.yaml@0.1.0#<section>` et renvoie ici. Toutes les valeurs de `strategy.yaml` sont des **hypothèses de
conception, à valider par l'équipe**; aucune ne vient des fiches de personas. L'étape 0 est **active par
défaut sur la branche de travail** (`build_portfolio(strategy=True)`, à valider par l'équipe avant toute fusion ; `strategy=False` rend l'ancien comportement); elle s'insère entre la compilation du mandat et le premier
tour de l'optimisation. Simulation éducative seulement, jamais un conseil.

Les notions sont expliquées dans [Style de portefeuille](../notions/style-de-portefeuille.md),
[Noyau et satellites](../notions/noyau-et-satellites.md) et
[Sélection de titres par règles](../notions/selection-par-regles.md).

| Facts | Section |
| --- | --- |
| `strat.style`, `strat.style_from_level`, `strat.preference`, `strat.preference_refused.*`, `strat.contradiction.*`, `strat.flag.*` | 1 |
| `strat.e_min`, `strat.e_cap`, `strat.pi`, `strat.band_target` | 2 |
| `strat.sector_cap.*` | 3 |
| `strat.feat.*`, `strat.sens.mom.rank.*` | 4 |
| `strat.n_candidates`, `strat.score.*`, `strat.rank.*` | 5 |
| `strat.ineligible.*` | 6 |
| `strat.K`, `strat.floor.*`, `strat.floor_cad.*` | 7 |
| `strat.fallback.*`, `strat.risk_cost`, `strat.applied` | 8 |

## 1. Style tiré du niveau, préférence et blocages

**Style par défaut** (`level_to_style`, convention d'équipe) : N0, N1, N2 → défensive; N3, N4 → dynamique;
N5 → offensive.

**Préférence** (`preference`) : le paramètre `style_preference`, sinon `objective.goal` (`income`, `preservation`,
`safety_cushion` → défensive; `growth` → offensive).

- **Descente** vers plus de prudence : toujours admise, du nombre de crans demandé.
- **Montée** : d'un cran au plus (`max_up: 1`), et refusée si l'un des blocages suivants est présent : statut du
  profil autre que complet; niveau N0; signal FOMO; signal d'attention; faible sang-froid ou aversion aux pertes; la
  capacité lie (voir section 2); une contradiction.
- **Contradictions** : préférence offensive avec un niveau tiré du score de risque en N0 ou N1 (tolérance faible ×
  croissance); faible littératie avec un niveau tiré du score en N4 ou N5 (connaissance faible × tolérance agressive);
  préférence offensive avec un horizon de moins de 3 ans.
- **Plafond débutant** : faible littératie → style au plus dynamique (`beginner_max_style`).

**Signaux comportementaux** (`profile_codes`), toujours des garde-fous, jamais une allocation :

| Signal | Déclencheurs |
| --- | --- |
| Excès de confiance | Auto-évaluation « avancé » avec au moins une mauvaise réponse au quiz (diversification ou obligations et taux), ou biais `surconfiance` du profil |
| FOMO | Achat important d'un titre médiatisé, ou part visée de 5 % et plus, ou biais `FOMO` |
| Attention | Actualité suivie chaque jour et envie d'acheter un titre médiatisé |
| Faible sang-froid | Tout vendre après une baisse, avoir vendu lors d'une baisse réelle, seuil de vente de 10 % ou moins, biais `aversion_perte`, ou limite `risk.cdar_m` dans le mandat |
| Faible littératie | Niveau débutant, ou produits connus sans les actions |

## 2. Position dans la bande d'actions (π) et plancher de croissance (g)

« La tolérance place, la capacité plafonne » (rapport d'équipe). La bande du niveau va de e_min (minimum
d'`alloc.growth`) à e_cap (part maximale d'actions, règle des dollars de `risk_levels.yaml`).

- **La capacité lie** si le niveau retenu est sous le niveau tiré du score de risque (un plafond d'horizon, de seau,
  de statut ou de dollars lie), ou si la capacité C est inférieure à la tolérance T.
- **π** = 0 si le profil n'est pas complet (position d'attente); π = 1 si la capacité lie; sinon
  π = (R − R_bas) / (R_haut − R_bas), borné à [0, 1], où [R_bas, R_haut] est l'intervalle de R du niveau.
- **Faible sang-froid** : π ≤ 0,5. Même plafond pour la contradiction connaissance faible × tolérance agressive
  (la réponse la plus prudente l'emporte).
- **Plancher de croissance** (`strat.growth_floor`, Fact `strat.band_target`) :
  g = arrondi inférieur à 5 % de [e_min + π × (e_cap − e_min)], puis g ≤ e_cap − plafond crypto. Il vise les
  classes d'actions hors cryptoactifs. Aucun plancher n'est émis si g ≤ e_min.

## 3. Plafonds sectoriels (look-through)

Généralisation de `satellites.theme_tech` de `risk_levels.yaml` :

cap_t = arrondi inférieur à 0,25 % de [e_cap × s_ref_t × (1 + τ_t) + φ × l* / δ_t], avec φ = 0,10

| Tag | s_ref (part dans le marché américain) | δ (baisse longue, arrondie au 5 % supérieur) |
| --- | --- | --- |
| tech | 0,44 | 0,80 |
| energy | 0,0311 | 0,60 |
| financials | 0,1132 | 0,70 |
| utilities | 0,024 | 0,45 |
| healthcare | 0,0799 | 0,50 |

- **τ** : défensive τ_tech = τ_energy = −0,25; dynamique et offensive : aucun τ.
- Hors capital humain, un plafond n'est émis que pour un tag à τ négatif ou le tag d'un titre retenu.
- Dans tous les cas, il n'est émis que s'il est plus strict que la limite de base `exp.<tag>`.
- **Capital humain** (Ibbotson et al., 2007) : pour le tag du secteur d'emploi (technologie → tech, finance →
  financials, énergie → energy, santé → healthcare), cap = e_cap × s_ref, **au poids du marché, sans terme
  satellite**. Même règle pour l'énergie quand les combustibles fossiles font l'objet d'une exclusion absolue.
  Voir [Capital humain](../notions/capital-humain.md).

## 4. Indicateurs (Facts `strat.feat.<titre>.<indicateur>`)

Calculés sur le jeu de départ, sans aucune donnée postérieure à la date d'analyse :

| Indicateur | Définition codée | Repère |
| --- | --- | --- |
| `vol` | Écart-type des rendements hebdomadaires (clôture ajustée du mercredi) sur 260 semaines, × √52, au moins 52 observations | FTSE §5.7 |
| `beta` | Covariance / variance des rendements quotidiens contre XIU.TO (titre en CAD) ou SPY (autres), sur les 504 dernières dates communes, au moins 250 | FTSE §5.9 |
| `corr_core` | Corrélation des rendements hebdomadaires en CAD avec un cœur 50 % XIU.TO + 50 % SPY, au moins 52 semaines communes | `reference_portfolios` |
| `dividend_yield` | Dividendes à date ex dans les 365 derniers jours / clôture `close` à la date | FTSE §5.8 |
| `mdd_long` | Baisse maximale de l'historique long raccordé (proxy d'industrie de Kenneth French avant la cotation, HYPOTHÈSE); à défaut, fenêtre du jeu de départ (HYPOTHÈSE « fenêtre courte ») | δ des satellites |
| `liquidity_cad` | Médiane de clôture × volume sur 63 séances, en CAD | éligibilité |
| `momentum` | Rendement de 12 mois avant la date à 1 mois avant la date | FTSE §5.3, **sensibilité seulement** |

La momentum n'entre jamais dans le score : elle donne seulement un rang de sensibilité (`strat.sens.mom.rank.<titre>`).

## 5. Score par rangs

Pour chaque indicateur f du style, chaque titre individuel de l'univers reçoit une utilité en rang centile :
u_f = 1 − r / (n − 1), où r est le rang (0 = le mieux classé selon le sens s_f) parmi les n titres dont la valeur est
connue. Une valeur manquante, ou un rendement du dividende nul, vaut 0. Les rangs portent sur tous les titres
individuels de l'univers, éligibles ou non.

score = Σ w_f × u_f / Σ w_f + 0,10 × (nombre de bonus) − 0,10 × (exclusions de simple préférence touchées)

| Style | Indicateurs : sens × poids |
| --- | --- |
| Défensive | vol −1 × 2; beta −1 × 1; mdd_long −1 × 1; dividend_yield +1 × 1; corr_core −1 × 1 |
| Dynamique | corr_core −1 × 2; mdd_long −1 × 1; dividend_yield +1 × 1; vol −1 × 1 |
| Offensive | beta +1 × 2; corr_core −1 × 1; mdd_long −1 × 1 |

- **Bonus de style** : défensive, tag `defensive_sector`; offensive, tags `tech`, `tech_platform`,
  `consumer_discretionary`, `communication`; dynamique, aucun.
- **Bonus d'intérêt** : sociétés canadiennes (`canada`), santé (`healthcare`), technologie (`tech`). Un intérêt pour
  les dividendes ajoute 1 au poids de `dividend_yield` au lieu d'un bonus. L'énergie propre n'a aucun actif dans le
  jeu de départ : l'intérêt est signalé, sans effet.
- **Aucun bonus** sur le tag du secteur d'emploi, ni de style ni d'intérêt.
- Inspiration : les inclinaisons multiples de FTSE §6.1, avec des rangs au lieu de scores Z, plus robustes sur une
  vingtaine de titres.

## 6. Éligibilité (Facts `strat.ineligible.<titre>`)

Un titre est écarté, avec sa raison, s'il est exclu par le mandat de base; si sa baisse maximale longue est inconnue
ou **dépasse 80 %** (le δ des titres individuels de `risk_levels.yaml`); si sa liquidité est sous 5 M$ CAD; s'il
s'agit d'un titre de l'employeur; s'il appartient au secteur d'emploi, par le secteur du jeu de départ **ou** par le
tag du moteur; si l'investisseur ne veut que du CAD et que le titre est en USD; s'il porte un tag d'exclusion de
valeurs (absolue, ou tolérée seulement dans un fonds); si son secteur est déjà concentré dans le portefeuille
existant. Une exclusion de simple préférence n'écarte pas : elle pénalise le score.

## 7. Nombre de titres K, sélection et planchers

**K** (Fact `strat.K`) : 0 au niveau N0, pour un profil incomplet, si `conc.single_each` ou `conc.single_total` est
nul, en cas de faible littératie ou de débutant, et pour l'approche « fonds indiciels ». Sinon
K = min(base, ⌊w_total / w_each⌋), avec base = 3 pour l'approche « titres individuels » et 2 sinon (approche mixte
ou sans préférence). Excès de confiance : K − 1.

**Sélection** : les titres éligibles dans l'ordre du score, **au plus un par secteur**, jusqu'à K. Les titres
individuels non retenus sortent de l'univers investissable (`non_shortlisted: exclude`), sauf un titre demandé par
l'investisseur, qui n'en est pas retiré.

**Plancher d'un titre** (Fact `strat.floor.<titre>`) :
f = min(arrondi inférieur à 0,25 % de [φ_style × min(w_each, w_total / n)], 3 %), où n est le nombre de titres
retenus, w_each et w_total les plafonds `conc.single_each` et `conc.single_total`, et φ = 0,5 (défensive),
0,5 (dynamique), 0,75 (offensive), et φ divisé par 2 en cas d'excès de confiance. Un plancher sous 0,25 %, ou une
ligne sous 500 $ quand le montant est connu, est retiré.

## 8. Limites non bloquantes, faisabilité et repli

**Toutes les limites `strat.*` sont non bloquantes** (`strat.growth_floor`, `strat.floor.<titre>`,
`strat.sector_cap.<tag>`). L'optimiseur les applique comme contraintes; le Judge les contrôle et les affiche, sans
jamais refuser une proposition à cause du style, et une limite non bloquante ne masque jamais une limite bloquante.

Le mandat avec l'étape 0 doit rester faisable : optimisation puis Judge, sans nouvelle violation bloquante par
rapport au mandat de base. Sinon, repli dans cet ordre, chaque palier étant un Fact `strat.fallback.<i>` :

1. planchers des titres divisés par 2;
2. retrait des planchers, du dernier rang au premier;
3. plancher de croissance abaissé de 5 points à la fois, puis retiré;
4. retrait des plafonds sectoriels du style;
5. abandon de la sélection : retour au mandat de base.

Pendant le débat, un plancher `strat.*` ne peut jamais être relevé; si un amendement abaisse un plafond, les
planchers liés baissent avec lui : la prudence l'emporte sur le style. Les contrefactuels testent un style d'un cran
plus prudent et, si la gouvernance l'admet, d'un cran plus offensif. `strat.risk_cost` donne l'écart de CVaR
mensuelle dû au style, jamais un rendement.

## 9. Ce que l'étape 0 ne fait jamais

- Elle ne modifie ni le score de risque R, ni le niveau, ni e_cap, ni la perte acceptable l*, ni un budget `risk.*`.
- Elle ne relâche aucune limite : elle n'ajoute que des planchers et des plafonds plus stricts.
- Elle ne retire jamais une exclusion de valeurs du mandat de base.
- Elle n'utilise ni la momentum ni le rendement passé dans le score : « Celui qui a le meilleur rendement historique
  est le meilleur placement » est le piège à éviter (atelier BNCD, diapositive 6).
- Aucun nombre ne vient d'un modèle de langage; aucune transaction n'est passée (énoncé, p. 17).
