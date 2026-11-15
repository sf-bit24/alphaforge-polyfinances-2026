# Robert : backtest 1926-2026, oracle, stratégie ex-ante robuste et rétro-ingénierie

> **Simulation historique uniquement, à partir de données publiques.** Ce document ne constitue pas un conseil financier
> personnalisé et n'entraîne aucune transaction. Les lignes `ORACLE` (`hindsight=True`) utilisent le futur : elles sont
> **non investissables** et ne servent qu'à la rétro-ingénierie. Les seuils ci-dessous sont des **propositions à valider
> par l'équipe**. Ils sont dérivés des données, jamais repris de la fiche du persona.

Tous les chemins sont relatifs à `research/backtest/`. Chaque chiffre renvoie à la trace JSON qui l'a produit. Les
traces contiennent `engine_sha256`, `data_version.data_sha256` (`008f122d5da4f8f7`), la graine (42) et le profil complet.
Notation : « réel » = rendement annualisé corrigé de l'inflation, sur la fenêtre ; « p10 » = 10e centile entre fenêtres.

## 1. Question

Robert a 59 ans, travaille dans la santé et prendra bientôt sa retraite. Son horizon est de 3 à 5 ans (4 ans au centre),
sa tolérance est faible à modérée et sa capacité, plus faible, prime. Il veut préserver son capital avec une croissance
modérée, préfère les entreprises établies et exclut la crypto. Le persona teste un point précis : le système doit
remettre en question une demande pour un titre très médiatisé au lieu d'acquiescer. De la fiche
`source/profil-investisseur-robert.md`, on ne retient que l'identité, les contraintes RRTTLLU, les objectifs, les biais
et ce que le persona teste. **Aucune allocation, aucun seuil et aucun « fait de marché » de la fiche n'a été utilisé.**

Questions traitées :

1. Sur chaque fenêtre de 4 ans (et de 3 ou 5 ans en sensibilité), quel mélange constant aurait été optimal **a posteriori**
   (ORACLE) ?
2. Quelle stratégie **ex-ante** reste la meilleure dans les mauvais cas ?
3. Quelles règles stables en ressortent, et quelles variables connues **au début** de chaque fenêtre y sont associées ?

**Objectif retenu** : `min_shortfall` avec `target_real_return: 0`. Le score d'une fenêtre est son rendement réel
annualisé. La sélection robuste prend la stratégie qui a le **meilleur 10e centile** de ce score, et `shortfall_prob`
donne la **probabilité de perte réelle** sur la fenêtre. Pourquoi ce choix :

- « préserver le capital », pour un futur retraité, veut dire préserver son **pouvoir d'achat**, d'où la cible réelle de 0 ;
- la croissance modérée est mesurée par le niveau du score ;
- le 10e centile vise les mauvais scénarios sans dépendre d'une seule fenêtre extrême, comme le ferait le pire cas.

Les deux objectifs suggérés (probabilité de perte réelle et 10e centile réel) sont donc rapportés ensemble.

## 2. Données et ères

| ère | profil | devise et inflation | univers (asset_id) | période effective |
|---|---|---|---|---|
| 1, longue (USD) | `profiles/robert_long_usd.yaml` (+ `_h3`, `_h5`) | USD, CPI-U US | US_MKT, US_IND_NODUR, US_IND_UTILS, US_IND_HLTH, CORP_AAA, UST_20Y, UST_10Y, UST_5Y, UST_2Y, UST_TBILL | 1926-08 → 2026-09 |
| 1b, USD avec or | `profiles/robert_usd_gold.yaml` | USD | ère 1 + GOLD | 1975-01 → 2026-09 |
| 2, canadienne (CAD) | `profiles/robert_cad.yaml` (+ `_eralimits`) | CAD, IPC Canada ; actifs US non couverts | CA_EQ, US_MKT, US_IND_NODUR, US_IND_UTILS, US_IND_HLTH, CA_GOV_10Y, UST_5Y, UST_2Y, GOLD, CA_TBILL | 1977-01 → 2026-09 (actif limitant CA_EQ) |
| tickers réels | `profiles/robert_tickers.yaml` | CAD | XIU.TO, SPY, GLD, XBB.TO, ZST.TO, AGG, TLT, PG, FTS.TO, JNJ, RY.TO, CA_TBILL | 2021-11 → 2026-09 |

**Hypothèse déclarée (ère 1)** : avant 1971, on assimile le retraité canadien à un investisseur en USD sur des proxys
américains. Il n'existe pas d'USDCAD gratuit avant 1971-02, et les actions canadiennes ne commencent qu'en 1977-01.
L'or est exclu de l'ère 1, car il n'était pas investissable avant 1975. Les secteurs « défensifs » (biens de consommation
courante, services publics, santé) servent de proxy à « entreprises établies ». Les autres secteurs sont hors univers,
puisque le titre technologique médiatisé est traité à part (§7). Sources et traitements : `data/SOURCES.md`.

## 3. Fenêtres et exécutions

| exécution | fenêtres | trace |
|---|---|---|
| USD, 4 ans, non chevauchant | 25 | `results/robert_long_usd/20261114T234617Z_non_overlapping_h4.json` |
| USD, 4 ans, roulant (pas de 12 mois) | 97 | `results/robert_long_usd/20261114T234412Z_rolling_h4.json` |
| USD, 3 ans (limites H=3), non chevauchant / roulant | 33 / 98 | `results/robert_long_usd_h3/20261114T233844Z_non_overlapping_h3.json`, `…/20261114T234405Z_rolling_h3.json` |
| USD, 5 ans (limites H=5), non chevauchant / roulant | 20 / 96 | `results/robert_long_usd_h5/20261114T233740Z_non_overlapping_h5.json`, `…/20261114T234355Z_rolling_h5.json` |
| USD 1975+ avec or, 4 ans | 12 / 48 | `results/robert_usd_gold/20261114T233730Z_non_overlapping_h4.json`, `…/20261114T234108Z_rolling_h4.json` |
| CAD, 4 ans | 12 / 46 | `results/robert_cad/20261114T233723Z_non_overlapping_h4.json`, `…/20261114T234006Z_rolling_h4.json` |
| CAD, roulant 3 et 5 ans (limites H=4) | 47 / 45 | `results/robert_cad/20261114T234007Z_rolling_h3.json`, `…/20261114T234023Z_rolling_h5.json` |
| CAD, limites propres à l'ère (sensibilité) | 12 / 46 | `results/robert_cad_eralimits/20261114T233709Z_non_overlapping_h4.json`, `…/20261114T233758Z_rolling_h4.json` |
| ORACLE grossier (actions × duration) | USD 25 / 97, CAD 12 / 46 | `results/robert_coarse_usd/…222847Z_non_overlapping_h4.json`, `…223045Z_rolling_h4.json`, `results/robert_coarse_cad/…223057Z_non_overlapping_h4.json`, `…223139Z_rolling_h4.json` |

Chaque profil teste un large ensemble de stratégies ex-ante (statiques et dynamiques) : cash ; échelle T-bill et 2 ans ;
obligations 5 ans et 20 ans ; 10 ou 20 % d'actions avec une jambe obligataire de 2, 5, 10 ou 20 ans ; barbell 30 % ;
30 % d'actions défensives ; 40/60 ; 60/40 ; glidepath 40 → 10 ; parité de risque 36 mois ; variance minimale 60 mois ;
moyenne-variance 60 mois ; deux filtres de tendance (10 mois) ; momentum (12 mois) avec un noyau court.
Toutes sont rebalancées chaque année (sauf tendance et momentum, mensuels), avec 10 pb de coûts.

## 4. Seuils dérivés (propositions à valider)

**Règle de dérivation** (`analysis/robert/derive_thresholds.py`, trace `results/robert_analysis/derive_thresholds.json`).
Robert ne peut pas attendre plus que son horizon H pour retrouver son sommet précédent. On construit une grille de
mélanges statiques « e % actions + (1 − e) % jambe obligataire », avec e de 0 à 100 % et toutes les jambes possibles.
Un mélange est **admissible** si sa plus longue période sous l'eau (nominale, du sommet au recouvrement) sur l'ère
reste ≤ 12·H mois. **L\*(H)** est la baisse maximale du mélange admissible le plus profond. Le seuil de CVaR mensuelle
5 % **CVaR\*(H)** est celui du même mélange.

| H | ère USD 1926+ (mélange frontière) | ère USD 1962+ | ère CAD 1977+ |
|---|---|---|---|
| 3 ans | L\* 0,196, CVaR\* 0,0300 (20 % US_MKT / 80 % UST_5Y) | 0,207 / 0,0449 | 0,154 / 0,0448 |
| 4 ans | **L\* 0,227, CVaR\* 0,0359** (20 % US_MKT / 80 % UST_10Y, 48 mois sous l'eau) | 0,342 / 0,0620 | 0,303 / 0,0684 |
| 5 ans | L\* 0,312, CVaR\* 0,0368 (30 % US_MKT / 70 % UST_5Y) | 0,405 / 0,0778 | 0,430 / 0,0962 |

**Proposition** : la capacité de perte appartient à Robert, pas à l'ère, et l'on retient la valeur la plus prudente,
celle de l'ère 1926+. Les limites deviennent **maxDD\* = 0,23 et CVaR\*5 = 0,036 à 4 ans**, puis 0,20 / 0,030 à 3 ans
et 0,31 / 0,037 à 5 ans. `max_vol` reste vide : la volatilité est symétrique, alors que la capacité de Robert porte
sur les pertes.

Sur l'ère 1926+, les parts d'actions maximales admissibles à 4 ans sont de 20 % (jambes de 2, 5 ou 10 ans), et de 0 %
pour la jambe T-bill, dont la plus longue période sous l'eau dépasse 48 mois dès 10 % d'actions. Les 55 combinaisons
« jambe × part d'actions » de la grille donnent toutes une probabilité de perte réelle sur 4 ans d'au moins 0,188
(minimum atteint par 40 % US_MKT / 60 % UST_5Y), et le cash pur en donne 0,458 (même trace, `eras.usd_1926.grid`).

**Robustesse de la règle** : la règle n'est pas monotone, car un mélange plus risqué peut récupérer plus vite qu'une
obligation longue seule, et elle dépend fortement de l'ère : L\* vaut 0,227 en USD 1926+ et 0,303 en CAD 1977+.
**Point de circularité** : la part d'actions de 20 % qui ressort plus loin est en partie la conséquence de ces limites.
La sensibilité `robert_cad_eralimits`, avec les limites CAD (0,30 et 0,068), le montre au §5.

## 5. Choix robuste, walk-forward et écart avec l'oracle

### 5.1 Résultats par fenêtre (4 ans, non chevauchant)

**Ère 1, USD** (trace `results/robert_long_usd/20261114T234617Z_non_overlapping_h4.json`, choix robuste `eq20_2y`
= 20 % US_MKT / 80 % UST_2Y) :

| fenêtre | ORACLE, poids (> 3 %) | ORACLE réel | ORACLE maxDD | meilleure ex-ante (a posteriori) | son réel | eq20_2y réel | eq20_2y maxDD | recouvrement (mois) | CVaR5 | perte réelle ? |
|---|---|---|---|---|---|---|---|---|---|---|
| 1926-08..1930-07 | CORP_AAA 0.81, US_IND_UTILS 0.19 | 0.119 | 0.076 | momentum_core2y | 0.123 | 0.077 | 0.058 | 5 | 0.035 | non |
| 1930-08..1934-07 | CORP_AAA 0.93, UST_20Y 0.07 | 0.126 | 0.092 | bonds_20y | 0.105 | 0.061 | 0.159 | 13 | 0.043 | non |
| 1934-08..1938-07 | CORP_AAA 0.79, US_MKT 0.21 | 0.068 | 0.111 | sixty_forty | 0.091 | 0.025 | 0.094 | non récupéré | 0.027 | non |
| 1938-08..1942-07 | CORP_AAA 1.00 | 0.005 | 0.048 | mean_variance_60m | -0.010 | -0.039 | 0.054 | non récupéré | 0.026 | oui |
| 1942-08..1946-07 | US_IND_UTILS 0.53, CORP_AAA 0.29, US_IND_NODUR 0.12, US_IND_HLTH 0.06 | 0.214 | 0.052 | sixty_forty | 0.130 | 0.015 | 0.018 | 3 | 0.013 | non |
| 1946-08..1950-07 | UST_10Y 0.57, US_MKT 0.43 | -0.017 | 0.079 | sixty_forty | -0.012 | -0.032 | 0.034 | 12 | 0.017 | oui |
| 1950-08..1954-07 | US_IND_UTILS 1.00 | 0.176 | 0.058 | sixty_forty | 0.104 | 0.029 | 0.014 | 4 | 0.009 | non |
| 1954-08..1958-07 | US_IND_HLTH 0.82, UST_2Y 0.13, UST_TBILL 0.05 | 0.222 | 0.060 | mean_variance_60m | 0.118 | 0.031 | 0.022 | 3 | 0.009 | non |
| 1958-08..1962-07 | US_IND_UTILS 0.32, UST_2Y 0.31, US_IND_NODUR 0.19, UST_TBILL 0.18 | 0.079 | 0.123 | mean_variance_60m | 0.110 | 0.034 | 0.040 | non récupéré | 0.014 | non |
| 1962-08..1966-07 | US_IND_HLTH 0.49, UST_TBILL 0.26, US_MKT 0.25 | 0.107 | 0.063 | sixty_forty | 0.069 | 0.034 | 0.011 | non récupéré | 0.008 | non |
| 1966-08..1970-07 | UST_TBILL 0.55, US_IND_HLTH 0.45 | 0.024 | 0.092 | glide_40_to_10 | 0.013 | 0.001 | 0.032 | non récupéré | 0.022 | non |
| 1970-08..1974-07 | CORP_AAA 0.71, US_IND_HLTH 0.29 | 0.011 | 0.131 | glide_40_to_10 | 0.018 | -0.008 | 0.032 | non récupéré | 0.015 | oui |
| 1974-08..1978-07 | US_IND_UTILS 0.59, UST_5Y 0.41 | 0.074 | 0.051 | momentum_core2y | 0.036 | 0.012 | 0.024 | 1 | 0.016 | non |
| 1978-08..1982-07 | UST_TBILL 0.55, US_IND_NODUR 0.45 | 0.016 | 0.048 | cash_100 | 0.013 | -0.000 | 0.046 | 1 | 0.031 | oui |
| 1982-08..1986-07 | US_IND_NODUR 0.71, US_IND_UTILS 0.29 | 0.322 | 0.070 | eq20_20y | 0.236 | 0.134 | 0.017 | 2 | 0.012 | non |
| 1986-08..1990-07 | UST_2Y 0.43, CORP_AAA 0.29, US_IND_NODUR 0.19, US_IND_HLTH 0.09 | 0.065 | 0.077 | sixty_forty | 0.057 | 0.040 | 0.042 | 3 | 0.020 | non |
| 1990-08..1994-07 | CORP_AAA 1.00 | 0.082 | 0.099 | eq20_20y | 0.069 | 0.039 | 0.028 | non récupéré | 0.013 | non |
| 1994-08..1998-07 | US_IND_HLTH 0.57, UST_TBILL 0.43 | 0.199 | 0.041 | sixty_forty | 0.167 | 0.078 | 0.012 | 2 | 0.011 | non |
| 1998-08..2002-07 | UST_5Y 0.91, CORP_AAA 0.09 | 0.050 | 0.041 | bonds_5y | 0.050 | 0.023 | 0.019 | 1 | 0.015 | non |
| 2002-08..2006-07 | US_MKT 0.42, CORP_AAA 0.34, US_IND_UTILS 0.13, US_IND_HLTH 0.08 | 0.078 | 0.055 | sixty_forty | 0.052 | 0.006 | 0.016 | 4 | 0.011 | non |
| 2006-08..2010-07 | CORP_AAA 0.42, UST_5Y 0.38, UST_10Y 0.12, UST_20Y 0.07 | 0.064 | 0.059 | bonds_20y | 0.073 | 0.020 | 0.062 | 7 | 0.018 | non |
| 2010-08..2014-07 | US_IND_HLTH 0.98 | 0.202 | 0.115 | sixty_forty | 0.096 | 0.016 | 0.032 | 5 | 0.012 | non |
| 2014-08..2018-07 | US_MKT 0.68, US_IND_UTILS 0.18, UST_20Y 0.14 | 0.088 | 0.070 | sixty_forty | 0.067 | 0.012 | 0.016 | 8 | 0.009 | non |
| 2018-08..2022-07 | UST_10Y 0.52, US_IND_UTILS 0.31, US_IND_HLTH 0.12, US_IND_NODUR 0.05 | 0.022 | 0.074 | sixty_forty | 0.037 | -0.008 | 0.071 | non récupéré | 0.021 | oui |
| 2022-08..2026-07 | US_MKT 0.49, UST_TBILL 0.42, US_IND_HLTH 0.09 | 0.084 | 0.066 | sixty_forty | 0.071 | 0.032 | 0.040 | 6 | 0.018 | non |

Sur 1970-08..1974-07, le glidepath (0,018) dépasse l'ORACLE (0,011). Ce n'est pas une erreur : l'ORACLE est le meilleur
mélange **constant**, alors qu'une stratégie dynamique peut le battre (README, point 7).

« Meilleure ex-ante (a posteriori) » désigne la stratégie qui a eu le meilleur score sur la fenêtre, toutes limites de
risque confondues : on ne pouvait pas la connaître d'avance. CORP_AAA y apparaît souvent, mais c'est une obligation
synthétique qui **ignore les défauts** (§10).

**Ère 2, CAD** (trace `results/robert_cad/20261114T233723Z_non_overlapping_h4.json`, choix robuste `eq20_gold10`
= 10 % CA_EQ / 10 % US_MKT / 10 % GOLD / 50 % CA_GOV_10Y / 20 % CA_TBILL) :

| fenêtre | ORACLE, poids (> 3 %) | ORACLE réel | ORACLE maxDD | meilleure ex-ante (a posteriori) | son réel | eq20_gold10 réel | eq20_gold10 maxDD | recouvrement (mois) | CVaR5 | perte réelle ? |
|---|---|---|---|---|---|---|---|---|---|---|
| 1977-01..1980-12 | GOLD 0.39, US_IND_HLTH 0.35, UST_2Y 0.15, CA_TBILL 0.09 | 0.183 | 0.077 | momentum_core_cash | 0.114 | 0.037 | 0.065 | 2 | 0.030 | non |
| 1981-01..1984-12 | US_IND_NODUR 0.73, CA_TBILL 0.27 | 0.145 | 0.057 | bonds_ca10y | 0.082 | 0.045 | 0.066 | 2 | 0.028 | non |
| 1985-01..1988-12 | CA_GOV_10Y 0.71, US_IND_NODUR 0.29 | 0.120 | 0.079 | eq30_defensive | 0.089 | 0.070 | 0.062 | 8 | 0.023 | non |
| 1989-01..1992-12 | US_IND_HLTH 0.67, CA_GOV_10Y 0.11, UST_2Y 0.10, UST_5Y 0.08, CA_TBILL 0.04 | 0.170 | 0.089 | momentum_core_cash | 0.114 | 0.066 | 0.059 | 7 | 0.021 | non |
| 1993-01..1996-12 | US_MKT 0.59, US_IND_HLTH 0.21, CA_EQ 0.13, US_IND_NODUR 0.07 | 0.168 | 0.055 | sixty_forty | 0.136 | 0.092 | 0.073 | 9 | 0.021 | non |
| 1997-01..2000-12 | US_IND_UTILS 0.46, US_IND_HLTH 0.22, CA_EQ 0.20, UST_5Y 0.05, UST_2Y 0.05 | 0.185 | 0.059 | sixty_forty | 0.123 | 0.062 | 0.037 | 2 | 0.021 | non |
| 2001-01..2004-12 | CA_GOV_10Y 0.83, GOLD 0.17 | 0.051 | 0.036 | bonds_ca10y | 0.051 | 0.028 | 0.017 | 3 | 0.010 | non |
| 2005-01..2008-12 | GOLD 0.50, CA_GOV_10Y 0.32, US_IND_UTILS 0.13, CA_EQ 0.05 | 0.100 | 0.065 | momentum_core_cash | 0.075 | 0.042 | 0.037 | non récupéré | 0.015 | non |
| 2009-01..2012-12 | GOLD 0.59, CA_EQ 0.41 | 0.122 | 0.072 | sixty_forty | 0.073 | 0.049 | 0.007 | 1 | 0.006 | non |
| 2013-01..2016-12 | US_IND_NODUR 0.88, US_IND_HLTH 0.12 | 0.216 | 0.054 | risk_parity_36m | 0.114 | 0.028 | 0.029 | 4 | 0.015 | non |
| 2017-01..2020-12 | US_MKT 0.55, GOLD 0.27, US_IND_HLTH 0.18 | 0.127 | 0.066 | mean_variance_60m | 0.080 | 0.038 | 0.034 | 11 | 0.016 | non |
| 2021-01..2024-12 | US_MKT 0.52, GOLD 0.34, US_IND_UTILS 0.14 | 0.104 | 0.093 | mean_variance_60m | 0.059 | -0.007 | 0.097 | 20 | 0.027 | oui |

Les fenêtres roulantes (pas de 12 mois) figurent dans les fichiers `_windows.csv` à côté de chaque trace.

### 5.2 Sélection robuste (meilleur p10 ; une stratégie est exclue si elle viole les limites dans plus de 10 % des fenêtres)

| exécution (trace) | choix robuste | p10 réel | médiane réel | pire réel | pire maxDD | taux de violation | P(perte réelle) |
|---|---|---|---|---|---|---|---|
| USD 4 ans, non chevauchant (`robert_long_usd/…234617Z_non_overlapping_h4.json`) | eq20_2y | -0.008 | 0.023 | -0.039 | 0.159 | 0.04 | 0.20 |
| USD 4 ans, roulant (`robert_long_usd/…234412Z_rolling_h4.json`) | eq20_2y | -0.016 | 0.021 | -0.050 | 0.159 | 0.05 | 0.22 |
| USD 3 ans (limites H=3), roulant (`robert_long_usd_h3/…234405Z_rolling_h3.json`) | cash_100 | -0.027 | 0.004 | -0.090 | 0.001 | 0.00 | 0.45 |
| USD 5 ans (limites H=5), roulant (`robert_long_usd_h5/…234355Z_rolling_h5.json`) | eq20_2y | -0.015 | 0.020 | -0.037 | 0.159 | 0.06 | 0.24 |
| USD 1975+ avec or, roulant (`robert_usd_gold/…234108Z_rolling_h4.json`) | eq20_gold10 | 0.002 | 0.035 | -0.019 | 0.120 | 0.08 | 0.10 |
| USD 1975+ avec or, non chevauchant (`robert_usd_gold/…233730Z_non_overlapping_h4.json`) | eq30_defensive (eq20_5y 0.005, eq20_gold10 0.005, eq20_2y 0.003 juste derrière) | 0.007 | 0.035 | -0.005 | 0.097 | 0.08 | 0.08 |
| CAD 4 ans, non chevauchant (`robert_cad/…233723Z_non_overlapping_h4.json`) | eq20_gold10 | 0.028 | 0.043 | -0.007 | 0.097 | 0.00 | 0.08 |
| CAD 4 ans, roulant (`robert_cad/…234006Z_rolling_h4.json`) | eq20_gold10 | 0.015 | 0.042 | -0.010 | 0.097 | 0.04 | 0.07 |
| CAD 3 ans, roulant (`robert_cad/…234007Z_rolling_h3.json`) | eq20_gold10 | 0.013 | 0.043 | -0.042 | 0.097 | 0.06 | 0.04 |
| CAD 5 ans, roulant (`robert_cad/…234023Z_rolling_h5.json`) | eq20_gold10 | 0.016 | 0.042 | -0.002 | 0.097 | 0.07 | 0.02 |
| CAD avec limites de l'ère, roulant (`robert_cad_eralimits/…233758Z_rolling_h4.json`) | momentum_core_cash | 0.019 | 0.074 | -0.000 | 0.109 | 0.00 | 0.02 |

Repères dans les mêmes traces :

- **60/40 sur l'ère USD** : pire maxDD de 0,493 en non chevauchant et de 0,587 en roulant, avec 0,68 et 0,74 de taux
  de violation ;
- **cash** : P(perte réelle) de 0,44 et 0,47 sur l'ère USD, de 0,33 et 0,30 sur l'ère CAD. Le cash n'est donc pas
  « sans risque » en termes réels.

### 5.3 Walk-forward et coût de ne pas connaître le futur

Trace : `results/robert_analysis/gaps.json`. Le walk-forward choisit chaque fois avec les seules fenêtres terminées
avant la fenêtre évaluée.

| exécution | fenêtres hors échantillon | score moyen hors échantillon | p10 hors échantillon | P(perte réelle) hors échantillon | écart moyen ORACLE − choix walk-forward | écart moyen ORACLE − choix robuste (moyenne / médiane) | choix du walk-forward |
|---|---|---|---|---|---|---|---|
| USD 4 ans, non chevauchant | 22 | 0.0073 | -0.0319 | 0.455 | 0.0911 | 0.0739 / 0.0450 | eq20_2y 10, bonds_20y 8, risk_parity 3, min_var 1 |
| USD 4 ans, roulant | 91 | 0.0155 | -0.0304 | 0.308 | 0.0801 | 0.0729 / 0.0574 | eq20_2y 34, risk_parity 27, trend_30_def 19, bonds_20y 7 … |
| CAD 4 ans, non chevauchant | 9 | 0.0443 | 0.0213 | 0.111 | 0.0937 | 0.0949 / 0.0946 | eq20_gold10 9 |
| CAD 4 ans, roulant | 40 | 0.0319 | -0.0004 | 0.125 | 0.1079 | 0.0958 / 0.0870 | eq20_gold10 13, eq20_ust2y 11, cash 8 … |
| USD 1975+ avec or, roulant | 42 | 0.0296 | 0.0030 | 0.095 | 0.0955 | 0.0857 / 0.0772 | eq20_2y 21, risk_parity 8, eq20_gold10 5 … |

**Lecture** : ne pas connaître le futur coûte de **7 à 11 points de rendement réel par an** en moyenne face à l'ORACLE.
Ce coût est irréductible, et l'oracle n'est pas une cible. En USD, le walk-forward a d'abord choisi `bonds_20y`, qui
avait bien réussi entre 1926 et 1938, puis il s'est stabilisé sur `eq20_2y` : avec peu de fenêtres passées, la
sélection est instable.

### 5.4 Stratégie retenue (simulation)

Les ères convergent vers une structure commune : **environ 20 % d'actions larges, des obligations courtes ou
intermédiaires et une poche de liquidités**, avec, depuis 1975, environ 10 % d'or. Retenu pour la traduction :
`eq20_gold10`, choix robuste en CAD dans les quatre exécutions de `robert_cad` (§5.2). Sur l'ère USD 1926+, sans or,
c'est `eq20_2y` qui ressort.

## Correctif moteur 2026-11-14 : glidepath, avant / après

**Correctif** : dans `engine/backtest.py` (`_progress`), la progression du glidepath est maintenant mesurée par rapport
au dernier mois de décision prévu de la fenêtre, et non plus par rapport à n. Avant, un glidepath rebalancé chaque
année n'atteignait jamais ses poids finaux : sur 4 ans, il s'arrêtait à 0,75.

Les 14 exécutions qui contiennent `glide_40_to_10` ont été relancées. Le hash du moteur passe de `5aa2575a94cacf75` à
`4d3e707a3271717d`. La comparaison complète est dans `results/robert_analysis/glidepath_fix.json`, produite par
`analysis/robert/glidepath_fix_diff.py`.

- **Rien ne change sur le choix robuste** : il est identique dans les 14 exécutions (eq20_2y, cash_100 à 3 ans en USD,
  eq30_defensive ou eq20_gold10 en USD 1975+, eq20_gold10 en CAD, momentum_core_cash en CAD avec les limites de l'ère).
  Le trio de tête, le walk-forward et l'écart avec l'oracle sont aussi identiques
  (`results/robert_analysis/gaps.json`). Toutes les stratégies autres que le glidepath donnent exactement les mêmes
  résultats (écart maximal de 0,0).
- **Les seuils ne changent pas** : `derive_thresholds`, `sensitivity`, `hype_pocket`, `oracle_coarse` et `robert_tickers`
  ne contiennent pas de glidepath.
- **Chiffres du glidepath qui ont bougé** (`glide_40_to_10`, avant → après) :

| exécution (trace après) | p10 réel | médiane réel | pire maxDD | taux de violation | rang / éligible |
|---|---|---|---|---|---|
| USD 4 ans, non chevauchant (`robert_long_usd/20261114T234617Z_non_overlapping_h4.json`) | -0.0000 → 0.0042 | 0.0342 → 0.0300 | 0.289 → 0.275 | 0.20 → 0.20 | 9 → 9 / non |
| USD 4 ans, roulant (`robert_long_usd/20261114T234412Z_rolling_h4.json`) | -0.0180 → -0.0193 | 0.0338 → 0.0275 | 0.289 → 0.275 | 0.22 → 0.19 | 15 → 15 / non |
| USD 3 ans, roulant (`robert_long_usd_h3/20261114T234405Z_rolling_h3.json`) | -0.0213 → -0.0186 | 0.0325 → 0.0274 | 0.275 → 0.248 | 0.35 → 0.30 | 6 → 5 / non |
| USD 5 ans, roulant (`robert_long_usd_h5/20261114T234355Z_rolling_h5.json`) | -0.0130 → -0.0163 | 0.0297 → 0.0262 | 0.298 → 0.289 | 0.22 → 0.20 | 12 → 15 / non |
| USD 1975+ avec or, roulant (`robert_usd_gold/20261114T234108Z_rolling_h4.json`) | 0.0011 → -0.0036 | 0.0349 → 0.0308 | 0.162 → 0.162 | 0.19 → 0.12 | 11 → 13 / non |
| **CAD 4 ans, non chevauchant** (`robert_cad/20261114T233723Z_non_overlapping_h4.json`) | 0.0072 → 0.0034 | 0.0489 → 0.0444 | 0.128 → 0.122 | **0.17 → 0.08** | **15 → 5 / non → oui** |
| CAD 4 ans, roulant (`robert_cad/20261114T234006Z_rolling_h4.json`) | 0.0096 → 0.0079 | 0.0444 → 0.0409 | 0.147 → 0.147 | 0.20 → 0.17 | 13 → 13 / non |

  Les autres exécutions (USD 3 et 5 ans non chevauchant, USD 1975+ non chevauchant, CAD 3 et 5 ans roulant, CAD avec les
  limites de l'ère) sont dans `glidepath_fix.json`, sans changement de choix robuste.
- **Lecture** : le glidepath finit maintenant plus prudent, ce qui baisse sa médiane et ses violations. En CAD non
  chevauchant, il devient éligible (rang 5) mais reste derrière `eq20_gold10` (p10 0,0034 contre 0,028).
- **Tableau par fenêtre** (§5.1) : la meilleure ex-ante a posteriori devient `glide_40_to_10` sur 1966-08..1970-07
  (0,013, avant `momentum_core2y` à 0,010) ; sur 1970-08..1974-07, elle passe de 0,011 à 0,018.
- **Rétro-ingénierie** : relancée (`results/robert_analysis/reverse_engineer.json`). Les corrélations portent sur
  l'ORACLE grossier et sur l'écart de duration, qui ne dépendent pas du glidepath : les étiquettes R1 à R7 ne changent
  pas. Seuls les comptes de « meilleure famille ex-post » changent, pour 2 fenêtres USD.

## 6. Sensibilités contrôlées (duration, or, part d'actions)

Trace : `results/robert_analysis/sensitivity.json`. Exécutions moteur dans `results/robert_sens_*/`, roulant 4 ans.

**Duration, USD 1926+, 20 % US_MKT et 80 % de la jambe indiquée** (`robert_sens_usd_duration/20261114T223149Z_rolling_h4.json`) :

| jambe | p10 réel | pire réel | pire maxDD | taux de violation | P(perte réelle) |
|---|---|---|---|---|---|
| UST_TBILL | -0.0181 | -0.0513 | 0.2032 | 0.062 | 0.247 |
| UST_2Y | **-0.0164** | -0.0505 | 0.1586 | 0.052 | 0.216 |
| UST_5Y | -0.0242 | -0.0510 | 0.1529 | 0.103 | 0.237 |
| UST_10Y | -0.0297 | -0.0742 | 0.1891 | 0.299 | 0.216 |
| CORP_AAA | -0.0330 | -0.0864 | 0.2584 | 0.309 | 0.237 |
| UST_20Y | -0.0365 | -0.0934 | 0.3044 | 0.526 | 0.258 |

On retrouve le même ordre en non chevauchant (`…223151Z_non_overlapping_h4.json` : p10 2Y -0.0077, TBILL -0.0088,
5Y -0.0202, 10Y -0.0236, 20Y -0.0281). Sur la période réelle, la variante TLT fait un rendement réel de -0,73 %/an
avec un maxDD de 0,172, contre +2,57 %/an et 0,092 pour la variante XBB.TO (§8).

**Or, CAD 1977+, actions fixées à 20 %** (`robert_sens_cad_gold/20261114T223144Z_rolling_h4.json`) :

| or | 0 % | 5 % | 10 % | 15 % | 20 % |
|---|---|---|---|---|---|
| p10 réel | -0.0047 | 0.0080 | 0.0153 | 0.0162 | 0.0154 |
| taux de violation | 0.000 | 0.000 | 0.043 | 0.065 | 0.087 |

En USD 1975+ (`robert_sens_usd_gold/20261114T223152Z_rolling_h4.json`), le p10 passe de -0.0121 (0 % d'or) à -0.0000
(5 %), 0.0036 (10 %) et 0.0061 (15 %).

**Part d'actions, CAD, avec 10 % d'or** (`robert_sens_cad_equity/20261114T223145Z_rolling_h4.json`) : le p10 monte avec
la part d'actions (0 % → -0.0037, 20 % → 0.0153, 40 % → 0.0193, 50 % → 0.0230), mais le taux de violation aussi
(20 % → 0.043, 30 % → 0.109, 40 % → 0.217, 50 % → 0.478). En USD 1926+ avec une jambe de 2 ans, il vaut 0.052 à 20 %,
0.124 à 30 % et 0.371 à 40 % (`robert_sens_usd_duration/…`). **C'est la limite de risque dérivée qui fixe la part
d'actions à 20 %, pas l'objectif de rendement.**

## 7. Analyse « titre médiatisé » (anti-complaisance)

Script : `analysis/robert/hype_pocket.py`. Trace : `results/robert_analysis/hype_pocket.json`, exécutions moteur dans
`results/robert_hype/`.

**Méthode** :

- **Portefeuille de base** : la stratégie retenue en tickers (XIU.TO 10 / SPY 10 / GLD 10 / XBB.TO 50), avec CA_TBILL
  à 20 % comme proxy de liquidités pour allonger l'historique. On ajoute une poche x ∈ {0, 1, …, 50 %} de TSLA, NVDA ou
  SHOP.TO, prélevée au prorata.
- **Simulation** : en CAD, rebalancement annuel, fenêtres roulantes de 3, 4 et 5 ans avec un pas d'un mois. Seule la
  période réelle de chaque titre est utilisée : TSLA de 2010-07, NVDA de 2004-12 (limitée par GLD), SHOP.TO de 2015-06.

**Règle de dérivation** (proposition) : on prend le plus grand x pour lequel trois conditions tiennent, pour x et pour
toutes les poches plus petites :

- **(a) chemin** : sur toutes les fenêtres, la pire baisse maximale reste ≤ L\* = 0,23 et la pire CVaR5 mensuelle
  reste ≤ CVaR\* = 0,036 ;
- **(b) stress** : budget B = L\* − pire maxDD de la base (0,091), et la poche perd en même temps sa propre pire baisse
  historique D_H ;
- **(c) perte totale** : même budget, avec la poche ramenée à 0. Ce cas couvre le biais du survivant : les titres
  médiatisés qui ont échoué ne sont pas dans l'univers.

**Chiffre citable** = min(a, b), d'abord sur chaque horizon, puis le minimum sur 3, 4 et 5 ans.

| titre | D_H (historique propre, CAD) | x(a) maxDD seul | x(a) CVaR seule (3 / 4 / 5 ans) | x(b) stress | x(c) perte totale | **taille max citable** |
|---|---|---|---|---|---|---|
| TSLA | 0.658 | 0.20 | 0.01 / 0.02 / 0.02 | 0.211 | 0.139 | **1 %** |
| NVDA | 0.873 | 0.15 | 0.02 / 0.03 / 0.03 | 0.159 | 0.139 | **2 %** |
| SHOP.TO | 0.808 | 0.12 | 0.02 / 0.03 / 0.03 | 0.172 | 0.139 | **2 %** |

La contrainte qui lie est la **CVaR mensuelle** : la base en consomme déjà 0,032 à 3 ans et 0,030 à 4 et 5 ans, sur un
budget de 0,036. Pour l'agent d'explicabilité, une phrase sourcée possible : « Avec la capacité de perte dérivée pour
Robert, une poche de plus de 1 % (TSLA) ou de 2 % (NVDA, SHOP.TO) aurait dépassé historiquement sa limite de perte
mensuelle extrême dans au moins une fenêtre de 3 à 5 ans (`results/robert_analysis/hype_pocket.json`). » Ordres de
grandeur pour une **demande à 50 %** (4 ans, même trace) :

- pire baisse maximale du portefeuille de 0,427 (TSLA), 0,470 (NVDA) et 0,537 (SHOP.TO) ;
- part des fenêtres où la baisse dépasse L\* : 0,561, 0,758 et 0,562.

**Mise en garde** : la probabilité de perte réelle *diminue* quand on ajoute ces titres (TSLA à 4 ans : 0,135 à 0 %,
0,007 à 5 %). La raison : ces trois titres ont été des gagnants a posteriori (biais du survivant). C'est pourquoi la
règle de taille repose sur les pertes (maxDD, CVaR, stress), et **jamais sur les rendements passés** du titre.

## 8. Traduction en tickers et vérification sur la période réelle 2021-11 → 2026-09

Correspondances, d'après `universe_tickers` / `proxy_for_ticker` de `data/processed/assets.csv` : CA_EQ → XIU.TO ;
US_MKT → SPY ; GOLD → GLD ; CA_GOV_10Y → XBB.TO (indice obligataire universel, approximatif) ; CA_TBILL → ZST.TO
(approximatif, corrélation de 0,4866 selon le README). **Stratégie retenue en tickers : XIU.TO 10 % · SPY 10 % ·
GLD 10 % · XBB.TO 50 % · ZST.TO 20 %**, rebalancement annuel.

Traces : `results/robert_tickers/20261114T224154Z_non_overlapping_h4.9167.json` (une fenêtre de 59 mois) et
`results/robert_tickers/20261114T224253Z_rolling_h3.json`.

| stratégie (tickers) | réel annualisé | nominal | vol | maxDD | CVaR5 | violation des limites |
|---|---|---|---|---|---|---|
| **retenue** (XIU 10/SPY 10/GLD 10/XBB 50/ZST 20) | **0.0257** | 0.0611 | 0.0571 | 0.0918 | 0.0273 | non |
| même structure, liquidités CA_TBILL | 0.0252 | | 0.0568 | 0.0904 | 0.0269 | non |
| plus courte (XBB 30 / ZST 40) | 0.0319 | | 0.0467 | 0.0678 | 0.0223 | non |
| sans or (XBB 57 / ZST 23) | 0.0057 | | 0.0552 | 0.1007 | 0.0288 | non |
| AGG au lieu de XBB | 0.0340 | | 0.0518 | 0.0728 | 0.0219 | non |
| **TLT au lieu de XBB** (duration longue) | **-0.0073** | 0.027 | 0.0859 | 0.1717 | 0.0423 | **oui (CVaR)** |
| 30 % actions défensives (XIU, PG, FTS, JNJ) | 0.0122 | | 0.0550 | 0.0851 | 0.0234 | non |
| 60/40 (XIU 30/SPY 30/XBB 40) | 0.0538 | 0.0902 | 0.0902 | 0.1356 | 0.0474 | **oui (CVaR)** |
| cash ZST.TO | -0.0001 | | 0.0062 | 0.0041 | 0.0020 | non |
| ORACLE (hindsight) : SPY 0.19, GLD 0.21, JNJ 0.31, RY.TO 0.29 | 0.1585 | | 0.0988 | 0.0662 | 0.0360 | — |

- **Stratégie retenue** : recouvrement en 15 mois et pire rendement sur 12 mois de -0,070. La variante TLT met 25 mois
  à récupérer, pour un pire 12 mois de -0,143.
- **Roulant sur 3 ans** : la stratégie retenue fait +0,81 %/an réel sur 2021-11..2024-10 et +8,73 %/an sur
  2022-11..2025-10.
- **Limite de la vérification** : une seule trajectoire (2022 compris), donc ce n'est pas une preuve. Le recul de la
  variante sans or (+0,57 % réel) montre que **l'or a beaucoup pesé** sur cette période.

## 9. Rétro-ingénierie

Script : `analysis/robert/reverse_engineer.py`. Trace : `results/robert_analysis/reverse_engineer.json`. Il s'appuie
sur l'ORACLE grossier, qui ne contient que les actions larges et la courbe des taux, pour lire « part d'actions ×
duration ». Les variables sont observées à la **fin du mois qui précède** chaque fenêtre :

- inflation sur 12 mois ;
- taux court (≈ 12 × rendement mensuel du cash) ;
- taux long (Shiller GS10, puis FRED GS10 après 2024-09 ; OECD IRLTLT01CAM156N pour le CAD) ;
- pente de la courbe et variation du taux long sur 12 mois ;
- taux court réel ;
- momentum des actions sur 12 mois et position face à la moyenne mobile 10 mois ;
- CAPE (USD seulement, **pas en point-in-time**).

Le lien est mesuré par le ρ de Spearman sur les fenêtres non chevauchantes (N = 25 en USD, N = 11 en CAD). Les fenêtres
roulantes se chevauchent : elles ne servent qu'à vérifier la cohérence. Environ 36 tests sont faits par échantillon,
d'où un **risque de faux positifs** (environ 2 attendus au seuil de 5 %). Grille d'étiquetage :

- **robuste** : même signe dans les deux ères, p < 0,05 dans au moins un échantillon non chevauchant, |ρ| ≥ 0,3 dans
  l'échantillon roulant de l'autre ère, et même signe avant et après 1975 ;
- **fragile** : significatif dans une seule ère ;
- **non concluante** : tous les autres cas.

**Stabilité des poids de l'oracle** :

- **USD** : la part d'actions de l'oracle a une moyenne de 0,387 et un écart-type de 0,307, avec un p10 à 0 et un p90
  à 0,778. La maturité obligataire a une moyenne de 9,4 ans et un écart-type de 7,8 ans, avec un p10 à 0,08 et un p90
  à 20 ans.
- **CAD** : la part d'actions a une moyenne de 0,469 et un écart-type de 0,337, avec un p10 à 0 et un p90 à 0,862.
- **Lecture** : l'oracle saute d'un extrême à l'autre, à 0 % ou à plus de 70 % d'actions et en T-bill ou à 20 ans de
  duration. Aucun mélange constant ne le reproduit.

| # | règle | données | confiance |
|---|---|---|---|
| R1 | **Pour Robert, la duration longue dégrade le mauvais cas** : avec 20 % d'actions, le p10 se détériore et les violations augmentent quand on passe de 2 à 20 ans de jambe obligataire. La jambe 2 ans est la meilleure, la jambe T-bill est proche. | §6 (même ordre en roulant et en non chevauchant), ère CAD (`bonds_ca10y` est la dernière en p10 dans les quatre exécutions CAD), période réelle (TLT) | **robuste** (inconditionnelle, 3 sources indépendantes) |
| R2 | **Aucun poids de l'oracle n'est stable** : l'écart moyen avec l'oracle va de 7 à 11 points réels par an, et la seule politique défendable est un compromis prudent et constant. | stabilité ci-dessus ; `gaps.json` | **robuste** |
| R3 | **Le cash n'est pas sans risque en termes réels** : P(perte réelle) de 0,44 à 0,49 pour le cash sur l'ère USD, de 0,30 à 0,34 sur l'ère CAD. Sur 3 ans, avec les limites H=3, c'est pourtant le cash ou l'échelle courte qui ressort sur l'ère USD. | §5.2 | **robuste** (les deux ères) |
| R4 | **Un taux court réel élevé au départ va avec une part d'actions de l'oracle plus faible** : ρ = -0,409 (p = 0,047) en USD non chevauchant, -0,330 (p = 0,32) en CAD, -0,358 et -0,314 en roulant, -0,377 et -0,420 avant et après 1975. Le taux court nominal donne le même signe dans les six échantillons, mais p ≈ 0,06. | `reverse_engineer.json` → `labels` | **robuste selon la grille, mais faible** (test multiple, N petit) |
| R5 | **Une courbe plus pentue va avec plus d'actions dans l'oracle** : ρ = 0,441 (p = 0,027) en USD, mais -0,006 avant 1975 et 0,321 (n.s.) en CAD. | idem | **fragile** |
| R6 | **10 à 15 % d'or améliore le p10 depuis 1975** (§6). Mais l'or n'est investissable que depuis 1975, et le résultat tient à quelques fenêtres où l'oracle CAD lui donne un gros poids (1977-80 : 0,39 ; 2005-08 : 0,50 ; 2009-12 : 0,59 ; 2021-24 : 0,34, §5.1). La période réelle le confirme sans le prouver. | `sensitivity.json`, `robert_tickers` | **fragile** |
| R7 | **CAPE, inflation sur 12 mois, tendance (MA10) et momentum 12 mois** : aucune association stable avec la part d'actions ou la duration de l'oracle. Le lien taux court ↔ maturité de l'oracle change même de signe entre les ères (ρ = -0,376 en USD, +0,432 en CAD). | idem | **non concluante** |

**Aucune de ces associations n'est causale.** Elles décrivent le passé sur peu de fenêtres indépendantes.

## 10. Signaux candidats pour l'étape 2 (à tester, non testés ici)

- Taux court réel (taux directeur − IPC sur 12 mois) et son niveau face à sa médiane historique (R4).
- Pente de la courbe (10 ans − 3 mois) et sa variation, comme signal de récession (R5).
- Signe de la corrélation actions-obligations sur 36 mois glissants, pour couvrir le régime de 2022 où les deux
  baissent ensemble.
- Écart de crédit Baa − Aaa : les fichiers FRED AAA et BAA sont déjà dans `data/raw/fred/`, mais il n'a pas été testé.
- Valorisation en point-in-time (rendement des bénéfices − taux réel) au lieu du CAPE révisé.
- Tendance de l'USDCAD, pour la poche US non couverte.
- Taux réels (obligations à rendement réel) comme déterminant de l'or.
- Fondamentaux du titre demandé (rentabilité, flux de trésorerie disponibles, levier, valorisation, volatilité) pour
  l'agent de gouvernance : la fiche demande des entreprises rentables au bilan sain.
- Nouvelles et incertitude politique (EPU) comme modulateurs du budget de risque.

## 11. Limites

- **Proxys** :
  - indices Ken French et secteurs SIC, qui ne sont pas des produits investissables ;
  - CA_TBILL est un taux interbancaire ;
  - les correspondances avec les tickers sont approximatives (XBB.TO face à CA_GOV_10Y : corrélation de 0,5843 ;
    ZST.TO face à CA_TBILL : 0,4866, d'après le README).
- **Obligations synthétiques** : leur volatilité est sous-estimée avant 1962 et pour le 10 ans canadien (taux moyens
  mensuels), ce qui flatte la variance minimale et la parité de risque sur la période ancienne. UST_2Y est interpolé
  avant 1953. CORP_AAA et CORP_BAA ignorent les défauts, ce qui gonfle leur rendement ; l'oracle choisit souvent
  CORP_AAA, et c'est en partie un artefact.
- **Or** : non investissable avant 1975, il est exclu de l'ère 1. Son rôle n'est estimé que sur 1975-2026.
- **Change** : le CAD n'existe qu'à partir de 1971, et l'ère CAD commence en 1977 à cause de CA_EQ. Avant, on fait
  l'hypothèse « USD ≈ retraité canadien ».
- **CVaR mensuelle** : sur 36 à 60 mois, la CVaR 5 % repose sur 2 ou 3 observations. Elle est bruitée, alors que c'est
  elle qui fixe la taille de la poche médiatisée.
- **Seuils** : ils sont dérivés d'une règle qui n'est pas monotone et qui dépend de l'ère (§4). La part d'actions de
  20 % en découle en partie (circularité, §4 et §6).
- **Biais** :
  - biais du survivant, l'univers ayant été choisi en 2026 (TSLA, NVDA et SHOP.TO sont des gagnants) ;
  - révisions des données FRED, dates de référence et non dates de publication ;
  - CAPE pas en point-in-time.
- **Frais et impôts** : on ne compte que 10 pb par unité échangée. Il n'y a ni frais de gestion des FNB ni impôts
  (REER, FERR et CELI sont ignorés), et aucun retrait n'est modélisé. Le risque de séquence des retraits d'un retraité
  n'est donc pas mesuré.
- **ORACLE** : il est calculé par pénalité. Sur les exécutions à 4 ans, il respecte les limites dans 95 fenêtres sur 97
  (USD, roulant) et dans 44 sur 46 (CAD, roulant), d'après le champ `risk_limits_met` des traces.

**Problèmes du moteur rencontrés** (moteur non modifié) :

1. Aucun bug bloquant n'a été trouvé.
2. Dans le walk-forward, avec peu de fenêtres passées, les premiers choix sont très instables (`bonds_20y` choisi 8 fois
   sur l'ère USD). Ce n'est pas un bug, mais il faut l'afficher.
3. `missed_target` et `shortfall_prob` mesurent une perte réelle annualisée, et non une perte nominale du capital.
4. La CVaR des fenêtres courtes est très sensible (voir plus haut).
5. Bug glidepath (progression mesurée par rapport à n) corrigé par l'équipe le 2026-11-14. Tout a été relancé, sans effet sur le choix robuste (section « Correctif moteur »).
6. Le moteur n'a pas de stratégie « poche satellite » ni de contrainte de CVaR imposée ex-ante. Contournement :
   stratégies statiques générées par script (`hype_pocket.py`, `sensitivity.py`).

## 12. Les quatre questions

- **Quelles données ?**
  - rendements mensuels reconstitués de 1926 à 2026 (Ken French, FRED/Shiller pour les obligations synthétiques,
    Banque du Canada, datahub pour l'or, yfinance et starter officiel pour les tickers) ;
  - CPI-U et IPC Canada ;
  - hash des données `008f122d5da4f8f7`.

  Détail dans `data/SOURCES.md`.
- **Pourquoi ce choix ?**
  - la capacité de perte de Robert est traduite en limites dérivées (maxDD 0,23 et CVaR5 0,036 à 4 ans) ;
  - l'objectif « meilleur rendement réel au 10e centile » traduit directement « préserver le pouvoir d'achat avec une
    croissance modérée » ;
  - la structure retenue (20 % d'actions larges, obligations courtes ou intermédiaires, liquidités, environ 10 % d'or
    depuis 1975) est la seule qui reste en tête ou proche de la tête dans les deux ères, sur 3 à 5 ans, en non
    chevauchant comme en roulant.
- **Quelles limites ?** Celles du §11 : proxys, obligations lissées, or tardif, CAD tardif, biais du survivant, pas
  d'impôts ni de retraits, petit nombre de fenêtres indépendantes et CVaR bruitée.
- **Qu'est-ce qui changerait la réponse ?**
  - **des limites de perte plus larges**, validées par l'équipe : avec les limites de l'ère CAD, le choix roulant
    devient `momentum_core_cash` et des mélanges à 40 % d'actions deviennent admissibles (§5.2) ;
  - un horizon de 3 ans, qui ramène vers le cash et l'échelle courte sur l'ère USD ;
  - un poids moindre de l'histoire 1926-1975 ;
  - des retraits mensuels (risque de séquence) ;
  - des frais et des impôts réels ;
  - un régime où l'or ne joue plus son rôle ;
  - pour le titre médiatisé, une CVaR\* plus large : la taille admissible suit presque linéairement le budget de CVaR
    restant.

## 13. Reproduire

```bash
cd research/backtest
.venv/bin/python -I analysis/robert/derive_thresholds.py
for p in robert_long_usd robert_long_usd_h3 robert_long_usd_h5 robert_usd_gold robert_cad robert_cad_eralimits; do
  .venv/bin/python -I -m engine.run --profile $p --out results/$p
  .venv/bin/python -I -m engine.run --profile $p --mode rolling --step 12 --out results/$p
done
.venv/bin/python -I -m engine.run --profile robert_cad --horizon 3 --mode rolling --step 12 --out results/robert_cad
.venv/bin/python -I -m engine.run --profile robert_cad --horizon 5 --mode rolling --step 12 --out results/robert_cad
.venv/bin/python -I analysis/robert/oracle_coarse.py
.venv/bin/python -I analysis/robert/sensitivity.py
.venv/bin/python -I analysis/robert/hype_pocket.py '{"XIU.TO":0.1,"SPY":0.1,"GLD":0.1,"XBB.TO":0.5,"CA_TBILL":0.2}'
.venv/bin/python -I -m engine.run --profile robert_tickers --out results/robert_tickers
.venv/bin/python -I -m engine.run --profile robert_tickers --mode rolling --horizon 3 --step 12 --out results/robert_tickers
.venv/bin/python -I analysis/robert/reverse_engineer.py
.venv/bin/python -I analysis/robert/gaps.py
.venv/bin/python -I analysis/robert/report_tables.py      # tableaux markdown de ce rapport
```
Les horodatages des fichiers de trace changent à chaque nouvelle exécution. Les scripts lisent toujours la trace la
plus récente.
