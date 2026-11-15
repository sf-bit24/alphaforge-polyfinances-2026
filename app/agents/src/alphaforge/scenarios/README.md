# Scénarios probabilistes de portefeuille (volet B)

> **Simulation uniquement. Modèle, pas prévision.** Ces distributions décrivent ce que *ce modèle*, ajusté sur
> *cette fenêtre historique*, juge plausible. Elles ne prédisent pas les rendements et ne sont pas un conseil
> financier personnalisé. Chaque chiffre est accompagné de son `model_id`, de sa famille de données, de son
> intervalle à 90 %, de `data_sha256` et de `code_sha`.

Le volet B remplace le contrôle « 2022 seulement » par une **distribution des résultats** : pour un mélange
d'actifs et un horizon, la probabilité de perdre plus de x %, le p10 du patrimoine final, la distribution de la perte
maximale, la CVaR 12 mois, chacun avec un intervalle de confiance issu de l'incertitude des paramètres.

## Arborescence

| fichier | rôle | dépendances |
|---|---|---|
| `schema.py` | schéma v0.2 de la table, `mix_id`, mélange le plus proche (L1), validation | bibliothèque standard |
| `grid.py` | grille de mélanges (multiples de 5 %) et ancres | bibliothèque standard |
| `data.py` | chargement du build long, pools par famille, ancrage du niveau des taux | numpy, pandas, pyarrow |
| `bootstrap.py` | bootstrap stationnaire vectorisé, longueur de bloc de Politis-White | numpy |
| `hmm.py` | HMM gaussien minimal (EM de Baum-Welch, BIC, chaîne simulée) | numpy |
| `models.py` | générateurs `sbb`, `iid`, `hmm_rs` (+ variantes `_ca`) ; `fit(pool, model_id, fitted_through)` | numpy |
| `engine.py` | simulation des portefeuilles, métriques, bootstrap externe, repères historiques | numpy |
| `job.py` | point d'entrée du job (local ou SageMaker Processing) | numpy, pandas, pyarrow, pyyaml |
| `configs/small.yaml`, `configs/full.yaml` | configurations livrées | |
| `requirements-job.txt` | dépendances épinglées pour l'image SageMaker (Python 3.12, avec `alphaforge.finance.backtest.build_data`) | |

Les fichiers `tool*.py` et `PROPOSAL_PROB_LOSS.md` appartiennent au volet E (outil Strands) ; ils ne lisent que
`schema.py` et les sorties compactes. Le runtime AgentCore n'a besoin d'aucune dépendance de ce volet.

## Lancer

```sh
cd app/agents
# Données longues (une fois ; sources publiques, réseau) : parquets dans alphaforge/data/long/, non versionnés.
# ALPHAFORGE_BT_DATA=<dossier> pour les écrire ailleurs.
uv run --group finance --group backtest-data python -I -m alphaforge.finance.backtest.build_data
uv sync --group scenarios                       # numpy, pandas, pyarrow (groupe optionnel, hors paquet AgentCore)
uv run --group scenarios python -m alphaforge.scenarios.job \
    --config small \
    --input src/alphaforge/data/long \
    --output /tmp/scenarios-small               # run_id du manifeste : --run-id, sinon le nom du dossier
uv run --group scenarios pytest tests/scenarios  # données synthétiques, sans réseau ni AWS
```

Options : `--config` (`small`, `full` ou un chemin YAML/JSON), `--seed`, `--fitted-through YYYY-MM`,
`--workers N` (une tâche = un pool × un modèle ; résultat identique quel que soit N, vérifié une fois à la main par
comparaison octet à octet de la table sur la configuration `small`), `--run-id`. Sous SageMaker Processing, `run.sh`
reconstruit les données dans `ALPHAFORGE_BT_DATA` (volume du job) et passe `--input $ALPHAFORGE_BT_DATA` ;
`--output` vaut `/opt/ml/processing/output`; le job ne fait aucun appel AWS.
Variables lues : `ALPHAFORGE_RELEASE` (devient `code_sha` s'il est défini et différent de `dev`, sinon
`code_sha` = empreinte sha256 des modules du job et des configurations), `ALPHAFORGE_RUN_ID` (`run_id` du
manifeste si `--run-id` manque ; à défaut, le nom du dossier de sortie) et `ALPHAFORGE_STARTER_DIR` (recopié dans
le manifeste).

### Entrée

Le dossier des données longues produit par `alphaforge.finance.backtest.build_data` (`alphaforge/data/long/` ou
`ALPHAFORGE_BT_DATA`, lecture seule) :
`monthly_returns.parquet` (format long `date, asset_id, return_usd, return_cad, source, flag`),
`inflation_monthly.parquet`, `data_version.json`. `data_sha256` est celui de `data_version.json` ; il change à chaque
retéléchargement (Yahoo recalcule `adj_close`) et il est recopié dans chaque ligne et dans le manifeste. Aucune
donnée n'est versionnée ici (licences).

### Sorties (`--output`)

| chemin | contenu |
|---|---|
| `table/scenarios.parquet` | table longue complète, schéma v0.2 (seul fichier du dossier : emplacement de la table Glue/Athena) |
| `runtime/scenarios_runtime.json` | sous-ensemble compact pour l'outil : `tables["<model_id>\|<famille>[+CRYPTO]"].mixes[mix][base][H][métrique] = [value, ci_lo, ci_hi]` |
| `runtime/scenarios_runtime.csv` | même sous-ensemble, colonnes de la table ; déclaré par `manifest["table"] = {file, format, sha256}` |
| `historical_reference.csv` | repères historiques non simulés : 2022 seul, pire 12 mois, perte max. de la fenêtre, pire rendement annualisé sur H ans glissants |
| `sensitivity_block_length.csv` | sensibilité du bootstrap stationnaire à la longueur moyenne de bloc (1 à 48 mois) |
| `fits.json` | détail des ajustements : longueurs de bloc (par série), BIC par K, matrices de transition, volatilité par régime, ancrage |
| `manifest.json` | configuration, graine, `data_sha256`, `code_sha`, `package_sha`, `git_sha`, sha256 de chaque sortie, lignes, durées, versions |

## Données : familles, blocs et traitement

| famille | devise | fenêtre (build 008f122d5da4f8f7) | blocs → série du build long |
|---|---|---|---|
| `CAD77` | CAD | 1977-01 → 2026-09 (597 mois) | CA_EQ → `CA_EQ`, US_MKT → `US_MKT`, BONDS → `CA_GOV_10Y`, CASH → `CA_TBILL`, GOLD → `GOLD` |
| `CAD77+CRYPTO` | CAD | 2014-10 → 2026-09 (144 mois) | les mêmes + CRYPTO → `BTC-USD` ; **toutes les lignes `hypothese=true`** |
| `CAD71` | CAD | 1971-02 → 2026-09 (668 mois) | US_MKT, BONDS → `CA_GOV_10Y`, CASH → `CA_TBILL` |
| `USD1926` | USD | 1926-07 → 2026-09 (1203 mois) | US_MKT, BONDS → `UST_10Y`, CASH → `UST_TBILL` |

Rendements totaux mensuels en devise de l'investisseur, **non couverts** (`return_cad` ou `return_usd` du build).
Inflation : `infl_ca` (CAD) ou `infl_us` (USD), même mois que les rendements.

Choix et raisons :
- **BONDS** : obligation synthétique à maturité constante de 10 ans (État canadien pour CAD, Trésor US pour USD),
  la seule série obligataire qui remonte avant 1977 dans chaque devise. `CA_GOV_10Y` est construite sur des
  moyennes mensuelles de taux (flag `monthly_avg_yield` sur les 597 mois de CAD77) : volatilité lissée, et durée plus
  longue qu'un indice universel comme XBB.TO (corrélation 0,5843 avec XBB.TO selon SOURCES.md du build long).
  `UST_10Y` avant 1953 vient du taux long de Shiller (321 mois flaggés `shiller_long_rate`).
- **CASH** : `CA_TBILL` est un proxy interbancaire à 3 mois (flag `proxy_interbank_rate`), pas un indice investissable.
- **CAD71** n'a ni CA_EQ (Ken French Canada commence en 1977-01) ni GOLD ; **USD1926** n'a pas GOLD (série annuelle
  répétée avant 1960, non investissable aux É.-U. de 1933 à 1974). Les mélanges de ces familles n'ont donc que
  US_MKT, BONDS et CASH. CAD77 est la famille de référence pour un investisseur canadien.
- **CRYPTO** (BTC-USD, 144 mois) forme un pool séparé : toute la fenêtre est réduite à 2014-10 → 2026-09 pour garder les
  corrélations du même mois. Douze ans d'un actif très jeune ne décrivent pas sa distribution de long terme : ces
  chiffres sont des **HYPOTHESE** (`hypothese=true`), à ne jamais présenter comme des faits.

Mois manquants et drapeaux : la fenêtre d'un pool est l'intersection des historiques de ses blocs ; un mois manquant
**à l'intérieur** de la fenêtre est une erreur (aucun comblement ni forward-fill ; aucun cas dans le build de
référence, testé par `test_interior_gap_is_an_error`). Les drapeaux de qualité sont conservés et comptés par bloc
(`manifest.pools[].flag_counts`), par exemple 9 mois `extended_with_XIU.TO` pour CA_EQ dans CAD77.

## Méthodes et raisons

Les trois générateurs tirent des **mois historiques entiers** (toutes les colonnes du même mois) : la corrélation
entre actifs d'un même mois est donc celle de l'histoire, sans hypothèse de loi normale.

1. **`sbb` : bootstrap stationnaire** (Politis et Romano, 1994). Blocs de longueur géométrique de moyenne L,
   panneau circulaire. L est choisi automatiquement par la règle de Politis et White (2004, correction de Patton,
   Politis et White, 2009), appliquée à chaque série risquée **en excès du cash** et à son carré (pour garder les
   grappes de volatilité), puis on prend le maximum, borné à [1, 24] mois. L'excès du cash rend L indépendant du
   niveau des taux (donc de l'ancrage `_ca`). Le cash est exclu du calcul : sa persistance donnerait L ≈ 40 mois.
   La borne de 24 mois est une hypothèse (au-delà, une trajectoire de 30 ans n'enchaîne qu'une quinzaine de blocs) ;
   elle est atteinte pour CAD77, CAD71 et USD1926 (valeurs brutes et par série dans `fits.json`), pas pour
   CAD77+CRYPTO. La sensibilité à L ∈ {1, 3, 6, 12, 24, 48} est écrite dans `sensitivity_block_length.csv`.
2. **`iid` : mois indépendants** (L = 1). Référence naïve : ce que donnerait l'histoire sans dépendance temporelle.
3. **`hmm_rs` : régimes cachés, semi-paramétrique.** HMM gaussien à covariances pleines sur les rendements risqués
   en excès du cash, standardisés ; K ∈ {1, 2, 3} choisi par **BIC** (plusieurs départs, graine fixée). Chaque K a
   son propre générateur aléatoire (`SeedSequence(graine, spawn_key=(K,))`, graine tirée une fois du générateur de
   l'ajustement) : les départs de K = 2 ou 3 ne dépendent plus des tirages faits pour K = 1, ni de la liste des
   candidats (changement après la validation C ; il modifie les ajustements HMM par rapport au run e74ab820c9b5).
   On simule la chaîne de régimes (départ dans la loi stationnaire par défaut ; `hmm_rs_fl` démarre dans le régime
   filtré du dernier mois de la fenêtre), puis, pour chaque
   mois simulé dans le régime k, on tire un mois historique avec une probabilité proportionnelle à sa probabilité
   lissée d'appartenir à k. Les gaussiennes ne servent qu'à classer les mois ; les rendements simulés restent des mois
   observés. Les états sont ordonnés par variance croissante (état 0 = le plus calme).
4. **Variantes `_ca` (ancrage du niveau des taux).** La fenêtre 1977-2026 contient des taux courts bien plus élevés
   qu'aujourd'hui (CA_TBILL : 5,31 %/an en moyenne sur 1977-01 → 2026-09, contre 2,26 %/an sur les 12 derniers mois,
   `fits.json` du run de référence). Sans ajustement, le modèle suppose que ces taux reviendront en moyenne. La
   variante `_ca` multiplie le cash de chaque mois par `s = moyenne(12 derniers mois) / moyenne(fenêtre)` et ajoute
   `(s − 1)·cash_t` aux autres blocs : les rendements **en excès du cash** de chaque mois sont inchangés, seul le
   niveau des taux change. L'inflation est mise à l'échelle de la même manière. C'est une hypothèse simple et
   explicite, pas une prévision des taux. L'effet dépend du signe : l'ancrage n'augmente le risque simulé (des
   obligations surtout) que si les taux récents sont **sous** la moyenne de la fenêtre (s < 1, cas de CAD77
   aujourd'hui) ; si s > 1 (USD1926 aujourd'hui, ou les années 1965-1981), il le **réduit**.
5. **Incertitude des paramètres** (intervalles `ci_lo`/`ci_hi`, 90 %). Bootstrap externe fondé sur le modèle :
   B pseudo-historiques de même longueur sont tirés du modèle ajusté, le modèle est réajusté sur chacun (longueur de
   bloc recalculée ; HMM à K fixé, départ chaud), puis simulé avec `n_paths_boot` trajectoires ; l'intervalle est
   formé des quantiles 5 % et 95 % des B valeurs. Il mesure l'incertitude d'**estimation dans un modèle donné**, pas
   l'incertitude sur le choix du modèle (comparer les `model_id` pour celle-ci). La valeur ponctuelle vient de
   l'ajustement sur l'histoire réelle : rien ne garantit qu'elle tombe dans l'intervalle (l'outil compte ces cas).
   Raisons : (a) chaque pseudo-historique est lui-même tiré du modèle, donc plus « mélangé » que l'histoire réelle
   (jointures de blocs, régimes réestimés), ce qui décale la distribution des réajustements par rapport à
   l'ajustement d'origine (biais du bootstrap) ; (b) pour les probabilités proches de 0 ou de 1 et les quantiles
   extrêmes, la distribution des réplications est très asymétrique ou tronquée à 0 ; (c) l'estimation ponctuelle
   (`n_paths`) et les réplications (`n_paths_boot`) n'ont pas le même bruit Monte Carlo. L'intervalle inclut ce
   bruit de `n_paths_boot` trajectoires (prudent).

### Simulation et métriques

Rebalancement **mensuel** vers les poids cibles, sans frais, impôts ni flux : le rendement mensuel du portefeuille
vaut alors exactement `w · r_t`. Chaque trajectoire dure 360 mois ; l'horizon H lit ses 12·H premiers mois (métriques
cohérentes entre horizons). Base `nominal` et base `real` (déflatée par l'IPC du même mois historique, tiré avec
les rendements : l'inflation garde sa corrélation avec les actifs).

Unités : probabilités, rendements et pertes en **fraction** (0,12 = 12 %) ; `wealth_p10` en **multiple du capital
initial** (richesse finale pour 1 placé).

| métrique | définition (fraction, sauf mention) |
|---|---|
| `ret_ann_p05`, `_p10`, `_p50`, `_p90` | quantiles du rendement annualisé sur H ans : `W_H^(1/H) − 1` |
| `wealth_p10` | p10 du patrimoine final pour 1 placé |
| `mdd_p50`, `mdd_p90` | médiane et p90 de la perte maximale (depuis un sommet, capital initial compris) sur H ans |
| `cvar95_12m` | moyenne des 5 % pires années civiles simulées (années 1..H de toutes les trajectoires), en **perte positive** ; une valeur négative veut dire que même ces années gagnent |
| `p_loss_gt_05` … `p_loss_gt_50` (pas de 5) | P(perte cumulée à l'horizon > x %), soit P(W_H < 1 − x) |
| `p_mdd_gt_10` … `p_mdd_gt_50` (pas de 5) | P(perte maximale sur H ans > x %) |

## Schéma v0.2 de la table

Une ligne par (`model_id`, `family`, `mix_id`, `horizon_years`, `basis`, `metric`). Changements par rapport à la v0.1
du plan : ajout de `basis` (`nominal` | `real`), `schema_version`, `currency`, `n_boot`, `window_start`,
`n_hist_months` et `hypothese` ; seuils `p_loss_gt_*` et `p_mdd_gt_*` explicités ; `model_id` étendu à `iid` et aux
variantes `_ca`. `family` reste `CAD77`, `CAD71` ou `USD1926` : les lignes du pool crypto ont `family = CAD77`,
`hypothese = true`, `window_start = 2014-10` et un `mix_id` qui finit par `-crNN`.

| colonne | type parquet | contenu |
|---|---|---|
| `schema_version` | string | `0.2` |
| `model_id` | string | `sbb`, `iid`, `hmm_rs`, `sbb_ca`, `iid_ca`, `hmm_rs_ca` |
| `family` | string | `CAD77`, `CAD71`, `USD1926` |
| `currency` | string | `CAD` ou `USD` |
| `mix_id` | string | poids en % multiples de 5 : `caNN-usNN-bdNN-csNN-gdNN[-crNN]` (100 s'écrit `100`) |
| `horizon_years` | int32 | 1, 3, 5, 10, 15, 20, 30 |
| `basis` | string | `nominal` ou `real` |
| `metric` | string | voir le tableau des métriques |
| `value`, `ci_lo`, `ci_hi` | float64 | estimation ponctuelle et intervalle à 90 % (bootstrap externe) |
| `n_paths`, `n_boot` | int32 | trajectoires de l'estimation ponctuelle, réplications du bootstrap externe |
| `seed` | int64 | graine du run |
| `fitted_through` | string | dernier mois utilisé (`YYYY-MM`) |
| `window_start`, `n_hist_months` | string, int32 | premier mois et longueur de la fenêtre historique |
| `hypothese` | bool | vrai pour le pool CRYPTO |
| `data_sha256`, `code_sha` | string | identifiants des données et du code |

L'outil (volet E) choisit le mélange de la grille le plus proche (`schema.nearest_mix`, distance L1 affichée) et
n'extrapole jamais hors de la grille. Grilles : `small` = 26 mélanges CAD77, 13 CAD77+CRYPTO, 13 CAD71, 13 USD1926 ;
`full` = 453 CAD77 (pas de 10 %, CA_EQ ≤ 50 %, GOLD ≤ 10 %, plus les ancres à 5 %), 151 CAD77+CRYPTO (CRYPTO 5 ou
10 %), 231 CAD71 et 231 USD1926 (pas de 5 %).

## Validation hors échantillon (crochet pour le volet C)

```python
from alphaforge.scenarios.data import load_inputs, build_pool
from alphaforge.scenarios.models import fit, rng_for
from alphaforge.scenarios.engine import simulate_metrics, hist_log_returns, weight_matrix

pool = build_pool(load_inputs(processed_dir), "CAD77")
fitted = fit(pool, "sbb", fitted_through="1999-12", seed=1)  # aucun mois postérieur n'est lu
idx = fitted.simulate_indices(10_000, 60, rng_for(1, "wf", "1999-12"))  # indices dans fitted.pool (≤ 1999-12)
metrics = simulate_metrics(fitted, ["ca35-us35-bd30-cs00-gd00"], [5], 10_000, rng_for(1, "m"))
```

`fit` tronque le pool **avant** tout calcul (longueur de bloc, standardisation, EM, choix de K, ancrage `_ca`).
`test_no_look_ahead` remplace tous les mois postérieurs à 2000-12 par du bruit et vérifie que l'ajustement, les
indices tirés et les métriques sont identiques, et qu'aucun indice ne dépasse la fenêtre. Le job accepte aussi
`--fitted-through`.

## Validation hors échantillon (volet C) et affichage

Rapport complet : [VALIDATION.md](../../../../../../../analyse/scenarios-validation/VALIDATION.md) (hors git, dans le dossier local `analyse/scenarios-validation/` de l'espace de travail ; walk-forward, couverture p10/p90, PIT, scores). Résumé par modèle :
`validation/models_validation.json` (versionné ici, recopié dans `manifest.json` → `models[].validation`).
Conséquences dans le manifeste :

- `default_model: sbb_ca` ; `models[].display` : `sbb_ca` → `default`, `sbb` → `compare`, `hmm_rs`, `hmm_rs_ca`,
  `hmm_rs_fl` → `sensitivity_only`, `iid`, `iid_ca` → `hidden` ;
- `validated_horizons: [1, 3, 5, 10]`, avec `validation_note` : « 5 et 10 ans : mise en garde forte ; 15–30 ans,
  base réelle, or et crypto : non validés ». Les lignes 15-30 ans restent dans la table mais ne sont pas validées.

## Hypothèses et limites

- **Modèle, pas prévision.** Les distributions supposent que les mois futurs ressemblent aux mois de la fenêtre
  (stationnarité). Les intervalles ne couvrent pas les ruptures (nouveau régime de taux, de change, de fiscalité).
- **Niveau des taux.** Sans `_ca`, la fenêtre CAD77 suppose le retour des taux moyens de 1977-2026 ; les obligations
  y profitent aussi de la longue baisse des taux depuis 1981, qui ne peut pas se répéter depuis les niveaux actuels.
  Le pire rendement obligataire annualisé sur 5 ans glissants de la fenêtre (`historical_reference.csv`) est récent ;
  les modèles le reproduisent rarement.
- **Obligations en hausse des taux : sous-estimées par tous les modèles.** La validation hors échantillon (volet C)
  le confirme sur 1965-1981 et 2021-2023 : la perte maximale des obligations réalisée dépasse souvent le p90 des
  modèles, et `sbb_ca` échoue lui aussi quand les taux récents dépassent la moyenne historique. C'est la limite
  principale de ces distributions.
- **Biais du survivant** : l'histoire du marché US (et canadien) est celle de marchés qui ont réussi. Pas de frais,
  d'impôts ni d'écarts acheteur-vendeur ; indices reconstitués a posteriori (voir SOURCES.md du build long).
- **Séries lissées** : obligations sur moyennes mensuelles de taux, or en moyenne mensuelle : volatilité et pertes
  maximales probablement sous-estimées pour BONDS et GOLD.
- **Dépendance longue** : des blocs d'au plus 24 mois ne reproduisent pas des décennies d'inflation élevée
  (années 1970) ; la base `real` sous-estime donc probablement le risque d'inflation persistante.
- **HMM** : sur USD1926, un des régimes retenus a une volatilité obligataire très faible ; sa durée attendue dépend
  de la graine et de `n_init` (de 132 à 823 mois sur 6 essais du volet C : l'EM est instable) ; il correspond surtout à la période d'avant 1953 où BONDS vient du taux long de
  Shiller (série lissée) : un régime « de construction des données » plus qu'un régime de marché. Sur
  CAD77+CRYPTO (144 mois), le BIC choisit K = 1 : `hmm_rs` y revient à `iid`.
- **Crypto** : 144 mois, un seul actif (BTC), une seule ère de marché : `hypothese = true` partout.
- **Change** : non couvert ; un investisseur couvert aurait une autre distribution.

## Taille du calcul

Mesures sur le poste de développement (WSL2, 24 processeurs logiques, 15 Go de RAM) :

- `small` (78 mélanges, 5 modèles, 2 000 trajectoires, 20 réplications × 500), un seul processus : voir le run de
  référence ci-dessous (110 s et 628 Mo de mémoire maximale en un processus pour le run actuel ; 267 s pour un run précédent sur le poste chargé par d'autres calculs). Avec `--workers 8`, la table et le CSV compact sont identiques à ceux du run à un processus.
- Mesure de charge (Python 3.12, `requirements-job.txt`) : pool CAD77, grille `full` (453 mélanges), modèle `sbb`,
  10 000 trajectoires et 5 réplications × 2 000 : simulation ponctuelle 163 s, bootstrap externe 145 s,
  mémoire maximale 2,9 Go.

Extrapolation (calcul, pas une mesure) pour `full` (1 066 mélanges, 5 modèles, 100 000 trajectoires,
50 réplications × 2 000) : le coût est proportionnel à mélanges × trajectoires, soit environ 3,6e-5 s par
(mélange × trajectoire, deux bases) et par cœur. La tâche la plus longue (CAD77 × un modèle) demande alors
environ 1 630 s + 1 450 s ≈ 50 min ; l'ensemble environ 10 h-cœur. Mémoire : environ 3 à 4 Go par processus,
plus la table finale (environ 2 millions de lignes) dans le processus principal. `configs/full.yaml` fixe donc
`workers: 8` pour l'instance par défaut `ml.m5.4xlarge` (16 vCPU, 64 Gio : 8 × 4 Go + le processus principal
laissent de la marge), soit environ 3 à 4 h (limite du job : 8 h). `workers: 16` seulement sur `ml.m5.8xlarge`
(32 vCPU, 128 Gio, variable `scenarios_instance_type`), en environ 1 h 30 à 2 h. Si le quota SageMaker manque, lancer `full` avec moins de trajectoires (`n_paths: 20000`) et le déclarer.

## Premiers résultats (run de référence `small`)

Run de référence : configuration `small`, graine 20261114, `data_sha256` 008f122d5da4f8f7, `code_sha` 5dd98773b8b4, 122850 lignes, 106 s (un processus). Valeurs en %, intervalle à 90 % entre crochets, base nominale, famille CAD77. Avec 2 000 trajectoires et 20 réplications × 500, les intervalles sont larges et bruités : chiffres indicatifs, à remplacer par ceux du run `full`.

**sbb**

| mélange (actions/obligations) | H | P(perte > 10 %) | P(perte max. > 20 %) | perte max. p90 | rend. annualisé p05 |
|---|---|---|---|---|---|
| 70/30 `ca35-us35-bd30-cs00-gd00` | 5 | 0.5 [0.0 ; 2.6] | 14.1 [2.9 ; 27.8] | 23.8 [15.5 ; 25.4] | 2.6 [0.6 ; 6.0] |
| 70/30 `ca35-us35-bd30-cs00-gd00` | 15 | 0.0 [0.0 ; 0.2] | 40.5 [11.0 ; 67.6] | 25.9 [20.3 ; 32.6] | 6.1 [4.2 ; 8.4] |
| 40/60 `ca20-us20-bd60-cs00-gd00` | 5 | 0.1 [0.0 ; 0.2] | 0.2 [0.0 ; 1.8] | 13.5 [11.0 ; 14.8] | 3.5 [2.0 ; 5.1] |
| 40/60 `ca20-us20-bd60-cs00-gd00` | 15 | 0.0 [0.0 ; 0.0] | 0.9 [0.0 ; 6.9] | 14.7 [12.2 ; 18.3] | 5.6 [4.3 ; 7.1] |
| 0/100 `ca00-us00-bd100-cs00-gd00` | 5 | 1.1 [0.0 ; 2.4] | 4.3 [0.0 ; 5.6] | 14.8 [10.3 ; 17.3] | -0.2 [-0.7 ; 3.2] |
| 0/100 `ca00-us00-bd100-cs00-gd00` | 15 | 0.1 [0.0 ; 0.2] | 15.0 [0.2 ; 18.1] | 21.3 [12.2 ; 22.8] | 2.6 [1.6 ; 5.5] |

**sbb_ca**

| mélange (actions/obligations) | H | P(perte > 10 %) | P(perte max. > 20 %) | perte max. p90 | rend. annualisé p05 |
|---|---|---|---|---|---|
| 70/30 `ca35-us35-bd30-cs00-gd00` | 5 | 2.0 [0.8 ; 9.8] | 31.1 [17.1 ; 43.8] | 26.9 [23.0 ; 28.8] | -0.0 [-3.6 ; 3.0] |
| 70/30 `ca35-us35-bd30-cs00-gd00` | 15 | 0.2 [0.0 ; 3.0] | 70.4 [45.5 ; 83.5] | 30.4 [26.9 ; 40.8] | 3.3 [0.3 ; 5.6] |
| 40/60 `ca20-us20-bd60-cs00-gd00` | 5 | 0.9 [0.0 ; 7.0] | 2.9 [0.8 ; 14.0] | 17.4 [14.2 ; 21.2] | 0.7 [-3.0 ; 2.5] |
| 40/60 `ca20-us20-bd60-cs00-gd00` | 15 | 0.1 [0.0 ; 2.1] | 9.3 [3.9 ; 44.5] | 19.7 [16.9 ; 28.3] | 3.1 [0.4 ; 4.4] |
| 0/100 `ca00-us00-bd100-cs00-gd00` | 5 | 6.5 [1.0 ; 15.7] | 13.5 [2.1 ; 25.7] | 21.6 [15.3 ; 25.5] | -2.5 [-4.7 ; -0.3] |
| 0/100 `ca00-us00-bd100-cs00-gd00` | 15 | 2.1 [0.0 ; 15.8] | 41.6 [7.5 ; 65.0] | 27.9 [19.0 ; 36.3] | 0.1 [-1.9 ; 2.1] |

**hmm_rs**

| mélange (actions/obligations) | H | P(perte > 10 %) | P(perte max. > 20 %) | perte max. p90 | rend. annualisé p05 |
|---|---|---|---|---|---|
| 70/30 `ca35-us35-bd30-cs00-gd00` | 5 | 0.5 [0.0 ; 4.2] | 11.8 [4.3 ; 24.7] | 21.1 [16.4 ; 29.1] | 2.3 [-1.3 ; 4.8] |
| 70/30 `ca35-us35-bd30-cs00-gd00` | 15 | 0.1 [0.0 ; 0.4] | 32.4 [16.1 ; 61.9] | 27.6 [22.5 ; 41.2] | 6.1 [2.7 ; 8.4] |
| 40/60 `ca20-us20-bd60-cs00-gd00` | 5 | 0.0 [0.0 ; 1.1] | 1.3 [0.2 ; 8.7] | 12.6 [10.4 ; 18.9] | 3.6 [0.7 ; 5.0] |
| 40/60 `ca20-us20-bd60-cs00-gd00` | 15 | 0.0 [0.0 ; 0.0] | 4.9 [0.6 ; 27.5] | 17.2 [12.9 ; 27.5] | 6.0 [3.9 ; 7.5] |
| 0/100 `ca00-us00-bd100-cs00-gd00` | 5 | 0.1 [0.0 ; 0.6] | 0.2 [0.0 ; 2.0] | 11.2 [10.2 ; 13.5] | 2.0 [0.6 ; 3.3] |
| 0/100 `ca00-us00-bd100-cs00-gd00` | 15 | 0.0 [0.0 ; 0.0] | 1.1 [0.2 ; 5.3] | 14.5 [13.5 ; 17.9] | 4.1 [2.7 ; 5.0] |

Repères historiques non simulés (CAD77, nominal, `historical_reference.csv`) :

| mélange | 2022 seul | perte max. 2022 | pire 12 mois | pire 5 ans annualisé | perte max. 1977-2026 |
|---|---|---|---|---|---|
| 70/30 | -9.9 | 15.0 | -20.6 (fin 2009-02) | 0.2 | 25.4 |
| 40/60 | -9.9 | 14.7 | -11.6 (fin 2022-09) | 2.8 | 14.7 |
| 0/100 | -10.2 | 14.3 | -13.9 (fin 2022-06) | -2.8 | 21.9 |

Lecture : « 2022 seulement » donne presque la même perte pour 70/30 et 40/60 (environ −10 % chacun en CAD) ; les
distributions les séparent nettement (les horizons de 15 ans ne sont pas validés hors échantillon). Dans CAD77,
l'ancrage des taux (`sbb_ca`) augmente le risque des mélanges obligataires parce que les taux récents sont sous la
moyenne de la fenêtre (s < 1) ; ce ne serait pas le cas avec des taux récents au-dessus. Après la validation C,
`default_model` vaut `sbb_ca` (voir la section « Validation hors échantillon »).

## Limites connues (non corrigées)

- `status = FAIT` des `Fact` désigne un nombre calculé par le modèle (sortie de simulation), pas un fait observé :
  décision d'équipe, chaque explication rappelle « c'est un modèle, pas une prévision ».
- Empreinte des données : la validation C porte sur le build `data_sha256` 008f122d5da4f8f7, mais le job SageMaker
  reconstruit les données à chaque run (nouveau `data_sha256`, Yahoo recalcule `adj_close`) ; l'écart n'est ni
  enregistré dans le manifeste ni signalé par l'outil.
- Deux exécutions concurrentes peuvent faire revenir `scenarios/latest.json` sur le run le plus ancien (le dernier
  à finir écrit le pointeur) ; lancer les runs l'un après l'autre.
- Aucun test automatique ne vérifie que la table est identique quel que soit `--workers` (vérification manuelle).
- Avec `small` (20 réplications × 500), l'IC à 90 % se réduit presque au min et au max des réplications, et
  `integrity["ci_not_enclosing"]` est un total sur toute la table, pas par point de la grille.
- Requêtes Athena : la clé KMS du bucket ne délègue pas à IAM ; seul un principal listé dans
  `kms_admin_principal_arns` (ou un rôle de `local.s3_kms_user_role_arns`) peut lire la table et les résultats.
