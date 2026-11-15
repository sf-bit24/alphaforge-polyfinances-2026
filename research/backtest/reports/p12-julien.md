# Persona 12 · Julien (et Mei-Lin) : backtest 1926-2026, soutenabilité des retraits, croisement réglementaire

> **Simulation historique uniquement, à partir de données publiques.** Ce document ne constitue pas un conseil financier
> personnalisé et n'entraîne aucune transaction. Les lignes `ORACLE` (`hindsight=True`) utilisent le futur : elles sont
> **non investissables** et ne servent qu'à la rétro-ingénierie. Tous les seuils sont des **propositions à valider par
> l'équipe**, dérivées des données ; aucun seuil, aucune allocation et aucun « fait de marché » de la fiche du persona
> n'a été utilisé. Un taux de retrait n'est **jamais « sûr »** : on montre des fréquences d'épuisement passées et un modèle.

Chemins relatifs à `research/backtest/`. Données `data_sha256 = 008f122d5da4f8f7` (build 2026-11-14T22:15Z), moteur
`engine_sha256 = 4d3e707a3271717d`, graine 42. Moteur et données **non modifiés**. Code propre au persona :
`analysis/p12/` ; profils générés : `profiles/p12_*.yaml` (par `analysis/p12/make_profiles.py`).

## 0. Références des traces (chaque chiffre cite l'une d'elles)

| tag | fichier | contenu |
|---|---|---|
| [DT] | `results/p12_analysis/derive_thresholds.json` | capacité, volonté, fenêtre de séquence k\* (`analysis/p12/derive_thresholds.py`) |
| [DC] | `results/p12_analysis/derive_caps.json` | plafonds titres / secteurs / or / crypto (`derive_caps.py`) |
| [SWR] | `results/p12_analysis/swr.json` | taux de retrait parfait (PWR), échecs, bootstrap, flexibilité, glidepath, stress 2022, âge ±2 ans, ORACLE de retrait (`swr.py`) |
| [WF] | `results/p12_analysis/wf_swr.json` | walk-forward du choix « meilleur pire cas de retrait » (`wf_swr.py`) |
| [REV] | `results/p12_analysis/reverse.json` | règles robustes/fragiles, signaux de début de fenêtre (`reverse.py`) |
| [TAB] | `results/p12_analysis/tables.json` | synthèse des traces moteur (`tables.py`) |
| [TK] | `results/p12_analysis/tickers_2021_2026.json` | vérification en tickers réels (`tickers.py`, `profiles/p12_tickers.yaml`) |
| [REC] | `results/p12_analysis/reconcile.json` | réconciliation avec `analyse/relation-profils-actifs/quant` (`reconcile.py`) |
| [A1] / [A2] | `results/p12_accum_usd/20261114T234926Z_non_overlapping_h6.json` / `…235059Z_rolling_h6.json` | accumulation USD 1926+ |
| [A3] / [A4] | `results/p12_accum_cad/20261114T234914Z_non_overlapping_h6.json` / `…235009Z_rolling_h6.json` | accumulation CAD 1977+ |
| [A5] / [A6] | `results/p12_accum_cad_h2/20261114T234911Z_non_overlapping_h6.json` / `…235005Z_rolling_h6.json` | accumulation CAD, cotisations H2 |
| [D1] / [D2] | `results/p12_decum_usd/20261114T234931Z_non_overlapping_h50.json` / `…235728Z_rolling_h50.json` | décaissement USD, 50 ans |
| [D3] / [D4] | `results/p12_decum_usd/20261114T235014Z_non_overlapping_h10.json` / `…235343Z_rolling_h10.json` | décaissement USD, décennie de séquence |
| [D5] / [D6] | `results/p12_decum_cad/20261114T235000Z_non_overlapping_h30.json` / `…235225Z_rolling_h30.json` | décaissement CAD, 30 ans |
| [D7] / [D8] | `results/p12_decum_cad/20261114T235039Z_non_overlapping_h10.json` / `…235245Z_rolling_h10.json` | décaissement CAD, 10 ans |
| [W1]–[W4] | `results/p12_decum_usd_will/…235117Z_rolling_h50.json`, `…235127Z_rolling_h10.json`, `results/p12_decum_cad_will/…235053Z_rolling_h30.json`, `…235126Z_rolling_h10.json` | mêmes runs, limite de **volonté seule** (sans oracle) |

Chaque trace moteur a ses `_windows.csv`, `_robust.csv`, `_walkforward.csv` à côté. Logs : `results/p12_logs/`.
Relancer : `bash analysis/p12/run_jobs.sh` (liste `analysis/p12/jobs.txt`) puis les scripts d'analyse (§14).

## 1. Question

Couple de 36 et 35 ans (Ontario, CAD), sans enfant ni héritier, revenu de ménage fictif de 205 k$, épargne déclarée de
58 %, capital fictif de 640 k$. Objectif : environ 1,3 M$ à 42 ans, puis retraits de 52 k$/an indexés de 42 à 92 ans
et plus ; marge de retour partiel au travail. Tolérance déclarée élevée ; capacité élevée aujourd'hui, **modérée dès
l'arrêt du revenu de travail**. Le persona teste un point : le système distingue-t-il les deux phases et refuse-t-il de
valider « 4 % sur 50 ans » sans preuve, en montrant le risque de séquence autour de 42 ans ?

Deux poches (comme les lignes `id=12` de `personas-tous.csv`) :

| poche | horizon de fenêtre retenu | pourquoi |
|---|---|---|
| **accumulation** | **6 ans** (36 → 42) | durée exacte jusqu'à la date de liberté ; flux : 640 k$ + cotisations mensuelles indexées |
| **décaissement** | **50 ans** (42 → 92), **55 ans** en stress de longévité (97 ans), **48/52 ans** pour l'âge ±2 ans, **10 ans** pour la « décennie de séquence » | horizon du plan ; k\* ≈ 9-11 ans dérivé des données (§4.3) |

**Objectifs moteur** (`profiles/p12_*.yaml`) :
- accumulation : `min_shortfall`, `target_real_wealth = 1 300 000` (score = richesse réelle finale / 1,3 M$ − 1) ;
  cotisation **H1 = 58 % × 205 k$ / 12 = 9 908 $/mois** indexée (borne haute : base brute, impôts ignorés) et
  **H2 = H1 / 2** en stress. La fiche ne dit pas si les 58 % portent sur le brut ou le net : c'est une hypothèse.
- décaissement : `min_shortfall`, `target_real_return = 0,03153`. C'est le rendement réel qui finance une rente de
  52/1 300 = 4,0 % pendant 50 ans (`make_profiles.py`, `R_REQ`). Flux : 1,3 M$ puis −4 333 $/mois indexés.
  **Limite du moteur** : les flux n'affectent que la richesse finale ; les autres métriques sont pondérées par le
  temps. Le vrai critère de Julien (l'épuisement) est donc calculé à part, dans `analysis/p12/swr.py` (§6).

## 2. Données et ères

| ère | devise / inflation | univers | période effective |
|---|---|---|---|
| **USD 1926+** | USD, CPI-U | US_MKT, US_IND_UTILS, US_IND_MONEY, US_IND_BUSEQ, US_IND_HLTH, UST_10Y, UST_5Y, UST_2Y, UST_TBILL | 1926-08 → 2026-09 (1 202 mois) [D2] |
| **CAD 1977+** | CAD, IPC Canada ; actifs US non couverts | CA_EQ, US_MKT, mêmes 4 secteurs US, CA_GOV_10Y, UST_5Y, GOLD, CA_TBILL | 1977-01 → 2026-09 (actif limitant CA_EQ) [D6] |
| tickers réels | CAD | XIU.TO, SPY, XBB.TO, ZST.TO, AGG, GLD, FTS.TO, RY.TO, BTC-USD | fenêtre 2021-11 → 2026-09 (59 mois), historique visible depuis 2014-10 [TK] |

**Hypothèse déclarée (ère USD)** : on assimile le ménage canadien à un investisseur en USD sur des proxys américains,
avec l'inflation US. Il n'y a pas d'USDCAD gratuit avant 1971 et les actions canadiennes commencent en 1977. Les secteurs KF
servent de **proxys de titres individuels** : US_IND_UTILS ≈ FTS.TO, US_IND_MONEY ≈ RY.TO/TD.TO (dividendes canadiens),
US_IND_BUSEQ, US_IND_HLTH ≈ titres US. L'or est exclu de l'ère USD (non investissable avant 1975) et testé en CAD 1977+
et USD 1975+. La crypto n'a pas d'historique long : elle n'est testée qu'à partir de 2014-10. Sources :
`data/SOURCES.md`.

**Nombre de fenêtres réellement indépendantes** (le point clé pour un horizon de 50 ans) [SWR] :

| ère | H | fenêtres roulantes (départ mensuel) | départs annuels | **indépendantes** |
|---|---|---|---|---|
| USD 1926+ | 30 | 843 | 70 | **3** |
| USD 1926+ | 40 | 723 | 60 | **2** |
| USD 1926+ | 50 | 603 | 50 | **2** |
| USD 1926+ | 55 | 543 | 45 | **1** |
| CAD 1977+ | 30 | 238 | 20 | **1** |
| CAD 1977+ | 40 | 118 | 10 | **1** |
| CAD 1977+ | 50 | 0 | 0 | **0** (49,75 ans de données) |

Un backtest de 5 ans (2021-2026) ne prouve rien sur 50 ans. Même 100 ans de données ne donnent que **2 fenêtres
indépendantes de 50 ans**. Toute probabilité d'épuisement sur 50 ans est donc une **extrapolation** : les fenêtres
roulantes se chevauchent à plus de 95 %.

## 3. Fenêtres et exécutions moteur

| exécution | fenêtres | trace |
|---|---|---|
| accumulation USD, 6 ans, non chevauchant / roulant 12 m | 16 / 95 | [A1] / [A2] |
| accumulation CAD, 6 ans | 8 / 44 | [A3] / [A4] |
| accumulation CAD, cotisation H2 | 8 / 44 | [A5] / [A6] |
| décaissement USD, 50 ans | 2 / 51 | [D1] / [D2] |
| décaissement USD, 10 ans (séquence) | 10 / 91 | [D3] / [D4] |
| décaissement CAD, 30 ans (50 ans impossible) | 1 / 20 | [D5] / [D6] |
| décaissement CAD, 10 ans | 4 / 40 | [D7] / [D8] |
| décaissement, limite de volonté seule | 51 / 91 / 20 / 40 | [W1]-[W4] |

Stratégies ex-ante (toutes projetées sur les contraintes, coûts de 10 pb, rebalancement annuel sauf tendance et
momentum, qui sont mensuels) : les **6 portefeuilles BNC publics** (revenu fixe = CA_GOV_10Y ou UST_10Y,
actions CA = CA_EQ, actions mondiales = US_MKT ; en USD, actions CA + mondiales = US_MKT) ; 100 % actions
(CA30/US70, US seul, CA seul) ; 70/5 or/25 ; 60 + coussin 10 % cash + 30 ; 60/40 sur obligations de 5 et 2 ans ;
« inclinaison dividendes » (CA_EQ 40 %, US_MKT 18 %, secteurs UTILS+MONEY aux plafonds, obligations 40 %) ; parité de
risque 36 m ; variance minimale ; moyenne-variance ; filtre de tendance sur un 60/40 ; momentum avec 40 % d'obligations
en noyau ; glidepath « tente » 85 → 55 % (accumulation) ou glidepath montant 40 → 70 % (décaissement).
Sélection : meilleur 10e centile du score, exclusion si taux de violation > 10 %.

## 4. Seuils dérivés (propositions à valider)

### 4.1 Volonté (AMF Q10) et capacité, poche par poche [DT]

- **Volonté** : la ligne `id=12` donne « Q10 élevée → 4-5 **(I)** » (réponse **inférée**). Palier 4 = baisse
  tolérable de 30 % ; palier 5 = plus de 30 %. Par la règle du plafond le plus bas, on retient **0,30**.
- **Capacité, accumulation**. Règle : un mélange statique « e % actions + jambe obligataire » est admissible si sa plus
  longue période sous l'eau **nominale** sur l'ère reste ≤ 72 mois (l'horizon). L\*acc est la perte max. du mélange
  admissible le plus profond. Une règle en termes réels n'admet aucun mélange en USD : même les T-bills restent sous
  leur sommet réel pendant 818 mois [DT, `usd_1926.grid`].
- **Capacité, décaissement**. C1 : perte max. du mélange le plus profond dont la plus longue période sous l'eau
  **réelle** ≤ 12·k\* mois, avec k\* = 11 ans (§4.3). C2 : perte max. du mélange qui maximise le pire taux de retrait
  (SAFEMAX) sur l'horizon le plus long de l'ère. Capacité = min(C1, C2). Comme pour Robert, on retient la valeur
  **la plus prudente des deux ères** : la capacité appartient au ménage, pas à l'ère.

| poche | USD 1926+ | CAD 1977+ | **capacité retenue** | volonté | **limite appliquée (min)** | qui gagne |
|---|---|---|---|---|---|---|
| accumulation | L\* 0,352 (30 % US_MKT / 70 % UST_10Y, 68 mois sous l'eau) | L\* 0,305 (80 % actions / 20 % CA_GOV_10Y, 66 mois) | 0,305 | 0,30 | **0,30** | volonté (de peu) |
| décaissement | C1 0,691 (70/30 UST_2Y) ; C2 0,615 (60/40 UST_5Y, SAFEMAX 50 ans 0,0346) | C1 **0,252** (70/30 CA_GOV_10Y, 75 mois sous l'eau réelle) ; C2 0,305 (80/20, SAFEMAX 40 ans 0,0717) | 0,252 | 0,30 | **0,252** | **capacité** |

Le passage de la capacité de 0,305 à 0,252 au jour 1 de la retraite reproduit, à partir des données, ce que dit
l'analyse réglementaire (« capacité modérée après arrêt du travail »).

### 4.2 Plafonds des classes satellite / limitée [DC]

Règle : une poche satellite ou limitée ne doit pas aggraver la perte max. du portefeuille de base de plus de **1 point**
(2 points en variante), dans le **pire cas** parmi les titres candidats. Le financement est pris au prorata. Les
portefeuilles de base sont les cibles BNC publiques : Croissance pour l'accumulation, Équilibré pour le décaissement.

| classe (statut) | test | accumulation (1 pt / 2 pt) | décaissement (1 pt / 2 pt) | titre qui contraint |
|---|---|---|---|---|
| actions CA, titres (satellite / limité) | 10 titres .TO, CAD, 2000-12+ | **1 %** / 2 % | **1 %** / 2 % | SHOP.TO (+1,9 pt à 2 %, période 2015+) |
| actions US, titres (satellite / limité) | 10 titres US, CAD | **5 %** / 7 % | **3 %** / 5 % | NVDA (+0,87 pt à 5 % en accumulation ; +1,65 pt à 5 % en décaissement) |
| proxys sectoriels (moteur) | 6 secteurs KF | USD 3 % / 7 % ; CAD 1 % / 3 % | USD 2 % / 3 % ; CAD 1 % / 2 % | US_IND_BUSEQ, US_IND_MONEY |
| crypto (limité) | BTC-USD 2014-10+, ETH-USD 2017-12+ | **1 %** / 2 % | **1 %** / 2 % | ETH-USD (+1,42 pt à 2 %) ; BTC seul +0,95 pt à 2 % |
| or (satellite) | SAFEMAX 30 ans CAD 1977+ / 40 ans USD 1975+ | **5 %** (proposition commune) | **5 %** | CAD : 5 % d'or améliore le SAFEMAX à 40 % d'actions (0,0681 → 0,0689), mais le dégrade à 60 % (0,0730 → 0,0709) ; USD 1975+ : 10 % / 5 % |

Ces plafonds sont injectés dans les profils (`asset_bounds`). Les règles sont lisibles, mais **N est petit** et les
titres ont été choisis en 2026 (biais du survivant).

### 4.3 Fenêtre de séquence k\* [DT]

On calcule, sur chaque fenêtre roulante, la corrélation de Spearman entre le taux de retrait parfait (60/40) et le
rendement réel des k premières années. k\* est le premier k qui atteint 90 % du maximum.
**USD : k\* = 9 (H=30), 10 (H=40), 11 (H=50)** ; à k = 11 et H = 50, ρ = 0,86 (maximum de 0,92 à k = 13). En CAD,
k\* vaut 9 (H=30) et 4 (H=40), mais avec **une seule fenêtre indépendante** : ce n'est pas exploitable. On retient
**k\* ≈ 10-11 ans** : la première décennie de retraite (42-52 ans) explique l'essentiel du résultat.

## 5. Choix robuste et walk-forward (moteur)

### 5.1 Accumulation : résultats par fenêtre (6 ans, non chevauchant)

**USD** [A1], choix robuste `bnc_pondere` (US_MKT 45 % / UST_10Y 55 %) :

| fenêtre | ORACLE (> 3 %) | ORACLE score | ORACLE maxDD | meilleure ex-ante (a posteriori) | son score | Pondéré score | réel | maxDD | richesse réelle finale ($) | objectif manqué ? |
|---|---|---|---|---|---|---|---|---|---|---|
| 1926-08..1932-07 | UST_5Y 1,00 | 0,575 | 0,103 | risk_parity_36m | 0,887 | 0,131 | 0,036 | 0,456 | 1 469 888 | non |
| 1932-08..1938-07 | US_MKT 0,53, UST_10Y 0,41 | 0,715 | 0,300 | bnc_actions | 1,006 | 0,572 | 0,109 | 0,209 | 2 043 856 | non |
| 1938-08..1944-07 | US_MKT 0,97 | 0,298 | 0,281 | bnc_actions | 0,295 | 0,116 | 0,012 | 0,121 | 1 451 331 | non |
| 1944-08..1950-07 | US_MKT 0,91 | 0,354 | 0,244 | bnc_actions | 0,351 | 0,113 | 0,014 | 0,110 | 1 446 499 | non |
| 1950-08..1956-07 | US_MKT 0,97 | 1,587 | 0,070 | bnc_actions | 1,566 | 0,584 | 0,092 | 0,032 | 2 058 900 | non |
| 1956-08..1962-07 | US_MKT 0,88 | 0,344 | 0,239 | mean_variance_60m | 0,316 | 0,208 | 0,032 | 0,098 | 1 570 082 | non |
| 1962-08..1968-07 | US_MKT 0,91 | 0,651 | 0,154 | bnc_actions | 0,622 | 0,278 | 0,052 | 0,084 | 1 661 028 | non |
| 1968-08..1974-07 | UST_TBILL 1,00 | 0,026 | 0,000 | min_variance_60m | 0,007 | −0,176 | −0,044 | 0,178 | 1 071 164 | **oui** |
| 1974-08..1980-07 | US_MKT 0,91 | 0,340 | 0,186 | bnc_actions | 0,337 | 0,060 | 0,008 | 0,096 | 1 378 493 | non |
| 1980-08..1986-07 | UST_10Y 0,46, US_MKT 0,45 | 0,907 | 0,096 | trend_eq60 | 0,927 | 0,899 | 0,122 | 0,093 | 2 468 483 | non |
| 1986-08..1992-07 | US_MKT 0,94 | 0,509 | 0,293 | bnc_actions | 0,496 | 0,418 | 0,065 | 0,126 | 1 843 153 | non |
| 1992-08..1998-07 | US_MKT 0,91 | 1,297 | 0,075 | bnc_actions | 1,244 | 0,701 | 0,106 | 0,082 | 2 211 150 | non |
| 1998-08..2004-07 | UST_10Y 0,94 | 0,223 | 0,087 | momentum_core_bond | 0,256 | 0,137 | 0,022 | 0,090 | 1 477 595 | non |
| 2004-08..2010-07 | UST_10Y 0,94 | 0,256 | 0,080 | trend_eq60 | 0,328 | 0,162 | 0,026 | 0,163 | 1 510 672 | non |
| 2010-08..2016-07 | US_MKT 0,94 | 0,764 | 0,174 | bnc_actions | 0,749 | 0,424 | 0,073 | 0,033 | 1 850 737 | non |
| 2016-08..2022-07 | US_MKT 0,94 | 0,531 | 0,218 | bnc_actions | 0,516 | 0,137 | 0,027 | 0,162 | 1 477 977 | non |

**CAD** [A3], choix robuste `trend_eq60` (filtre de tendance sur CA_EQ 18 / US_MKT 42 / CA_GOV_10Y 40) :

| fenêtre | ORACLE (> 3 %) | ORACLE score | ORACLE maxDD | meilleure ex-ante | son score | choix score | réel | maxDD | richesse réelle finale ($) | manqué ? |
|---|---|---|---|---|---|---|---|---|---|---|
| 1977-01..1982-12 | US_MKT 0,76, CA_EQ 0,16, GOLD 0,05 | 0,409 | 0,164 | eq100_us | 0,370 | 0,253 | 0,033 | 0,087 | 1 629 164 | non |
| 1983-01..1988-12 | US_MKT 0,74, CA_GOV_10Y 0,25 | 0,541 | 0,223 | eq100_us | 0,531 | 0,332 | 0,066 | 0,145 | 1 731 777 | non |
| 1989-01..1994-12 | US_MKT 0,97 | 0,759 | 0,175 | eq100_us | 0,754 | 0,370 | 0,065 | 0,094 | 1 780 914 | non |
| 1995-01..2000-12 | US_MKT 0,96 | 1,269 | 0,131 | eq100_us | 1,243 | 0,708 | 0,125 | 0,095 | 2 220 938 | non |
| 2001-01..2006-12 | CA_EQ 0,95, GOLD 0,05 | 0,590 | 0,273 | eq100_ca | 0,589 | 0,306 | 0,047 | 0,043 | 1 697 195 | non |
| 2007-01..2012-12 | CA_GOV_10Y 0,95, GOLD 0,05 | 0,319 | 0,043 | bnc_prudent | 0,265 | 0,204 | 0,029 | 0,047 | 1 565 299 | non |
| 2013-01..2018-12 | US_MKT 0,97 | 0,991 | 0,106 | eq100_us | 0,983 | 0,332 | 0,065 | 0,047 | 1 731 145 | non |
| 2019-01..2024-12 | US_MKT 0,99 | 0,949 | 0,205 | eq100_us | 0,943 | 0,264 | 0,041 | 0,113 | 1 643 332 | non |

### 5.2 Accumulation : sélection robuste et walk-forward

| run | choix robuste | p10 score | médiane | pire maxDD | violations | P(manquer 1,3 M$) | walk-forward : n / score moyen / P(manquer) / écart oracle |
|---|---|---|---|---|---|---|---|
| USD non chev. [A1] | bnc_pondere | 0,0865 | 0,1849 | 0,456 | 0,06 | 0,06 | 13 / 0,296 / 0,08 / 0,303 |
| USD roulant [A2] | dividend_tilt | 0,0259 | 0,2968 | 0,591 | 0,06 | 0,08 | 87 / 0,261 / 0,15 / 0,292 |
| CAD non chev. [A3] | trend_eq60 | 0,2385 | 0,3186 | 0,145 | 0,00 | 0,00 | 5 / 0,431 / 0,00 / 0,393 |
| CAD roulant [A4] | momentum_core_bond | 0,2454 | 0,3801 | 0,126 | 0,00 | 0,00 | 36 / 0,421 / 0,00 / 0,392 |
| CAD H2 non chev. [A5] | trend_eq60 | −0,0835 | 0,0006 | 0,145 | 0,00 | **0,50** | 5 / 0,092 / 0,60 / 0,336 |
| CAD H2 roulant [A6] | momentum_core_bond | −0,0753 | 0,0461 | 0,126 | 0,00 | **0,34** | 36 / 0,080 / 0,39 / 0,324 |

Valeurs tirées de [TAB] (et des `_robust.csv`). En USD roulant, les cinq premiers sont à égalité pratique : p10 de
0,0259 (dividend_tilt), 0,0251 (60 + coussin), 0,0241 (BNC Équilibré), 0,0225 (60/40 UST_5Y), 0,0174 (BNC Pondéré) [A2].
**Choix inter-ères** (meilleur rang le plus défavorable sur les 4 runs H1) : `dividend_tilt`, pire rang 3, devant
bnc_pondere (6), bnc_equilibre et eq60_ust2y40 (7) [calcul sur les `robust_selection` de A1-A4]. La règle robuste
est une **famille** (45-60 % d'actions, 40-55 % d'obligations), pas une variante. Le « dividend tilt » est surtout un
biais domestique (XIU.TO 40 %) : les titres à dividendes n'y pèsent que 1-3 % (plafonds §4.2). Il ne valide donc **pas**
le biais de dividende.

Constats :
- Avec H1, presque toutes les stratégies atteignent 1,3 M$. **C'est l'épargne, pas le rendement, qui atteint
  l'objectif** : même le BNC Pondéré, dans la pire fenêtre de 1968-74, termine à 1 071 164 $ réels [A1]. Avec H2, le
  taux d'échec monte à 0,34-0,50 [A5, A6] : la cotisation est la variable dominante, et elle manque (brut ou net ?).
- **100 % actions** (BNC Actions, eq100) : violations de 0,25 à 0,41 (pire maxDD de 0,39 à 0,84). La stratégie est
  exclue de la sélection robuste dans les 4 runs [A1-A4].
- La « tente » obligataire 85 → 55 % n'est pas robuste : rang 11 en CAD, et exclue en USD roulant (violations de 0,22) [A2-A4].
- Le walk-forward coûte de 0,29 à 0,39 de score (richesse/cible) face à l'ORACLE : ne pas connaître le futur a un coût
  irréductible.

### 5.3 Décaissement : ce que dit le moteur (rendement pondéré par le temps)

| run | limite | choix robuste | p10 (réel − 3,15 %) | P(réel < 3,15 %) | 100 % actions : p10 / violations |
|---|---|---|---|---|---|
| USD 50 ans roulant [D2] | 0,252 (min) | **bnc_conservateur** | −0,0113 | 0,33 | 0,0222 / 1,00 |
| USD 50 ans roulant [W1] | 0,30 (volonté) | trend_eq60 | −0,0011 | 0,14 | 0,0222 / 1,00 |
| USD 10 ans roulant [D4] | 0,252 | trend_eq60 | −0,0306 | 0,32 | −0,0369 / 0,62 |
| USD 10 ans roulant [W2] | 0,30 | bnc_equilibre | −0,0272 | 0,25 | −0,0369 / 0,47 |
| CAD 30 ans roulant [D6] = [W3] | 0,252 / 0,30 | eq70_gold5_bond25 | 0,0360 | 0,00 | 0,0392 / 1,00 |
| CAD 10 ans roulant [D8] = [W4] | 0,252 / 0,30 | momentum_core_bond | 0,0123 | 0,05 | −0,0037 / 0,68 |

Sans limite de risque, **le 100 % actions aurait le meilleur p10 pondéré par le temps sur 50 ans USD** (0,0222 [D2]).
C'est l'inverse du résultat avec retraits (§6) : le moteur ne voit pas la séquence. Pour ce persona, il ne faut **pas**
choisir la stratégie de décaissement sur le score du moteur. Le walk-forward est impossible à 50 ans (il faudrait
au moins 3 fenêtres terminées) ; il est fait à 30 et 40 ans au §6.4.

Résultats par fenêtre de la décennie de séquence (USD 10 ans, non chevauchant [D3], choix `bnc_pondere`) :

| fenêtre | ORACLE (> 3 %) | ORACLE score | meilleure ex-ante | son score | Pondéré score | réel | maxDD | richesse réelle finale ($) | manqué ? |
|---|---|---|---|---|---|---|---|---|---|
| 1926-08..1936-07 | UST_10Y 0,79, US_MKT 0,13 | 0,048 | momentum_core_bond | 0,075 | 0,058 | 0,090 | 0,456 | 2 230 725 | non |
| 1936-08..1946-07 | UST_10Y 0,51, US_MKT 0,47 | −0,008 | bnc_actions | 0,012 | −0,012 | 0,020 | 0,209 | 952 668 | oui |
| 1946-08..1956-07 | US_MKT 0,96 | 0,086 | bnc_actions | 0,085 | 0,016 | 0,047 | 0,080 | 1 248 104 | non |
| 1956-08..1966-07 | US_MKT 0,94 | 0,047 | bnc_actions | 0,044 | 0,009 | 0,040 | 0,098 | 1 286 199 | non |
| 1966-08..1976-07 | UST_2Y 0,88, US_MKT 0,06 | −0,026 | trend_eq60 | −0,021 | −0,038 | −0,006 | 0,224 | **731 404** | oui |
| 1976-08..1986-07 | US_MKT 0,94 | 0,052 | bnc_actions | 0,050 | 0,033 | 0,065 | 0,096 | 1 508 082 | non |
| 1986-08..1996-07 | US_MKT 0,81, UST_10Y 0,15 | 0,055 | bnc_actions | 0,061 | 0,035 | 0,067 | 0,126 | 1 722 844 | non |
| 1996-08..2006-07 | US_MKT 0,63, UST_10Y 0,31 | 0,029 | trend_eq60 | 0,031 | 0,021 | 0,053 | 0,090 | 1 586 195 | non |
| 2006-08..2016-07 | US_MKT 0,50, UST_10Y 0,44 | 0,028 | trend_eq60 | 0,032 | 0,023 | 0,055 | 0,163 | 1 497 180 | non |
| 2016-08..2026-07 | US_MKT 0,96 | 0,082 | bnc_actions | 0,081 | 0,003 | 0,034 | 0,206 | 1 201 793 | non |

Partir à la retraite en 1966 aurait laissé, après 10 ans de retraits de 4 %, 731 404 $ réels sur 1,3 M$ [D3].

## 6. Soutenabilité des retraits (calcul propre, `analysis/p12/swr.py`)

**Méthode.** Retrait annuel = taux × capital initial, payé chaque mois (taux/12), indexé sur l'IPC de l'ère depuis le
départ. Épuisement = richesse ≤ 0 avant la fin. Taux de retrait parfait (PWR) d'une fenêtre, en forme fermée :
PWR = 12 / Σ c_s/G_s, où G est la croissance cumulée et c l'indice des prix. Un taux r épuise le capital **si et
seulement si** r > PWR (vérifié par simulation mois par mois). SAFEMAX = PWR minimal = plus haut taux sans aucun
épuisement passé. Mélanges constants rebalancés chaque mois (simplification déclarée). Ni frais, ni impôts, ni RPC/SV.

### 6.1 Historique : taux de retrait par horizon (USD 1926+) [SWR `eras.usd_1926.tables`]

| mélange | H = 30 SAFEMAX / p10 | H = 40 | **H = 50** | H = 55 | échec à 4 % sur 50 ans | échec à 3,5 % sur 50 ans | pire départ (50 ans) |
|---|---|---|---|---|---|---|---|
| **60/40 (US_MKT / UST_5Y)** | 0,0392 / 0,0456 | 0,0364 / 0,0413 | **0,0346** / 0,0380 | 0,0340 / 0,0370 | 0,179 | 0,002 | 1968-12 |
| 70/30 (UST_5Y) | 0,0385 / 0,0459 | 0,0360 / 0,0419 | 0,0341 / 0,0387 | 0,0332 / 0,0379 | 0,136 | 0,003 | 1929-09 |
| 50/50 (UST_5Y) | 0,0397 / 0,0445 | 0,0360 / 0,0395 | 0,0322 / 0,0363 | 0,0313 / 0,0354 | 0,323 | 0,028 | 1937-03 |
| BNC Équilibré (UST_10Y 40 / US_MKT 60) | 0,0380 / 0,0444 | 0,0354 / 0,0404 | 0,0339 / 0,0373 | 0,0334 / 0,0363 | 0,199 | 0,017 | 1968-12 |
| BNC Croissance (80 % actions) | 0,0363 / 0,0454 | 0,0342 / 0,0416 | 0,0325 / 0,0386 | 0,0317 / 0,0378 | 0,124 | 0,012 | 1929-09 |
| BNC Pondéré | 0,0378 / 0,0422 | 0,0349 / 0,0377 | 0,0322 / 0,0347 | 0,0312 / 0,0338 | 0,448 | 0,128 | 1937-03 |
| BNC Conservateur | 0,0363 / 0,0390 | 0,0310 / 0,0335 | 0,0268 / 0,0289 | 0,0259 / 0,0277 | 0,824 | 0,494 | 1940-05 |
| **100 % actions (BNC Actions)** | 0,0289 / 0,0447 | 0,0278 / 0,0414 | **0,0268** / 0,0391 | 0,0264 / 0,0379 | 0,129 | 0,030 | 1929-09 |
| 100 % T-bills | — | — | 0,0125 [DT] | — | — | — | — |

- **Meilleur SAFEMAX** : 50/50 à 30 ans (0,0397), **60/40 UST_5Y de 40 à 55 ans** (0,0364 → 0,0340) [SWR `best_by_min`].
- Le 100 % actions (la demande du couple) a le **pire** SAFEMAX des mélanges riches en actions (0,0268 sur 50 ans,
  départ 1929-09), même si son p10 et sa médiane sont plus hauts. Le risque de séquence est là.
- **Règle des 4 % (fait externe, à vérifier)** : Bengen, W. P. (1994), « Determining Withdrawal Rates Using Historical
  Data », *Journal of Financial Planning*. Le résultat porte sur **30 ans**, avec des données US et 50-75 % d'actions.
  Il n'est pas recalculé à l'identique ici (données annuelles chez Bengen, mensuelles ici). Nos données le recoupent à
  30 ans (SAFEMAX 0,0397 à 50 % d'actions), **mais pas à 50 ans** : 0,0346 au mieux, et 4 % échoue dans 17,9 % des
  603 départs mensuels du 60/40.
- **CAD 1977+** : SAFEMAX de 0,0730 (BNC Équilibré, 30 ans) et de 0,0717 (80/20, 40 ans) [SWR `eras.cad_1977`]. Ces
  chiffres ne sont **pas crédibles comme estimation** : il n'y a qu'une fenêtre indépendante, et tous les départs
  (1977-1996) profitent de la désinflation et de la baisse des taux 1981-2020. Même 100 % T-bills CAD donne 0,0374 sur
  30 ans. On les présente comme une ère favorable, pas comme une norme.

### 6.2 Modèle : bootstrap par blocs (USD, 4 000 trajectoires, graine 42) [SWR `bootstrap_usd`]

Bootstrap stationnaire (Politis-Romano) sur les lignes mensuelles jointes (rendements et IPC), blocs moyens de 60 et
de 120 mois. **Modèle, pas prévision** : il casse le retour à la moyenne des valorisations et des taux.

| mélange | échec 50 ans à 3,0 % (60 / 120) | 3,5 % | **4,0 %** | 4,5 % | échec 55 ans à 4,0 % |
|---|---|---|---|---|---|
| 60/40 UST_5Y | 0,045 / 0,031 | 0,100 / 0,077 | **0,182 / 0,164** | 0,292 / 0,270 | 0,202 / 0,183 |
| BNC Équilibré | 0,045 / 0,033 | 0,097 / 0,079 | 0,173 / 0,155 | 0,274 / 0,256 | 0,191 / 0,174 |
| BNC Croissance | 0,046 / 0,032 | 0,084 / 0,066 | 0,140 / 0,124 | 0,214 / 0,193 | 0,149 / 0,135 |
| 100 % actions | 0,059 / 0,039 | 0,093 / 0,076 | 0,146 / 0,126 | 0,203 / 0,184 | 0,153 / 0,132 |
| BNC Conservateur | — | 0,280 / 0,274 | 0,454 / 0,442 | 0,606 / 0,619 | — |

Le bootstrap favorise un peu plus d'actions (80-100 %) que l'historique, qui favorise 60 %. **Ce point est
non concluant** : il dépend du modèle. La conclusion, elle, est la même dans les deux cas : **4 % sur 50 ans échoue
dans environ 12 à 20 % des cas**, quel que soit le mélange.

### 6.3 Taux de retrait soutenable dérivé (proposition à valider)

**Règle** : on retient le plus haut taux qui (a) n'a **jamais** épuisé le capital dans l'historique USD 1926+ à 50 ans
avec le meilleur mélange statique, **et** (b) épuise dans au plus 5 % des trajectoires bootstrap, pour les deux
longueurs de bloc (grille de 0,5 pt).
- (a) donne **3,46 %** (60/40 UST_5Y ; 3,40 % à 55 ans) [SWR] ;
- (b) donne **3,0 %** : échec de 4,5 % et 3,1 % à 3,0 % ; 10,0 % et 7,7 % à 3,5 % [SWR].

→ **Plage proposée : 3,0-3,5 %**, et non 4 %. Ramené aux 52 k$/an, cela correspond à un capital de 52 000 / 0,0346 ≈ 1,50 M$
à 52 000 / 0,030 ≈ 1,73 M$ (arithmétique sur ces deux taux). Le capital visé de 1,3 M$ correspond à 4,0 %.

**Ce qui déplace ce taux** (même trace, USD, 50 ans, 603 départs mensuels) :

| levier | SAFEMAX | échec à 4 % |
|---|---|---|
| 60/40 statique | 0,0346 | 0,179 |
| + dépenses flexibles : −10 % pendant 12 mois après une année réelle négative | 0,0359 | 0,121 |
| + flexibilité de −20 % | 0,0375 | 0,060 |
| glidepath **montant** 40 → 70 % d'actions sur k\* = 11 ans (« tente » au départ) | 0,0366 | 0,141 |
| glidepath montant + flexibilité de −20 % | 0,0389 | 0,013 |
| glidepath **descendant** 70 → 40 % | 0,0265 | 0,421 |
| 100 % actions | 0,0268 | 0,129 |
| BNC Équilibré | 0,0339 | 0,199 |

Le glidepath montant a été testé sur la même histoire qui a servi à fixer k\* : c'est un résultat **dans
l'échantillon**, non validé hors échantillon. **Âge de retraite ±2 ans** (capital accumulé avec BNC Croissance, USD,
cotisations H1 ; taux implicite = 52 k$ / capital ; échec historique 60/40 sur l'horizon restant) [SWR
`retirement_age_sensitivity_usd`] :

| retraite à | horizon | capital réel p10 → taux → échec | capital réel médian → taux → échec |
|---|---|---|---|
| 40 ans | 52 ans | 1 024 161 $ → 5,08 % → 0,69 | 1 371 369 $ → 3,79 % → 0,12 |
| **42 ans** | 50 ans | 1 308 565 $ → 3,97 % → 0,16 | 1 831 887 $ → 2,84 % → 0,00 |
| 44 ans | 48 ans | 1 604 246 $ → 3,24 % → 0,00 | 2 349 139 $ → 2,21 % → 0,00 |
| 42 ans, cotisations H2 | 50 ans | 955 886 $ → 5,44 % → 0,73 | 1 390 674 $ → 3,74 % → 0,08 |

Deux ans de plus ou de moins font passer le scénario défavorable (p10) de 0 % à 69 % d'échec. L'ancrage sur « 42 ans »
est le levier le plus fort, devant le choix du portefeuille.

### 6.4 Walk-forward du choix de retrait [WF]

À chaque départ annuel t, on choisit le mélange qui a le meilleur SAFEMAX sur les seules fenêtres **terminées** avant
t, puis on l'évalue sur la fenêtre qui commence en t.
- H = 30 : 39 fenêtres hors échantillon (1958-1996). Choix : 50/50 UST_10Y 25 fois (sinon 20-60 % d'actions).
  PWR hors échantillon : minimum 0,0368, p10 0,0392. Échec à 3,5 % : 0 ; à 4 % : 0,18. Écart moyen avec l'ORACLE :
  0,0109.
- H = 40 : 19 fenêtres (1968-1986). Choix : 60/40 UST_10Y 11 fois, 40/60 6 fois. PWR minimum 0,0366 ; échec à 4 % :
  0,16 ; écart avec l'ORACLE : 0,0090.
- L'ORACLE (hindsight) choisit 100 % actions dans 31 des 39 fenêtres (H = 30) et dans 14 des 19 (H = 40) : **la règle
  ex-ante robuste (50-60 %) et l'optimum a posteriori (100 %) divergent**.

### 6.5 Stress « 2022 en première année de retraite » (tickers réels, CAD, 4 % indexés sur l'IPC CA, 2021-12 → 2026-09) [SWR `stress_2022_start_cad`]

| portefeuille | rendement 2022 | richesse réelle fin 2022 | richesse réelle min. (mois) | richesse réelle 2026-09 |
|---|---|---|---|---|
| 100 % actions (XIU 30 / SPY 70) | −0,107 | 0,829 | 0,793 (2022-09) | 1,381 |
| BNC Croissance | −0,108 | 0,825 | 0,798 (2022-09) | 1,202 |
| **BNC Équilibré** | −0,109 | 0,821 | 0,798 (2023-10) | 1,043 |
| 60 + ZST 10 + XBB 30 | −0,096 | 0,832 | 0,812 (2022-09) | 1,063 |
| BNC Conservateur | −0,112 | 0,814 | 0,766 (2023-10) | 0,838 |
| BNC Prudent | −0,113 | 0,811 | 0,755 (2023-10) | 0,778 |

En 2022, les obligations n'ont pas protégé : Prudent (−0,113) a fait comme 100 % actions (−0,107). Le rebond a ensuite
favorisé les actions. **Ce n'est pas un pire cas** : dans l'historique USD, après 58 mois de retraits de 4 %, le p10 de la
richesse réelle est de 0,751 (60/40) et de 0,630 (100 % actions) [SWR `usd_history_context`]. Un départ en 2022 se
situe au-dessus de ce p10. **Biais de récence** : la fenêtre de 5 ans est courte et favorable aux actions US (avec
+13,45 % d'effet de change USD/CAD selon `quant/resultats.md`).

### 6.6 ORACLE de retrait (hindsight=True, grille de 10 %, mélange constant) [SWR `oracle_withdrawal`]

| ère, H | part d'actions de l'ORACLE p10 / médiane / p90 | autres poids p10-p90 | PWR de l'ORACLE min / médiane |
|---|---|---|---|
| USD, 50 ans (50 départs annuels) | 0,79 / 1,00 / 1,00 | UST_* 0-0,02 | 0,0358 / 0,0603 |
| USD, 30 ans (70) | 0,59 / 1,00 / 1,00 | 0 | 0,0422 / 0,0825 |
| CAD, 30 ans (20) | 0,90 / 1,00 / 1,00 | CA_EQ 0-0,82, GOLD 0 | 0,0837 / 0,1002 |
| CAD, 40 ans (10) | 0,89 / 1,00 / 1,00 | GOLD 0-0,01 | 0,0813 / 0,0949 |

Même avec la connaissance du futur, le pire départ de 50 ans ne permet que 3,58 %. Le meilleur mélange a posteriori
est presque toujours 80-100 % actions, mais on ne peut pas savoir d'avance dans quelle fenêtre on se trouve.

## 7. Stratégie retenue par poche (simulation, pas une recommandation)

| poche | stratégie robuste (proxys) | en tickers de l'univers | justification chiffrée |
|---|---|---|---|
| accumulation | famille 45-60 % actions / 40-55 % obligations ; représentant inter-ères `dividend_tilt` | XIU.TO 40 % · SPY 18 % · FTS.TO 1 % · RY.TO 1 % · XBB.TO 40 % (variante BNC Équilibré : XIU 18 / SPY 42 / XBB 40) | pire rang 3 sur 4 runs ; P(manquer 1,3 M$) de 0 à 0,08 avec H1 [A1-A4] |
| décaissement | **60/40 statique**, jambe obligataire courte ou intermédiaire ; variante glidepath montant 40 → 70 % sur ~11 ans | XIU.TO 18 % · SPY 42 % · XBB.TO 40 % (= BNC Équilibré) ; variante coussin : XBB 30 % + ZST.TO 10 % ; or GLD ≤ 5 % optionnel ; titres ≤ 1 % (CA) / 3 % (US) ; crypto ≤ 1 % | meilleur SAFEMAX de 40 à 55 ans [SWR] ; walk-forward 50-60 % [WF] ; taux associé 3,0-3,5 % |

### 7.1 Vérification sur la période réelle 2021-11 → 2026-09 (59 mois, CAD) [TK]

Variante décaissement (1,3 M$, 4 % indexés) :

| stratégie | réel annualisé | maxDD (mensuel) | 2022 | richesse réelle finale ($) |
|---|---|---|---|---|
| bnc_equilibre (XIU 18 / SPY 42 / XBB 40) | 0,0557 | 0,146 | −0,111 | 1 372 243 |
| eq60_buffer10_bond30 (ZST 10) | 0,0590 | 0,134 | −0,099 | 1 396 826 |
| eq60_agg40 (AGG au lieu de XBB) | 0,0626 | 0,131 | −0,093 | 1 422 804 |
| glide_rising_40_to_70 | 0,0577 | 0,121 | −0,096 | 1 384 249 |
| dividend_tilt | 0,0524 | 0,127 | −0,096 | 1 347 054 |
| eq60_btc1 (1 % BTC-USD) | 0,0566 | 0,149 | −0,116 | 1 378 223 |
| bnc_actions (XIU 30 / SPY 70) | 0,1119 | 0,160 | −0,108 | 1 806 533 |
| eq100_spy | 0,1166 | 0,187 | −0,126 | 1 849 403 |
| trend_eq60 | 0,0267 | 0,137 | −0,134 | 1 178 194 |
| momentum_core_bond | 0,0288 | 0,143 | −0,143 | 1 188 487 |
| ORACLE (hindsight) | 0,1220 | 0,181 | — | 1 897 327 |

Variante accumulation (640 k$ + 9 908 $/mois) : BNC Équilibré termine à 1 578 883 $ réels, dividend_tilt à 1 562 634 $,
BNC Croissance à 1 759 066 $ [TK]. **Ces 59 mois ne prouvent rien sur 50 ans**. Ils montrent seulement que la
traduction en tickers se comporte comme les proxys (ordre de grandeur des maxDD). Ils montrent aussi que les stratégies
dynamiques robustes en CAD (tendance, momentum) ont souffert des faux signaux de 2022.

## 8. Rétro-ingénierie [REV]

Règles testées sur USD 30/40/50/55 ans et CAD 30/40 ans (N de fenêtres indépendantes : 3, 2, 2, 1, 1, 1) :

| règle | verdict |
|---|---|
| SAFEMAX BNC Équilibré > SAFEMAX BNC Conservateur | **robuste** (6/6) |
| 100 % actions : SAFEMAX plus bas que BNC Croissance | **robuste** (6/6) |
| SAFEMAX 60 % ≥ SAFEMAX 100 % actions | robuste en USD, fragile en CAD (faux à 40 ans) |
| meilleur SAFEMAX avec 50-70 % d'actions | robuste en USD, fragile en CAD (80 % à 40 ans) |
| SAFEMAX < 4 % pour le meilleur mélange ; échec à 4 % > 0 | robuste en USD (4/4), faux en CAD (ère favorable, 1 fenêtre) |
| 5 % d'or améliore le pire retrait | **non concluant** (oui à 40 % d'actions, non à 60 % en CAD ; oui en USD 1975+) [DC] |
| glidepath montant > statique | non concluant (USD seulement, dans l'échantillon) [SWR] |
| tente obligataire en accumulation | **rejetée** (rang 11 en CAD, exclue en USD roulant) [A2-A4] |

**Signaux connus au début de la fenêtre** (Spearman avec le PWR du 60/40 ; départs annuels qui se chevauchent : **association
seulement, aucune causalité, p-valeurs naïves**) :

| ère, H (départs) | rendement réel actions des 10 ans précédents | inflation 12 m | rendement du cash 12 m | baisse des actions au départ |
|---|---|---|---|---|
| USD, 50 ans (40) | −0,36 | +0,31 | −0,22 | +0,30 |
| USD, 30 ans (60) | −0,42 | +0,46 | +0,40 | +0,15 |
| CAD, 30 ans (10) | −0,37 | +0,30 | +0,49 | +0,46 |

Le seul signe stable dans les trois cas : **une décennie précédente très bonne pour les actions va de pair avec un taux
de retrait soutenable plus bas** (retour à la moyenne ou valorisation). C'est un candidat pour l'étape 2, pas une
règle. Le signe de l'inflation est contre-intuitif et non interprété. Dans l'accumulation, la part d'actions de
l'ORACLE n'est pas liée à ce signal (ρ = −0,09 en USD, n = 85 ; −0,22 en CAD, n = 34) [REV `accum_oracle`].

## 9. Croisement avec l'analyse réglementaire (B1-B6)

### B1. Statuts → contraintes

La ligne `id=12` ne contient **aucun** statut « exclu » ni « pas maintenant ». Cœur → pas de plafond ; satellite et
limité → plafonds du §4.2. Le statut « pas maintenant » ne s'applique pas. Pour mémoire, son coût d'inflation dans le
cas d'une retraite tout en encaisse : SAFEMAX de 1,25 % sur 50 ans USD (100 % T-bills) [DT] contre 3,46 % pour le 60/40
[SWR] ; 3,74 % contre 7,30 % sur 30 ans CAD [SWR].

### B2. Volonté vs capacité (31-103CP : le minimum)

| poche | volonté (Q10 [inf]) | capacité dérivée | appliquée | effet sur la stratégie robuste |
|---|---|---|---|---|
| accumulation | 0,30 | 0,305 | 0,30 (volonté) | exclut 100 % actions et BNC Croissance en USD (violations de 0,25-0,35) [A1, A2] ; Croissance reste admissible en CAD roulant (0,07) [A4] |
| décaissement | 0,30 | **0,252** | **0,252 (capacité)** | USD 50 ans : trend_eq60 [W1] → **bnc_conservateur** [D2] ; USD 10 ans : bnc_equilibre [W2] → trend_eq60 [D4] ; CAD : aucun changement [D6 = W3] |

**Contradiction trouvée** : en décaissement, une limite de perte max. tirée de la capacité pousse vers le
Conservateur, dont le SAFEMAX sur 50 ans est de 2,68 %, contre 3,39 % pour l'Équilibré [SWR]. Elle **réduit la
soutenabilité de 0,7 pt**. Pour un décaissement de 50 ans, la capacité doit se mesurer par le risque
d'**épuisement** (taux de retrait ≤ plage dérivée de 3,0-3,5 %), pas par la perte max. pondérée par le temps.
Proposition à trancher par l'équipe.

### B3. Concordance poche × classe

Poids robustes : §7. Plage ORACLE : moteur (p10-p90 des fenêtres roulantes) [TAB] et ORACLE de retrait [SWR].
« Titres » : proxys sectoriels dans les ères longues.

| poche | classe | leur statut | poids robuste | ORACLE p10-p90 | verdict | explication |
|---|---|---|---|---|---|---|
| accum. | actions CA | satellite | 1 % (FTS) + 1 % (RY) | titres 0-3 % CAD [A4] ; 3-9 % USD [A2] | cohérent | petite part plafonnée à 1 % par SHOP.TO ; le « dividende » vient surtout de XIU.TO |
| accum. | actions US | satellite | 0 % | idem (secteurs aux plafonds) | cohérent | plafond de 5 % dérivé ; l'ORACLE remplit les plafonds, le choix robuste n'en a pas besoin |
| accum. | FNB actions | cœur | 58 % | 21-99 % CAD ; 0-97 % USD | cohérent | cœur dans toutes les stratégies robustes ; aucune part n'est optimale a posteriori de façon stable |
| accum. | FNB oblig. | cœur (montée avant 42 ans) | 40 % | 0-78 % CAD ; 0-94 % USD | **à trancher** | cœur confirmé, mais la « montée progressive » (tente 85 → 55) n'est pas robuste [A2-A4] |
| accum. | or | satellite | 0 % | 0-5 % (au plafond) | à trancher | l'ORACLE l'utilise, le choix robuste non ; effet sur le pire retrait non concluant |
| accum. | crypto | limité | 0 % (≤ 1 %) | non testable avant 2014 | cohérent | +0,47 pt (BTC) / +0,71 pt (ETH) de perte max. pour 1 % [DC] |
| décais. | actions CA | limité | 0 % titres (XIU 18 %) | titres 6-8 % USD 50 ans [D2] | cohérent | plafond de 1 % ; « vivre des dividendes » ne change pas le rendement total |
| décais. | actions US | limité | 0 % titres | idem | cohérent | plafond de 3 % (NVDA) |
| décais. | FNB actions | cœur | 60 % | **79-100 %** (ORACLE de retrait USD 50 ans) ; 32-47 % (ORACLE moteur pénalisé, maxDD ≤ 0,252) | cohérent / à trancher | cœur confirmé ; le niveau dépend du critère : épuisement → 60 %, perte max. → 30 % (B2) |
| décais. | FNB oblig. | cœur (coussin des premières années) | 40 % (ou 30 % + 10 % ZST) | 0-2 % (ORACLE de retrait) | **à trancher** | jamais optimales a posteriori, mais nécessaires au pire cas (SAFEMAX 0,0346 contre 0,0268 sans elles) ; tente au départ : +0,2 pt dans l'échantillon |
| décais. | or | satellite | 0-5 % | 0-0 % (CAD), une fenêtre à 10 % | à trancher | non concluant (§8) |
| décais. | crypto | limité | 0 % (≤ 1 %) | non testable | cohérent | 1 % de BTC ajoute +0,3 pt de maxDD sur 2021-2026 (0,149 contre 0,146) [TK] |

**Bilan : 7 cohérents, 4 à trancher, 1 mixte (FNB actions en décaissement : cohérent sur le statut, à trancher sur
le niveau), aucune contradiction de statut.** La seule contradiction est de **méthode** (B2 : critère de capacité en
décaissement).

### B4. Profil BNC assigné vs BNC le plus robuste

| poche | assigné par l'analyse | le plus robuste sous les limites du persona | concordance |
|---|---|---|---|
| accumulation | **Croissance** (20/24/56) | Équilibré (CAD non chev. [A3], USD roulant [A2]) ; Pondéré (CAD roulant [A4], USD non chev. [A1]) ; jamais Croissance (exclu en USD pour violations de 0,25-0,28, rang 9-12 en CAD) | **ne concorde pas** : un ou deux crans plus prudent. Avec H1, l'objectif est atteint sans le risque du Croissance |
| décaissement | **Équilibré** (40/18/42) | par l'épuisement : **Équilibré** (meilleur BNC à 30 et 50 ans en USD : 0,0380 / 0,0339 ; à 30 ans en CAD : 0,0730) [SWR] ; par le moteur avec maxDD ≤ 0,252 : Conservateur (USD 50 ans [D2]), Équilibré (CAD 30 ans [D6]) | **concorde** si le critère est l'épuisement ; ne concorde pas avec le critère de perte max. (B2) |

### B5. Réconciliation des chiffres (2021-11 → 2026-09 mensuel vs leur quotidien jusqu'au 2026-11-12) [REC]

Décomposition pas à pas : leur valeur publiée → leur méthode recalculée ici (1 282 jours TSX ∪ US, report du dernier
prix, ×usdcad) → même méthode arrêtée au 2026-09-30 → mensuel à partir du quotidien → moteur.

| ticker | métrique | leur valeur | quotidien recalculé (même fin) | quotidien → 2026-09 | mensuel 2021-11-30 → 2026-09 | **moteur** |
|---|---|---|---|---|---|---|
| XIU.TO | CAGR / vol / maxDD / 2022 | 0,1366 / 0,1292 / 0,1636 / −0,0635 | identique | 0,1305 / 0,1285 / 0,1636 | 0,1425 / 0,1236 / 0,1428 | 0,1425 / 0,1236 / 0,1428 / −0,0635 |
| SPY | idem | 0,1447 / 0,1650 / 0,2225 / −0,1259 | identique | 0,1491 / 0,1644 / 0,2225 | 0,1525 / 0,1346 / 0,1867 | 0,1524 / 0,1346 / 0,1867 / −0,1259 |
| XBB.TO | idem | 0,0071 / 0,0657 / 0,1548 / −0,1166 | identique | 0,0040 / 0,0661 / 0,1548 | 0,0026 / 0,0625 / 0,1301 | 0,0026 / 0,0625 / 0,1301 / −0,1166 |
| GLD | idem | 0,1821 / 0,1822 / 0,2600 / +0,0601 | identique | 0,2030 / 0,1804 / 0,2367 | 0,2140 / 0,1656 / 0,2102 | 0,2139 / 0,1656 / 0,2102 / +0,0601 |
| ZST.TO | idem | 0,0341 / 0,0055 / 0,0043 / +0,0122 | identique | 0,0345 / 0,0055 / 0,0043 | 0,0348 / 0,0062 / 0,0041 | 0,0348 / 0,0062 / 0,0041 / +0,0122 |
| CNQ.TO | idem | 0,2868 / 0,3037 / 0,3311 / **+0,5292** | identique | 0,2826 / 0,3026 / 0,3311 | 0,2847 / 0,2855 / 0,2062 | 0,2789 / 0,2851 / 0,2062 / **+0,4969** |

Explications :
1. **Leur script est reproduit à l'identique.** Il n'y a pas d'erreur de leur côté.
2. **Date de fin** (2026-11-12 vs 2026-09-30) : elle explique l'essentiel de l'écart pour GLD (perte max. de 0,2600
   contre 0,2367 : la baisse d'octobre 2026 est hors fenêtre) et une partie de l'écart des CAGR.
3. **Fréquence** : la perte max. mensuelle est plus faible, car elle ne voit pas les creux en cours de mois (SPY 0,2225
   → 0,1867). La vol mensuelle × √12 diffère de la vol quotidienne × √252 (SPY 0,1644 → 0,1346).
4. **Début** : leur départ est le 2021-11-12, celui du moteur le 2021-11-30 (base du premier rendement du starter).
5. **Change** : la même source BdC, reportée sur les fériés, donne des valeurs identiques en fin de mois.
6. **CNQ.TO** : en août 2022, le moteur retient un rendement de +0,0397 contre +0,0621 dans le starter brut. C'est le
   dividende spécial compté deux fois (rendement du jour 0,027794 → 0,006078, `data_version.json`). Leur 2022 vaut
   +0,5292, le nôtre +0,4969. Leur note (« aucune correction appliquée ») est donc **à corriger** : l'écart
   `adj_close`-`close` de 2,2 pts n'est pas un « split », c'est un double comptage.

### B6. Comparaison avec le bloc YAML du persona (oracle de test, lu en dernier)

| élément YAML | nos conclusions | verdict |
|---|---|---|
| `no_certainty_language` | aucun taux n'est « sûr » ; échecs de 12 à 20 % à 4 % sur 50 ans | cohérent |
| `horizon_disclosure` | 2 fenêtres indépendantes de 50 ans, bootstrap = modèle, CAD non crédible | cohérent |
| `withdrawal_test_required` (≥ 3 taux + 1 stress) | 6 taux (2,5-5 %), stress 2022, pires départs, longévité, âge ±2 | cohérent |
| `crypto_max: 2 %` | 1 % (règle à 1 pt), 2 % (règle à 2 pts) | cohérent (ordre de grandeur ; le nôtre est plus strict) |
| `single_name_max: 5 %` | US : 5 % en accumulation, 3 % en décaissement ; **CA : 1 %** (SHOP.TO) | partiellement cohérent (plus strict pour les titres CA) |
| `all_equity_at_retirement` | 100 % actions : SAFEMAX de 2,68 % contre 3,46 % (pire départ 1929-09) | cohérent |
| `dividend_preference` | rendement total partout ; l'inclinaison est surtout un biais domestique | cohérent |
| `longevity` 95+ | 55 ans testés : SAFEMAX de 3,40 % ; bootstrap à 4 % : échec de 0,18-0,20 | cohérent |
| `missing_info` | REER/CELI/non enregistré, flexibilité (testée en sensibilité), revenus d'appoint, assurances ; **en plus** : profil KYC de Mei-Lin et base des 58 % (brut ou net) | cohérent, avec deux ajouts |

## 10. Signaux candidats pour l'étape 2 (nouvelles, macro, fondamentaux ; non testés ici)

1. **Valorisation au départ** (CAPE, rendement en dividendes, taux de bénéfice) : le seul signal de début de fenêtre
   de signe stable est le rendement réel des actions des 10 années précédentes (ρ de −0,36 à −0,42) [REV].
2. **Taux réels au départ** (obligations à rendement réel du Canada, TIPS) : ils fixent le plancher d'un « coussin »
   indexé. Ce n'est pas dans les données (source à documenter).
3. **Régime d'inflation et chocs d'IPC** : les pires départs (1965-1969, 1937) précèdent des décennies inflationnistes [SWR `sequence_usd_eq60_h50`].
4. **USD/CAD au départ** : 70 % d'actions US pour des dépenses en CAD (effet de +13,45 % sur 2021-2026).
5. **RPC/RRQ et SV** (source gouvernementale à ajouter) : rentes différées qui réduisent le retrait net après 60-65 ans.
6. **Longévité du couple** : tables de mortalité conjointes (source à documenter) plutôt qu'un horizon fixe.

## 11. Limites

- **N** : 2 fenêtres indépendantes de 50 ans en USD, 1 de 30 ans en CAD, 0 de 50 ans en CAD. Les fréquences d'épuisement
  sont des fréquences sur des fenêtres qui se chevauchent, pas des probabilités.
- **Ère et devise** : l'ère USD assimile un Canadien à un Américain (inflation US, pas de change) ; l'ère CAD 1977+ est
  exceptionnellement favorable (désinflation). Biais du survivant des marchés US et des titres choisis en 2026.
- **Obligations synthétiques** : lissées avant 1962 et pour CA_GOV_10Y (vol sous-estimée). Les proxys sectoriels
  KF ≠ titres GICS.
- **Simplifications** : retraits mensuels fixes indexés, mélange rebalancé chaque mois (calcul de retrait), ni frais,
  ni impôts, ni ordre de décaissement REER/CELI/FERR, ni RPC/SV, ni rente viagère. Le budget de 52 k$ est-il brut
  ou net d'impôt ? C'est inconnu.
- **Bootstrap** : il casse le retour à la moyenne, d'où des conclusions sur la part d'actions différentes de
  l'historique. Le glidepath montant et la règle de flexibilité sont testés dans l'échantillon.
- **Cotisations** : la base des 58 % (brut ou net) est inconnue ; H1 est une borne haute.
- **Couple** : un seul profil de risque inféré ; il faut deux KYC. L'agent ne tranche pas le débat du couple : il
  chiffre les deux positions (4 % ≈ 1,3 M$ ; 3,0-3,5 % ≈ 1,50-1,73 M$).

### Bugs et particularités du moteur (non modifiés, contournés)

1. **Flux sans effet sur les métriques** (documenté dans le README, point 9). En décaissement, le moteur classe le 100 %
   actions premier en p10 pondéré par le temps sur 50 ans [D2], alors qu'il est dernier en épuisement. Contourné par
   `analysis/p12/swr.py`. Suggestion : un objectif `max_pwr` / `min_exhaustion` dans le moteur.
2. **ORACLE pénalisé par la perte max.** sur 50 ans : il est limité à 32-47 % d'actions [TAB], donc il n'est pas
   comparable à un ORACLE de retrait. Contourné par l'ORACLE de grille de `swr.py`.
3. `run_profile` charge les données **à partir de** `period.start` : une fenêtre de vérification récente ne voit pas
   l'historique antérieur (stratégies à estimation en repli). Contourné en appelant `run_window` directement avec un
   `Window` (`tickers.py`).
4. Walk-forward vide à 50 ans (il faut au moins 3 fenêtres terminées) : refait à 30 et 40 ans dans `wf_swr.py`.
5. **Documentation** : dans `data/processed/data_version.json`, la clé `qa.cnq_2022_08_month_return_starter` contient la
   valeur **corrigée** d'août 2022 (0,039656), alors que le starter brut donne 0,0621 [REC]. L'étiquette est trompeuse ;
   la correction elle-même est bonne.

## 12. Les quatre questions

- **Quelles données ?** Rendements mensuels du moteur (`data/processed`, `data_sha256 008f122d5da4f8f7`) : marché US
  et industries KF, Trésors US synthétiques, T-bills, or (1975+), actions CA (1977+), obligations CA 10 ans
  synthétiques, T-bills CA, IPC US et Canada, USDCAD ; tickers réels depuis le starter (`adj_close`) après 2021-12.
  Sources et traitements : `data/SOURCES.md`.
- **Pourquoi ce choix ?** Le risque de Julien et Mei-Lin, c'est l'épuisement, pas la volatilité. On mesure donc le
  taux de retrait sur toutes les fenêtres de 30 à 55 ans disponibles, plus un bootstrap. La décennie 42-52 ans explique
  l'essentiel du résultat (k\* ≈ 11 ans). Un 60/40 a le meilleur pire cas en USD de 40 à 55 ans, et le 100 % actions
  le pire. En accumulation, l'épargne atteint l'objectif : la prise de risque n'est pas nécessaire.
- **Quelles limites ?** 2 fenêtres indépendantes de 50 ans ; ère CAD trop favorable ; proxys US ; ni impôts, ni frais,
  ni rentes publiques ; bootstrap = modèle ; seuils et plafonds à valider ; 5 ans de tickers = illustration.
- **Qu'est-ce qui changerait la réponse ?** Retarder la retraite de 2 ans (échec p10 : 0,16 → 0 ; l'avancer de 2 ans : 0,69) ;
  accepter de baisser les dépenses de 10-20 % après une mauvaise année (échec à 4 % : 0,179 → 0,060) ; un revenu
  d'appoint ou les rentes RPC/SV (non modélisés) ; des cotisations plus faibles (H2 : échec de 0,34-0,50 dans
  l'accumulation) ; une valorisation de départ élevée (signal candidat) ; des données canadiennes plus longues.

## 13. Reproduire

```bash
cd research/backtest
.venv/bin/python -I analysis/p12/derive_thresholds.py   # [DT]
.venv/bin/python -I analysis/p12/derive_caps.py         # [DC]
.venv/bin/python -I analysis/p12/make_profiles.py       # profiles/p12_*.yaml
bash analysis/p12/run_jobs.sh                           # 18 runs moteur -> results/p12_*/
.venv/bin/python -I analysis/p12/tables.py              # [TAB]
.venv/bin/python -I analysis/p12/swr.py                 # [SWR]
.venv/bin/python -I analysis/p12/wf_swr.py              # [WF]
.venv/bin/python -I analysis/p12/reverse.py             # [REV]
.venv/bin/python -I analysis/p12/tickers.py             # [TK]
.venv/bin/python -I analysis/p12/reconcile.py           # [REC] (lit le starter et analyse/…/quant en lecture seule)
```
