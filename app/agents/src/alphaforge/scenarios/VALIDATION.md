# Validation hors échantillon des scénarios probabilistes (volet C)

> **Simulation uniquement. Modèle, pas prévision.** Ce rapport mesure à quel point les distributions du volet B
> auraient décrit correctement l'incertitude **si on les avait utilisées dans le passé**. Ce n'est pas une garantie
> pour l'avenir, ni un conseil financier.

## Résumé en 8 lignes

1. **Aucun modèle n'est bien calibré partout.** À 1 an, les intervalles à 80 % couvrent 73 à 91 % des résultats
   réalisés sur les mélanges risqués : c'est correct. La couverture se dégrade quand l'horizon s'allonge.
2. **Les modèles sans ancrage (`sbb`, `iid`, `hmm_rs`) surestiment nettement les obligations et le cash** dans la
   période de test canadienne (1990-2026, taux en baisse). Sur CAD77 à 5 ans, le rendement réalisé passe sous leur
   p10 dans 35 à 41 % des cas (attendu : 10 %).
3. **`sbb_ca` corrige ce biais de niveau** (5 % sous le p10, perte max. au-dessus du p90 dans 10 % des cas sur CAD77 à
   5 ans), mais il devient **prudent** : il surestime P(perte max. > 20 %) pour les mélanges équilibrés. Il
   **échoue** aussi quand les taux récents sont au-dessus de leur moyenne (États-Unis 1965-1981).
4. **Tous les modèles sous-estiment la perte maximale des obligations quand les taux montent** (1965-1981, 2021-2023).
   Le recul obligataire de 2022 est hors de leurs intervalles à 90 %, sauf en partie pour `sbb_ca`.
5. **`hmm_rs` n'apporte pas de gain démontré** sur `sbb` (les scores de Brier ont des intervalles qui se chevauchent).
   Il fait moins bien sur USD1926, et son régime « calme » d'USD1926 est un effet de construction des données
   d'avant 1953.
6. **La borne de 24 mois sur la longueur de bloc ne change presque rien** (6 à 96 mois : écarts dans les intervalles).
7. **« 2022 seulement » n'est pas une mesure de risque probabiliste** : la perte max. réalisée sur 10 ans dépasse la
   perte max. de 2022 dans 41 % des fenêtres CAD77, et son score de Brier vaut 0,62 contre 0,07 à 0,09 pour les modèles.
8. **Recommandation** : par défaut `sbb_ca` sur CAD77, toujours affiché à côté de `sbb` comme fourchette de modèles
   et à côté du repère historique de 2022. Seuls 1 à 5 ans sont présentables ; 10 ans et plus, seulement avec une
   mise en garde forte.

## 1. Protocole (reproductible)

- **Code** : `app/agents/src/alphaforge/scenarios/validation/` (module `walkforward`, `scoring`, `analysis`, `checks`,
  `report`), tests `app/agents/tests/scenarios/test_validation.py` (7 tests, données synthétiques).
- **Commande** (wall time 2 min 38 s sur 12 processus) :
  ```sh
  cd app/agents
  uv run --group scenarios python -m alphaforge.scenarios.validation \
    --input src/alphaforge/data/long \
    --output <ce dossier> --ref <analyse/scenarios-ref-small> --n-paths 4000 --n-boot 1000 --workers 12
  ```
  (Le run d'origine lisait le même build, alors sous `research/backtest/data/processed`.)
- **Identifiants** (`manifest.json`) : `data_sha256` **008f122d5da4f8f7**, `scenarios_package_sha` e74ab820c9b5 (même code
  du volet B que le run de référence), `validation_code_sha` 1bd12840289a, graine 20261114, 54 504 lignes de scores.
  Le résultat ne dépend pas du nombre de processus (testé).
- **Walk-forward** : origines en fin d'année (décembre), **tous les 12 mois** : CAD77 de 1990-12 à 2025-12,
  CAD71 de 1975-12, USD1926 de 1950-12, USD1953 (USD1926 sans les 321 mois d'avant 1953-04, où les obligations
  viennent du taux long de Shiller) de 1963-12. Horizons de 1, 3, 5 et 10 ans ; une origine n'est notée à l'horizon H
  que si les 12·H mois suivants existent. À chaque origine T, chaque modèle est ajusté par
  `models.fit(pool, model_id, fitted_through=T)`, avec les paramètres de `configs/full.yaml` (HMM : `n_init` 6). On
  simule ensuite **4 000 trajectoires** (un compromis de calcul : le produit en vise 10⁵) sans bootstrap externe : on
  évalue la distribution prédictive ponctuelle, **pas** les intervalles `ci_lo`/`ci_hi`.
- **Mélanges** (étiquette = **actions d'abord, revenu fixe ensuite**) : `eq30_fi70` (30 % actions / 70 % obligations),
  `eq40_fi60`, `eq70_fi30`, `eq100_fi00` (100 % actions), `eq00_fi100` (100 % obligations 10 ans), `eq00_cs100`
  (100 % cash). En CAD77, les actions sont réparties 50/50 entre CA_EQ et US_MKT (`eq40_fi60` = `ca20-us20-bd60-cs00-gd00`,
  `eq70_fi30` = `ca35-us35-bd30-cs00-gd00`, `eq30_fi70` = `ca15-us15-bd70-cs00-gd00`). En CAD71 et USD, les actions
  sont à 100 % en US_MKT.
- **Modèles évalués** : `sbb`, `sbb_ca`, `iid`, `iid_ca`, `hmm_rs`, `hmm_rs_ca`, `hmm_rs_fl` (`hmm_rs` qui démarre dans
  le régime filtré du dernier mois au lieu de la loi stationnaire), et `sbb_L06`, `sbb_L12`, `sbb_L48`, `sbb_L96` (borne de
  bloc à 6, 12, 48 ou 96 mois au lieu de 24).
- **Repères** : (a) `hist_emp`, la distribution empirique de toutes les fenêtres glissantes de H ans entièrement
  contenues dans l'historique avant T (au moins 12 fenêtres) ; (b) `stress_2022`, une prévision ponctuelle : le
  rendement de 2022 répété chaque année et la perte max. de 2022. **Ce repère lit 2022, donc il a un avantage
  d'information pour les origines antérieures** ; c'est voulu, puisque c'est le contrôle actuel du produit.
- **Métriques** : couverture des intervalles centraux à 80 % (p10-p90) et 90 % (p05-p95) du rendement annualisé et de la
  perte max. (depuis un sommet, capital initial compris, même définition que `engine.py`) ; taux de dépassement
  unilatéral (rendement < p10, perte max. > p90 : 10 % attendus) ; PIT randomisé et test de Kolmogorov-Smirnov ; CRPS
  exact sur l'échantillon et score de compétence CRPSS = 1 − CRPS/CRPS(`hist_emp`) ; perte pinball au p05/p10 ; score
  de Brier et tableaux de fiabilité pour P(perte cumulée > 0, 10, 20 %) et P(perte max. > 10, 20, 30 %).
- **Dépendance et petits échantillons.** Avec des origines annuelles, deux fenêtres de H ans se chevauchent sur H − 1
  ans. Les moyennes (couverture, CRPS, Brier) utilisent toutes les origines. Leur **IC à 90 %** vient d'un bootstrap par
  blocs mobiles circulaire sur la suite des origines (blocs de max(2, H) origines, 1 000 réplications), et tous les
  mélanges d'une même origine sont rééchantillonnés ensemble. Le **KS** n'est appliqué qu'à des sous-ensembles
  **non chevauchants** (origines espacées de H ans, décalage 0 ; `per_mix.csv` donne aussi la plus petite p-valeur
  sur les H décalages). Nombre de fenêtres indépendantes : CAD77 35 / 11 / 7 / 3 à H = 1 / 3 / 5 / 10 ; USD1926
  75 / 25 / 15 / 7. **À 10 ans, l'IC du bootstrap est lui-même optimiste** : 3 à 7 observations indépendantes ne
  permettent pas d'estimer correctement la dépendance.
- **Absence de look-ahead** : c'est vérifié de trois façons. (1) À chaque ajustement, le code contrôle que
  `fitted_through == T`, que le pool ajusté contient exactement les mois ≤ T, et que l'indice maximal tiré est ≤ T.
  (2) Sur les **vraies** données (`checks/look_ahead_real.csv`), les 321 ou 165 mois qui suivent 1999-12 ou 2012-12
  ont été remplacés par du bruit : ajustement, indices et métriques sont identiques pour `sbb`, `sbb_ca`, `hmm_rs` et
  `hmm_rs_ca`, sur CAD77 et USD1926 (16 cas sur 16). (3) Le test `test_walkforward_no_look_ahead` vérifie la même
  chose sur données synthétiques au niveau des scores. Il reste deux limites : un look-ahead **de millésime** (les
  séries sont reconstruites et révisées après coup) et le biais du survivant, qu'aucun test ne peut retirer.

## 2. Résultats principaux

Valeurs en %, IC à 90 % entre crochets. Mélanges **sans cash** (le cash est traité plus bas). Sources :
`tables.md`, section « Mélanges risqués seulement », et `pooled.csv`.

**CAD77 (famille de référence), origines 1990-12 à 2025-12**

| H | modèle | couv. 80 % rend. | rend. < p10 (att. 10) | perte max. > p90 (att. 10) | Brier (6 évén.) |
|---|---|---|---|---|---|
| 1 | sbb | 86 [79; 92] | 14 [8; 21] | 10 [5; 16] | 0.0505 |
| 1 | sbb_ca | 91 [86; 97] | 5 [1; 10] | 6 [2; 10] | 0.0523 |
| 1 | hmm_rs | 83 [74; 90] | 16 [8; 25] | 13 [7; 20] | 0.0504 |
| 1 | hist_emp | 87 [79; 93] | 13 [7; 21] | 10 [5; 15] | 0.0505 |
| 3 | sbb | 75 [62; 86] | 25 [14; 38] | 18 [9; 28] | 0.0716 |
| 3 | sbb_ca | 85 [78; 92] | 5 [2; 10] | 7 [2; 12] | 0.0815 |
| 3 | hmm_rs | 71 [60; 82] | 27 [16; 39] | 15 [7; 24] | 0.0692 |
| 3 | hist_emp | 71 [59; 82] | 28 [17; 41] | 18 [9; 27] | 0.0744 |
| 5 | sbb | 64 [52; 76] | 35 [23; 48] | 23 [12; 33] | 0.0748 [0.0620; 0.0877] |
| 5 | sbb_ca | 85 [78; 92] | 5 [1; 8] | 10 [5; 16] | 0.0894 [0.0791; 0.1008] |
| 5 | iid | 58 [44; 73] | 41 [26; 56] | 27 [17; 38] | 0.0721 |
| 5 | hmm_rs | 59 [46; 72] | 40 [25; 54] | 19 [10; 28] | 0.0702 [0.0511; 0.0911] |
| 5 | hmm_rs_ca | 83 [72; 92] | 4 [1; 6] | 9 [4; 14] | 0.0763 |
| 5 | hist_emp | 54 [35; 70] | 45 [27; 65] | 28 [17; 38] | 0.0840 |
| 5 | stress_2022 | n/a | 0 | 25 [15; 34] | 0.6151 |
| 10 | sbb | 45 [25; 68] | 55 [32; 75] | 38 [31; 45] | 0.0797 |
| 10 | sbb_ca | 85 [78; 91] | 6 [0; 13] | 5 [0; 11] | 0.0911 |
| 10 | hmm_rs | 41 [20; 62] | 59 [38; 80] | 20 [15; 25] | 0.0661 |
| 10 | hist_emp | 21 [3; 38] | 79 [62; 97] | 48 [37; 57] | 0.0990 |
| 10 | stress_2022 | n/a | 0 | 41 [34; 48] | 0.6269 |

**USD1926, origines 1950-12 à 2025-12** (période de test plus longue et plus variée : taux en hausse puis en baisse)

| H | modèle | couv. 80 % rend. | rend. < p10 | perte max. > p90 | Brier |
|---|---|---|---|---|---|
| 5 | sbb | 80 [72; 87] | 5 [3; 8] | 8 [5; 13] | 0.0823 |
| 5 | sbb_ca | 87 [82; 91] | 8 [4; 12] | 12 [8; 15] | 0.0842 |
| 5 | iid | 79 [71; 86] | 6 [4; 10] | 19 [12; 27] | 0.0827 |
| 5 | hmm_rs | 75 [67; 81] | 11 [7; 16] | 25 [15; 35] | 0.0841 |
| 5 | hist_emp | 75 [65; 84] | 6 [3; 9] | 8 [5; 13] | 0.0857 |
| 10 | sbb | 75 [58; 89] | 4 [1; 7] | 7 [3; 13] | 0.0792 |
| 10 | sbb_ca | 86 [81; 91] | 8 [3; 13] | 12 [6; 17] | 0.0785 |
| 10 | hmm_rs | 66 [52; 79] | 12 [5; 22] | 24 [11; 40] | 0.0882 |

Lecture :

- **Biais de niveau (CAD77).** Sans ancrage, le modèle croit que les taux de 1977-T reviendront en moyenne. Sur la
  période 1990-2026, où les taux ont baissé, le rendement réalisé est donc trop souvent sous le p10, de plus en plus
  quand l'horizon s'allonge. C'est surtout le cas des mélanges obligataires et du cash. Pour 100 % cash (`per_mix.csv`,
  H = 5), le rendement réalisé passe sous le p10 dans 94 % des cas avec `sbb` et 100 % avec `hmm_rs`, contre 32 % avec
  `sbb_ca`. **Un rendement du cash ou des obligations non ancré n'est pas présentable.**
- **CRPS** (`tables.md`, sections « Agrégé »). Le CRPSS du rendement contre `hist_emp`, à H = 5 et H = 10 sur CAD77,
  vaut 6 [2; 9] et 16 [12; 19] % pour `sbb`, contre 41 [17; 56] et 63 [50; 71] % pour `sbb_ca`. Pour la perte max., il
  vaut 9 [3; 16] et 10 [6; 12] % pour `sbb`, −5 [−20; 10] et −4 [−20; 11] % pour `sbb_ca`, et 14 [2; 27] et 17 [12; 24] %
  pour `hmm_rs`. Tous les modèles battent nettement `hist_emp` à long horizon. `stress_2022` est très loin derrière
  (CRPSS du rendement de −306 % à H = 5).
- **PIT et KS** (`ks_summary.csv`). Sur CAD77, le KS du rendement rejette l'uniformité (5 %) pour 2 à 3 mélanges sur 5
  avec `sbb`, `iid` et `hmm_rs` à H = 1, 3 et 5, contre 0 à 3 avec les variantes `_ca` (0 à H = 3 et H = 5). Sur USD1926 et USD1953, il ne
  rejette presque rien, mais avec 7 à 25 fenêtres indépendantes **son pouvoir est faible** : un « non-rejet » n'est
  pas une preuve de calibration.
- **Fiabilité des probabilités** (`reliability.csv`, événements de perte max., tous horizons). Sur CAD77, `sbb`
  sous-estime les probabilités faibles à moyennes (classe 10-25 % : 16,8 % prévu, 31,3 % observé) et surestime les
  fortes (classe 75-100 % : 86,5 % prévu, 74,8 % observé). `sbb_ca` est prudent sur toute l'échelle (classe 50-75 % :
  63,4 % prévu, 38,9 % observé). Sur USD1926, `sbb` est un peu prudent (classe 25-50 % : 36,1 % prévu, 27,6 % observé).

### Par mélange : 100 % obligations et 100 % actions (`per_mix.csv`)

| famille | H | mélange | modèle | rend. < p10 | perte max. > p90 | P̄(MDD > 20 %) prévu | fréquence observée |
|---|---|---|---|---|---|---|---|
| CAD77 | 5 | eq00_fi100 | sbb | 35 | 16 | 0.7 | 12.9 |
| CAD77 | 5 | eq00_fi100 | sbb_ca | 6 | 10 | 13.4 | 12.9 |
| CAD77 | 5 | eq00_fi100 | hmm_rs | 45 | 13 | 0.9 | 12.9 |
| CAD77 | 5 | eq100_fi00 | sbb | 26 | 29 | 44.9 | 35.5 |
| CAD77 | 5 | eq100_fi00 | sbb_ca | 10 | 26 | 56.1 | 35.5 |
| CAD77 | 5 | eq100_fi00 | hmm_rs | 29 | 32 | 34.1 | 35.5 |
| USD1926 | 5 | eq00_fi100 | sbb | 18 | 32 | 0.1 | 5.6 |
| USD1926 | 5 | eq00_fi100 | sbb_ca | 23 | 54 | 1.6 | 5.6 |
| USD1926 | 5 | eq100_fi00 | sbb | 4 | 4 | 67.3 | 50.7 |
| USD1926 | 5 | eq100_fi00 | hmm_rs | 14 | 24 | 50.5 | 50.7 |

La perte max. des obligations est **sous-estimée par tous les modèles sauf `sbb_ca` en CAD77**. Sur USD1926, elle
dépasse le p90 dans 31 à 54 % des fenêtres de 5 ans. P(MDD > 20 %) pour 100 % obligations est prévue à 0,1-1,6 % alors
que 5,6 % des fenêtres l'ont connue. Pour les actions, `hmm_rs` donne la probabilité moyenne la plus proche de la
fréquence observée, mais ses dépassements du p90 (24 à 32 %) montrent une distribution trop étroite dans la queue.

## 3. Contrôles demandés par l'auteur des modèles

### (i) Risque obligataire en hausse des taux : confirmé, et c'est la limite principale

On retient les fenêtres réalisées entièrement entre l'origine et 1981-12 (`checks/rising_rates.csv`). Les origines
vont de 1965-12 à 1980-12 pour USD1926 et USD1953, et de 1975-12 à 1980-12 pour CAD71. CAD77 ne permet pas ce test : sa
fenêtre commence en 1977-01, donc il n'existe aucune origine avec assez d'historique avant 1981.

| famille | mélange | modèle | H | n | PIT moyen de la perte max. (0,5 attendu) | perte max. > p90 |
|---|---|---|---|---|---|---|
| USD1926 | eq00_fi100 | sbb | 1 / 3 / 5 | 16 / 14 / 12 | 0.89 / 0.88 / 0.86 | 62 / 64 / 58 |
| USD1926 | eq00_fi100 | sbb_ca | 1 / 3 / 5 | 16 / 14 / 12 | 0.95 / 0.96 / 0.95 | 81 / 64 / 75 |
| USD1926 | eq00_fi100 | hmm_rs | 1 / 3 / 5 | 16 / 14 / 12 | 0.86 / 0.84 / 0.83 | 50 / 57 / 50 |
| USD1953 | eq00_fi100 | sbb | 1 / 3 / 5 | 16 / 14 / 12 | 0.76 / 0.72 / 0.69 | 38 / 29 / 33 |
| USD1953 | eq00_fi100 | sbb_ca | 1 / 3 / 5 | 16 / 14 / 12 | 0.81 / 0.83 / 0.82 | 50 / 64 / 75 |
| CAD71 | eq00_fi100 | sbb | 1 / 3 | 6 / 4 | 0.51 / 0.58 | 33 / 50 |

Les obligations de 1926-1953 (taux long de Shiller, lissé) rendent le risque obligataire d'USD1926 encore plus faible ;
les retirer (USD1953) améliore la calibration sans la corriger. **`sbb_ca` est le pire modèle dans ce régime.** En 1965,
les taux courts des 12 derniers mois dépassaient la moyenne de la fenêtre. Le facteur d'ancrage s > 1 a donc *relevé*
le rendement de tous les blocs, ce qui a rendu les reculs plus rares. L'ancrage déplace la moyenne : ce n'est pas un
modèle du risque de taux. Il n'est « bon » sur CAD77 1990-2026 que parce que, dans cette période, s < 1 a abaissé le
rendement des obligations dans le bon sens.

**2021-2023** (`checks/recent_2021_2023.csv`) :

| famille | origine | H | mélange | réalisé : rend. ann. / perte max. | sbb : p05 rend. / p95 perte max. | sbb_ca : p05 / p95 | P(MDD > 20 %) sbb / sbb_ca |
|---|---|---|---|---|---|---|---|
| CAD77 | 2020-12 | 3 | eq00_fi100 | −5,0 / 20,5 | 1,0 / 13,5 | −5,9 / 23,5 | 0,0 / 9,7 |
| CAD77 | 2021-12 | 1 | eq00_fi100 | −10,2 / 14,3 | −5,6 / 10,3 | −11,5 / 15,0 | 0,0 / 1,7 |
| CAD77 | 2021-12 | 1 | eq40_fi60 | −9,9 / 14,7 | −2,8 / 10,6 | −10,1 / 14,6 | 0,0 / 1,2 |
| USD1926 | 2021-12 | 1 | eq00_fi100 | −16,4 / 18,3 | −4,9 / 8,5 | −8,0 / 11,1 | 0,0 / 0,4 |
| USD1926 | 2021-12 | 1 | eq40_fi60 | −17,5 / 19,9 | −6,2 / 13,4 | −10,7 / 15,6 | 0,9 / 2,1 |

En 2022, les résultats réalisés tombent hors de l'intervalle à 90 % de `sbb`, de `hmm_rs` et de `hist_emp` (PIT du
rendement ≤ 0,011). `sbb_ca` est le seul à les placer en bordure de son intervalle en CAD (PIT de 0,05 à 0,07) ; en USD,
il les rate aussi. **Il faut donc toujours afficher le repère historique (2022, pire épisode) à côté de la distribution.**

### (ii) Borne de 24 mois sur la longueur de bloc : sans effet matériel

La longueur Politis-White brute aux origines a une médiane de 25,1 mois sur CAD77 (de 5,4 à 34,1) et de 44,3 mois sur
USD1926 (de 23,6 à 57,3) (`fits.csv`). La borne de 24 mois est donc atteinte presque partout. À H = 10 sur CAD77, la part
des pertes max. au-dessus du p90 vaut 34 / 34 / 38 / 39 / 38 % pour des bornes de 6 / 12 / 24 / 48 / 96 mois, et sur
USD1926 12 / 10 / 7 / 7 / 7 %. Les scores de Brier restent dans les mêmes intervalles (CAD77, H = 10 : 0,0750 pour une
borne de 6 mois, 0,0797 pour 24 mois). Relever la borne (48 ou 96 mois) ne change rien ; la baisser à 6 ou 12 mois
dégrade un peu USD1926 et améliore un peu CAD77. **Garder 24 mois.** La dépendance de très long terme (décennies
d'inflation) n'est de toute façon pas captée, quelle que soit la borne.

### (iii) HMM sur USD1926 : un régime « de construction des données », confirmé

Ajusté sur toute la fenêtre avec les paramètres de `full.yaml` (`checks/hmm_usd1926.json`), le HMM retient K = 3. L'un
des régimes a une volatilité obligataire de 0,17 %/mois (contre 1,5 et 3,0 % pour les deux autres). Il contient
**99,85 % des mois d'avant 1953-04**, et 94 % de sa masse est située avant 1953-04. Ce régime décrit la série de
Shiller, pas un état du marché.

L'EM est aussi **instable** : selon la graine et `n_init`, le BIC de K = 3 varie de 5 345,76 à 5 431,15, et la durée
attendue du régime d'avant 1953 varie de 132 à 823 mois (6 essais). Le README cite « plusieurs centaines de mois » :
c'est vrai pour certaines graines seulement.

Hors échantillon, `hmm_rs` fait moins bien que `sbb` sur USD1926 (H = 10 : perte max. au-dessus du p90 dans 24 % des
cas contre 7 % ; Brier 0,0882 contre 0,0792). Sur USD1953, il fait jeu égal avec `sbb` (H = 5 : 28 % contre 26 %).
**Ne pas exposer `hmm_rs` sur USD1926.** Si on garde un HMM en USD, utiliser une fenêtre à partir de 1953-04.

### (iv) `sbb` ou `sbb_ca` : ni l'un ni l'autre n'est calibré, et ils encadrent le résultat observé

Cas cité par l'auteur (CAD77, `eq70_fi30` = 70 % actions / 30 % obligations, H = 5, P(perte max. > 20 %)) : le run de
référence ajusté sur toute la fenêtre donne 14,1 % (`sbb`) et 31,1 % (`sbb_ca`). Hors échantillon (31 origines,
7 fenêtres indépendantes), la probabilité moyenne prévue vaut **12,6 % (`sbb`) et 37,6 % (`sbb_ca`)**, pour une
fréquence observée de **25,8 %** (8 fenêtres sur 31, chevauchantes). Les scores de Brier sont proches : 0,233 contre
0,242. Les deux modèles se trompent en sens opposés. Sur l'ensemble des mélanges risqués de CAD77, `sbb_ca` est meilleur
pour les quantiles de rendement et la queue de la perte max. (5 % sous le p10 et 10 % au-dessus du p90, contre 35 % et
23 % pour `sbb` à H = 5), mais moins bon au score de Brier des événements (0,0894 contre 0,0748). Il surestime en effet
P(MDD > x) pour les mélanges équilibrés : pour `eq40_fi60`, 9,1 % prévus contre 0 % observé à H = 5. L'écart entre les
deux modèles mesure une **incertitude de modèle** qu'il faut montrer à l'utilisateur, pas arbitrer en secret.

### (v) Monotonie et ordre des tableaux du README : vrai historique, pas un bug

- **Étiquettes du README** : elles sont cohérentes, au format actions/obligations. « 70/30 » = `ca35-us35-bd30`, « 40/60 » =
  `ca20-us20-bd60`, « 0/100 » = `bd100` (100 % obligations).
- Dans le run de référence (`checks/monotonicity_reference.csv`), le long de la ligne actions/obligations de CAD77 à
  H = 5, P(MDD > 20 %) vaut 4,3 / 0,3 / 1,1 / 8,4 / 14,1 / 40,0 % pour 0 / 40 / 50 / 60 / 70 / 100 % d'actions avec `sbb`
  (minimum à 40 %). Avec `sbb_ca`, elle vaut 13,5 / 2,9 / 8,3 / 18,2 / 31,0 / 48,3 %. La courbe est en U : 100 %
  obligations est plus risqué que 40/60.
- **Ce n'est pas un bug, c'est l'histoire récente, pas 1977-1981** (`checks/historical_mdd_windows.csv`). Sur CAD77, 8,0 %
  des fenêtres glissantes de 5 ans en 100 % obligations ont une perte max. > 20 % (maximum 21,9 %). Toutes commencent
  entre 2017 et 2021, c'est-à-dire qu'elles couvrent la hausse des taux de 2020-2023. Aucune fenêtre `eq40_fi60` ne
  dépasse 20 % (maximum 14,7 %). Les fenêtres de 1977-1981 ne dépassent pas 20 % pour l'indice obligataire canadien
  (moyennes mensuelles de taux, donc lissé). `sbb` conserve des séquences de 24 mois, donc le recul continu de
  2020-2023 ; `iid` et `hmm_rs` les cassent et restent monotones sur CAD77 (0 cas non monotone sur 63). La diversification
  actions/obligations rend le mélange 40/60 moins risqué que chacune de ses deux parties.
- Hors échantillon, le risque obligataire réel était même **plus élevé** que ce que dit `sbb` (12,9 % observés contre
  0,7 % prévus à H = 5 pour 100 % obligations).

## 4. Bugs et anomalies trouvés

1. **Doublon dans la sensibilité à la longueur de bloc** (petit bug, **non corrigé**). Dans `configs/small.yaml`
   (ligne 65) et `configs/full.yaml` (ligne 67), `sensitivity.mixes` contient deux fois `ca00-us00-bd100-cs00-gd00`
   (probablement à la place de `ca00-us100-bd00-cs00-gd00`), et `job.py:150` ne retire pas les doublons. Résultat :
   dans `sensitivity_block_length.csv` du run de référence, 2 268 lignes sur 5 670 sont des doublons exacts (1 134
   paires, `checks/sensitivity_duplicates.json`). Patch proposé :
   ```python
   # job.py, _sensitivity
   targets = list(dict.fromkeys(m for m in sens.get("mixes", []) if m in mixes)) or mixes[:3]
   ```
   et, dans les deux YAML, remplacer le second `ca00-us00-bd100-cs00-gd00` par `ca00-us100-bd00-cs00-gd00`. Je ne l'ai
   pas appliqué : cela change `package_sha` et donc le `code_sha` du run de référence.
2. **Instabilité de l'EM du HMM** (anomalie, pas un bug) : voir (iii). `fit_hmm` consomme aussi des tirages aléatoires
   pour K = 1 (`starts` est construit avant d'être tronqué), si bien que les départs de K = 2 et K = 3 dépendent de
   `n_init` même pour K = 1. C'est sans conséquence sur la validité, mais `n_init` = 6 peut donner un *moins bon* optimum
   que `n_init` = 3 (BIC de K = 3 : 5 431,15 contre 5 352,82 avec la graine 20261114). Proposition : un générateur dédié
   par K (`rng_for(seed, "hmm", K)`) et davantage de départs pour K = 3.
3. **README à nuancer** (pas un bug du code) : la durée « de plusieurs centaines de mois » du régime d'USD1926 dépend de
   la graine. La phrase « l'ancrage des taux augmente nettement le risque des mélanges obligataires » n'est vraie que si
   s < 1 (taux récents sous la moyenne) ; si s > 1, l'ancrage *réduit* le risque simulé.
4. Aucun look-ahead, ni dans `fit`, ni dans `simulate_indices`, ni dans l'ancrage `_ca` (contrôles du §1). Les
   définitions de la perte max. et du rendement annualisé d'`engine.py` concordent avec un recalcul indépendant
   (`test_realized_and_rolling_outcomes_agree_with_engine_definition`).

## 5. Recommandations

- **Modèle par défaut : `sbb_ca` sur CAD77**, avec `sbb` toujours affiché à côté sous la forme d'une fourchette de
  modèles (« selon les hypothèses de taux : 13 à 38 % »). Raisons : les taux actuels sont sous la moyenne de la fenêtre
  (CA_TBILL : 2,26 %/an sur 12 mois contre 5,31 %/an, `fits.json` du run de référence), ce qui ressemble au contexte de
  1990-2026 où `sbb_ca` est le mieux calibré pour les quantiles. Son biais restant est **prudent**, ce qui est
  préférable pour un outil de protection de l'investisseur. Le `default_model: sbb` actuel du manifeste est le moins
  bon choix sur CAD77 pour les mélanges obligataires.
- **`hmm_rs`, `hmm_rs_ca`, `hmm_rs_fl`** : à garder seulement comme analyse de sensibilité, pas dans l'interface.
  Ils n'apportent pas de gain démontré, sont instables (EM) et sont faussés sur USD1926. **`iid` et `iid_ca`** : à ne
  pas exposer (ce sont des références naïves).
- **Familles** : **CAD77** par défaut. **CAD71** comme contrôle de longue période en CAD (sans CA_EQ ni or ; même
  conclusion). **USD1926** seulement pour un investisseur en USD, avec `sbb` ; c'est la famille la mieux calibrée
  (H = 5 : 5 % sous le p10 et 8 % au-dessus du p90), mais le risque obligataire y est sous-estimé à cause des données
  d'avant 1953. Proposer **USD1953** comme famille si un HMM est retenu en USD. Crypto : non validée (144 mois),
  toujours HYPOTHESE.
- **Ce qui est assez fiable pour être montré (avec l'IC et le `model_id`)** : à 1 et 3 ans, les quantiles de rendement
  et P(perte max. > x) des mélanges diversifiés et actions. À 1 an, la couverture des intervalles à 80 % vaut 80 à 91 %
  sur CAD77 pour les mélanges risqués.
- **À montrer seulement avec une mise en garde forte** :
  - à 5 ans, tout : 7 fenêtres indépendantes sur CAD77, dépassements de 10 à 23 % selon le modèle ;
  - à 10 ans, tout : 3 fenêtres indépendantes, intervalles trop étroits avec `sbb` (38 % des pertes max. au-dessus du
    p90) ;
  - le **risque des obligations et du cash**, quel que soit le modèle : sous-estimé quand les taux montent, avec
    toujours le repère de 2022 à côté ;
  - les rendements du cash ou des obligations **non ancrés** : à ne pas montrer du tout.
- **Non validé, à ne pas présenter comme validé** : les horizons de 15, 20 et 30 ans (une à deux fenêtres
  indépendantes au mieux), la base `real` (inflation), les intervalles d'incertitude des paramètres `ci_lo`/`ci_hi` (ce
  run n'évalue que la distribution ponctuelle), les mélanges avec or ou crypto.
- **Texte pour `manifest.models[].validation`** : `models_validation.json` (une phrase par modèle, chiffres de ce run).
  Par exemple, pour `sbb_ca` : « Hors échantillon (CAD77, H = 5 ans) : rendement sous le p10 dans 5 % des cas, perte
  max. au-dessus du p90 dans 10 % des cas (attendu : 10 %) ; le modèle est prudent : il surestime P(perte max. > 20 %)
  pour les mélanges équilibrés (actions 40 / obligations 60 : 9,1 % prévu, 0 % observé) ; il échoue quand les taux
  récents dépassent la moyenne historique (USD 1965-1981, 100 % obligations : perte max. au-dessus du p90 dans 75 % des
  fenêtres de 5 ans). »

## 6. Les 4 questions (NBDB)

**Quelles données ?** Le build long (`alphaforge.finance.backtest.build_data`, `data_sha256` 008f122d5da4f8f7, lecture seule) : rendements
mensuels totaux non couverts (French, FRED, Shiller, BdC), pools CAD77 (1977-01 → 2026-09), CAD71, USD1926 et USD1953.
Les résultats réalisés viennent des mêmes séries, mois T+1 à T+12·H. Aucune donnée ajoutée.

**Pourquoi ce choix ?** Le walk-forward par l'API `fit(..., fitted_through=T)` reproduit exactement l'usage du produit
(ajuster sur le passé, décrire l'avenir) sans look-ahead. Les scores choisis (couverture, PIT, CRPS, Brier) évaluent
une **distribution**, pas une prévision ponctuelle, ce qui correspond à l'objectif de « décrire l'incertitude ». Les
deux repères répondent à la question du produit : un modèle fait-il mieux que l'historique brut, et mieux que
« 2022 seulement » ?

**Quelles limites ?**
- Peu d'observations indépendantes (CAD77 : 7 à 5 ans, 3 à 10 ans) : les IC des métriques sont larges, et à 10 ans
  eux-mêmes peu fiables.
- La période de test CAD77 est dominée par la baisse des taux. Un « bon » modèle sur 1990-2026 peut être mauvais
  dans un autre régime de taux (c'est le cas de `sbb_ca` en 1965-1981).
- Les mélanges sont corrélés entre eux (le bootstrap les rééchantillonne ensemble, mais la moyenne sur les mélanges
  n'est pas un échantillon plus grand).
- 4 000 trajectoires au lieu de 10⁵, et pas de bootstrap externe : les IC de paramètres du produit ne sont pas
  validés.
- Look-ahead de millésime (séries révisées ou reconstruites), biais du survivant, indices sans frais.
- Base nominale seulement ; or et crypto non testés.

**Qu'est-ce qui changerait la réponse ?**
- Une période de test avec des taux en hausse au Canada : elle pénaliserait `sbb_ca` et favoriserait `sbb`.
- Un indice obligataire de durée plus courte, ou des rendements de fin de mois au lieu de moyennes mensuelles de
  taux : le risque obligataire serait mieux mesuré.
- Un ancrage des taux qui modélise leur trajectoire (et non une simple mise à l'échelle de la moyenne).
- Des origines mensuelles (plus de points, mais pas plus de fenêtres indépendantes).
- Le run `full` avec 10⁵ trajectoires et le bootstrap externe, pour valider les IC de paramètres.
- Retirer les données d'avant 1953 en USD.

## Fichiers

Dossier `analyse/scenarios-validation/` (hors git) :

| fichier | contenu |
|---|---|
| `scores.csv.gz` | une ligne par famille × modèle × origine × mélange × H |
| `per_mix.csv`, `pooled.csv` | résumés par mélange et agrégés, avec IC |
| `reliability.csv` | tableaux de fiabilité des probabilités |
| `pit_hist.csv` | histogrammes PIT |
| `ks_summary.csv` | rejets du test KS |
| `fits.csv` | longueurs de bloc, K et facteur d'ancrage par origine |
| `checks/` | contrôles ciblés : look-ahead, hausse des taux, 2021-2023, HMM, fenêtres historiques, monotonie, doublons |
| `tables.md` | tous les tableaux générés |
| `manifest.json` | configuration, graine, empreintes, durées |
| `models_validation.json` | texte proposé pour `manifest.models[].validation` |

Une copie de ce rapport se trouve dans `app/agents/src/alphaforge/scenarios/VALIDATION.md`.
