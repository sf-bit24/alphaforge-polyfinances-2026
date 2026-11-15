# Mateo : backtest 1926-2026, oracle a posteriori, stratégies ex-ante et rétro-ingénierie

> **Simulation historique uniquement.** Ce rapport ne constitue pas un conseil financier personnalisé. Il décrit
> le passé reconstitué à partir de proxys ; il ne prédit rien. Les lignes `ORACLE` (`hindsight=True`) utilisent
> le futur : elles ne sont **pas investissables** et ne servent qu'à la rétro-ingénierie. Tous les seuils
> ci-dessous sont des **propositions dérivées des données, à valider par l'équipe**.

Persona fictif (énoncé officiel) : 41 ans, gestionnaire des opérations, en couple, deux enfants, tolérance
modérée, horizon 8 à 12 ans, croissance équilibrée, grande importance des critères ESG, éviter les controverses,
pas de spéculation. Test officiel : intégrer des critères non financiers sans dénaturer l'équilibre
rendement/risque. De la fiche d'équipe (`source/profil-investisseur-mateo.md`), seuls ont été retenus
l'identité, le cadre RRTTLLU **qualitatif** (échéance probablement rigide liée aux enfants, fonds d'urgence hors
portefeuille, refus de la spéculation), les biais (cadrage éthique, comptabilité mentale, aversion au regret) et
l'exigence d'auditabilité. **Aucune** allocation, aucun seuil chiffré ni aucun « fait de marché » de la fiche
n'a été utilisé.

## 0. Références des traces (chaque chiffre cite l'une d'elles)

Chemins relatifs à `research/backtest/`. Les traces du moteur portent `engine_sha256`, `data_version`
(`data_sha256 = mateo_ext_5599152341587fba`, dérivé de `008f122d5da4f8f7`, voir §1), la graine 42 et le profil.

| id | fichier |
|---|---|
| A-L | `results/mateo_sens_usd_long_esg/20261114T222809Z_rolling_h10.json` (+ `..._222800Z_non_overlapping_h10.json`) |
| A-G | `results/mateo_sens_usd_gold_esg/20261114T222851Z_rolling_h10.json` |
| A-C | `results/mateo_sens_cad_esg/20261114T222915Z_rolling_h10.json` ; A-CS = `results/mateo_sens_cad_esgstrict/20261114T222927Z_rolling_h10.json` |
| A-grid | `results/mateo_analysis/stageA_grid.csv` (synthèse des 42 traces `results/mateo_sens_*`, colonne `trace`) |
| L-R / L-N | `results/mateo_usd_long_esg/20261115T000606Z_rolling_h10.json` / `..._20261114T234205Z_non_overlapping_h10.json` |
| G-R / G-N | `results/mateo_usd_gold_esg/20261114T235948Z_rolling_h10.json` / `..._234145Z_non_overlapping_h10.json` |
| C-R / C-N | `results/mateo_cad_esg/20261114T234928Z_rolling_h10.json` / `..._234337Z_non_overlapping_h10.json` |
| CS-R | `results/mateo_cad_esgstrict/20261114T235026Z_rolling_h10.json` |
| PRE | traces **antérieures au correctif moteur** (§13) : `analysis/mateo/pre_fix/runs_B_*.json` (index des traces), synthèses `results/mateo_analysis/pre_fix/` |
| base | mêmes ères, variante sans exclusion : `results/mateo_{usd_long,usd_gold,cad}_base/*` (liste exacte : `analysis/mateo/runs_B_*.json`) |
| X-era | `results/mateo_analysis/cross_era_esg.csv`, `cross_era_esg_agg.csv`, `cross_era_base.csv` (lus depuis L-R, G-R, C-R et les h8/h12) |
| WF | `results/mateo_analysis/extra.json` (walk-forward avec filtre de violations) et `walkforward_summary.csv` |
| ESG | `results/mateo_analysis/esg_cost.csv` (appariement base/esg par fenêtre × stratégie) et `esg_struct.json` |
| TECH | `results/mateo_analysis/tech_cap_grid.csv` (traces `results/mateo_*_tc{20,25,30,35}/*`) |
| GLIDE | `results/mateo_analysis/glide_{usd_long,usd_gold,cad}_esg_{annual,quarterly}.json` (après correctif) |
| REV | `results/mateo_analysis/reverse_corr.csv`, `reverse_consistency.csv`, `oracle_stability.csv`, `regimes.csv` |
| WIN | `results/mateo_analysis/per_window_h10.csv` |
| REAL | `results/mateo_analysis/real_check.json` (profil `profiles/mateo_real_tickers.yaml`) |

Reproduction : `analysis/mateo/build_ext_data.py` → `make_profiles.py A` → `batch.py A …` → `analyze_a.py` →
`make_profiles.py B` → `batch.py B_<n> …` (liste `analysis/mateo/jobs_B.txt`) → `glide.py`, `esg_struct.py`,
`analyze_b.py main esg tech reverse regimes cross`, `extra.py`, `real_check.py`. Toujours `.venv/bin/python -I`.

## 1. Question, données, ères, fenêtres

**Question.** Sur chaque fenêtre de la longueur de l'horizon de Mateo (10 ans ; sensibilité 8 et 12), quelle
combinaison d'actifs aurait été la meilleure a posteriori (oracle) et quelle stratégie ex-ante l'aurait
approchée, sous ses contraintes ; combien coûte l'exclusion ESG proxy ; quelles règles stables en ressortent.

**Données.** Couche partagée `data/processed` (Ken French, FRED, Shiller, Banque du Canada, datahub or,
yfinance, starter officiel ; voir `data/SOURCES.md`), **non modifiée**. Un seul actif synthétique a été ajouté
dans une copie (`analysis/mateo/data_ext/`, chargée via `ALPHAFORGE_BT_DATA`) :
`US_MKT_XEN` = marché US hors énergie = mélange pondéré par la capitalisation des 11 industries KF autres
que `Enrgy`, avec les parts de capitalisation KF du mois (taille de fin de mois t-1, donc sans anticipation).
Corrélation mensuelle avec `US_MKT` : 0,9953 (sortie de `build_ext_data.py`). Pourquoi : `US_MKT` contient
l'énergie (part 0,162 en 1926-07, 0,031 en 2026-09 selon `SOURCES.md`) ; exclure le seul tag `fossil_fuel`
laisserait donc l'énergie dans le cœur indiciel.

**Ères.**
1. `usd_long` : USD, 1926-08 → 2026-09 (limité par `UST_2Y`), sans or (non investissable avant 1975).
   Hypothèse de devise : investisseur USD (aucune conversion CAD possible avant 1971).
2. `usd_gold` : USD, 1975-01 → 2026-09, avec or.
3. `cad` : CAD (devise de référence de Mateo), 1977-01 → 2026-09 : `CA_EQ`, `US_MKT`/`US_MKT_XEN` convertis
   (non couverts), 6 secteurs US, `CA_GOV_10Y`, `UST_5Y`, or, `CA_TBILL`.

**Variantes.** `base` (cœur `US_MKT`, aucune exclusion) ; `esg` (cœur `US_MKT_XEN`, tag `fossil_fuel` exclu,
donc `US_IND_ENRGY`, `XOM`, `CNQ.TO`, `ENB.TO`) ; en CAD, `esgstrict` (exclut aussi `CA_EQ`, dont la part
énergie est inconnue faute de données sectorielles canadiennes). `_classes` = mêmes profils sans les 12
secteurs (oracle par classes d'actifs, plus lisible). Crypto exclue (préférence du profil).

**Fenêtres.** Non chevauchantes (10 en `usd_long`, 5 en `usd_gold`, 4 en `cad`) et roulantes au pas de 12 mois
(91, 42, 40 fenêtres). **Les fenêtres roulantes se chevauchent à 90 %** : leur nombre n'est pas un nombre
d'observations indépendantes (environ 10, 5 et 4 décennies distinctes).

**Stratégies ex-ante** (profil généré par `analysis/mateo/make_profiles.py`, identique entre variantes) :
mélanges statiques 40/50/60/70/80 % d'actions (poche obligataire en échelle 2/5/10 ans US, ou 50 % `CA_GOV_10Y`
+ 50 % `UST_5Y` en CAD ; en CAD la poche actions est 50 % `CA_EQ` + 50 % cœur US), 60 % + 10 % or, glidepath
linéaire 70→40, glidepaths retardés (dé-risquage à partir de l'année 3, 5, 7, 8 ou 9 ; type `delayed_glidepath`
ajouté par `analysis/mateo/common.py` ; convention : poids de départ tenus jusqu'au mois `ceil(derisk_start × n)` écoulé
— mois 60 pour « année 5 » quelle que soit la fréquence —, puis interpolation linéaire jusqu'aux poids finaux,
atteints à la **dernière décision** de la fenêtre : mois 108 en annuel, 117 en trimestriel, 119 en mensuel ; en annuel,
« année 9 » = statique car il ne reste aucune décision après le mois 108), parité de risque inverse-vol 36 mois, min-variance 60 mois, max-Sharpe,
moyenne-variance (aversion 4 et 10), filtre de tendance 10 mois, momentum sectoriel top 3, momentum dual top 2
(classes). Coûts 10 pb par unité échangée, rééquilibrage annuel par défaut.

**Objectif.** `min_shortfall` avec cible réelle 0 % : score = rendement réel annualisé de la fenêtre ; la
sélection robuste maximise le **10e centile** du score entre fenêtres. Oracle = meilleur mélange constant
rebalancé mensuellement, pénalisé au-delà des limites de risque.

## 2. Seuils dérivés (propositions à valider)

Méthode : étape A = grille de mélanges statiques 0 à 100 % d'actions, sans contrainte ni limite, puis règles
lisibles. Valeurs dans A-grid (vue roulante 10 ans).

| seuil | valeur proposée | règle de dérivation | chiffres d'appui |
|---|---|---|---|
| cible réelle (`target_real_return`) | **0 %/an** | capacité : l'échéance (enfants) est rigide, donc le minimum est de ne pas perdre de pouvoir d'achat sur l'horizon | A-L : P(réel < 0) = 0,352 à 0 % d'actions, 0,110 à 60 % |
| part d'actions de politique | **60 %** | (i) la vol médiane reste sous le point médian « modéré » entre 100 % obligations et 100 % actions ; (ii) dans le plateau du 10e centile réel | point médian de vol : 0,0992 (A-L), 0,1008 (A-G), 0,0968 (A-C) ; part max sous ce point : 60 %, 60 %, 70 % ; argmax du 10e centile réel en A-L = 60 % (−0,03 %/an), plateau à 0,5 pt : 50-80 % |
| bande d'actions (contrainte dure) | **[40 %, 80 %]** | politique ± 20 pts, couvre les plateaux USD | plateau A-G : 50-100 % ; A-C : 70-100 % |
| `max_vol` | **10 %** | point médian « modéré » ci-dessus, arrondi | 0,0968 à 0,1008 |
| `max_drawdown` | **20 %** | 90e centile de la perte maximale du mélange 60 % dans l'ère CAD (devise de Mateo), arrondi au 5 pts supérieur | 0,1785 (A-C) ; à titre de comparaison 0,2994 en A-L |
| plafond tech look-through | **30 %** | plus petit plafond qui ne force pas une sous-pondération active de la tech du cœur ESG actuel, sans coût mesurable sur le 10e centile | voir §6 |
| début du dé-risquage | **année 5** (horizon résiduel ≤ 5 ans), de 70 % à 40 % | meilleur compromis entre risque des 36 derniers mois et 10e centile réel | voir §7 |
| taux de violation toléré pour la sélection | **≤ 25 % des fenêtres** | une décennie sur quatre au plus hors limites ; sensibilité à 50 % et sans filtre fournie | robust_all.csv |

Tension à faire trancher : avec ces limites, le mélange 60 % viole vol ou perte maximale dans 60,4 % des
fenêtres USD 1926+ et 66,7 % des fenêtres USD 1975+, mais seulement 15 % en CAD (X-era). Les limites dérivées en
CAD sont donc plus strictes que ce que le 60/40 a vécu en USD long. Deux options : garder 10 %/20 % (le choix
robuste tombe alors vers ~40 % d'actions, §4) ou relâcher la perte maximale vers le niveau USD (≈ 30 %).

## 3. Résultats par fenêtre (non chevauchantes, 10 ans, variante ESG)

Oracle = poids constants a posteriori. « Meilleure ex-ante » = meilleure stratégie sur la fenêtre **a
posteriori** (elle n'était pas identifiable à l'avance). Écart = score oracle − score meilleure ex-ante.
Sources : L-N, C-N (et G-N dans WIN).

**USD 1926+ (L-N)**

| fenêtre | oracle : réel / vol / perte max | oracle : principales lignes | meilleure ex-ante (réel / perte max) | écart |
|---|---|---|---|---|
| 1926-08..1936-07 | 8,47 % / 10,0 % / 26,2 % | UST_5Y 0,54 ; NODUR 0,26 ; TELCM 0,14 | max_sharpe_60 (13,81 % / 51,5 %) | −5,34 pts |
| 1936-08..1946-07 | 4,69 % / 10,0 % / 19,2 % | CORP_AAA 0,48 ; HLTH 0,36 ; SHOPS 0,16 | static_eq80 (3,28 % / 40,2 %) | 1,41 |
| 1946-08..1956-07 | 9,57 % / 10,0 % / 13,4 % | UST_10Y 0,26 ; MANUF 0,24 ; UTILS 0,19 | static_eq80 (8,24 % / 16,3 %) | 1,33 |
| 1956-08..1966-07 | 10,51 % / 10,0 % / 20,0 % | HLTH 0,41 ; UTILS 0,19 ; DURBL 0,17 | sector_mom12_top3 (8,38 % / 15,4 %) | 2,13 |
| 1966-08..1976-07 | 1,34 % / 9,4 % / 20,0 % | UST_2Y 0,49 ; CHEMS 0,31 ; HLTH 0,13 | sector_mom12_top3 (1,26 % / 16,1 %) | 0,08 |
| 1976-08..1986-07 | 10,76 % / 10,0 % / 8,0 % | NODUR 0,53 ; TELCM 0,22 ; T-bills 0,14 | static_eq80 (7,70 % / 11,6 %) | 3,06 |
| 1986-08..1996-07 | 9,51 % / 10,0 % / 15,7 % | CORP_AAA 0,46 ; NODUR 0,28 ; CHEMS 0,13 | static_eq80 (8,17 % / 23,5 %) | 1,33 |
| 1996-08..2006-07 | 9,05 % / 10,0 % / 12,3 % | CORP_AAA 0,35 ; MONEY 0,30 ; MANUF 0,18 | mean_var_60_ra4 (6,84 % / 16,2 %) | 2,21 |
| 2006-08..2016-07 | 9,51 % / 8,5 % / 20,0 % | NODUR 0,57 ; UST_20Y 0,33 ; HLTH 0,09 | sector_mom12_top3 (6,48 % / 20,9 %) | 3,03 |
| 2016-08..2026-07 | 9,19 % / 10,0 % / 16,6 % | BUSEQ 0,42 ; T-bills 0,40 ; UTILS 0,13 | static_eq80 (8,85 % / 23,0 %) | 0,35 |

Lecture : l'oracle sature presque toujours la limite de vol (10 %) et choisit des secteurs différents à chaque
décennie (aucun secteur ne revient de façon stable). Sur 1926-1936, une stratégie ex-ante bat l'oracle constant
car elle est dynamique (normal, voir README §7) mais avec une perte maximale de 51,5 %, incompatible avec le
profil.

**CAD 1977+ (C-N)**

| fenêtre | oracle : réel / vol / perte max | oracle : principales lignes | meilleure ex-ante (réel / perte max) | écart |
|---|---|---|---|---|
| 1977-01..1986-12 | 12,34 % / 10,0 % / 8,5 % | NODUR 0,58 ; CA_TBILL 0,16 ; or 0,13 ; UTILS 0,13 | dual_mom12_top2 (12,27 % / 9,8 %) | 0,07 |
| 1987-01..1996-12 | 11,79 % / 10,0 % / 16,4 % | NODUR 0,46 ; CA_GOV_10Y 0,42 ; HLTH 0,12 | sector_mom12_top3 (10,42 % / 18,8 %) | 1,37 |
| 1997-01..2006-12 | 8,97 % / 10,0 % / 19,8 % | CA_EQ 0,50 ; CA_GOV_10Y 0,20 ; MONEY 0,16 | mean_var_60_ra4 (7,18 % / 24,3 %) | 1,79 |
| 2007-01..2016-12 | 10,06 % / 9,1 % / 9,4 % | NODUR 0,80 ; or 0,20 | dual_mom12_top2 (6,59 % / 8,8 %) | 3,47 |

## 4. Choix robuste et walk-forward

**Classement par ère (roulant 10 ans, ESG, 10e centile du rendement réel, X-era).**

| stratégie | USD 1926+ p10 / violations | USD 1975+ p10 / violations | CAD 1977+ p10 / violations | actions moy. |
|---|---|---|---|---|
| risk_parity_iv36 | −0,15 % / 7,7 % | 2,54 % / 0 % | 3,81 % / 0 % | 0,41 |
| static_eq60 | −0,03 % / 60,4 % | 3,48 % / 66,7 % | 3,61 % / 15,0 % | 0,61 |
| static_eq60_gold | n.d. (pas d'or) | 4,05 % / 66,7 % | 4,15 % / 15,0 % | 0,61 |
| dual_mom12_top2 | 0,52 % / 25,3 % | 5,17 % / 40,5 % | 3,93 % / 10,0 % | 0,47 |
| glide_delay5y_70_40 | −0,10 % / 62,6 % | 3,20 % / 69,0 % | 3,60 % / 52,5 % | 0,63 |
| static_eq40 | −0,78 % / 7,7 % | 2,89 % / 0 % | 3,02 % / 0 % | 0,41 |

**Règle de sélection inter-ères** (X-era, `cross_era_esg_agg.csv`) : parmi les stratégies dont le taux de
violation est ≤ 25 % dans **chaque** ère, maximiser le pire 10e centile. Résultat : **`risk_parity_iv36`**
(pire p10 −0,15 %, violation max 7,7 %, pire perte maximale 40,4 %, en USD 1926+), devant min-variance
(−0,42 %) et moyenne-variance aversion 10 (−0,44 %). Sans filtre de violations, le classement favorise les
momentums et les mélanges à 80 % d'actions (robust_all.csv), ce qui ne respecte pas le profil modéré.

Deux observations à garder visibles :
- `risk_parity_iv36` est **en pratique un portefeuille ~40 % actions** : l'inverse-vol pousse vers les
  obligations, puis la projection sur la bande d'actions remonte la poche actions au plancher de 40 %. En USD,
  la projection (moindres carrés) répartit ce plancher également entre le cœur et les 11 secteurs (≈ 0,029
  chacun, 0,084 sur `US_MKT_XEN` ; extra.json) : la poche actions est donc quasi équipondérée par secteur, pas
  pondérée par la capitalisation. Comportement attendu de `ConstraintSet.project`, mais à savoir.
- En CAD seul (devise de Mateo), `static_eq60_gold` a le meilleur p10 éligible (4,15 %, violations 15 %), puis
  dual momentum (3,93 %) et parité de risque (3,81 %) (C-R). Le choix inter-ères est plus prudent car il
  intègre 1929-1945 et les années 1970.

**Walk-forward** (choix fait uniquement sur des fenêtres terminées avant la fenêtre évaluée ; WF) :

| ère (ESG, roulant) | filtre violations | n hors échantillon | moyenne | p10 | P(réel < 0) | écart moyen à l'oracle | stratégies choisies |
|---|---|---|---|---|---|---|---|
| USD 1926+ | ≤ 25 % | 79 | 4,87 % | −0,83 % | 16,5 % | 4,25 pts | dual_mom 33, risk_parity 20, eq80 10, … |
| USD 1926+ | aucun | 79 | 5,59 % | 0,40 % | 8,9 % | 3,54 pts | sector_mom 58, eq80 11, … |
| USD 1975+ | ≤ 25 % | 30 | 4,35 % | 1,29 % | 0 % | 6,60 pts | eq40 12, risk_parity 10, … |
| CAD 1977+ | ≤ 25 % | 28 | 6,14 % | 2,09 % | 0 % | 6,05 pts | mean_var_ra4 8, dual_mom 6, max_sharpe 6, … |

Lecture : le **coût de ne pas connaître le futur** (écart à l'oracle) est de 4 à 7 points de rendement réel
par an en moyenne ; le choix walk-forward change souvent de stratégie (instabilité de sélection), ce qui
plaide pour une règle simple et stable plutôt qu'une sélection dynamique de stratégie.

**Sensibilité à l'horizon** (X-era, `cross_era_esg.csv`, roulant, ESG, p10 du rendement réel pour 8 / 10 / 12 ans) :
risk_parity_iv36 = CAD 2,84 % / 3,81 % / 3,76 % ; USD 1975+ 2,34 % / 2,54 % / 2,91 % ; USD 1926+ −0,15 % / −0,15 % / 0,25 %.
static_eq60 = CAD 3,49 % / 3,61 % / 3,47 % ; USD 1975+ 2,40 % / 3,48 % / 2,80 % ; USD 1926+ 0,14 % / −0,03 % / 0,14 %.
Le classement relatif ne change pas de nature avec l'horizon.

## 5. Coût de l'exclusion ESG proxy (résultat central)

Comparaison appariée (même fenêtre, même stratégie) variante `esg` − variante `base`, en points de rendement réel
annualisé (ESG).

**Structure du cœur actions** (esg_struct.json, `US_MKT_XEN` − `US_MKT`, fenêtres 10 ans) :
- USD 1926+ roulant (91) : médiane +0,05 pt/an, 10e centile −0,62 pt, pire −1,15 pt, meilleur +0,94 pt ;
  l'exclusion fait mieux dans 53,8 % des fenêtres ; vol +0,10 pt (médiane) ; perte max +0,60 pt (médiane),
  +2,22 pts au pire ; écart de suivi médian 1,57 %/an ; diversification : nombre effectif d'industries −0,90.
- CAD 1977+ roulant (40) : médiane +0,20 pt, 10e centile −0,33 pt, pire −0,57 pt ; meilleur dans 75 % des
  fenêtres ; perte max +0,65 pt (médiane), +3,37 pts au pire.
- La part d'énergie retirée variait de 0,055 à 0,208 de la capitalisation au début des fenêtres non
  chevauchantes USD (pic 1956).

**Portefeuilles du profil** (ESG, roulant 10 ans) :

| stratégie | ère | médiane | 10e centile de l'écart | pire écart | Δ vol médiane | Δ perte max médiane |
|---|---|---|---|---|---|---|
| static_eq60 | USD 1926+ | +0,04 pt | −0,38 pt | −0,67 pt | +0,07 pt | +0,44 pt |
| static_eq60 | CAD | +0,07 pt | −0,09 pt | −0,18 pt | +0,03 pt | +0,22 pt |
| risk_parity_iv36 (choix robuste) | USD 1926+ | −0,03 pt | −0,23 pt | −0,35 pt | +0,09 pt | +0,39 pt |
| risk_parity_iv36 | CAD | +0,02 pt | −0,14 pt | −0,22 pt | +0,08 pt | +0,07 pt |
| sector_mom12_top3 | USD 1926+ | −0,19 pt | −1,16 pt | −1,89 pt | −0,09 pt | 0 |
| ORACLE (secteurs) | USD 1926+ | −0,03 pt | −1,05 pt | −3,35 pt | 0 | 0 |
| ORACLE (classes) | CAD | +0,04 pt | −0,01 pt | −0,09 pt | 0 | 0 |

**Exclusion stricte en CAD** (retirer aussi `CA_EQ`, CS-R vs base) : static_eq60 10e centile de l'écart
−3,04 pts, pire −3,50 pts, perte max médiane +1,81 pt ; le p10 du niveau passe de 3,70 % à 0,85 % ; oracle
classes 10e centile −3,88 pts. Paradoxe : la médiane de l'écart est positive (+1,35 pt, la période 1977-2026 ayant favorisé les actions US) mais la queue est bien pire. Ce coût de queue vient surtout de la perte de la poche actions en devise locale (actions
US non couvertes = risque de change), **pas** de l'exclusion de l'énergie elle-même.

**Période réelle 2021-11..2026-09** (REAL, vrais tickers, CAD) : panier équipondéré des 20 actions du starter
17,50 %/an réel contre 16,20 % sans XOM, CNQ.TO, ENB.TO (−1,30 pt), perte max 13,6 % contre 19,7 % : sur cette
période où l'énergie a monté, l'exclusion a coûté en rendement **et** en risque. ESGV au lieu de SPY dans le
mélange 60 % : 5,37 % contre 5,73 % (−0,36 pt), mais ESGV exclut plus que l'énergie (sa méthodologie n'est pas
dans nos données).

Conclusion (marquée **robuste** pour le signe et l'ordre de grandeur, **fragile** pour la valeur exacte) :
sur un siècle, l'exclusion sectorielle du fossile a un coût **médian quasi nul** pour un portefeuille diversifié
(±0,1 pt/an) avec une **queue défavorable de l'ordre de −0,2 à −0,7 pt/an** sur une décennie et un peu plus de
perte maximale ; le coût grandit avec la concentration de la stratégie (momentum sectoriel, oracle). Une
exclusion mal outillée (retirer tout le marché canadien faute de données) coûte dix fois plus.

## 6. Dérive tech induite et plafond tech

- Dérive structurelle (esg_struct.json) : la part BusEq de `US_MKT_XEN` dépasse celle de `US_MKT` de +1,16 pt
  en médiane (USD roulant), +2,17 pts au maximum ; elle vaut aujourd'hui 0,4495 (part 2026-09 rescalée,
  `data_ext/assets.csv`). Un portefeuille 60 % actions US ESG aurait donc ≈ 27 % de tech look-through
  aujourd'hui (0,60 × 0,4495).
- Exposition tech moyenne du mélange 60 % (au début des fenêtres) : 0,0692 ESG contre 0,0619 base (USD 1926+),
  maximum 0,2075 ESG (TECH). Les stratégies concentrées dérivent davantage : momentum sectoriel jusqu'à 0,2975,
  oracle jusqu'à 0,5125 (fenêtres récentes, BusEq).
- Grille de plafonds (ESG, roulant, TECH) : le 10e centile du meilleur choix sans filtre de violations ne bouge pas (USD 1926+ 1,09 % à 1,08 %
  de 35 % à 20 % ; USD 1975+ 5,17 % ; CAD 4,15 %) ; l'oracle médian perd 0,14 pt à 30 % et 0,36 pt à 25 % en USD
  1926+ (8,89 % → 8,75 % → 8,53 %), rien en CAD.
- Règle proposée : **plafond 30 %** = plus petit niveau de la grille au-dessus de la tech structurelle actuelle
  d'un 60 % ESG US (≈ 27 %), donc il ne contraint que les paris actifs (momentum, optimiseurs) ; 25 % serait
  contraignant aujourd'hui pour un portefeuille indiciel. Limite : `CA_EQ`, XIU.TO, AGG, XBB.TO sont comptés à
  0 % de tech faute de données de détention, et ESGV est approché par la part tech de `US_MKT`, donc la tech
  réelle est sous-estimée.

## 7. Glidepath et date de dé-risquage (GLIDE)

Après le correctif moteur du 2026-11-14 (§13), les glidepaths atteignent leurs poids finaux à la dernière décision
quelle que soit la fréquence. Tableau = rééquilibrage **annuel** (celui du profil), fenêtres roulantes 10 ans, ESG ;
`glide_*_esg_annual.json`. Mesure clé pour une échéance fixe : perte maximale dans les **36 derniers mois**.

| stratégie | actions moy. | p10 réel USD 1926+ / 1975+ / CAD | médiane réelle USD 1926+ / 1975+ / CAD | perte max 36 derniers mois, 90e centile USD 1926+ / 1975+ / CAD |
|---|---|---|---|---|
| static_eq60 | 0,60 | −0,03 % / 3,48 % / 3,61 % | 5,48 % / 6,58 % / 7,04 % | 20,4 % / 19,8 % / 14,6 % |
| glidepath linéaire 70→40 | 0,55 | −0,17 % / 3,37 % / 3,61 % | 4,83 % / 6,96 % / 6,88 % | 15,7 % / 16,6 % / 12,3 % |
| dé-risquage dès l'année 3 | 0,60 | −0,17 % / 3,04 % / 3,43 % | 5,20 % / 7,28 % / 7,10 % | 16,1 % / 16,7 % / 12,3 % |
| **dé-risquage dès l'année 5**, 70→40 | 0,63 | −0,10 % / 3,20 % / 3,60 % | 5,62 % / 7,44 % / 7,08 % | 16,6 % / 17,6 % / 12,3 % |
| dé-risquage dès l'année 7 | 0,66 | 0,02 % / 3,38 % / 3,88 % | 5,96 % / 7,18 % / 7,13 % | 20,1 % / 18,9 % / 14,2 % |
| dé-risquage dès l'année 8 | 0,67 | −0,31 % / 3,55 % / 3,68 % | 6,01 % / 7,28 % / 7,22 % | 21,3 % / 22,0 % / 17,8 % |

Règle dérivée (**inchangée** par le correctif ; **robuste** sur les 3 ères, mais N effectif petit) : démarrer le
dé-risquage quand l'horizon résiduel passe sous **5 ans** (mois 60). Par rapport au 60 % statique, il réduit le
90e centile de perte des 36 derniers mois de 3,8, 2,1 et 2,3 pts, pour un 10e centile réel inférieur de 0,07,
0,28 et 0,01 pt et une médiane **plus élevée dans les trois ères**. Un départ à l'année 3 ou un glidepath linéaire
protègent autant la fin d'horizon mais avec une médiane plus basse en USD 1926+ ; un départ à 7 ans a le meilleur
10e centile mais ne protège presque plus la fin d'horizon (réduction de 0,3 à 0,9 pt seulement) ; à 8 ans, la fin
d'horizon est plus risquée qu'en statique. En trimestriel (`glide_*_esg_quarterly.json`), même conclusion :
dé-risquage dès l'année 5 = p10 −0,14 % / 3,10 % / 3,45 %, perte des 36 derniers mois 18,1 % / 17,1 % / 12,1 %.

## 8. Rétro-ingénierie (REV)

Oracle « classes » (ESG) : actions moyennes 0,57 (USD 1926+), 0,53 (USD 1975+), 0,61 (CAD), écart-type 0,12 à
0,15, collées aux bornes 0,40 et 0,80 dans de nombreuses fenêtres ; obligations 0,38 / 0,31 / 0,18 avec un
écart-type ≈ 0,19 à 0,21 ; or (quand disponible) 0,15 / 0,19 avec écart-type 0,20 à 0,23 (oracle_stability.csv).

Corrélations de Spearman entre variables observées **à la fin du mois précédant la fenêtre** et poids de
l'oracle (6 échantillons = 3 ères × {non chevauchant, roulant} ; N = 4 à 91, roulant chevauchant ; p-values naïves
non valides). Classement : **robuste** = même signe dans tous les échantillons et |ρ| ≥ 0,3 dans la plupart ;
**fragile** = même signe mais faible ou une seule période de taux ; **non concluant** sinon.

| # | règle | chiffres (ρ) | niveau |
|---|---|---|---|
| R1 | Plus le taux long de départ est élevé, plus l'oracle détient d'obligations | 0,80 / 0,74 (CAD), 0,90 / 0,71 (USD 1975+), 0,28 / 0,37 (USD 1926+) | **robuste** (signe), force modérée sur le siècle |
| R2 | Plus le taux réel court de départ est élevé, plus l'oracle détient d'obligations | 0,40 / 0,61, 0,70 / 0,48, 0,39 / 0,39 | **robuste** |
| R3 | Taux longs élevés au départ → plus de duration longue (20 ans, Aaa) | 0,82 / 0,43 (USD 1975+), 0,41 / 0,22 (USD 1926+) | **fragile** |
| R4 | Taux de départ élevés → moins d'or ; CAPE élevé → plus d'or | long : −0,63 / −0,70, −0,89 / −0,55 ; CAPE : −0,21 / 0,75, 0,78 / 0,65 | **fragile** (un seul cycle de désinflation 1980-2020) |
| R5 | Part d'actions vs CAPE, tendance, momentum, pente | signes contradictoires (ex. CAPE : 0,80 / −0,12 / −0,70 / −0,35 / −0,07 / −0,28) | **non concluant** |
| R6 | Description ex post : quand les taux longs montent de plus d'1 pt sur la fenêtre, l'oracle évite la duration longue (0,0011 en USD 1926+, 0,0052 en USD 1975+) et détient du cash (0,14) ; quand ils baissent, duration longue 0,41 / 0,34 | regimes.csv | **robuste** comme description, **non observable** au départ |
| R7 | Fenêtres contenant 2022 (12 fenêtres roulantes) : oracle quasi sans obligations (≤ 0,084, sauf une fenêtre à 0,103) et remplacées par cash (USD 1926+) ou or (USD 1975+, CAD) | regimes.csv | **fragile** (un seul épisode) |
| R8 | Aucun secteur n'est stable d'une décennie à l'autre dans l'oracle sectoriel (§3) ; seuls les défensifs NODUR/HLTH/UTILS reviennent souvent | WIN | **robuste** comme constat d'instabilité |

Règles transformables en stratégie à tester ensuite (hors périmètre ici) : (a) moduler la part obligataire (et
sa duration) avec le niveau du taux long et du taux réel au départ (R1-R3), à l'intérieur de la bande
[40 %, 80 %] ; (b) ne pas tenter de chronométrer la part d'actions avec CAPE ou la tendance (R5) ; (c) garder une
petite poche or comme diversifiant à évaluer, sans en faire un pari (R4, R7).

## 9. Traduction en tickers et vérification 2021-11..2026-09 (REAL)

Correspondance (assets.csv) : `US_MKT_XEN` → ESGV (approximation : ESGV exclut plus que l'énergie) ; `CA_EQ`
→ XIU.TO (**contient de l'énergie, non filtrée**) ; `CA_GOV_10Y` → XBB.TO ; `UST_5Y` → AGG ; or → GLD ;
cash → ZST.TO. Contraintes : bande d'actions [40 %, 80 %], limites 10 % vol / 20 % perte max, CAD, coûts 10 pb.

| stratégie (variante ESG, sauf mention) | poids moyens | réel/an | vol | perte max | violations |
|---|---|---|---|---|---|
| **risk_parity_iv36** (choix robuste) | ESGV 0,200 ; XIU.TO 0,209 ; XBB.TO 0,253 ; AGG 0,239 ; GLD 0,099 | 4,81 % | 7,45 % | 12,1 % | aucune |
| static_eq60 | ESGV/XIU.TO 0,30/0,30 ; XBB.TO/AGG 0,20/0,20 | 5,37 % | 8,88 % | 14,0 % | aucune |
| static_eq60_gold | + GLD 0,10 | 7,36 % | 8,80 % | 13,1 % | aucune |
| dual_mom12_top2 | ESGV 0,439 ; GLD 0,405 ; ZST.TO 0,110 | 11,77 % | 10,18 % | 13,2 % | vol > 10 % |
| glidepath compressé 70→40 (dé-risquage au mois 30, fin à la dernière décision trimestrielle) | — | 5,12 % | 9,31 % | 14,6 % | aucune |
| risk_parity_iv36, variante base (SPY) | SPY 0,206 ; XIU.TO 0,204 ; … | 5,08 % | 7,29 % | 11,3 % | aucune |
| risk_parity_iv36, variante stricte (sans XIU.TO) | ESGV 0,408 ; XBB.TO 0,263 ; AGG 0,248 ; GLD 0,082 | 4,56 % | 8,14 % | 14,9 % | aucune |

Lecture : sur la seule période réelle, la parité de risque ESG respecte les limites dérivées et reste au-dessus
de la cible réelle 0 % ; les variantes avec or ou momentum ont mieux fait parce que l'or a fortement monté sur la
période (une seule période de 5 ans, moitié de l'horizon : ce n'est pas une validation). Le glidepath compressé
sur 5 ans est une illustration, pas la politique sur 10 ans.

Formulation de simulation : *dans cette simulation, la stratégie la plus robuste entre les ères, sous les
contraintes dérivées pour le profil de Mateo, aurait été une parité de risque inverse-vol sur ESGV / XIU.TO /
XBB.TO / AGG / GLD avec un plancher de 40 % d'actions ; ce n'est pas une recommandation.*

## 10. Signaux candidats pour l'étape 2 (à tester, non testés ici)

- Taux : niveau du 10 ans, taux réel court (T-bill − inflation 12 mois), pente 10 ans − 3 mois, variation 12 mois
  du 10 ans ; versions canadiennes (BdC, OCDE) ; vintages ALFRED pour éviter les révisions.
- Inflation : IPC 12 mois et surprise d'inflation ; régime croissance × inflation ; signe de la corrélation
  actions-obligations sur 36 mois (2022).
- Crédit : écart Baa − Aaa (disponible), écarts OAS.
- Valorisation : CAPE (Shiller, s'arrête en 2024-09 dans nos données), rendement des bénéfices − taux réel.
- ESG (manquant) : listes de controverses datées par émetteur (rapports de durabilité, SEDAR+, EDGAR, actualités
  GDELT), compositions datées de ESGV et XIU.TO (part énergie et tech réelles), méthodologie d'indice ESG datée.
- Actualité / politique : incertitude de politique économique (EPU Canada), risque géopolitique (GPR), annonces
  BdC / FOMC.
- Fondamentaux : ratios de qualité (marges, endettement) des émetteurs du starter via EDGAR/SEDAR+.

## 11. Limites

- **Proxys** : 12 industries SIC de Ken French ≠ GICS ; exclusion « fossile » = SIC pétrole, gaz, charbon
  seulement (les gazoducs SIC 4922 restent dans `Utils`, ENB.TO n'est donc qu'en partie couvert par le proxy) ;
  aucune exclusion sociale (tabac, armement) possible avec ces données.
- **Pas de données ESG** : ni notes, ni controverses datées. ESGV n'a pas d'historique ESG propre (avant 2018 =
  marché US). Toute liste de controverses par ticker exige une source datée ; nous n'en avons pas, d'où la seule
  exclusion sectorielle.
- `CA_EQ` / XIU.TO : part énergie et tech inconnues (pas de données sectorielles canadiennes) ; la variante
  stricte les exclut, avec un coût élevé dû au change.
- Obligations synthétiques construites sur des moyennes mensuelles de taux avant 1962 et pour le Canada 10 ans :
  volatilité sous-estimée (flatte parité de risque et min-variance sur la période ancienne) ; obligations de
  sociétés sans défaut (rendement surestimé).
- Or non investissable avant ~1975 (exclu de l'ère 1926+) ; CAD seulement depuis 1971 (ère CAD dès 1977).
- Perte maximale calculée en nominal ; CAPE avec léger décalage de publication des bénéfices ; séries FRED/OCDE
  révisées (pas de vintages).
- Biais du survivant (univers choisi en 2026) ; pas de frais de gestion ni d'impôts (REEE, CELI, REER non modélisés).
- N petit : 10 décennies USD, 5 en USD 1975+, 4 en CAD ; les fenêtres roulantes se chevauchent ; corrélations
  descriptives, **aucune conclusion causale**.
- Seuils dérivés par des règles choisies par nous (point médian « modéré », 90e centile, arrondis) : d'autres
  règles raisonnables donneraient d'autres valeurs, d'où le statut de proposition.

**Moteur : comportements signalés (non modifiés, contournés dans `analysis/mateo/`)**
1. Look-through variable dans le temps limité à `US_MKT` (et aux tickers dont `proxy_for_ticker = US_MKT`) : un
   actif dérivé comme `US_MKT_XEN` n'en bénéficie pas → contourné par un enrobage de
   `engine.constraints.exposure_vector` (`common.py`).
2. **Corrigé dans le moteur le 2026-11-14** : avec un rééquilibrage annuel, la dernière cible d'un glidepath était
   fixée à 90 % de l'horizon (`progress = i / n`) et n'atteignait jamais ses poids finaux. Désormais `progress = i /
   dernier mois de décision`. `delayed_glidepath` a été adapté (voir §1) et tous les runs concernés relancés (§13).
3. `project()` remplit un plancher de groupe en répartissant le manque également entre actifs admissibles
   (parité de risque → poche actions équipondérée par secteur). Pas un bug, mais un effet de construction.
4. Avertissement `invalid value encountered in log1p` pendant l'optimisation de l'oracle (poids extrêmes
   intermédiaires) ; sans effet sur les résultats finaux observés.
5. `load_profile` refuse les types de stratégie non listés : `delayed_glidepath` ajouté à l'exécution.
   Les profils `profiles/mateo*.yaml` utilisent `US_MKT_XEN` et doivent donc être lancés via
   `analysis/mateo/run_mateo.py` ou `batch.py` (pas avec `engine.run` seul).

## 12. Les quatre questions

- **Quelles données ?** Rendements mensuels 1926-2026 de proxys publics (Ken French, FRED, Shiller, Banque du
  Canada, or datahub, yfinance, starter officiel), un actif dérivé « marché US hors énergie » et les tickers réels
  du starter pour 2021-11..2026-09 ; aucune donnée ESG.
- **Pourquoi ce choix ?** Parce que, sous des limites dérivées pour un profil modéré à échéance rigide (vol 10 %,
  perte max 20 %, bande d'actions 40-80 %), la parité de risque inverse-vol est la seule stratégie testée qui
  reste sous 25 % de fenêtres hors limites dans les trois ères tout en ayant le meilleur pire 10e centile ; et
  parce que l'exclusion du fossile y coûte peu en médiane (−0,03 à +0,02 pt/an) avec une queue de −0,14 à
  −0,23 pt/an.
- **Quelles limites ?** Proxys sectoriels, pas d'ESG réel ni de controverses, `CA_EQ`/XIU.TO non filtrés,
  obligations anciennes lissées, N petit, aucun frais ni impôt, passé ≠ futur.
- **Qu'est-ce qui changerait la réponse ?** Relâcher la perte maximale tolérée vers 30 % (le 60 % statique ou le
  dual momentum deviendraient éligibles) ; un horizon plus court (dé-risquage plus tôt) ; des données ESG datées
  (exclusions par émetteur, exposition réelle de XIU.TO) ; une exclusion stricte du marché canadien (coût ≈ −3 pts
  au 10e centile en CAD) ; un régime de taux montants comme 1950-1980, où l'oracle évite la duration longue.

## 13. Correctif moteur 2026-11-14 : avant / après

Le moteur calcule maintenant `ctx.progress = i / (dernier mois de décision)` au lieu de `i / n`. `delayed_glidepath`
(`analysis/mateo/common.py`) a été réécrit pour garder « année 5 » = mois 60 écoulé pour toute fréquence (test dans
le code : annuel 60→0, 72→0,25, 108→1 ; trimestriel 117→1 ; mensuel 119→1). Les 104 runs de l'étape B, `glide.py`
(annuel et trimestriel) et `real_check.py` ont été relancés. Avant = PRE (`results/mateo_analysis/pre_fix/`), après
= X-era, GLIDE, REAL actuels.

- **Seules les stratégies glidepath changent** : comparaison ligne à ligne des synthèses `cross_era_esg.csv` avant/après
  (6 stratégies modifiées, toutes de type glidepath) ; ORACLE, statiques, optimiseurs, momentum, corrélations
  (`reverse_corr.csv`, 0 ligne modifiée), régimes, stabilité de l'oracle : identiques.
- **Choix robuste inchangé** : `risk_parity_iv36` (pire p10 −0,15 %, violation max 7,7 %) avant et après
  (`cross_era_esg_agg.csv`). Walk-forward : seule la répartition des choix en USD 1926+ base sans filtre bouge de
  façon négligeable (moyenne 5,866 % → 5,865 %, extra.json) ; walk-forward ESG identique.
- glide_delay5y_70_40, p10 roulant 10 ans (X-era) : USD 1926+ −0,15 % → −0,10 % ; USD 1975+ 3,27 % → 3,20 % ;
  CAD 3,63 % → 3,60 % ; actions moyennes 0,64 → 0,63 ; violations USD 1975+ 71,4 % → 69,0 %.
- glide_delay7y_70_40 : pire p10 inter-ères −0,33 % → +0,02 % (le meilleur pire p10 de toutes les stratégies
  testées, mais violations jusqu'à 76,2 % : non éligible) ; glide_delay8y : −0,44 % → −0,31 % ; glidepath linéaire :
  −0,15 % → −0,17 % (`cross_era_esg_agg.csv`, avant/après).
- glide_delay9y en annuel reste identique à static_eq70 (aucune décision après le mois 108) : c'est maintenant
  voulu par la convention, plus un effet de bord.
- Étude de dé-risquage, ancienne version trimestrielle (PRE `glide_*_esg.json`) → annuel corrigé : réduction de la
  perte des 36 derniers mois vs 60 % statique en USD 1926+ 2,2 → 3,8 pts ; USD 1975+ 2,5 → 2,1 ; CAD 2,3 → 2,3 ;
  la date dérivée (année 5) ne change pas.
- Période réelle (REAL) : glidepath compressé ESG 5,19 % → 5,12 %/an réel ; base 5,61 % → 5,53 % ; strict 5,38 % →
  5,31 %. Autres stratégies inchangées.
- Coût ESG du glidepath année 5 (esg_cost.csv) : USD 1926+ roulant médiane +0,01 pt, p10 −0,43 pt (avant −0,45) ;
  CAD +0,08 / −0,10 pt.
