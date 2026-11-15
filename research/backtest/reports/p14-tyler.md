# Persona 14 · Tyler Kowalchuk : backtest 1926-2026, capital humain lié à l'énergie et croisement réglementaire

> **Simulation historique uniquement.** Ce rapport n'est pas un conseil financier personnalisé. Il décrit un passé
> reconstitué à partir de proxys et ne prédit rien. Les lignes `ORACLE` (`hindsight=True`) utilisent le futur : elles ne
> sont **pas investissables** et servent seulement à la rétro-ingénierie. Les seuils sont des **propositions dérivées des
> données, à valider par l'équipe**. Les montants personnels sont des faits **fictifs** du persona. Le modèle de capital
> humain est un **scénario déclaré**, pas une mesure.

**Persona (fictif).** 39 ans, opérateur de salle de contrôle dans une usine de valorisation de bitume (Fort McMurray).
Conjointe employée dans le même groupe. Deux enfants (4 et 8 ans), hypothèque élevée, CAD. Tolérance déclarée élevée,
capacité évaluée modérée. Objectifs : retraite anticipée vers 55 ans, études des enfants, résilience à un choc pétrolier.
Biais : familiarité, survivant, dotation/loyauté, excès de confiance. **Test du persona** : le système ose-t-il proposer de
*sous-pondérer* ENB.TO, CNQ.TO et XOM parce que le capital humain du ménage est déjà exposé au pétrole, sans moraliser ?
Seuls l'identité, les contraintes RRTTLLU qualitatives, les objectifs, les horizons, les biais et les critères ✅/❌ de la fiche
ont été utilisés, plus deux faits du profil fictif : 310 k$ investissables, dont 140 k$ en CNQ.TO (45 %). **Aucune**
allocation illustrative, aucun seuil chiffré ni aucun « fait de marché » de la fiche n'est entré dans le calcul. Le bloc
YAML sert uniquement d'oracle de test, en fin de rapport (§12).

## 0. Références (chaque chiffre cite l'une d'elles)

Chemins relatifs à `research/backtest/`. Traces moteur : `engine_sha256 = 4d3e707a3271717d…`, données
`p14_ext_c69551f9fef87bd3` (dérivées de `008f122d5da4f8f7`, voir §1), graine 42.

| id | fichier |
|---|---|
| ET-U-R / ET-U-N | `results/p14_etudes_usd/20261115T000101Z_rolling_h10.json` / `…/20261115T000143Z_non_overlapping_h10.json` |
| ET-C-R / ET-C-N | `results/p14_etudes_cad/20261114T235638Z_rolling_h10.json` / `…/20261114T235710Z_non_overlapping_h10.json` |
| RE-U-R / RE-U-N / RE-U-20 | `results/p14_retraite_usd/20261115T000120Z_rolling_h16.json` / `…000145Z_non_overlapping_h16.json` / `…000206Z_rolling_h20.json` |
| RE-C-R / RE-C-N / RE-C-20 | `results/p14_retraite_cad/20261114T235543Z_rolling_h16.json` / `…235556Z_non_overlapping_h16.json` / `…235609Z_rolling_h20.json` |
| CO-U / CO-C | `results/p14_coussin_usd/20261115T000241Z_rolling_h1.json` (+ `…000234Z_non_overlapping_h1.json`) / `results/p14_coussin_cad/20261115T000239Z_rolling_h1.json` (+ `…000234Z_non_overlapping_h1.json`) |
| variantes | `_libre` (sans plafond énergie) et `_volonte` (perte max. de volonté) : liste exacte dans `analysis/p14/runs_*.json` |
| TI / TI-L | `results/p14_titres_cad/20261114T235810Z_rolling_h10.json` / `results/p14_titres_cad_libre/20261114T235946Z_rolling_h10.json` |
| EN | `results/p14_analysis/energy_comoves.csv`, `energy_episodes.csv`, `energy_style_ca_eq.csv` (`analysis/p14/energy.py`) |
| SW | `results/p14_analysis/sweep_A_capacity.csv`, `sweep_B_energy_eq{50,70}.csv`, `sweep_C_ca_eq{50,70}.csv`, `sweep_D_cnq_eq{50,70}.csv` (`sweep.py`) |
| TH | `results/p14_analysis/derived_thresholds.json` (`derive.py`) |
| HH | `results/p14_analysis/household_*.csv` (`household.py`) |
| AN | `results/p14_analysis/per_window_*.csv`, `cross_era.csv`, `robust_summary.csv`, `walkforward_summary.csv`, `oracle_classes.csv`, `robust_classes.csv`, `energy_cap_effect.csv`, `reverse_signals.csv` (`analyze.py`) |
| REAL | `results/p14_analysis/real_check.json` / `.csv` (`real_check.py`, profil documentaire `profiles/p14_real_tickers.yaml`) |
| REC | `results/p14_analysis/recon.csv` (`recon.py`) |

Reproduction (toujours `.venv/bin/python -I`) : `analysis/p14/build_ext_data.py` → `energy.py` → `sweep.py A` puis
`sweep.py B C D eq=0.5` et `eq=0.7` → `derive.py` → `make_profiles.py` et `make_profiles.py titles` → `batch.py <tag> <jobs>`
(liste : `analysis/p14/jobs.txt`, plus `G p14_titres_cad:rolling:10:1 p14_titres_cad_libre:rolling:10:1`) → `household.py`,
`real_check.py`, `recon.py`, `analyze.py`.

## 1. Question, poches, données, ères, fenêtres

**Question.** Pour chaque poche de Tyler et chaque fenêtre de la durée de cette poche, on cherche : (a) quel mélange
aurait été le meilleur a posteriori (oracle) ; (b) quelle stratégie ex-ante s'en approchait sous ses limites ; (c) combien
la sous-pondération de l'énergie change le pire cas du **patrimoine total**, c'est-à-dire le portefeuille plus le capital
humain lié au pétrole ; (d) si ces résultats concordent avec les statuts réglementaires de
`analyse/relation-profils-actifs/`.

**Poches** (lignes `id=14` de `personas-tous.csv`) et horizon de fenêtre retenu :

| poche | AMF / BNC (analyse réglementaire) | fenêtre | justification |
|---|---|---|---|
| coussin mise à pied | 1 Sécurité (Q3 < 5 ans) / Liquidités | **1 an** (non chevauchant + roulant) | argent à dépenser pendant une mise à pied ; un épisode de baisse de l'énergie dure 3 à 27 mois entre le pic et le creux (HH, §5.2) |
| études enfants | 3 Équilibré (plafond Q7) / Pondéré | **10 ans** | horizon donné par le persona (enfants de 4 et 8 ans) |
| retraite | 3 Équilibré (plafond Q7) / Équilibré | **16 ans** (sensibilité 20) | de 39 à 55 ans, l'âge de retraite anticipée visé ; « 16–20 ans » dans la fiche |

**Données.** On utilise la couche partagée `data/processed` (Ken French, FRED, Shiller, Banque du Canada, yfinance, starter
officiel), **sans la modifier**. Un actif synthétique y est ajouté, dans une copie `analysis/p14/data_ext/` (méthode recopiée
de `analysis/mateo/build_ext_data.py`) : `US_MKT_XEN` = marché US hors énergie, pondéré par la capitalisation des 11
industries KF autres que `Enrgy`. Sa corrélation mensuelle avec `US_MKT` vaut 0,9953 (sortie du script). Le fichier
`analysis/p14/common.py` enveloppe `exposure_vector` à l'exécution (énergie de `US_MKT_XEN` = 0) ; `engine/` est intact.

**Ères.** (1) **USD 1926-08 → 2026-09** : proxys US, investisseur supposé en USD, car il n'existe pas d'USDCAD avant 1971.
Les portefeuilles BNC y versent la part « actions canadiennes » dans `US_MKT` (hypothèse déclarée). (2) **CAD 1977-01 →
2026-09** : `CA_EQ`, `CA_GOV_10Y`, `CA_TBILL`, actifs US non couverts convertis, or. Le coussin CAD commence en 1971-02, et
l'ère « titres réels » en 1995-02 (CNQ.TO, ENB.TO, XOM, JNJ, PG ; Yahoo avant 2021-12, starter après).

**Fenêtres.** Non chevauchantes : 10 (études USD), 4 (études CAD), 6 (retraite USD), 3 (retraite CAD), 100 et 55 (coussin
USD et CAD). Roulantes au pas de 12 mois : 91, 40, 85, 34 (traces ci-dessus). **Les fenêtres roulantes se chevauchent** : leur
nombre n'est pas un nombre d'observations indépendantes.

**Stratégies ex-ante** (`make_profiles.py`, identiques entre variantes) :
- les 6 portefeuilles BNC publics (revenu fixe / actions CA / actions mondiales) ;
- BNC Équilibré et Croissance avec un cœur US hors énergie ;
- mélanges statiques de 40 à 80 % d'actions sur un cœur hors énergie (CA 30 % / US 70 %, la répartition des cibles BNC) ;
- « demande de Tyler » : 60/40 + 20 % d'énergie ;
- tilt défensif (santé, consommation de base, services publics) ; 60/40 + 10 % d'or (CAD) ;
- glidepath : 70→30 pour les études, 80→50 pour la retraite ;
- parité de risque inverse-vol 36 mois, min-variance 60 mois, moyenne-variance (aversion 4), filtre de tendance 10 mois,
  momentum dual top 2.

Coûts 10 pb, rééquilibrage annuel. Objectif `min_shortfall`, cible réelle 0 % : score = rendement réel annualisé. Sélection
robuste = meilleur 10e centile parmi les stratégies dont le taux de violation est ≤ 25 % (convention reprise de Mateo).

## 2. Seuils dérivés (propositions à valider) et méthode (TH, SW)

| seuil | études | retraite | règle lisible |
|---|---|---|---|
| **capacité** (`max_drawdown`) | **20 %** | **30 %** (25,9 % avant arrondi) | R-CAP : plus grande part d'actions du cœur hors énergie dont la plus longue période sous l'eau **réelle** (CAD 1977+, échantillon complet) est ≤ horizon/2. Études : 50 % d'actions, 58 mois sous l'eau, perte max. 16,1 %. Retraite : 70 %, 76 mois, 25,9 %. Arrondi aux 5 points supérieurs. En USD 1926+, aucun mélange ne passe (au moins 123 mois sous l'eau, à cause de 1929) |
| **volonté** (Q10 AMF) | 30 % [inf] | 30 % [inf] | « tolérance déclarée élevée » lue comme la case Q10 « 30 % ». Réponse **inférée**, pas fournie par le persona |
| **limite appliquée** (31-103CP) | **20 % (la capacité gagne)** | **30 % (égalité ; capacité plus basse avant arrondi)** | minimum des deux |
| énergie directe ajoutée | **5 %** | **10 %** | R-ENERGY : plus grand poids `US_IND_ENRGY` tel que le p90 (entre fenêtres) de la perte max. du **patrimoine total** (h = 1/2) n'augmente pas de plus de b = 10 % de la limite (2 pts / 3 pts) en CAD 1977+. En USD 1926+, la règle serait plus large (15 % / 30 %) |
| énergie look-through totale L | **8,6 %** | **15 %** | L = énergie implicite du cœur (part d'actions × 0,3 × charge énergie de CA_EQ 0,239) + plafond direct. Imposée comme contrainte de groupe `exposure: energy` |
| employeur CNQ.TO | **2,5 %** | **5 %** | R-EMPLOYER : plus grand poids CNQ tel que, dans la **pire** fenêtre roulante de 5 et 10 ans (CAD 1995+, pas de 3 mois), la perte max. du portefeuille financier n'augmente pas de plus de b (même convention que la règle R-IDIO d'Amira). Sensibilité : b = 1 pt → 0 % ; 2 → 2,5 % ; 3 → 5 % ; 4 → 7,5 % |
| CA_EQ / XIU.TO (implicite) | 36 % (charge 0,239) ; 20 % (charge 2007-16 de 0,432) | 63 % ; 35 % | L / charge énergie de CA_EQ, sans énergie directe |
| coussin | perte max. 1 % sur 1 an | | case Q10 « 0 % » du profil AMF 1 [inf] + 1 pt de tolérance de mesure |

À l'échelle du ménage, on propose de retenir la valeur de poche la plus basse : énergie directe 5 %, L = 8,6 %, CNQ 2,5 %.
Un même choc pétrolier frappe toutes les poches en même temps.

**Charge énergie de CA_EQ / XIU.TO** (EN, `energy_style_ca_eq.csv`). Le moteur ne connaît pas la part d'énergie de XIU.TO.
On l'estime par une **régression sur les rendements** (moindres carrés non négatifs, somme = 1) des rendements USD de CA_EQ
sur les 12 industries KF US. Résultats : 0,239 sur l'échantillon complet 1977-2026 (R² 0,686) ; 0,323 / 0,303 / 0,214 /
0,432 / 0,106 par bloc de 10 ans ; XIU.TO : 0,201 sur 1999-2026, 0,063 sur 2019-2026. Ce n'est **pas** une donnée de
détention. Elle est à remplacer par une fiche sectorielle iShares datée (source à ajouter).

Une sensibilité au profil AMF retenu (3, dont la case Q10 correspond à 15 %) n'a pas été lancée comme limite. Dans la
grille CAD, aucun mélange statique n'a une perte max. ≤ 15 % : le minimum est 15,49 % à 30 % d'actions (SW-A).

## 3. Capital humain et énergie : corrélations et co-baisse (EN, HH, SW)

**Corrélations mensuelles** (EN) : énergie US ~ marché US hors énergie 0,675 (USD 1926+) et 0,413 (CAD 1977+). Énergie ~
CA_EQ 0,538. Énergie ~ obligations à 10 ans −0,041 (USD) et −0,055 (CA). Énergie ~ or −0,048 (CAD).
Titres réels (CAD) : CNQ.TO ~ XOM 0,812 et CNQ.TO ~ ENB.TO 0,448 sur 2021-12..2026-09 ; CNQ ~ XIU.TO 0,582 (1999+) ;
CNQ ~ SPY 0,276 (1995+) ; CNQ ~ XBB.TO −0,019 ; ~ GLD −0,099 ; ~ AGG −0,382.

**Co-baisse.** Rendement moyen de chaque actif pendant les 10 % pires mois de l'énergie (EN) :

| ère / actif | n mois de stress | énergie | actions | obligations / cash | or |
|---|---|---|---|---|---|
| USD 1926+ | 121 | −10,25 % | US hors énergie −6,15 % (négatif 88 % du temps) | 10 ans +0,54 % ; T-bills +0,29 % | — |
| CAD 1977+ | 60 | −9,14 % | CA_EQ −3,75 % (75 % négatif) ; US hors énergie −2,73 % | CA 10 ans +0,81 % ; CA_TBILL +0,46 % (jamais négatif) | +1,99 % |
| CNQ.TO, 1995+ (CAD) | 38 | CNQ −14,2 % | XIU.TO −3,8 % ; SPY −1,5 % | XBB.TO +0,1 % ; AGG +1,9 % | GLD +1,3 % |

Lecture : quand l'énergie chute, les actions larges chutent aussi, mais moins (surtout en USD 1926+). Les obligations et le
cash ne chutent pas. Le portefeuille qui « ne baisse pas pour la même raison » que le revenu, ce sont donc les obligations,
le cash et l'or, pas les actions canadiennes.

**Modèle de capital humain (scénario).** Patrimoine total T = (1−h)·F + h·HC. Le rendement de HC est celui de
`US_IND_ENRGY` : bêta 1 sur la **seule part du capital humain liée à l'énergie** (primes, risque de mise à pied).
h ∈ {1/3, 1/2, 2/3}, soit HC à risque / F = 0,5, 1 ou 2 ; h est tenu constant, ce qui est une simplification. Aucune
série de revenus n'existe dans les données : c'est une hypothèse, pas une mesure.

**Effet de la sous-pondération sur le pire cas du patrimoine total** (HH `household_total_wealth.csv`, CAD 1995-02 → 2026-09,
cœur 60/40 hors énergie, h = 1/2) :

| état du portefeuille financier | perte max. F | perte max. T | T 2018-08..2020-03 | F 2018-08..2020-03 | F en 2022 | réel ann. F |
|---|---|---|---|---|---|---|
| actuel : CNQ 45 % (fait fictif 140/310 k$) | 38,6 % | **42,9 %** | −42,9 % | −25,3 % | +14,2 % | 11,8 % |
| actuel + demande (ENB 10 %, XOM 10 %) | 36,8 % | **45,1 %** | −45,1 % | −30,7 % | +27,0 % | 12,8 % |
| CNQ 20 % | 28,2 % | 36,5 % | −36,5 % | −8,9 % | −0,5 % | 9,2 % |
| CNQ 5 % | 21,4 % | 32,6 % | −32,6 % | +1,7 % | −8,9 % | 7,3 % |
| CNQ 2,5 % | 20,9 % | 31,9 % | −31,9 % | +3,5 % | −10,3 % | 7,0 % |
| CNQ 0 % | 20,6 % | **31,3 %** | −31,2 % | +5,4 % | −11,6 % | 6,7 % |

Ramener CNQ de 45 % à 2,5–5 % réduit la perte max. du patrimoine total d'environ **10 à 11 points** (42,9 % → 31,9–32,6 %)
dans ce scénario. La perte du portefeuille financier pendant le choc 2018-2020 passe de −25,3 % à +1,7–3,5 %. **Le coût est
réel et doit être affiché** : sur 1995-2026, CNQ (un titre survivant choisi en 2026) a rapporté davantage (11,8 % réel/an
contre 6,7 %), et en 2022 l'état actuel a fait +14,2 % contre −11,6 %. Sur la longue histoire USD 1926+, où l'énergie US
tient lieu de CNQ, l'effet est plus petit : 73,4 % → 70,2 % pour T (h = 1/2), car 1929-1932 domine (HH).
Sensibilité au poids d'énergie directe (SW-B, CAD 1977+, études, h = 1/2) : chaque tranche de 2,5 points d'énergie ajoute
environ 0,8 point au p90 de la perte max. de T (30,46 % à 0 %, 31,24 % à 2,5 %, 32,01 % à 5 %). Pour un investisseur
**sans** capital humain énergie (h = 0), l'énergie n'aggrave pas le risque : en retraite CAD, le p90 passe de 25,9 % à
24,9 % à 20 % d'énergie. Le plafond est donc **propre à Tyler**, et non un jugement sur le secteur.

## 4. Résultats par fenêtre (non chevauchant, variante de base)

« Meilleure ex-ante » = meilleure stratégie sur la fenêtre **a posteriori** (non identifiable à l'avance). Écart = score oracle
− score meilleure ex-ante. Un écart négatif vient d'une stratégie dynamique qui bat le meilleur mélange constant ; ce n'est pas
un bug (AN `per_window_*.csv`).

**Études, USD 1926+ (ET-U-N), limite 20 %, L = 8,6 %**

| fenêtre | oracle réel / perte max. | oracle : principales lignes | meilleure ex-ante (réel / perte max.) | écart |
|---|---|---|---|---|
| 1926-08..1936-07 | 9,86 % / 20,0 % | CORP_AAA 0,83 ; HLTH 0,09 | dual_mom12_top2 (16,27 % / 21,6 %) | −6,41 |
| 1936-08..1946-07 | 4,42 % / 20,0 % | HLTH 0,54 ; CORP_AAA 0,46 | dual_mom12_top2 (5,31 % / 25,0 %) | −0,89 |
| 1946-08..1956-07 | 11,23 % / 19,6 % | US_MKT_XEN 0,91 ; ENRGY 0,09 | dual_mom12_top2 (8,58 % / 14,6 %) | 2,65 |
| 1956-08..1966-07 | 9,83 % / 20,0 % | HLTH 0,53 ; UST_2Y 0,17 | dual_mom12_top2 (10,01 % / 11,9 %) | −0,18 |
| 1966-08..1976-07 | 1,40 % / 20,0 % | UST_2Y 0,53 ; HLTH 0,38 ; ENRGY 0,09 | request_eq60_energy20 (−0,04 % / 28,6 %) | 1,43 |
| 1976-08..1986-07 | 13,71 % / 12,6 % | NODUR 1,00 | mean_var_60_ra4 (8,07 % / 7,5 %) | 5,64 |
| 1986-08..1996-07 | 10,44 % / 20,0 % | NODUR 0,66 ; CORP_AAA 0,34 | dual_mom12_top2 (9,39 % / 26,9 %) | 1,05 |
| 1996-08..2006-07 | 8,50 % / 20,0 % | UTILS 0,51 ; CORP_AAA 0,25 ; ENRGY 0,086 | dual_mom12_top2 (8,65 % / 15,0 %) | −0,15 |
| 2006-08..2016-07 | 9,11 % / 20,0 % | NODUR 0,53 ; CORP_AAA 0,38 | bnc_actions (6,81 % / 43,1 %) | 2,30 |
| 2016-08..2026-07 | 10,29 % / 20,0 % | US_MKT_XEN 0,73 ; UTILS 0,17 | bnc_actions (11,22 % / 24,8 %) | −0,93 |

**Études, CAD 1977+ (ET-C-N)**

| fenêtre | oracle réel / perte max. | oracle : lignes | meilleure ex-ante | écart |
|---|---|---|---|---|
| 1977-01..1986-12 | 15,21 % / 13,7 % | NODUR 1,00 | dual_mom12_top2 (13,49 % / 15,1 %) | 1,72 |
| 1987-01..1996-12 | 12,48 % / 20,0 % | HLTH 0,42 ; CA_GOV_10Y 0,32 ; NODUR 0,26 | bnc_actions (10,34 % / 27,0 %) | 2,14 |
| 1997-01..2006-12 | 8,36 % / 20,0 % | UTILS 0,42 ; CA_EQ 0,36 ; CA_GOV_10Y 0,22 | dual_mom12_top2 (10,25 % / 12,3 %) | −1,89 |
| 2007-01..2016-12 | 10,66 % / 20,0 % | NODUR 1,00 | dual_mom12_top2 (8,73 % / 9,2 %) | 1,92 |

**Retraite (16 ans), USD 1926+ (RE-U-N) et CAD (RE-C-N)**

| fenêtre | oracle réel / perte max. | oracle : lignes | meilleure ex-ante | écart |
|---|---|---|---|---|
| USD 1926-08..1942-07 | 6,30 % / 24,4 % | CORP_AAA 0,76 ; HLTH 0,24 | dual_mom12_top2 (8,07 % / 25,0 %) | −1,77 |
| USD 1942-08..1958-07 | 14,65 % / 24,0 % | UTILS 0,67 ; HLTH 0,18 ; ENRGY 0,15 | bnc_actions (12,27 % / 24,3 %) | 2,39 |
| USD 1958-08..1974-07 | 6,99 % / 29,9 % | HLTH 0,80 ; ENRGY 0,15 | dual_mom12_top2 (4,74 % / 12,2 %) | 2,25 |
| USD 1974-08..1990-07 | 13,56 % / 29,3 % | NODUR 1,00 | bnc_actions (8,62 % / 29,9 %) | 4,94 |
| USD 1990-08..2006-07 | 9,10 % / 30,0 % | HLTH 0,64 ; ENRGY 0,15 ; UTILS 0,11 | dual_mom12_top2 (10,11 % / 15,0 %) | −1,02 |
| USD 2006-08..2022-07 | 8,14 % / 30,0 % | HLTH 0,97 | bnc_actions (7,40 % / 50,3 %) | 0,74 |
| CAD 1977-01..1992-12 | 14,94 % / 29,9 % | NODUR 1,00 | dual_mom12_top2 (10,10 % / 26,1 %) | 4,83 |
| CAD 1993-01..2008-12 | 7,64 % / 26,6 % | CA_EQ 0,50 ; HLTH 0,33 | dual_mom12_top2 (11,62 % / 16,0 %) | −3,98 |
| CAD 2009-01..2024-12 | 13,97 % / 21,3 % | US_MKT_XEN 1,00 | bnc_actions (11,73 % / 17,3 %) | 2,24 |

Lecture : sous plafond, l'oracle **sature** souvent le budget énergie (0,086 en études, 0,15 en retraite USD). Sans
plafond (variante `_libre`), il met 100 % en énergie en 1946-1956 (études USD) et en 1993-2008 (retraite CAD), et 88 % en
1996-2006 (AN `per_window_*_libre.csv`). C'est du **hindsight** : l'énergie a eu des décennies fastes, mais on ne pouvait pas
les identifier au départ (§8).

## 5. Poche coussin mise à pied

### 5.1 Backtest (CO-C, CO-U)
CAD 1971+, 55 fenêtres roulantes d'un an : **`cad_cash100` (CA_TBILL ≈ ZST.TO)** est le seul choix sans violation de la
limite de 1 % (perte max. 0,0 %). Son p10 réel est de −1,56 %/an : c'est le coût de l'inflation. Les T-bills US non couvertes
(en CAD) violent la limite dans 83,6 % des fenêtres, et le 10 ans canadien dans 90,9 %. En USD 1926+, `min_variance_36` arrive
en tête (p10 réel −3,09 %, 1 % de violations), devant `tbill100` (0 % de violations). Walk-forward CAD : cash choisi dans 47
fenêtres sur 52, moyenne réelle hors échantillon 2,01 %, p10 −1,51 % (AN).

### 5.2 Tests pendant les chocs pétroliers (HH `household_buffer_*.csv`)
Sur les 9 épisodes de baisse d'au moins 30 % (US_IND_ENRGY en CAD depuis 1971, CNQ.TO depuis 1995), CA_TBILL a un rendement
positif dans tous les cas (+0,92 % à +33,0 %), sans aucune baisse. ZST.TO est positif dans les 2 épisodes couverts (+0,45 % et
+3,79 %), avec une perte max. ≤ 0,69 %. CA_EQ, lui, a perdu jusqu'à 41,9 % (2008-06..2009-02).
Les T-bills US converties en CAD **montent** pendant les chocs (+25,5 % en 2008-09 et en 2014-15 : le CAD baisse avec le
pétrole). Mais elles affichent une perte max. allant jusqu'à 20,4 % et des mois négatifs dans 34 % des mois de stress :
elles ne servent pas de coussin (constat à verser à l'étape 2).

### 5.3 Dimensionnement (scénario)
Durée pic → creux D des 9 épisodes : médiane 15 mois, p75 20, max. 27, min. 3. Mois de dépenses à couvrir = D × φ, où φ est
la part des dépenses qui n'est plus couverte par le revenu restant pendant le choc. **φ et les dépenses du ménage sont des
informations manquantes.**

| D | φ = 0,25 (primes perdues) | φ = 0,5 (un revenu perdu) | φ = 1 (deux revenus perdus) |
|---|---|---|---|
| médiane 15 mois | 3,8 mois | 7,5 mois | 15 mois |
| p75 20 mois | 5,0 | 10,0 | 20 |
| max. 27 mois | 6,8 | 13,5 | 27 |

Coût de l'inflation : CA_TBILL a rapporté 1,95 % réel/an sur 1977-2026, mais −0,23 % réel/an sur 2021-12..2026-09 ; ZST.TO,
+0,02 % réel/an sur la même période (HH `household_buffer_inflation.csv`).

## 6. Sélection robuste, walk-forward, B2 (volonté vs capacité)

**Règle inter-ères** (AN `cross_era.csv`) : parmi les stratégies dont le taux de violation est ≤ 25 % dans les deux ères,
on maximise le pire p10 du rendement réel.

| poche (limite) | choix robuste | pire p10 (USD / CAD) | violations USD / CAD | pire perte max. USD / CAD | suivants |
|---|---|---|---|---|---|
| études (20 %, capacité) | **`xen_eq40`** (40 % d'actions hors énergie) | −0,52 % / 3,26 % | 6,6 % / 0 % | 39,3 % / 15,8 % | bnc_conservateur (−0,75 %), trend10_eq60 (−0,86 %), bnc_prudent, risk_parity |
| études (30 %, volonté) | `dual_mom12_top2` | 1,21 % / 6,02 % | 0 % / 0 % | 26,9 % / 24,2 % | request_eq60_energy20 (0,77 %), bnc_equilibre (0,39 %) |
| retraite (30 %) | `request_eq60_energy20` **projetée sur L = 15 %** | 2,17 % / 4,73 % | 12,9 % / 0 % | 60,4 % / 19,3 % | dual_mom12_top2 (1,94 %), xen_eq60 (1,58 %), bnc_equilibre (1,51 %) |

**Effet de B2.** Appliquer la capacité (20 %) plutôt que la volonté (30 %) en études fait passer le choix d'un momentum
dynamique à environ 60 % d'actions vers un mélange statique à 40 %. Le coût mesuré est de 1,73 point sur le pire p10 (USD) et
de 2,76 points sur le p10 CAD. Ce coût de la capacité est le prix de la règle 31-103CP.

**Point à trancher (retraite).** La sélection, qui ne regarde que le **portefeuille financier**, pousse l'énergie jusqu'au
plafond : `request_eq60_energy20` projetée détient 15,1 % d'énergie en moyenne (AN `robust_classes.csv`). Dans ces données,
l'énergie a amélioré le p10 financier (SW-B : en CAD retraite, h = 0, le p10 passe de 4,11 % à 4,90 % avec 20 %
d'énergie). Le coût ne se voit que dans le patrimoine total (§3). Le plafond L dérivé du ménage est donc indispensable :
sans lui (`_libre`), la même stratégie atteint 20,2 % d'énergie en moyenne (USD). Remarque : avec le budget énergie déjà
consommé par le reliquat de CNQ (≤ 5 %) et le look-through de XIU.TO (§9), il n'est **pas nécessaire d'acheter de l'énergie
neuve** pour atteindre L. L'écart avec le meilleur 60/40 hors énergie (`xen_eq60`) vaut 0,59 point de p10 en USD et 0,32 point
en CAD. Variante sans énergie : `xen_eq60` ou BNC Équilibré.

**Sensibilité à l'horizon** (RE-U-20, RE-C-20) : à 20 ans, USD → request (p10 2,80 %, 13,6 % de violations), puis dual_mom
(2,76 %) ; CAD → dual_mom (7,82 %), puis xen_eq60_defensive (5,45 %). Le classement ne change pas de nature.

**Walk-forward** (choix fait uniquement sur des fenêtres terminées ; AN `walkforward_summary.csv`) :

| poche / ère | n hors éch. | moyenne réelle | p10 | P(réel < 0) | écart moyen à l'oracle | choix |
|---|---|---|---|---|---|---|
| études USD | 79 | 3,55 % | −1,17 % | 16,5 % | 6,27 pts | xen_eq40 55, bnc_prudent 15, … |
| études CAD | 28 | 5,86 % | 0,73 % | 0 % | 6,69 pts | xen_eq60_defensive 20, bnc_prudent 5, … |
| retraite USD | 67 | 6,93 % | 1,66 % | 1,5 % | 2,93 pts | dual_mom 54, request 13 |
| retraite CAD | 16 | 6,35 % | 3,73 % | 0 % | 2,60 pts | bnc_actions 6, dual_mom 5, defensive 5 |
| titres CAD 1995+ | 10 | 3,58 % | 2,10 % | 0 % | 9,93 pts | min_variance 6, risk_parity 4 |

Le coût de ne pas connaître le futur va de 2,6 à 9,9 points/an, et le choix hors échantillon change souvent. Cela plaide pour
une règle simple et stable.

**Effet du plafond énergie sur les stratégies ex-ante** (AN `energy_cap_effect.csv`, même fenêtre et même stratégie) : il est
nul pour les mélanges hors énergie et les BNC Pondéré et moins risqués. Pour la « demande » en études CAD, la médiane est de
−0,38 point réel/an (p10 −0,79), avec −2,8 points de perte max. (médiane). BNC Actions : +0,14 point réel, −1,9 point de perte
max.

## 7. Titres réels CAD 1995+ (TI, TI-L) : l'état actuel face aux limites

Dans la variante sans plafond (TI-L), l'état actuel (CNQ 45 %) **viole la limite de 20 % dans 91 % des 22 fenêtres de 10 ans**
(pire perte max. 38,2 %). C'est aussi le cas de CNQ 45 % + demande (91 %, 37,1 %) et de CNQ 20 % (45 %, 25,5 %). CNQ 5 % et
2,5 % passent (0 %). Le p10 réel est pourtant plus haut avec CNQ 45 % (4,70 %) qu'avec le cœur seul (1,96 %). C'est un
résultat a posteriori sur un titre survivant. Le choix robuste est `risk_parity_iv36` (p10 5,33 % sans plafond, 3,68 % avec)
en CAD 1995+. Oracle sans plafond : énergie directe p10–p90 0–100 %, médiane 45 % (AN `oracle_classes.csv`).

## 8. Rétro-ingénierie (N petit, aucune causalité)

| règle | statut | appui |
|---|---|---|
| coussin en encaisse CAD (CA_TBILL / ZST.TO) | **robuste** | 0 violation sur 55 fenêtres CAD ; positif dans les 9 chocs pétroliers (§5) |
| obligations et cash ne co-baissent pas avec l'énergie | **robuste** (2 ères) | corrélation −0,04 / −0,05 ; rendement moyen positif dans les mois de stress (§3) |
| la concentration employeur viole la capacité | **robuste** sur 1995+ (un seul titre, N = 22 fenêtres qui se chevauchent) | 91 % de violations (§7) |
| sans capital humain énergie, l'énergie est un diversifiant | **robuste** in-sample | SW-B, h = 0 |
| tilt sectoriel défensif (NODUR/HLTH) de l'oracle | **fragile** : présent dans 85–94 % des fenêtres USD, mais le secteur dominant change à chaque décennie, et la version ex-ante (`xen_eq60_defensive`) viole 41,8 % des fenêtres USD en études | AN |
| momentum dual | **fragile** : excellent en CAD (or 1977-80), mais 33 % de violations en études USD | `cross_era.csv` |
| signaux de début de fenêtre (énergie relative 12 mois, perte de l'énergie, inflation 12 mois) → poids énergie de l'oracle | **non concluant** : non chevauchant, N = 3 à 9, aucun ρ significatif ; en roulant (chevauchant), ρ = −0,40 en études CAD et −0,28 en retraite USD (retour à la moyenne ?) | `reverse_signals.csv` |
| inflation 12 mois → part d'actions de l'oracle (retraite CAD) | **non concluant** : ρ = 0,52, p = 0,002, mais 34 fenêtres qui se chevauchent | idem |

## 9. Traduction en tickers et vérification 2021-12 → 2026-09 (REAL)

Correspondances : CA_EQ → XIU.TO ; US_MKT_XEN → SPY (environ 3 % d'énergie, look-through moteur) ou ESGV (variante ; son
exclusion fossile n'est pas vérifiée dans nos données) ; CA_GOV_10Y → XBB.TO ; CA_TBILL → ZST.TO ; US_IND_ENRGY →
CNQ.TO / ENB.TO / XOM. Fenêtre de 58 mois, rééquilibrage annuel, 10 pb.

| poche | traduction (simulation) | réel/an | perte max. | 2022 | mois pires CNQ | énergie look-through |
|---|---|---|---|---|---|---|
| coussin | ZST.TO 100 % | 0,02 % | 0,41 % | +1,22 % | +0,16 % | 0 |
| études | XIU.TO 12 / SPY 28 / XBB.TO 60 (`core_eq40`) | 2,63 % | 13,8 % | −11,2 % | −1,39 % | 1,7–3,5 % |
| études, variante | même mélange avec ESGV | 2,31 % | 15,0 % | −13,0 % | −1,34 % | 0,8–2,5 % |
| retraite | XIU.TO 18 / SPY 42 / XBB.TO 40 (= BNC Équilibré) | 5,48 % | 14,5 % | −11,0 % | −1,79 % | 2,6–5,1 % |
| retraite + reliquat CNQ 5 % | idem × 0,95 + CNQ.TO 5 % | 6,57 % | 12,3 % | −7,9 % | −2,37 % | 8,0–10,4 % (≤ L 15 %) |
| études + reliquat CNQ 2,5 % (base 60/40) | | 6,03 % | 13,4 % | −9,5 % | −2,08 % | 5,3–7,8 % (≤ L 8,6 %) |
| état actuel CNQ 45 % | | 14,51 % | 13,8 % | +16,6 % | **−6,38 %** | 48,7–50,0 % |
| état actuel + demande ENB/XOM | | 17,15 % | 13,2 % | +29,8 % | −6,86 % | 67,7–68,5 % |

La fourchette d'énergie look-through va de la charge XIU.TO 2019-2026 (0,063) à la charge de l'échantillon complet (0,201).
**À dire honnêtement** : sur 2021-2026, la concentration en énergie a payé (période haussière du pétrole). Sa perte max.
mensuelle est même plus faible. Ce que les données montrent, c'est la **co-baisse** : corrélation de 0,95 avec CNQ, et −6,4 %
en moyenne les mois où CNQ va le plus mal, contre −1,8 % pour le 60/40 (REAL). Une seule période haussière de 5 ans ne
contredit pas le risque « double peine » : elle ne l'a simplement pas déclenché.

## 10. Croisement avec l'analyse réglementaire (B1–B6)

### B1. Statuts → contraintes
- **exclu → 0.** Coussin : actions, or et crypto absents de l'univers du coussin.
- **pas maintenant → encaisse.** Crypto (études, retraite) : 0 %, absente de l'univers (pas de proxy avant 2014). Le coût de
  l'inflation est montré sur le coussin (§5.3).
- **limité / satellite → plafond dérivé.** Actions CA limitées (CNQ) : 2,5–5 %. Énergie : 5–10 % en direct, L = 8,6–15 %.
  Actions US hors énergie et or : satellites sans plafond imposé ; leur poids robuste est petit (§10 B3).
- **cœur → pas de plafond.** FNB d'actions et d'obligations.

### B2. Volonté vs capacité (§2, §6)
Q10 [inf] = 30 %. La capacité dérivée vaut 20 % (études) et 30 % (retraite, 25,9 % avant arrondi). Le plafond AMF de la
poche est Q7 (deux emplois du même secteur), qui porte lui aussi sur la capacité. **La capacité gagne en études et fait
égalité en retraite.** Effet : choix robuste xen_eq40 au lieu de dual_mom12_top2, −1,73 point de pire p10.

### B3. Concordance poche × classe

| poche · classe | statut (analyse) | poids robuste (ici) | oracle p10–p90 | verdict | explication |
|---|---|---|---|---|---|
| coussin · actions CA / US / FNB actions | exclu (Q3) | 0 | hors univers | cohérent | CA_EQ −41,9 % et US hors énergie −33,9 % dans les chocs pétroliers (HH) |
| coussin · FNB oblig. | cœur : ZST.TO | 100 % CA_TBILL ≈ ZST.TO | oracle = CA_TBILL 1,00 dans la plupart des années (CO-C) | cohérent | seul actif sans violation ; le 10 ans canadien viole 91 % des fenêtres |
| coussin · or | exclu | 0 | hors univers | cohérent | non testé (volatil sur 1 an) |
| coussin · crypto | exclu (profil 1) | 0 | hors univers | cohérent | non testé |
| études · actions CA | limité : CNQ concentré, aucun nouvel achat | 0 (cœur) ; CNQ ≤ 2,5 % | énergie directe 0–8,6 % sous plafond ; 0–100 % sans (TI-L) | cohérent | l'oracle sans plafond aime CNQ a posteriori, mais l'état actuel viole la capacité dans 91 % des fenêtres |
| études · actions US | satellite hors énergie | 0 | hors énergie 0–91 % (USD), 0–100 % (CAD) | **à trancher** | l'oracle concentre souvent sur des secteurs défensifs, sans stabilité ex-ante (§8) |
| études · FNB actions | cœur | 40 % | 0–64 % (USD), 0–38 % (CAD) | cohérent | cœur indiciel ; l'oracle préfère des secteurs non identifiables à l'avance |
| études · FNB oblig. | cœur | 60 % | 0–71 % (USD), 0–31 % (CAD) | cohérent | amortisseur sans co-baisse avec l'énergie |
| études · or | satellite | 0 (cross-era, pas d'or en USD) ; 17,8 % dans dual_mom CAD | 0–88 % (CAD) | cohérent | corrélation −0,05 avec l'énergie, +1,99 % en stress ; seulement 1977+ |
| études · crypto | pas maintenant | 0 | non testé | cohérent | aucune donnée longue |
| retraite · actions CA | limité | CNQ ≤ 5 % | — | cohérent | idem études |
| retraite · actions US | satellite hors énergie | 1,7 % | 27–100 % (USD), 0–100 % (CAD) | **à trancher** | idem études |
| retraite · FNB actions | cœur | 49–53 % | 0–16 % (USD), 0–63 % (CAD) | cohérent | |
| retraite · FNB oblig. | cœur | 30–34 % | 0–37 % (USD), 0–1 % (CAD) | cohérent | présent pour la limite de perte ; l'oracle CAD n'en veut pas |
| retraite · or | satellite | 0 (USD) / 17 % (CAD) | 0–37 % | cohérent | |
| retraite · crypto | pas maintenant | 0 | non testé | cohérent | |
| transversal · énergie directe, études | aucun nouvel achat | 0 | 0–8,6 % | cohérent | |
| transversal · énergie directe, retraite | aucun nouvel achat | **15 % (au plafond)** | 0–15 % (médiane 15 % en USD) | **contradiction** | la sélection financière seule pousse l'énergie au plafond (in-sample) ; c'est le patrimoine total qui la borne (§6) |

**Bilan : 15 cohérents, 2 à trancher, 1 contradiction** (énergie directe en retraite).

### B4. Profil BNC assigné vs BNC le plus robuste
- **Études** : l'analyse assigne Pondéré (55/13,5/31,5). Avec la capacité de 20 %, Pondéré viole 26,4 % des fenêtres USD,
  juste au-dessus du seuil de 25 %, et 0 % en CAD. Le BNC éligible le plus robuste est **Conservateur** (pire p10 −0,75 %). En
  CAD seul, Équilibré a le meilleur p10 BNC (3,63 %, 0 % de violations). Avec la limite de volonté, Équilibré devient le BNC
  le plus robuste. Verdict : **concordance partielle**. Pondéré se situe entre la réponse « capacité, USD » (Conservateur) et
  la réponse « CAD » (Équilibré).
- **Retraite** : l'analyse assigne Équilibré (40/18/42). Le BNC le plus robuste éligible est **Équilibré** (pire p10 1,51 % ;
  Croissance et Actions violent 38–65 % des fenêtres). Verdict : **concordant**.
- Note : XIU.TO / CA_EQ contient de l'énergie (charge estimée 0,239, §2). Sur 2021-2026, l'énergie look-through de BNC
  Équilibré vaut 2,6–5,1 % (REAL), sous L.

### B5. Réconciliation des chiffres (REC)

Comparaison de nos chiffres (mensuels, CAD, base 2021-11-30 → 2026-09) avec les leurs (quotidiens, 2021-11-12 → 2026-11-12) :

| actif | 2022 ici / eux | CAGR ici / eux | perte max. ici / eux | écart principal |
|---|---|---|---|---|
| CNQ.TO | **49,69 % / 52,92 %** | 27,89 % / 28,68 % | 20,6 % / 33,1 % | le moteur corrige le dividende spécial compté deux fois le 2022-08-22 ; sans correction, notre 2022 = 52,92 % exactement |
| ENB.TO | 13,96 % / 13,96 % | 13,75 % / 12,80 % | 17,4 % / 21,4 % | date de fin ; le creux quotidien n'est pas vu en mensuel |
| XOM | 100,21 % / 100,21 % | 29,94 % / 28,83 % | 17,3 % / 19,1 % | idem |
| SPY | −12,59 % / −12,59 % | 15,24 % / 14,47 % | 18,7 % / 22,2 % | vol. mensuelle 13,5 % vs quotidienne 16,5 % |
| XBB.TO | −11,66 % / −11,66 % | 0,26 % / 0,71 % | 13,0 % / 15,5 % | date de fin |
| GLD | 6,01 % / 6,01 % | 21,39 % / 18,21 % | 21,0 % / 26,0 % | leur creux du 2026-10-30 est après notre fin |

Les rendements 2022 concordent exactement, sauf pour CNQ.TO (le change étant identique, la conversion FX n'introduit pas
d'écart). Les pertes max. mensuelles sont plus faibles : on ne voit pas les creux intramensuels. Pour CNQ, leur creux
(2024-04 → 2025-04) est −33,1 % en quotidien contre −20,6 % en mensuel ; le correctif ne pèse que sur 2022. Les CAGR
diffèrent par la date de fin (+2 mois chez eux). Portefeuilles BNC (proxys XBB/XIU/SPY) : Équilibré 9,13 % / vol. 9,28 % /
perte max. 14,5 % / 2022 −11,0 % ici (REAL), contre 8,8 % / 9,4 % / 16,5 % / −10,9 % chez eux (`10-synthese.md`).

### B6. Comparaison au YAML du persona (oracle de test)

| règle YAML | nos conclusions | verdict |
|---|---|---|
| energy_direct_max ≤ 10 %, aucun nouvel achat | énergie directe 5 % (études) / 10 % (retraite) ; budget couvert par le reliquat de CNQ | **cohérent** (retraite identique, études plus strict) |
| CNQ ramené < 10 % sur 24–36 mois | CNQ 2,5–5 % ; trajectoire graduelle non modélisée (acquisition et blackout inconnus) | **cohérent en direction**, plus strict ; calendrier non testé |
| layoff_buffer ZST.TO ≥ 6 mois | ZST.TO/CA_TBILL cœur ✔ ; 6 mois ⇔ φ entre 0,25 et 0,5 sur la durée médiane d'un choc (§5.3) | **cohérent sous condition** (φ à mesurer) |
| xiu_cap ≤ 10 % | XIU.TO implicite 36 % (études) / 63 % (retraite) à charge 0,239 ; 20 % / 35 % à charge 2007-16 | **pas cohérent** : notre limite est plus large |
| crypto_max 2 % | pas maintenant (0) | **pas cohérent** (même écart que l'analyse réglementaire) |
| soft flags (corrélation du ménage, immobilier local, pas de moralisation) | mesuré (§3) / non modélisé, signalé / ton de risque | cohérent |
| missing_info | identique + dépenses du ménage, φ, part du revenu liée à la production | cohérent |

## 11. Signaux candidats pour l'étape 2 (non testés ici)
- **Prix du pétrole WTI / WCS** (EIA, Alberta Energy Regulator ; absent des données, à sourcer et dater) : mesurer directement
  le bêta revenu–pétrole et remplacer `US_IND_ENRGY` comme facteur de capital humain.
- **Emploi en Alberta / dans l'extraction** (StatCan, Enquête sur la population active) : estimer φ et la durée des mises à pied.
- **USDCAD comme monnaie pétrolière** : le CAD baisse pendant les chocs (§5.2). La part USD non couverte agit comme couverture
  partielle, mais elle est volatile.
- **Composition sectorielle de XIU.TO** (fiche iShares datée) : remplacer la charge estimée.
- **Fondamentaux CNQ** (SEDAR+), prix de l'immobilier à Fort McMurray (CREA, non modélisé).
- Inflation sur 12 mois et force relative de l'énergie : non concluants ici (§8).

## 12. Limites
- Le capital humain est un **scénario** (bêta 1, h constant), pas une mesure ; l'immobilier local n'est pas modélisé.
- Les proxys KF sont des industries SIC (≠ GICS ; ENB est en Utils chez KF). L'or n'existe qu'en 1977+ (ère CAD).
  CA_TBILL est un taux interbancaire, pas un indice investissable. Les obligations sont synthétiques et lissées avant 1962.
- La charge énergie de CA_EQ / XIU.TO est une **estimation statistique** instable : 0,11 à 0,43 selon la décennie.
- **Biais du survivant** : CNQ, XOM et ENB sont choisis en 2026 ; l'énergie US a eu des décennies très fortes in-sample.
- Les fenêtres roulantes se chevauchent (N effectif ≈ 10 / 5 / 3 décennies) ; un seul titre employeur.
- La réponse Q10 est **inférée** ; φ, les dépenses, les règles d'acquisition et de blackout et la pension sont inconnus.
- Pas d'impôts : le gain en capital sur la vente des CNQ n'est pas modélisé ; pas de frais de gestion.

**Particularités du moteur (contournées, `engine/` non modifié) :**
1. `ConstraintSet.project` redistribue l'excédent sur **tous** les actifs, y compris ENB/XOM. Dans TI, « etat_cnq45 »
   projeté devient CNQ 2,8 % + ENB 1,6 % + XOM 1,6 % + … Les états du ménage doivent donc être lus dans la variante `_libre`
   ou via `household.py`.
2. Le moteur n'a **aucun look-through énergie** pour CA_EQ / XIU.TO. Il faut un `exposure_overrides`, ici fondé sur notre
   estimation documentée.
3. La moyenne des poids (`avg_weights`) inclut la dérive entre rééquilibrages : CNQ 2,8 % > plafond 2,5 %.
4. Le walk-forward compte des fenêtres passées qui se chevauchent (déjà signalé par Amira).
5. Doublons par construction : `bnc_equilibre_xen` = `xen_eq60` et `bnc_croissance_xen` = `xen_eq80`, car le partage CA/US
   (30/70) est identique.
6. Les stratégies de même nom diffèrent entre ères (candidats du momentum, or absent en USD) : c'est notre choix, à garder en
   tête dans la règle inter-ères.

Aucun bug bloquant.

## 13. Les quatre questions
- **Quelles données ?** Rendements mensuels KF / FRED / Shiller / Banque du Canada / Yahoo / starter (`data/SOURCES.md`),
  plus `US_MKT_XEN` dérivé (§1). Faits fictifs du persona : 310 k$, dont 140 k$ en CNQ. Aucune série de pétrole ni de revenu.
- **Pourquoi ce choix ?** Quand l'énergie chute, le revenu du ménage et les actions canadiennes baissent en même temps
  (CA_EQ −3,75 % en moyenne dans les pires mois de l'énergie), alors que les obligations et le cash montent (§3). Ramener CNQ
  de 45 % à 2,5–5 % réduit la perte max. du patrimoine total d'environ 10–11 points dans le scénario h = 1/2, et l'état
  actuel viole la capacité dans 91 % des fenêtres (§7). Il s'agit de risque, pas d'un jugement sur le secteur : sans capital
  humain énergie, l'énergie serait plutôt un diversifiant (§3).
- **Quelles limites ?** §12. Les gains passés de CNQ et de l'énergie sont réels in-sample : la sous-pondération a coûté du
  rendement en 1995-2026 et en 2021-2026.
- **Qu'est-ce qui changerait la réponse ?**
  - un emploi hors énergie pour l'un des deux (h baisse → les plafonds remontent ; avec h = 0, aucun plafond énergie) ;
  - une pension à prestations déterminées ou une assurance perte d'emploi (φ baisse → coussin plus petit) ;
  - une série WTI/WCS montrant un bêta revenu–pétrole différent de 1 ;
  - une fiche XIU.TO datée (charge énergie différente) ;
  - les règles d'acquisition et de blackout (calendrier de réduction) ;
  - une réponse Q10 réelle inférieure à 30 % (la volonté deviendrait limitante en retraite).
