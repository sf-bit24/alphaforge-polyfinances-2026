# research/backtest : données longues (1926-2026) et moteur de backtest mensuel

Ce dossier est la couche de données et le moteur de backtest partagés d'AlphaForge AI.
Les agents « profil » (Amira, Mateo, Robert) s'en servent pour comparer des stratégies d'allocation
sur des fenêtres historiques adaptées à l'horizon de chaque profil.

> **Simulation uniquement.** Rien ici n'est un conseil financier. Les backtests décrivent le passé
> et ne prédisent rien. Les lignes `ORACLE` (`hindsight=True`) utilisent le futur : elles sont
> **non investissables** et ne servent qu'à la rétro-ingénierie.

Principe : *le code calcule, le modèle explique, chaque chiffre cite sa source.* Chaque exécution
écrit une trace JSON (paramètres, actifs, période, hash des données et du moteur, graine, résultats).

## Installation (uv, Python 3.12)
```bash
cd research/backtest
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e .      # numpy pandas scipy pyarrow pyyaml openpyxl xlrd yfinance pytest
```
L'installation en mode éditable permet `python -I -m engine...`. Avec `-I` (mode isolé), Python
n'ajoute ni le répertoire courant ni celui du script au `sys.path`.

## Reconstruire les données
```bash
.venv/bin/python -I data/build_data.py            # télécharge ce qui manque dans data/raw/ puis reconstruit
.venv/bin/python -I data/build_data.py --refresh  # retélécharge tout (from scratch)
.venv/bin/python -I data/build_data.py --offline  # reconstruit depuis data/raw/ sans réseau
```
- Les fichiers bruts sont des données **non fiables** : un dossier par source dans `data/raw/<source>/`
  avec un `manifest.json` (url, date UTC, sha256). Ils ne sont jamais exécutés et ne sont pas versionnés.
- Le starter officiel est lu en place dans le dépôt, `app/agents/src/alphaforge/data/starter/`
  (identique octet pour octet à la copie des organisateurs ; variable `ALPHAFORGE_STARTER_DIR` pour en lire une autre).
  Il n'est jamais copié.
- Sorties dans `data/processed/` :

| fichier | contenu |
|---|---|
| `monthly_returns.parquet` | format long : `date, asset_id, return_usd, return_cad, source, flag` |
| `assets.csv` | `asset_id, name, asset_class, currency, start, end, n_months, tags, exposures, universe_tickers, proxy_for_ticker, maturity_years, notes` |
| `inflation_monthly.parquet` | `infl_us` (CPI-U NSA), `infl_ca` (IPC Canada), `flag_us` |
| `fx_monthly.parquet` | USDCAD fin de mois + source |
| `lookthrough_us_mkt.parquet` | part de chaque industrie KF dans la capitalisation US (look-through) |
| `qa_overlap.csv`, `data_version.json` | contrôles de concordance, hash des données (`data_sha256`), manifestes bruts |

Sources, traitements, hypothèses, limites et conditions d'utilisation : **[data/SOURCES.md](data/SOURCES.md)**.

### Ce qui est versionné dans git (et pourquoi)
| Versionné | Non versionné (reconstruire) |
|---|---|
| `engine/`, `tests/`, `profiles/`, `analysis/`, `reports/`, `data/build_data.py`, `data/SOURCES.md` | `data/raw/` (bruts téléchargés) |
| `data/processed/assets.csv`, `coverage.csv`, `qa_overlap.csv`, `data_version.json` (catalogue et métadonnées) | `data/processed/*.parquet` : une partie dérive de Yahoo/yfinance (redistribution interdite) et de séries Moody's / OCDE (copyright) → `python -I data/build_data.py` |
| `results/*_analysis/` (synthèses par analyse, citées par les rapports) | `results/<run>/` (traces brutes, ~650 Mo, reproductibles avec `engine.run`) ; `analysis/*/data_ext/` (copies locales dérivées) ; `.venv/` |

Sans les parquets, `pytest` saute les tests qui lisent les données (avec la raison) et exécute les autres.
Les rapports citent des traces `results/<run>/…` : pour les vérifier, reconstruire les données puis relancer
la commande indiquée dans le rapport (les hash `data_sha256` / `engine_sha256` de la trace permettent la comparaison).

## Lancer un profil
```bash
.venv/bin/python -I -m engine.run --profile example                               # non chevauchant, horizon du profil
.venv/bin/python -I -m engine.run --profile example --mode rolling --horizon 3 --step 12
.venv/bin/python -I -m engine.run --profile path/to/amira.yaml --start 1975-01 --no-oracle
```
La commande affiche les résultats par fenêtre (stratégies ex-ante + ORACLE), un tableau score × fenêtre,
la sélection robuste, le walk-forward et un résumé. Elle écrit aussi dans `results/<profile id>/` :
- `<stamp>_<mode>_h<N>.json` : trace complète. Chaque chiffre est relié à `data_version.data_sha256`,
  `engine_sha256`, la graine, le profil, la période effective et l'actif limitant ;
- `_windows.csv` (une ligne par fenêtre et par stratégie), `_robust.csv`, `_walkforward.csv`.

Depuis Python (pour les agents) :
```python
from engine.data import load_returns, load_inflation, load_assets
from engine.windows import windows
from engine.profile import load_profile
from engine.run import run_profile
from engine import metrics as M

R = load_returns(["US_MKT", "UST_10Y", "GOLD"], start="1926-07", currency="USD")  # dates communes uniquement
R.attrs["info"]   # période effective, actif limitant (début/fin), fx_fill, avertissements
ws = windows(3, R.index.min(), R.index.max(), mode="non_overlapping", index=R.index)
res = run_profile(load_profile("example"), mode="rolling", horizon=10)
res["rows"], res["robust"], res["walk_forward"], res["trace_path"]
```

## Moteur (`engine/`)
| module | rôle |
|---|---|
| `data.py` | `load_returns(assets, start, end, currency="CAD"/"USD", fx_fill="none"/"flat")`, `load_inflation`, `load_assets`, `exposure_vector` (look-through) |
| `windows.py` | `windows(horizon_years, start, end, mode="non_overlapping"/"rolling", step_months=12)` ; par exemple, 3 ans sur 1926-07..2026-09 en non chevauchant donne 33 fenêtres (testé) |
| `bonds.py` | prix et rendement d'une obligation synthétique au pair à maturité constante (testé sur un cas calculé à la main) |
| `constraints.py` | contraintes linéaires dures (bornes, exclusions, groupes par tag/classe/liste, look-through) ; `project()` = poids admissibles les plus proches (moindres carrés, SLSQP, repli LP) |
| `strategies.py` | stratégies **ex-ante** : `static`, `sixty_forty`, `glidepath`, `risk_parity` (inverse-vol / ERC), `min_variance`, `max_sharpe`, `mean_variance` (μ rétréci, covariance Ledoit-Wolf), `trend_filter` (moyenne mobile 10 mois → cash), `momentum` (relatif top-k + absolu vs cash) |
| `backtest.py` | simulation mensuelle : décision en t avec les données < t, projection sur les contraintes, dérive des poids, rebalancement (mensuel / trimestriel / annuel / bandes / jamais), coûts (bps × Σ\|Δw\|), flux indexés |
| `oracle.py` | ORACLE a posteriori : poids constants (rebalancés chaque mois) qui maximisent l'objectif sous contraintes, avec pénalité sur les limites de risque ; `hindsight=True` |
| `validation.py` | sélection robuste (meilleur 10e centile du score entre fenêtres) et walk-forward (choix fait uniquement sur des fenêtres terminées avant la fenêtre évaluée) |
| `metrics.py` | fonctions pures testées : rendement annualisé nominal/réel, vol, max drawdown, recouvrement, Sharpe, Sortino, Calmar, VaR/CVaR 5 % mensuelles, pire 12 mois, probabilité de manquer l'objectif, richesse finale avec flux, corrélations, turnover |
| `run.py` | CLI + `run_profile()` + trace JSON |

### Schéma de profil (`profiles/<id>.yaml`)
Un exemple complet et commenté se trouve dans [`profiles/example.yaml`](profiles/example.yaml). C'est un profil
générique : **les profils Amira, Mateo et Robert sont à créer par les agents de profil**. Les clés :
- `id`, `description`, `currency` (CAD|USD), `fx_fill` (none|flat), `horizon_years`, `mode`, `step_months`, `period.start/end`
- `universe` (liste d'`asset_id`), `cash_asset` (actif refuge des filtres et taux sans risque du Sharpe)
- `objective.type` ∈ `max_real_return | max_sharpe | max_return_over_cvar | min_shortfall`,
  `target_real_return` ou `target_real_wealth`. Ce sont eux qui alimentent `missed_target` et `shortfall_prob`.
- `constraints` : `default_bounds`, `asset_bounds`, `class_max_weight`, `exclude.{assets,tags,classes}`,
  `groups` (`{name, exposure|tags_any|classes|assets, min, max}`), `exposure_overrides`
- `risk_limits` : `max_vol`, `max_drawdown`, `max_cvar_5`. Ils sont vérifiés par fenêtre et comptés comme
  violations (`n_breaches`), et servent de pénalités pour l'ORACLE.
- `flows` : `initial`, `monthly` (+ cotisation / − retrait en fin de mois), `indexed_to_inflation`
- `rebalancing` : `{frequency, band}` par défaut ; chaque stratégie peut le surcharger
- `costs_bps`, `fallback_weights`, `strategies` (`{name, type, params, rebalancing}`),
  `selection` (`quantile`, `max_breach_rate`, `min_past_windows`), `oracle` (`enabled`, `n_starts`), `seed`

Tags disponibles dans `assets.csv` : `equity, broad_market, sector, tech, tech_platform, tech_heavy,
energy, fossil_fuel, utilities, financials, healthcare, consumer_staples, consumer_discretionary,
industrials, materials, communication, defensive_sector, defensive, cash, cash_like, bond, government,
corporate, investment_grade, credit_risk, long_duration, gold, commodity, crypto, speculative,
esg_screened, canada, cyclical`.

## Proxys et couverture
Aucun ticker réel n'existe en 1926 : la longue histoire repose sur des **proxys par classe d'actifs**.
Le tableau ci-dessous est généré à partir de `data/processed/assets.csv` (build `data_sha256 = 008f122d5da4f8f7`, récupération 2026-11-14).
Les correspondances avec les tickers sont **approximatives** et s'appuient sur la classification (12 industries
SIC de Ken French ≠ GICS).

| asset_id | classe | devise | début | fin | mois | tickers de l'univers correspondants |
|---|---|---|---|---|---|---|
| US_MKT | equity_us | USD | 1926-07 | 2026-09 | 1203 | SPY ; ESGV ; QQQ (partiel) |
| UST_TBILL | cash | USD | 1926-07 | 2026-09 | 1203 | cash ; ZST.TO (approx., CAD) |
| US_IND_NODUR | sector_us | USD | 1926-07 | 2026-09 | 1203 | PG ; ATD.TO (approx.) |
| US_IND_DURBL | sector_us | USD | 1926-07 | 2026-09 | 1203 | TSLA |
| US_IND_MANUF | sector_us | USD | 1926-07 | 2026-09 | 1203 | (aucun) |
| US_IND_ENRGY | sector_us | USD | 1926-07 | 2026-09 | 1203 | XOM ; CNQ.TO ; ENB.TO (gazoduc : SIC 4922 = Utils chez KF) |
| US_IND_CHEMS | sector_us | USD | 1926-07 | 2026-09 | 1203 | (aucun) |
| US_IND_BUSEQ | sector_us | USD | 1926-07 | 2026-09 | 1203 | AAPL ; MSFT ; NVDA ; GOOGL ; CSU.TO ; SHOP.TO ; QQQ (partiel) |
| US_IND_TELCM | sector_us | USD | 1926-07 | 2026-09 | 1203 | (aucun) |
| US_IND_UTILS | sector_us | USD | 1926-07 | 2026-09 | 1203 | FTS.TO ; ENB.TO (partiel) |
| US_IND_SHOPS | sector_us | USD | 1926-07 | 2026-09 | 1203 | AMZN ; ATD.TO |
| US_IND_HLTH | sector_us | USD | 1926-07 | 2026-09 | 1203 | JNJ |
| US_IND_MONEY | sector_us | USD | 1926-07 | 2026-09 | 1203 | JPM ; RY.TO ; TD.TO ; MFC.TO |
| US_IND_OTHER | sector_us | USD | 1926-07 | 2026-09 | 1203 | CNR.TO |
| UST_2Y | bond_synthetic | USD | 1926-08 | 2026-10 | 1203 | AGG (partiel) ; ZST.TO (très approx.) |
| UST_5Y | bond_synthetic | USD | 1926-08 | 2026-10 | 1203 | AGG (approx.) |
| UST_10Y | bond_synthetic | USD | 1926-01 | 2026-10 | 1210 | AGG (partiel) ; TLT (partiel) |
| UST_20Y | bond_synthetic | USD | 1926-01 | 2026-10 | 1210 | TLT |
| CORP_AAA | bond_synthetic | USD | 1926-01 | 2026-10 | 1210 | AGG (poche crédit) |
| CORP_BAA | bond_synthetic | USD | 1926-01 | 2026-10 | 1210 | AGG (poche crédit) |
| GOLD | commodity | USD | 1926-01 | 2026-10 | 1210 | GLD (**non investissable / peu informatif avant 1975**) |
| CA_EQ | equity_ca | CAD | 1977-01 | 2026-10 | 598 | XIU.TO et les 10 actions canadiennes (KF jusqu'en 2025-12, puis XIU.TO) |
| CA_GOV_10Y | bond_synthetic | CAD | 1955-02 | 2026-09 | 860 | XBB.TO (approx.) |
| CA_TBILL | cash | CAD | 1956-02 | 2026-09 | 848 | ZST.TO (approx.) |

Tickers réels : yfinance avant 2021-12, starter officiel ensuite.

| asset_id | classe | devise | début | fin | mois | proxy long |
|---|---|---|---|---|---|---|
| RY.TO | equity_single | CAD | 1995-02 | 2026-10 | 381 | US_IND_MONEY / CA_EQ |
| TD.TO | equity_single | CAD | 1995-02 | 2026-10 | 381 | US_IND_MONEY / CA_EQ |
| MFC.TO | equity_single | CAD | 1999-10 | 2026-10 | 325 | US_IND_MONEY / CA_EQ |
| ENB.TO | equity_single | CAD | 1995-02 | 2026-10 | 381 | US_IND_ENRGY, US_IND_UTILS / CA_EQ |
| CNQ.TO | equity_single | CAD | 1995-02 | 2026-10 | 381 | US_IND_ENRGY / CA_EQ |
| CNR.TO | equity_single | CAD | 1996-12 | 2026-10 | 359 | US_IND_OTHER / CA_EQ |
| FTS.TO | equity_single | CAD | 1995-02 | 2026-10 | 381 | US_IND_UTILS / CA_EQ |
| ATD.TO | equity_single | CAD | 1996-09 | 2026-10 | 362 | US_IND_SHOPS / CA_EQ |
| SHOP.TO | equity_single | CAD | 2015-06 | 2026-10 | 137 | US_IND_BUSEQ / CA_EQ |
| CSU.TO | equity_single | CAD | 2007-11 | 2026-10 | 228 | US_IND_BUSEQ / CA_EQ |
| AAPL | equity_single | USD | 1981-01 | 2026-10 | 550 | US_IND_BUSEQ |
| MSFT | equity_single | USD | 1986-04 | 2026-10 | 487 | US_IND_BUSEQ |
| NVDA | equity_single | USD | 1999-02 | 2026-10 | 333 | US_IND_BUSEQ |
| GOOGL | equity_single | USD | 2004-09 | 2026-10 | 266 | US_IND_BUSEQ |
| AMZN | equity_single | USD | 1997-06 | 2026-10 | 353 | US_IND_SHOPS |
| TSLA | equity_single | USD | 2010-07 | 2026-10 | 196 | US_IND_DURBL |
| JPM | equity_single | USD | 1980-04 | 2026-10 | 559 | US_IND_MONEY |
| JNJ | equity_single | USD | 1962-02 | 2026-10 | 777 | US_IND_HLTH |
| PG | equity_single | USD | 1962-02 | 2026-10 | 777 | US_IND_NODUR |
| XOM | equity_single | USD | 1962-02 | 2026-10 | 777 | US_IND_ENRGY |
| XIU.TO | etf_equity | CAD | 1999-11 | 2026-10 | 324 | CA_EQ |
| SPY | etf_equity | USD | 1993-02 | 2026-10 | 405 | US_MKT |
| QQQ | etf_equity | USD | 1999-04 | 2026-10 | 331 | US_IND_BUSEQ (partiel) ; US_MKT |
| ESGV | etf_equity | USD | 2018-10 | 2026-10 | 97 | US_MKT (sans filtre ESG) |
| XBB.TO | etf_bond | CAD | 2000-12 | 2026-10 | 311 | CA_GOV_10Y |
| ZST.TO | etf_bond | CAD | 2011-03 | 2026-10 | 188 | CA_TBILL |
| AGG | etf_bond | USD | 2003-10 | 2026-10 | 277 | UST_5Y ; CORP_AAA |
| TLT | etf_bond | USD | 2002-08 | 2026-10 | 291 | UST_20Y |
| GLD | commodity | USD | 2004-12 | 2026-10 | 263 | GOLD |
| BTC-USD | crypto | USD | 2014-10 | 2026-10 | 145 | aucun (pas de proxy avant 2014) |
| ETH-USD | crypto | USD | 2017-12 | 2026-10 | 107 | aucun |

Concordance proxy ~ FNB (corrélations mensuelles calculées par le build) : US_MKT~SPY 0,9874 ;
UST_20Y~TLT 0,9870 ; US_IND_BUSEQ~QQQ 0,9819 ; CA_EQ~XIU.TO 0,9835 ; UST_10Y~AGG 0,8775 ;
GOLD~GLD 0,6323 ; CA_GOV_10Y~XBB.TO 0,5843 ; CA_TBILL~ZST.TO 0,4866. Détail dans `data/SOURCES.md`.

## Tests
```bash
.venv/bin/python -I -m pytest -q
```
Les tests couvrent : la formule obligataire (cas calculé à la main), les métriques sur des séries jouets, le
nombre de fenêtres, des poids qui somment à 1 et respectent les contraintes à chaque date de transaction,
l'absence de look-ahead (perturber les rendements futurs ne change aucune décision passée, et la stratégie
ne voit que des dates < t), le fait que l'ORACLE porte `hindsight=True` et bat les mélanges fixes admissibles,
la conversion FX, la provenance starter après 2021-12, ainsi qu'un test de bout en bout avec écriture de la trace.

## Décisions et limites à connaître (agents de profil)
1. **Devise CAD = 1971-02 au plus tôt** pour tout ce qui doit être converti (pas d'USDCAD gratuit avant).
   Pour 1926+, il faut soit `currency: USD`, soit `fx_fill: flat` (hypothèse de change constant, à déclarer).
   Les actifs canadiens commencent en 1955-02 (obligations 10 ans), 1956-02 (cash) et **1977-01** (actions).
2. `load_returns` ne garde que les dates où **tous** les actifs existent. Un seul actif récent (BTC-USD 2014-10,
   ESGV 2018-10, SHOP.TO 2015-06) réduit donc toute la période. L'actif limitant est indiqué dans `attrs["info"]`
   et dans la trace. Sur de longs horizons, utiliser les proxys et réserver les tickers réels aux fenêtres récentes.
3. **L'or avant 1975 est non investissable et peu informatif** (prix fixe, interdiction de détention privée aux É.-U.
   1933-1974, valeurs annuelles avant 1960). Mieux vaut commencer à 1975-01 si l'or est dans l'univers, ou le justifier.
4. **Lissage des obligations** construites sur des moyennes mensuelles de taux (avant 1962 et Canada 10 ans) : leur
   volatilité est sous-estimée, ce qui flatte min-variance et risk parity sur la période ancienne. Les obligations de
   sociétés synthétiques ignorent les défauts (rendement surestimé, surtout Baa).
5. **Look-through tech** : `US_MKT` (et SPY/ESGV par approximation) prend la part BusEq de la capitalisation au moment
   de chaque décision (0,435 en 2026-09). Pour QQQ et XIU.TO, il n'existe pas de données de détention : leur exposition
   vaut 0 tant qu'aucun `exposure_overrides` n'est fourni (un avertissement est émis). Toute valeur fournie doit avoir
   une source documentée. ESGV n'a pas de proxy ESG : son historique long est celui du marché US.
6. **Contraintes** : elles sont imposées à chaque transaction. Entre deux rebalancements, la dérive peut les violer,
   et la colonne `drift_months_outside_constraints` le mesure. Pour la limiter, utiliser `rebalancing: bands`.
   Les `risk_limits` ne sont pas imposées ex-ante : elles sont **mesurées** (`n_breaches`, `breach_rate`) et
   `selection.max_breach_rate` permet d'exclure les stratégies fautives.
7. **ORACLE** = meilleur mélange **constant** rétrospectif. Une stratégie dynamique (momentum, tendance) peut donc le
   battre sur une fenêtre. Ce n'est pas un bug : c'est une borne pour les politiques statiques.
8. Les stratégies à estimation (risk parity, min-var, max-Sharpe, MV, tendance, momentum) utilisent les
   `fallback_weights` tant que l'historique est insuffisant (`fallback_months`, `fallback_share`). Les premières
   fenêtres d'une période peuvent ainsi être en partie « statiques ».
9. Les flux (cotisations et retraits) n'affectent que `final_wealth` et `final_real_wealth`. Les métriques de risque
   et de rendement sont calculées sur les rendements pondérés par le temps du portefeuille.
10. **Biais du survivant** (univers choisi en 2026), révisions FRED, dates de référence, absence de frais de gestion
    et d'impôts. Ce sont des **faits historiques reconstitués, pas des prévisions**.
