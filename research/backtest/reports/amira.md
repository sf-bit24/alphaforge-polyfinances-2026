# Amira : backtest 1926-2026, oracle a posteriori, stratégie ex-ante robuste et rétro-ingénierie

> **Simulation historique uniquement.** Ce document décrit le passé reconstitué à partir de données publiques.
> Ce n'est ni une prévision, ni un conseil financier personnalisé, ni une recommandation d'achat ou de vente.
> Les lignes **ORACLE** (`hindsight=True`) utilisent le futur : elles sont **non investissables** et ne servent
> qu'à la rétro-ingénierie. Amira est un **persona fictif**. Tous les seuils ci-dessous sont des
> **propositions à valider par l'équipe**.

Moteur : `research/backtest/engine` (sha256 `engine_sha256` dans chaque trace), données `data_sha256 = 008f122d5da4f8f7`.
Code d'analyse : `research/backtest/analysis/amira/` (aucun fichier de `engine/` ni de `data/` n'a été modifié).

## 0. Comment lire les références `[X]`

Chaque chiffre renvoie à la trace qui l'a produit. Les chemins sont relatifs à `research/backtest/`.

| code | fichier | contenu |
|---|---|---|
| S1 | `results/amira_sweep_tech/20261114T222738Z_rolling_h15.json` | balayage tech × actions, USD 1926+, roulant 15 ans (86 fenêtres) |
| S2 | `results/amira_sweep_tech/20261114T222844Z_rolling_h20.json` | idem, 20 ans (81 fenêtres) |
| S3 | `results/amira_sweep_tech/20261114T222907Z_rolling_h15.json` | balayage, CAD 1977+, roulant 15 ans (35 fenêtres) |
| S4 | `results/amira_sweep_tech/20261114T222929Z_rolling_h20.json` | idem, 20 ans (30 fenêtres) |
| D1 | `results/amira_sweep_tech/derived_thresholds.json` | dérivation : part d'actions de référence, plafond tech, budget de baisse |
| L1 | `results/amira_analysis/lookthrough_facts.json` | part BusEq de la capitalisation US (look-through) |
| N0 / N1 | `results/amira_sat_single/sat_single_summary.json` / `derived_single_name_cap.json` | titre individuel (8 titres tech réels) |
| C0a / C0m | `results/amira_sat_crypto/sat_crypto_summary.json` / `results/amira_sat_crypto_monthly/sat_crypto_summary.json` | crypto, rééquilibrage annuel / mensuel |
| C1 / C2 | `results/amira_sat_crypto/derived_crypto_cap.json` / `crypto_proposal.json` | dérivation de la poche crypto |
| A1, A2, A3 | `results/amira_long_usd/20261114T223410Z_non_overlapping_h15.json`, `…T230318Z_rolling_h15.json`, `…T230622Z_rolling_h20.json` | ère 1 : USD 1926+, 12 industries + obligations (sans or) |
| B1, B2, B3 | `results/amira_usd_1975/20261114T223333Z_non_overlapping_h15.json`, `…T224334Z_rolling_h15.json`, `…T224614Z_rolling_h20.json` | USD 1975+, avec or |
| R1, R2, R3 | `results/amira/20261114T223315Z_non_overlapping_h15.json`, `…T224053Z_rolling_h15.json`, `…T224056Z_rolling_h20.json` | ère 2 : **profil de référence** CAD 1977+ |
| E1, E2, E3 | `results/amira_etf/20261114T224838Z_non_overlapping_h15.json`, `…T225010Z_rolling_h15.json`, `…T225046Z_rolling_h20.json` | CAD 1977+, univers **traduisible en FNB** |
| U1, U2, U3 | `results/amira_etf_long_usd/20261114T224857Z_non_overlapping_h15.json`, `…T225227Z_rolling_h15.json`, `…T225343Z_rolling_h20.json` | USD 1926+, univers traduisible en FNB |
| X1 | `results/amira_analysis/cross_era_etf.json` | choix robuste inter-ères (regret minimax) |
| V1 | `results/amira_tickers/verify_20261114T230945Z.json` | vérification 2021-12 → 2026-09 avec les vrais tickers |

Pour chaque trace `T`, `results/amira_analysis/<profil>__<run_id>_analysis.json` contient le tableau par fenêtre,
la stabilité des poids ORACLE et les associations, et `…_select.json` la sélection selon la règle d'Amira (§4).
Les tableaux de ce rapport sont produits par `analysis/amira/tables.py` et `per_window_strategy.py`, qui ne font que
recopier ces fichiers.

Reproduire (depuis `research/backtest/`, toujours avec `.venv/bin/python -I`). Les horodatages des traces changeront.
1. `analysis/amira/sweep_tech.py` puis `derive_thresholds.py` : seuils tech, actions et baisse (S1-S4, D1).
2. `analysis/amira/make_profiles.py` puis `make_profiles.py --etf` : écrit `profiles/amira*.yaml`.
3. `-m engine.run --profile <amira|amira_long_usd|amira_usd_1975|amira_etf|amira_etf_long_usd> --mode non_overlapping`,
   puis `--mode rolling --horizon 15 --step 12` et `--mode rolling --horizon 20 --step 12`.
4. `analysis/amira/sweep_satellite.py single`, `sweep_satellite.py crypto`, `sweep_satellite.py crypto monthly`, puis
   `derive_satellite.py`.
5. `analysis/amira/analyze_main.py <traces>`, `select_amira.py <traces>`, `cross_era.py`, `lookthrough_facts.py`,
   `verify_tickers.py`, `tables.py`.

## 1. Question

Sur chaque fenêtre historique de la longueur de l'horizon d'Amira (15 ans, sensibilité 20 ans) :
(a) quelle combinaison constante d'actifs aurait été la meilleure **a posteriori** sous ses contraintes (ORACLE) ;
(b) quelle stratégie **ex-ante**, qui n'utilise que le passé, aurait été la plus robuste ;
(c) quelles règles stables et quels signaux observables en début de fenêtre ressortent de ces résultats.

Entrées retenues du persona (énoncé officiel et fiche d'équipe, **qualitatives seulement**) : 26 ans, ingénieure
logicielle, horizon de 15 ans et plus, croissance du capital, tolérance élevée, attirance pour l'IA, la tech et la
crypto, volonté de garder une vraie diversification, pas de retrait prévu, fonds d'urgence hors portefeuille, biais de
familiarité, de surconfiance, d'aversion aux pertes et de FOMO. Test officiel : « risque élevé ≠ tout est
acceptable ». **Aucune** allocation, aucun plafond chiffré ni aucun « fait de marché » de la fiche n'a été utilisé.

Capital humain : son revenu dépend du secteur tech. La fiche affirme au contraire que ce revenu est peu corrélé aux
marchés. Nous n'avons aucune donnée de salaire pour trancher : c'est une **hypothèse** prudente, qui sert à choisir
l'ère la moins favorable à la tech dans la règle R-TECH (§3.1).

## 2. Données, ères, fenêtres

| ère | profil | devise | période effective | univers |
|---|---|---|---|---|
| 1 longue | `amira_long_usd` | USD (hypothèse : investisseur USD, pas de change) | 1926-08 → 2026-09 (actif limitant UST_2Y) [A2] | US_MKT, 12 industries KF, T-bill, Trésor 2/5/10/20 ans synthétiques, Aaa et Baa synthétiques. **Sans or** (non investissable avant 1975) |
| 1 bis | `amira_usd_1975` | USD | 1975-01 → 2026-09 [B2] | idem + GOLD |
| 2 CAD (référence) | `amira` | CAD, actifs US non couverts | 1977-01 → 2026-09 (actif limitant CA_EQ) [R2] | CA_EQ, US_MKT, 12 industries, UST 5/10 ans, Canada 10 ans, encaisse CAD, or |
| FNB CAD | `amira_etf` | CAD | 1977-01 → 2026-09 [E2] | uniquement des proxys qui ont un FNB du starter : US_MKT, CA_EQ, BusEq, UST 10/20, Canada 10 ans, or, encaisse |
| FNB USD | `amira_etf_long_usd` | USD | 1926-08 → 2026-09 [U2] | US_MKT, BusEq, UST 5/10/20, T-bill |

Fenêtres de 15 ans : non chevauchantes (6 fenêtres en USD 1926+ [A1], 3 en CAD 1977+ [R1]) et roulantes au pas de
12 mois (86 [A2] et 35 [R2]). **Les fenêtres roulantes se chevauchent** : deux fenêtres voisines partagent 14 ans sur 15.
Le nombre d'observations indépendantes est donc proche de n × 12 / 180, soit environ 5,7 en USD et 2,3 en CAD
(colonne « n effectif » des fichiers `_analysis.json`). Sensibilité à 20 ans : 81 [A3] et 30 [R3] fenêtres roulantes.

Paramètres communs : objectif `max_real_return` (rendement réel annualisé pondéré par le temps), cible de manque
`target_real_return = 0` (perte de pouvoir d'achat sur la fenêtre), coûts de 10 pb par unité échangée, rééquilibrage
annuel (mensuel pour les stratégies de tendance et de momentum), ORACLE activé (`n_starts = 6`).

**Pourquoi le 10e centile du rendement réel ?** Amira n'a aucun besoin de revenu : seule compte la croissance réelle
sur l'horizon. Le 10e centile entre fenêtres mesure la « mauvaise fenêtre plausible » sans dépendre d'un calendrier de
cotisations (inconnu, il serait inventé). La richesse finale avec cotisations indexées est calculée par le moteur
(`final_real_wealth`), mais avec `flows.monthly = 0` elle n'ajoute rien ici. C'est un prolongement possible.

## 3. Seuils dérivés (propositions à valider)

### 3.1 Plafond tech « look-through », part d'actions de référence, budget de baisse

**Méthode** (`analysis/amira/sweep_tech.py`, `derive_thresholds.py`, règles écrites avant de lire les résultats) :
grille de politiques statiques. La part d'actions E vaut 0,6 à 1,0 et l'exposition tech T vaut 0 à 1,0 du portefeuille.
BusEq = T, le reste des actions est réparti à parts égales entre les 11 industries non tech (l'exposition tech vaut
donc exactement T), et les obligations sont des UST 5/10 ans (ère USD) ou le Canada 10 ans (ère CAD).
- **R-UW** : une politique est admissible si, dans **toutes** les fenêtres, sa plus longue période sous le sommet
  précédent dure au plus H/2 (90 mois pour 15 ans). Au-delà, l'horizon n'a plus le temps de capitaliser, et c'est la
  situation qui mène à la capitulation (aversion aux pertes, biais du persona).
- **R-P10** : parmi les politiques admissibles, on retient le meilleur 10e centile réel.
- **R-TECH** : le plafond est le plus grand T admissible, à la part d'actions retenue, **dans les deux ères**
  (hypothèse du capital humain tech).
- **R-DD** : le budget de baisse est le 90e centile de la baisse maximale de la politique retenue en USD 1926+,
  arrondi à 5 points.

**Résultats à E = 0,8** (politique de référence retenue par R-P10 : E080_T035 en USD [D1]) :

| T (tech) | USD 1926+ : réel p10 % / pire % / maxDD pire % / sous l'eau max (mois) [S1] | CAD 1977+ : réel p10 % / pire % / maxDD pire % / sous l'eau max [S3] |
|---|---|---|
| 0,00 | 2,1 / −1,0 / 70,4 / 85 | 5,2 / 4,5 / 28,4 / 41 |
| 0,10 | 2,0 / −1,2 / 72,1 / 85 | 4,9 / 4,3 / 27,8 / 53 |
| 0,20 | 2,0 / −1,4 / 73,8 / 86 | 4,6 / 3,6 / 33,0 / 66 |
| 0,30 | 2,1 / −1,6 / 75,4 / 88 | 4,3 / 3,0 / 39,3 / **80** |
| 0,35 | 2,2 / −1,7 / 76,1 / **88** | 4,2 / 2,6 / 42,3 / 122 (fenêtre 1996-01..2010-12) |
| 0,40 | 2,2 / −1,8 / 76,9 / 164 (fenêtre 1928-08..1943-07) | 4,1 / 2,3 / 45,2 / 128 |
| 0,60 | 2,0 / −2,3 / 79,8 / 177 | 3,4 / 0,8 / 55,9 / 157 |
| 0,80 | 1,5 / −2,8 / 82,4 / 179 | 2,7 / −0,8 / 65,8 / 175 |

Lecture [D1] :
- **Part d'actions de référence : 80 %.** C'est la politique admissible au meilleur p10 en USD (E080_T035). Avec 85 %
  d'actions ou plus, la fenêtre de 1929 dépasse 90 mois sous l'eau dès que T > 0,10.
- **Plafond tech look-through : 30 % du portefeuille.** Le plafond admissible vaut 35 % en USD et 30 % en CAD, et on
  retient le minimum. Deux crises indépendantes fixent la cassure : 1929 en USD (le recouvrement passe de 88 à 164 mois
  entre T = 0,35 et 0,40) et la bulle 2000-2002 en CAD (de 80 à 122 mois entre 0,30 et 0,35).
- Côté rendement, la tech n'apporte **aucun gain robuste** au 10e centile. L'optimum de T pour le p10 vaut 0,4 à 0,5 en
  USD sur 15 ans, mais 0,1 sur 20 ans, **0 en CAD sur 15 ans** et 0,4 à 0,5 en CAD sur 20 ans [D1, S1-S4]. Le pire
  rendement réel baisse à chaque cran de T dans les deux ères. Le plafond est donc une **limite de risque, pas une
  cible**.
- Sensibilité au seuil de R-UW (lue dans le tableau) : avec 120 mois, le plafond reste à 30 % (CAD) et 35 % (USD).
  Avec 60 mois (H/3), aucune politique à 80 % d'actions n'est admissible en USD, et le plafond CAD tombe à 10 %.
  Le seuil H/2 est un **choix normatif**.
- **Budget de baisse : 40 %.** Le 90e centile de la baisse maximale de E080_T035 vaut 40,6 % [D1]. Il sert de
  `risk_limits.max_drawdown` (pénalité de l'ORACLE et comptage des dépassements).
- Les industries KF autres que la tech sont aussi plafonnées à 30 % chacune (`class_max_weight.sector_us`). C'est une
  **extension par hypothèse** du plafond tech (« aucune industrie au-dessus du plafond tech »), sans dérivation propre.

**Concentration tech mesurée du marché US** [L1] : la part BusEq de la capitalisation vaut 0,052 en 1926-07, 0,078 en
1929-08, 0,302 en 2000-02, 0,148 en 2002-09, 0,354 en 2021-12 et 0,435 en 2026-09. Le maximum de 0,453 est atteint en
2026-06. La part a dépassé 30 % dans 7,0 % des mois, pour la première fois en 2000-01. **Conséquence : en 2026, un
fonds US pondéré par la capitalisation (SPY) seul dépasse le plafond.** Sans autre tech, son poids maximal compatible
vaut 0,30 / 0,435 ≈ 68,9 % [L1]. Le marché US pondéré à 100 % a d'ailleurs un p10 inférieur aux politiques
diversifiées : 1,19 % en USD 1926+ contre 2,13 % pour E080_T030 [S1], et 2,17 % en CAD contre 4,34 % [S3].

Limite : BusEq (codes SIC) ≠ GICS. QQQ, XIU.TO et CA_EQ ont une exposition tech de 0 dans le moteur (aucune donnée de
détention datée), ce qui **sous-estime** la tech canadienne et celle du Nasdaq-100.

### 3.2 Plafond par titre individuel

**Méthode** (`sweep_satellite.py single`, `derive_satellite.py`), avec les vrais tickers en CAD sur leur période
réelle : portefeuille = (1 − k) × cœur CAD de référence + k × titre, fenêtres roulantes de 5 et 10 ans au pas de
3 mois. On mesure, **dans la même fenêtre**, l'augmentation de la baisse maximale par rapport à k = 0.
- **R-IDIO** : un titre seul ne doit pas ajouter plus de b = 10 % du budget de baisse (0,1 × 40 % = 4 points). Le
  risque diversifiable n'est pas rémunéré en moyenne. Le 10 % est une **convention**, d'où la sensibilité.

| budget b (points de baisse ajoutés) | 2 | **4** | 6 | 8 |
|---|---|---|---|---|
| plafond par titre [N1] | < 2 % | **3 %** | 5 % | 7 % |

Le titre limitant est toujours NVDA sur 5 ans : à 3 %, sa pire fenêtre ajoute 3,4 points de baisse, et 4,5 points à
4 % (fenêtre 1999-11..2004-10) [N0]. Sur l'échantillon complet, la pire baisse des titres atteint 0,873 pour NVDA,
0,927 pour AMZN, 0,794 pour AAPL et 0,808 pour SHOP.TO [N0]. À 3 %, la part du risque total portée par un titre
(contribution d'Euler) vaut 0,098 pour NVDA, 0,097 pour TSLA, 0,091 pour SHOP.TO et 0,061 pour AAPL [N0].

Biais du survivant : ces huit titres ont été choisis en 2026 parmi les gagnants. Les fenêtres affichent pourtant un
p10 de rendement réel **plus bas** avec AAPL et MSFT à tous les poids, par exemple −0,44 point pour AAPL à 5 % sur
5 ans [N0]. Un titre qui a fait faillite (absent des données) aurait coûté k points entiers : c'est un scénario
**fictif** de perte totale, et 3 % ≤ 4 points le respecte.

**Proposition : 3 % maximum par titre individuel.** Avec ce plafond, un panier tech de six titres vaut au plus 18 %, à
l'intérieur du plafond look-through global.

### 3.3 Poche crypto (sous-analyse séparée, 2014-10 → 2026-09 seulement)

**Ne pas mélanger avec les conclusions centenaires.** BTC commence en 2014-10 et ETH en 2017-12. Fenêtres roulantes de
3, 4 et 5 ans au pas d'un mois, soit 109 / 97 / 85 fenêtres pour BTC et 71 / 59 / 47 pour BTC+ETH [C0a]. Elles se
chevauchent presque entièrement : il y a **environ 3 à 4 observations indépendantes et 2 à 3 cycles crypto**.
L'échantillon est minuscule.

Même règle R-IDIO (4 points), plus **R-RISK** : la poche crypto ne doit pas porter plus de risque que le titre le plus
risqué au plafond par titre (0,098, NVDA à 3 %) [C2].

| | BTC seul | BTC+ETH 50/50 |
|---|---|---|
| pire baisse de l'actif sur l'échantillon (CAD) | 0,744 (vol. 0,70) [C0a] | 0,793 (vol. 0,74) [C0a] |
| R-IDIO, rééquilibrage **annuel** | **1 %** (à 2 %, la pire fenêtre de 3 ans ajoute 4,1 points) [C1] | 5 % [C1] |
| R-IDIO, rééquilibrage **mensuel** | 7,5 % [C2] | 5 % [C2] |
| R-RISK (part de risque ≤ 0,098) | 3 % (part 0,090) [C2] | 2 % (0,061 ; 3 % donnerait 0,099) [C2] |
| **proposition** | **3 %** avec rééquilibrage mensuel ou par bandes, **1 %** sinon [C2] | **2 %** [C2] |

Le rééquilibrage compte plus que la taille de la poche. Avec un rééquilibrage annuel, 2 % de BTC peuvent dériver vers
une part bien plus grande avant un krach : la pire hausse de baisse vaut 4,09 points à 2 % [C0a] contre 0,99 point en
mensuel [C0m]. Le moteur n'a que des bandes **absolues** : nous avons pris une bande égale à la moitié de la cible.
La crypto n'entre ni dans le plafond tech ni dans les fenêtres de 15 ans.

## 4. Sélection robuste et walk-forward

**Règle d'Amira** (`select_amira.py`, fonctions `engine.validation`) : le meilleur 10e centile réel parmi les
stratégies dont le taux de dépassement du budget de baisse est ≤ 10 %. C'est cohérent avec la définition du budget
(un 90e centile). Le walk-forward refait ce choix en n'utilisant que les fenêtres terminées avant celle qu'on évalue.

| run | choix (règle d'Amira) | réel p10 % | médian % | maxDD pire % | à comparer | walk-forward : p10 hors échantillon % |
|---|---|---|---|---|---|---|
| A2 USD 1926+ 15 ans | Mom_sectors_top3 | 2,42 | 7,17 | 37,9 | S_core_E80_T30 : 2,13 / maxDD 75,4 | 2,14 (69 fenêtres) |
| A3 USD 1926+ 20 ans | Mom_sectors_top3 | 3,96 | 6,80 | 37,9 | S_core_E80_T30 : 3,33 | 3,68 (59) |
| B2 USD 1975+ 15 ans | S_core_E80_T30_gold20 | 5,62 | 7,72 | 38,5 | Mom_all_top4 : 5,53 | 4,82 (20) |
| R2 CAD 1977+ 15 ans | Mom_all_top4 | 6,28 | 10,63 | 31,7 | S_core_E80_T30_gold20 : 4,92 | 5,43 (18) |
| R3 CAD 1977+ 20 ans | Mom_all_top4 | 7,96 | 9,93 | 31,7 | S_core_E80_T30_gold10 : 6,50 | 6,58 (8) |
| E2 CAD FNB 15 ans | Trend10_E80 | 5,32 | 6,35 | 19,0 | Mom_etf_top3 : 5,16 ; E70_us50_g10_t0 : 4,82 | **2,74** (18) |
| U2 USD FNB 15 ans | Trend10_E80 | 1,84 | 5,62 | 34,4 | E80_us100_g0_t0 : 1,38 / maxDD 72,8 | 2,02 (69) |

Sources : les fichiers `_select.json` de chaque trace, et les traces elles-mêmes pour les colonnes de comparaison.

Lecture :
1. **Coût de ne pas connaître le futur** (écart moyen ORACLE − choix du walk-forward) : 3,5 points par an en USD 1926+
   [A2 select], 2,1 en CAD [R2], 3,0 dans l'univers FNB CAD [E2 select] et 2,3 dans l'univers FNB USD [U2 select].
   La meilleure stratégie ex-ante *a posteriori* de chaque fenêtre ne fait guère mieux : son écart moyen avec le choix
   du walk-forward vaut 1,4 point [A2 select] et 0,6 point [R2 select].
2. **Instabilité du choix** : dans l'univers FNB CAD, le walk-forward choisit une politique statique à 90-100 %
   d'actions (E100_us70 11 fois, E90_us70 5 fois sur 18), parce que les trois premières fenêtres (1977-1993) lui
   étaient favorables. Son p10 hors
   échantillon tombe alors à 2,74 %, contre 5,32 % pour le choix fait sur tout l'échantillon [E2 select]. Avec
   3 fenêtres passées qui se chevauchent (une observation effective), **la sélection n'apprend presque rien**.
3. Le moteur sans filtre de dépassements choisit Mom_all_top4 en USD 1926+ (p10 3,6 %), mais avec 13 % de fenêtres
   au-delà du budget de baisse [A2]. La règle d'Amira l'écarte.

### Choix inter-ères (univers traduisible en tickers)

Les stratégies sur les 12 industries KF ne se traduisent pas en tickers du starter sans concentration sur des titres
individuels : il n'y a **aucun FNB sectoriel** dans l'univers. Le choix final se fait donc dans les univers FNB, avec
une règle fixée d'avance (`cross_era.py`) : regret = meilleur p10 éligible du run − p10 de la stratégie, et on retient
le plus petit **regret maximal** sur les 6 runs (E1-E3, U1-U3), en exigeant l'éligibilité partout [X1].

| stratégie | E1 | E2 | E3 | U1 | U2 | U3 | regret max (pt) | regret moyen | p10 minimal |
|---|---|---|---|---|---|---|---|---|---|
| **Mom_etf_top3** | 6,19 | 5,16 | 5,68 | 2,76 | 0,95 | 1,62 | **1,53** | 0,96 | 0,95 |
| Trend10_E80 | 5,43 | 5,32 | 5,24 | 4,29 | 1,84 | 2,93 | 2,18 | **0,51** | **1,84** |
| Mom_etf_top2 | 5,28 | 4,05 | 4,68 | 2,66 | 0,86 | 1,69 | 2,33 | 1,48 | 0,86 |
| RP_invvol_36m | 5,82 | 5,01 | 5,13 | −0,20 | −1,35 | −0,62 | 4,49 | 2,39 | −1,35 |

(p10 réels en %, meilleur p10 éligible par run : 7,62 / 5,32 / 6,11 / 4,29 / 1,84 / 2,93 [X1].) Aucune politique
statique n'est éligible partout : en USD 1926+ non chevauchant, toutes dépassent le budget de baisse dans 1 fenêtre
sur 6 ou plus [X1].

**Choix robuste retenu par la règle : `Mom_etf_top3`.** C'est un momentum relatif à 12 mois (en sautant le dernier
mois) : un tiers sur chacun des 3 meilleurs actifs parmi actions US, actions CA, BusEq, UST 10/20 ans, Canada 10 ans
et or, avec un filtre absolu (un actif qui fait moins bien que l'encaisse est remplacé par l'encaisse) et un
rééquilibrage mensuel. **Statut : fragile.** Trend10_E80 (80 % d'actions US/CA à parts égales et 20 % Canada 10 ans,
chaque poche d'actions passant à l'encaisse sous sa moyenne mobile de 10 mois) arrive premier dans 4 runs sur 6, a le
plus petit regret moyen et le meilleur p10 minimal [X1]. Un critère « maximiser le pire p10 » le choisirait. Les deux
reposent sur la même idée (règle de sortie vers l'encaisse ou les obligations) et leur écart n'est pas significatif.

Coûts de cette robustesse :
- **Croissance médiane plus faible en USD** : 4,2 % réel pour Mom_etf_top3 contre 6,4 % pour E80_us100_g0_t0 [U2].
  En CAD, c'est l'inverse : 7,1 % contre 7,2 % pour E80_us50_g10_t0 [E2].
- **Rotation** d'environ 1,6 à 1,9 fois par an (médiane de `turnover_ann`) [E2, U2]. Les coûts de 10 pb sont inclus,
  les **impôts ne le sont pas**. C'est surtout pertinent hors CELI/REER.
- En échange, la pire baisse maximale sur toutes les fenêtres vaut 30,4 % en CAD [E2] et 26,7 % en USD 1926+ [U2],
  contre 72,8 % pour la politique statique 80/20 USD [U2].

Tableau par fenêtre de la stratégie retenue (non chevauchant, USD 1926+) [U1] :

| fenêtre | ORACLE (poids principaux) | ORACLE réel % | meilleure ex-ante (réel %) | Mom_etf_top3 réel % | vol % | maxDD % | recouvr. (mois) | CVaR5 mens. % | réel < 0 ? | écart ORACLE pt |
|---|---|---|---|---|---|---|---|---|---|---|
| 1926-08..1941-07 | UST_20Y 0.74; US_IND_BUSEQ 0.26 | 7.4 | RP_invvol_36m (8.5) | 7.7 | 12.2 | 26.7 | 64 | 9.1 | non | -0.3 |
| 1941-08..1956-07 | US_MKT 0.75; US_IND_BUSEQ 0.25 | 12.3 | E100_us100_g0_t10 (12.0) | 4.8 | 8.2 | 18.2 | 26 | 4.6 | non | 7.5 |
| 1956-08..1971-07 | US_MKT 0.80; US_IND_BUSEQ 0.20 | 6.2 | E100_us100_g0_t10 (6.0) | 1.9 | 6.8 | 12.8 | 21 | 4.1 | non | 4.4 |
| 1971-08..1986-07 | US_MKT 0.84; UST_5Y 0.16 | 4.2 | Trend10_E80 (4.8) | 3.7 | 8.5 | 7.9 | 6 | 4.4 | non | 0.6 |
| 1986-08..2001-07 | US_MKT 0.86; UST_20Y 0.14 | 9.5 | E100_us100_g0_t10 (10.7) | 6.2 | 10.3 | 19.5 | 20 | 6.7 | non | 3.3 |
| 2001-08..2016-07 | UST_20Y 0.70; US_IND_BUSEQ 0.30 | 5.9 | Trend10_E80 (6.0) | 4.1 | 7.7 | 9.2 | 10 | 4.3 | non | 1.8 |

Non chevauchant, CAD 1977+ [E1] :

| fenêtre | ORACLE (poids principaux) | ORACLE réel % | meilleure ex-ante (réel %) | Mom_etf_top3 réel % | vol % | maxDD % | recouvr. (mois) | CVaR5 mens. % | réel < 0 ? | écart ORACLE pt |
|---|---|---|---|---|---|---|---|---|---|---|
| 1977-01..1991-12 | US_MKT 1.00 | 8.6 | E100_us70_g0_t0 (7.8) | 6.0 | 13.2 | 30.4 | 45 | 8.2 | non | 2.6 |
| 1992-01..2006-12 | CA_EQ 0.87; US_IND_BUSEQ 0.09; UST_20Y 0.04 | 10.5 | Mom_etf_top2 (10.7) | 10.5 | 10.4 | 19.6 | 50 | 5.1 | non | -0.0 |
| 2007-01..2021-12 | US_MKT 0.57; GOLD 0.33; US_IND_BUSEQ 0.10 | 9.4 | E90_us70_g10_t10 (8.9) | 7.1 | 9.7 | 17.9 | 48 | 5.7 | non | 2.3 |

L'ORACLE peut être battu (écart négatif en 1926-41 et 1992-2006) : c'est le meilleur mélange **constant**, alors que
le momentum est dynamique (README du moteur, point 7). Les tableaux complets, ère par ère, avec la meilleure stratégie
ex-ante, le choix robuste, la volatilité, la baisse maximale, le recouvrement et la CVaR, sont en annexe.

## 5. Rétro-ingénierie

### 5.1 Ce que choisit l'ORACLE (sous les contraintes d'Amira)

- **Actions presque toujours dominantes**, sauf quand une crise arrive tôt dans la fenêtre. Poids moyen des actions de
  l'ORACLE : 89 % [13-100] en USD 1926+ [A2] et 92 % [25-100] en CAD [R2]. Pour les fenêtres commençant 0 à 36 mois
  avant 1929, il tombe à 14,6 % (85,4 % d'obligations) [A2]. Avant 2000-2002 : 58,2 % d'actions et 41,8 %
  d'obligations [A2], ou 45,8 % d'or en CAD [R2].
- **La tech n'est presque jamais là où on l'attendait.** Exposition tech moyenne de l'ORACLE : 12 % [0-30] en USD
  [A2] et 12 % [0-30] en CAD [R2]. Elle vaut **0** pour les fenêtres qui commencent avant 1929, 1973-74 et 2000-02
  (sur les industries) [A2], et atteint le plafond de 30 % seulement pour les fenêtres qui commencent avant 2008
  [A2, R2]. Avec un plafond tech à 30 %, l'ORACLE l'atteint dans ces fenêtres de rattrapage, rarement ailleurs.
- **Rotation des industries gagnantes** : en USD 1926+, les plus fréquentes sont la santé (poids moyen 15 %, > 5 %
  dans 58 % des fenêtres), l'énergie (15 %, 59 %) et BusEq (12 %, 47 %) [A2]. Le podium change d'une fenêtre à
  l'autre (tableaux en annexe) : **aucun poids sectoriel n'est stable**.
- **Or** (après 1975) : absent dans la majorité des fenêtres, massif dans quelques-unes. En CAD, 8 % en moyenne
  [0-75] [R2] ; dans l'univers FNB CAD, 20 % [0-100] et > 5 % dans 43 % des fenêtres [E2].
- Dans l'univers FNB : US_MKT pèse en moyenne 62 % de l'ORACLE (> 5 % dans 87 % des fenêtres) et UST_20Y 21 % [U2] ;
  en CAD, US_MKT 46 %, CA_EQ 21 % et or 20 % [E2].
- La contrainte de baisse de 40 % est **active** : la baisse maximale de l'ORACLE vaut 40,0 % dans tous les runs,
  avec une seule fenêtre légèrement au-delà en A2 (`risk_limits_met`).

### 5.2 Signaux observables en début de fenêtre

Signaux calculés au mois précédant la fenêtre (`analysis/amira/signals.py`) : CAPE de Shiller (décalé de 3 mois pour la
publication des bénéfices), taux long, T-bill, pente, variation du taux long sur 12 mois, inflation sur 12 mois (décalée
d'un mois), T-bill réel, tendance du marché sur 12 mois et vs MM10, part BusEq, rendement relatif tech/marché sur
3 ans, taux long canadien, USDCAD. Mesures : corrélation de Spearman entre fenêtres roulantes, et **accord de signe**
sur les 15 sous-échantillons non chevauchants décalés d'un an (défini seulement en USD 1926+, où chaque sous-échantillon
compte au moins 4 fenêtres). Corrélation ≠ causalité. N effectif ≈ 6 (USD) et ≈ 2 (CAD).

| # | règle (descriptive) | preuves | confiance |
|---|---|---|---|
| 1 | **Plus le CAPE est élevé en début de fenêtre, plus le meilleur résultat possible sur 15 ans est faible et plus l'ORACLE réduit les actions.** | rendement réel ORACLE vs CAPE : −0,60 (accord 1,00, terciles 14,0 / 9,7 / 7,7 %) [A2] ; −0,62 (1,00) [U2] ; −0,82 [R2] ; −0,76 [E2]. Part d'actions ORACLE vs CAPE : −0,65 (0,93 ; 94 / 77 / 53 %) [U2] ; −0,69 [R2] ; −0,75 [E2] | **robuste** (même signe dans les 4 univers et sur 100 % des sous-échantillons USD), descriptive |
| 2 | **Quand le CAPE est élevé, la règle de tendance perd moins (ou gagne) par rapport au cœur statique.** | écart Trend10 − cœur vs CAPE : +0,61 (accord 0,93 ; −2,9 / −0,7 / −0,3 pt par tercile) [A2] ; +0,52 [R2] | **robuste en signe, fragile en ampleur** |
| 3 | **Une exposition tech au-delà d'environ 30 % du portefeuille allonge brutalement le pire recouvrement** (1929 en USD, 2000-02 en CAD), sans gain robuste au p10. | §3.1 [S1-S4, D1] | **robuste** comme limite de risque ; **non concluante** pour un surpoids tech |
| 4 | **Les valeurs refuges que choisit l'ORACLE après une valorisation ou une concentration tech élevées changent selon l'ère** : obligations longues en USD 1926+, or en CAD 1977+. | obligations ORACLE vs CAPE : +0,48 (0,87) [U2] ; or ORACLE vs CAPE : +0,85, vs part BusEq : +0,83 [E2] ; +0,69 [R2] | **fragile** (l'actif refuge dépend de l'ère et des taux de départ) |
| 5 | **Le momentum bat davantage le cœur statique quand les taux longs sont bas en début de fenêtre.** | écart Mom_all_top4 − cœur vs taux long : −0,58 (accord 1,00 ; 1,6 / 0,9 / 0,2 pt) [A2] ; signe non retrouvé parmi les 12 premières associations en CAD [R2] | **fragile** |
| 6 | Taux réel du T-bill élevé en début de fenêtre → l'ORACLE détient plus d'obligations. | +0,41 (0,80 ; 2,2 / 3,2 / 24,5 %) [A2] ; +0,37 (0,87) [U2] | **fragile** |
| 7 | Inflation de départ élevée → moins d'obligations dans l'ORACLE. | −0,40 (accord 0,60 seulement) [A2] | **non concluante** |

Garde-fous : environ 14 signaux × 12 cibles (≈ 170 tests) par run, il y a donc un risque élevé de fausses découvertes. Seule la
règle 1 survit à tous les univers. Aucune de ces règles ne doit devenir un *timing* agressif : la règle 1 dit que
l'issue sur 15 ans est **moins bonne en moyenne** quand la valorisation de départ est élevée, pas *quand* le marché
corrige.

### 5.3 Règles stables pour une stratégie (synthèse)

1. **Cœur diversifié sur au moins deux marchés** (US + Canada) avec environ 70 à 90 % d'actions. Ajouter de l'or
   améliore le p10 après 1975 : USD 1975+ 5,09 % → 5,37 % (or 10 %) → 5,62 % (or 20 %) [B2] ; FNB CAD, 4,43 % → 4,70 %
   à 80 % d'actions et 50 % US [E2]. Confiance : **robuste** après 1975 (non testable avant).
2. **Exposition tech look-through ≤ 30 %**, sans surpondération systématique (§3.1). **Robuste** comme limite.
3. **Une règle de sortie vers l'encaisse ou les obligations** (tendance 10 mois ou momentum absolu) réduit la pire
   baisse de moitié environ en USD 1926+ (37,9 % contre 75,4 % [A2] ; 34,4 % contre 72,8 % [U2]) avec un p10 égal ou
   meilleur. Elle coûte de la croissance médiane en USD et a perdu en 2022 (§6). **Robuste pour la baisse, fragile
   pour le rendement.**
4. **Satellites bornés** : ≤ 3 % par titre ; crypto ≤ 3 % avec rééquilibrage discipliné (≤ 1 % sinon).
   **Fragile** (échantillons courts, survivants).
5. Les stratégies à estimation de moyennes (MinVar, MaxSharpe, MV) sont les moins bonnes au p10 dans presque tous les
   runs (par exemple MinVar −1,5 % en USD [A2] et 1,5 % en CAD [R2]). **Robuste** pour Amira : elles fuient les actions
   qui font sa croissance.

## 6. Traduction en tickers et vérification 2021-12 → 2026-09

Correspondance (assets.csv) : US_MKT→SPY, CA_EQ→XIU.TO, Canada 10 ans→XBB.TO, or→GLD, encaisse CAD→ZST.TO,
UST 10 ans→AGG, UST 20 ans→TLT, BusEq→panier égal AAPL, MSFT, NVDA, GOOGL, CSU.TO, SHOP.TO (au plus 3 % par titre).
**Écart de traduction** : BusEq ne peut pas être un candidat du momentum en tickers, faute de FNB tech dont
l'exposition est documentée (QQQ vaut 0 dans le moteur), donc il est retiré des candidats. Contraintes en tickers :
tech look-through ≤ 30 % (SPY via US_MKT), `equity_single` ≤ 3 %, `crypto` ≤ 3 %.

**Stratégie retenue en tickers (simulation)** : chaque mois, un tiers sur chacun des 3 actifs ayant le meilleur
rendement sur 12 mois (en sautant le dernier mois) parmi **SPY, XIU.TO, AGG, TLT, XBB.TO, GLD**. Un actif dont le
rendement passe sous celui de **ZST.TO** est remplacé par ZST.TO. En option, une poche **BTC-USD de 3 %**, réajustée
dès qu'elle s'écarte de 1,5 point. Un panier tech de titres, chacun ≤ 3 %, peut s'ajouter tant que SPY × part BusEq
+ panier ≤ 30 %.

Une seule fenêtre de 58 mois, en CAD [V1] :

| | réel annualisé % | vol % | maxDD % | pire 12 mois % |
|---|---|---|---|---|
| **Mom_etf_top3, tickers** | **11,09** | 9,19 | 10,84 | −6,58 |
| Mom_etf_top3, proxys (même période) | 11,49 | 7,75 | 9,57 | −5,85 |
| Mom_etf_top3, proxys avec BusEq candidat | 11,73 | 9,15 | 14,88 | −11,38 |
| Mom_etf_top3 + BTC 3 %, tickers | 11,35 | 9,68 | 12,45 | −8,65 |
| Trend10_E80, tickers | 4,27 | 8,29 | 14,68 | −13,73 |
| Statique E80_us50_g10_t0 (SPY 40, XIU 40, GLD 10, XBB 10), tickers | 10,31 | 10,22 | 13,02 | −8,18 |
| idem + panier tech 6 % (1 % par titre), tickers | 11,05 | 10,59 | 14,22 | −9,70 |
| *Référence sans contrainte* : SPY 100 % | 11,38 | 13,46 | 18,67 | −12,59 |
| *Référence sans contrainte* : QQQ 100 % | 13,20 | 19,28 | 28,17 | −27,97 |
| *Scénario FICTIF « demande tout tech/crypto »* (QQQ 40, NVDA 15, TSLA 10, SHOP 10, BTC 15, ETH 10) | 15,34 | 31,70 | **50,84 > budget de 40** | −46,31 |

Lecture : sur cette fenêtre haussière qui contient 2022, la traduction en tickers reste proche des proxys (11,09 %
contre 11,49 %). Trend10 a subi des faux signaux en 2022 (4,27 %). La demande fictive « tout tech/crypto » a le
meilleur rendement de la fenêtre, mais **dépasse le budget de baisse** (50,8 %) : un seul cycle haussier ne justifie
pas d'abandonner la diversification. C'est exactement l'épreuve « risque élevé ≠ tout est acceptable ». En fin de
fenêtre, la stratégie retenue détenait 1/3 SPY, 1/3 XIU.TO et 1/3 GLD [V1]. **Le momentum peut placer un tiers en
or** : l'équipe doit valider si c'est acceptable pour la diversification d'Amira.

## 7. Signaux candidats pour l'étape 2 (non testés ici)

- **Valorisation** : CAPE (règle 1), rendement des bénéfices moins taux réel, CAPE sectoriel tech, part de la tech
  dans la capitalisation (déjà disponible, `lookthrough_us_mkt.parquet`) comme jauge de concentration ou de bulle.
- **Taux et courbe** : pente 10 ans − 3 mois (probit de récession), taux réels (TIPS), variation des taux,
  écart Baa − Aaa (stress de crédit).
- **Inflation** : niveau et surprise, régime croissance × inflation, signe de la corrélation actions-obligations
  (détermine si les obligations protègent ; règle 4).
- **Fondamentaux tech** : croissance des bénéfices et marges, révisions, dispersion des valorisations, ratio cours /
  ventes, rachats (SEC EDGAR / SEDAR+, avec date de dépôt pour rester point-in-time).
- **Nouvelles et politique** : incertitude économique (EPU Canada et US), risque géopolitique (GPR), textes BoC et FOMC
  (extraction par Bedrock), réglementation IA, droits de douane, sanctions.
- **Crypto** : MVRV, flux des FNB spot, régime de taux réels, corrélation à la tech (à documenter, sources ajoutées).
- **Change** : écart de taux Canada − US, termes de l'échange (pétrole) pour la décision CAD vs USD.
- **Sentiment et positionnement** : VIX, ampleur du marché (part des titres au-dessus de la MM200), flux vers les FNB
  tech (signal de FOMO à confronter aux biais d'Amira).

## 8. Limites

- **Proxys** : 12 industries Ken French (SIC ≠ GICS), CRSP centré NYSE avant 1962, aucun ticker réel avant 1962.
  Les correspondances proxy → ticker sont approximatives, surtout or → GLD et Canada 10 ans → XBB.TO (concordances
  calculées par le build : README du moteur et `data/processed/data_version.json`, non recalculées ici).
- **Obligations synthétiques** à maturité constante, construites sur des moyennes mensuelles de taux avant 1962 et pour
  le Canada 10 ans : leur **volatilité est sous-estimée**, ce qui flatte risk parity et min-variance sur la période
  ancienne. Le crédit synthétique ignore les défauts (Baa surestimé).
- **Or non investissable avant 1975** (prix fixe, interdiction 1933-1974, valeurs annuelles avant 1960) : il est exclu
  de l'ère 1926+.
- **CAD seulement depuis 1971** (FX) et actions canadiennes depuis **1977** : 35 fenêtres roulantes, environ 2
  indépendantes. L'ère USD suppose un investisseur en USD (pas de change).
- **Crypto seulement depuis 2014** : sous-analyse à part, 2 à 3 cycles.
- **Biais du survivant** : univers choisi en 2026, et titres tech gagnants.
- **Pas d'impôts, ni de frais de gestion des FNB, ni d'écart acheteur-vendeur** au-delà des 10 pb de transaction.
  La rotation de 1,6 à 1,9 par an des stratégies de momentum serait coûteuse hors CELI/REER.
- **Look-through tech incomplet** : 0 pour CA_EQ, XIU.TO et QQQ, ce qui sous-estime l'exposition réelle.
- **Révisions FRED, dates de référence** (pas de dates de publication) ; CAPE décalé de 3 mois par prudence.
- **Petits N et sélection multiple** : de nombreuses stratégies ont été comparées, donc le p10 du gagnant est biaisé
  vers le haut. Le walk-forward le montre (2,74 % hors échantillon contre 5,32 % dans l'échantillon [E2 select]).
- Les seuils (H/2 pour le recouvrement, 10 % du budget de baisse par satellite, 10 % de dépassement toléré) sont des
  **conventions normatives**. Leur sensibilité est donnée, mais l'équipe doit les valider.

## 9. Bugs ou particularités du moteur rencontrés (non modifiés, contournés)

1. **Bandes de rééquilibrage absolues seulement** (`backtest.py`, `np.max(np.abs(w_drift - tgt)) <= band`). Pour une
   petite poche (crypto à 3 %), une bande de 5 points la laisse grossir jusqu'à 8 %. Contournement : bande = moitié de
   la cible. Suggestion : des bandes relatives.
2. **Pas d'historique avant la première fenêtre dans `run_profile`** : les fenêtres commencent à `R.index.min()`, donc
   la première fenêtre d'une période courte utilise les poids de repli (`fallback`). Contournement pour la vérification
   2021-2026 : appel direct de `run_window` avec un historique depuis 2019 (`verify_tickers.py`).
3. **ORACLE à pénalité souple** : la baisse maximale est collée au budget (40,0 % partout), avec une fenêtre de A2
   légèrement au-delà (`risk_limits_met = False`). C'est le comportement attendu d'une pénalité linéaire. À savoir
   avant de lire « ORACLE respecte les limites ».
4. **Avertissements look-through répétés** : un message par `ConstraintSet` créé, soit des centaines par run pour
   CA_EQ et XIU.TO. Ils sont dédupliqués dans la trace, mais bruyants sur stderr.
5. **Walk-forward sur fenêtres roulantes** : avec `min_past_windows = 3`, les premiers choix reposent sur 3 fenêtres
   qui se chevauchent, soit environ une observation (instabilité, §4). Ce n'est pas un bug, mais une suggestion :
   compter les fenêtres passées **non chevauchantes**.

## 10. Les quatre questions

- **Quelles données ?** Ken French (marché US, 12 industries, Canada), FRED (taux du Trésor, Moody's, IPC, USDCAD,
  OCDE Canada), Shiller (taux long avant 1953, CAPE), or (datahub), starter officiel et yfinance pour les tickers.
  Tout est mensuel, en rendement total, fin 1926 → 2026-09 (§2, `data/SOURCES.md`).
- **Pourquoi ce choix ?** Amira vise la croissance réelle sur au moins 15 ans, avec une tolérance élevée mais une
  vraie diversification. On a donc maximisé le **mauvais cas plausible** (10e centile réel), sous un plafond de baisse
  et de recouvrement dérivé des crises de 1929 et 2000, avec des satellites bornés par une règle unique de risque
  idiosyncratique. La stratégie retenue est celle qui **regrette le moins** dans les deux ères (§4, [X1]).
- **Quelles limites ?** Proxys, obligations lissées, or et CAD tardifs, crypto courte, survivants, pas d'impôts,
  N effectif de 2 à 6, sélection fragile entre deux stratégies proches (§8).
- **Qu'est-ce qui changerait la réponse ?** Un seuil de recouvrement plus strict (H/3 = 60 mois → plafond tech de 10 % en CAD) ;
  une donnée de revenu montrant que le capital humain d'Amira n'est pas lié à la tech (on pourrait alors utiliser le
  plafond USD de 35 %) ; des impôts dans un compte non enregistré (pénalise le momentum) ; une période qui commence
  avec un CAPE bas (meilleur sort des actions, règle 1) ; l'arrivée d'un FNB tech dont la composition est documentée ;
  un rééquilibrage seulement annuel (crypto ramenée à 1 %).

---

## Annexe A : tableaux par ère (copiés de `tables.py`)

### A.1 USD 1926+, 12 industries, non chevauchant [A1]

| stratégie | rang | réel p10 % | réel médian % | réel pire % | maxDD pire % | taux dépass. DD | P(réel<0) |
|---|---|---|---|---|---|---|---|
| Mom_all_top4 | 1 | 5.8 | 8.4 | 5.1 | 43.9 | 0.17 | 0.00 |
| Mom_sectors_top3 | 2 | 5.2 | 7.6 | 4.7 | 37.9 | 0.00 | 0.00 |
| S_eqw_sectors80 | 3 | 4.9 | 6.3 | 4.6 | 71.6 | 0.17 | 0.00 |
| S_1overN | 4 | 4.8 | 6.1 | 4.5 | 65.1 | 0.17 | 0.00 |
| S_core_E90_T25 | 5 | 4.7 | 6.8 | 4.3 | 80.1 | 0.50 | 0.00 |
| S_core_E80_T20 | 6 | 4.6 | 6.6 | 4.3 | 73.8 | 0.17 | 0.00 |
| S_core_E80_T30 | 7 | 4.4 | 6.8 | 4.0 | 75.4 | 0.17 | 0.00 |
| S_mkt80_bonds20 | 8 | 4.3 | 4.9 | 4.2 | 72.5 | 0.17 | 0.00 |
| Trend10_core | 9 | 4.2 | 6.3 | 3.7 | 48.6 | 0.17 | 0.00 |
| MinVar_60m | 16 | -0.8 | 1.3 | -2.2 | 49.3 | 0.17 | 0.17 |

| fenêtre | ORACLE (poids principaux) | ORACLE réel % | ORACLE maxDD % | meilleure ex-ante | son réel % | choix robuste moteur (Mom_all_top4) réel % | vol % | maxDD % | recouvr. (mois) | CVaR5 % | écart ORACLE pt |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1926-08..1941-07 | CORP_AAA 0.52; US_IND_CHEMS 0.28; CORP_BAA 0.19 | 10.1 | 40.0 | RP_invvol_36m | 10.4 | 9.4 | 20.3 | 43.9 | 27 | 15.0 | 0.7 |
| 1941-08..1956-07 | US_IND_DURBL 0.30; US_IND_MANUF 0.30; US_IND_ENRGY 0.30; US_IND_BUSEQ 0.06 | 15.3 | 25.3 | Mom_all_top4 | 12.0 | 12.0 | 13.5 | 27.6 | 27 | 6.7 | 3.3 |
| 1956-08..1971-07 | US_IND_NODUR 0.30; US_IND_SHOPS 0.30; US_IND_HLTH 0.30; US_IND_BUSEQ 0.10 | 10.8 | 31.9 | Mom_all_top4 | 7.4 | 7.4 | 11.7 | 25.4 | 21 | 7.0 | 3.4 |
| 1971-08..1986-07 | US_IND_NODUR 0.30; US_IND_TELCM 0.30; US_IND_UTILS 0.20; US_IND_ENRGY 0.20 | 7.0 | 37.4 | Mom_sectors_top3 | 5.7 | 5.1 | 13.1 | 17.2 | 14 | 7.6 | 1.9 |
| 1986-08..2001-07 | US_IND_HLTH 0.30; US_IND_MONEY 0.30; US_IND_BUSEQ 0.21; US_IND_ENRGY 0.19 | 12.7 | 30.6 | S_core_E90_T25 | 10.5 | 9.4 | 16.0 | 31.9 | 20 | 10.5 | 3.4 |
| 2001-08..2016-07 | CORP_BAA 0.31; US_IND_NODUR 0.30; US_IND_MANUF 0.28; US_IND_CHEMS 0.11 | 8.0 | 36.3 | Mom_all_top4 | 6.4 | 6.4 | 12.5 | 21.7 | 16 | 7.8 | 1.6 |

### A.2 USD 1975+, avec or, non chevauchant [B1]

| fenêtre | ORACLE (poids principaux) | ORACLE réel % | ORACLE maxDD % | meilleure ex-ante | son réel % | choix robuste (S_core_E80_T30_gold15) réel % | vol % | maxDD % | recouvr. (mois) | CVaR5 % | écart ORACLE pt |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1975-01..1989-12 | US_IND_NODUR 0.30; US_IND_TELCM 0.30; US_IND_SHOPS 0.30; US_IND_ENRGY 0.10 | 14.1 | 28.7 | Mom_all_top4 | 11.0 | 8.3 | 14.3 | 26.0 | non récupéré | 7.8 | 5.8 |
| 1990-01..2004-12 | US_IND_HLTH 0.30; US_IND_MONEY 0.30; US_IND_BUSEQ 0.23; US_IND_MANUF 0.11 | 11.4 | 40.0 | S_core_E90_T25 | 9.1 | 8.0 | 13.3 | 38.0 | non récupéré | 8.0 | 3.3 |
| 2005-01..2019-12 | US_IND_BUSEQ 0.30; US_IND_SHOPS 0.30; US_IND_HLTH 0.30; US_IND_MANUF 0.08 | 9.3 | 40.0 | S_core_E80_T30_gold20 | 8.1 | 7.9 | 11.4 | 37.5 | 14 | 7.1 | 1.4 |

(« non récupéré » : le sommet d'avant la pire baisse n'est pas retrouvé avant la fin de la fenêtre, `recovery_months`
= NaN dans la trace.)

### A.3 CAD 1977+, profil de référence, non chevauchant [R1]

| fenêtre | ORACLE (poids principaux) | ORACLE réel % | ORACLE maxDD % | meilleure ex-ante | son réel % | choix robuste (Mom_all_top4) réel % | vol % | maxDD % | recouvr. (mois) | CVaR5 % | écart ORACLE pt |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1977-01..1991-12 | US_IND_NODUR 0.30; US_IND_SHOPS 0.30; US_IND_HLTH 0.30; US_IND_TELCM 0.10 | 13.0 | 31.6 | Mom_all_top4 | 10.0 | 10.0 | 16.2 | 31.7 | 36 | 10.8 | 2.9 |
| 1992-01..2006-12 | US_IND_ENRGY 0.30; US_IND_MONEY 0.30; US_IND_MANUF 0.26; US_IND_BUSEQ 0.14 | 13.1 | 28.0 | Mom_all_top4 | 11.2 | 11.2 | 11.9 | 26.9 | 22 | 6.4 | 1.9 |
| 2007-01..2021-12 | US_IND_BUSEQ 0.30; US_IND_SHOPS 0.30; US_IND_DURBL 0.21; US_IND_HLTH 0.19 | 13.4 | 40.0 | Mom_all_top4 | 10.9 | 10.9 | 11.9 | 13.4 | 4 | 6.4 | 2.5 |

### A.4 CAD 1977+, roulant 15 ans, ORACLE fenêtre par fenêtre [R2]

Tableau complet dans `results/amira_analysis/amira__20261114T224053Z_rolling_h15_analysis.json` (`per_window`), à
regénérer avec `tables.py --per-window`. Faits saillants recopiés de ce fichier : les fenêtres qui commencent de 1977 à
1984 sont 100 % industries (consommation courante, distribution, santé, télécoms, finance) sans tech. De 1985 à 1992,
BusEq vaut 14 à 30 %, sauf en 1988 (0). Les fenêtres 1993 à 1996 sont dominées par CA_EQ (40 à 70 %) et l'énergie.
Celles qui commencent de 1997 à 2002 (après la bulle, CAPE élevé) détiennent 26 à 75 % d'or. Celles qui commencent
de 2003 à 2011 ont 22 à 30 % de BusEq, avec la distribution et, à partir de 2006, les biens durables.
