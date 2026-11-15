# `scripts/backtest` : études par persona sur le moteur de backtest

Études de recherche qui utilisent le moteur `alphaforge.finance.backtest`
([`src/alphaforge/finance/backtest/README.md`](../../src/alphaforge/finance/backtest/README.md)) pour dériver et
vérifier des seuils par persona. **Simulation uniquement** : backtests historiques, aucun conseil financier. Les
seuils qui en sortent sont des **propositions** à valider par l'équipe (fiche `product/personas.md` du Brain) ; ils
ne sont pas une configuration du produit.

| dossier | contenu |
|---|---|
| `profiles/` | profils YAML des études : `amira*`, `mateo*`, `robert*`, `p12_*` (Julien), `p14_*` (Tyler), `p35_*` (Denise), `x_*` (croisement). Le profil générique `example.yaml` est dans le paquet du moteur. |
| `analysis/<étude>/` | scripts d'une étude (`amira`, `mateo`, `robert`, `p12`, `p14`, `p35`, `croisement`, `decisions`), listes de jobs, entrées figées (`runs_*.json`, `derived_thresholds.json`). |
| `results/*_analysis/`, `results/decisions/` | synthèses versionnées, citées par les rapports. |
| `results/<run>/` (non versionné) | traces brutes du moteur (~650 Mo, reproductibles). |

Ces scripts sont exclus de `ruff` (`extend-exclude` dans `pyproject.toml`) : ce sont des études ponctuelles reprises
telles quelles, dont seuls les imports et les chemins ont été adaptés.

## Lancer une étude

Depuis ce dossier (les scripts écrivent dans `results/` relatif à `scripts/backtest/`) :

```bash
cd app/agents/scripts/backtest
uv run --group finance python -I analysis/croisement/hist2022.py
uv run --group finance python -I analysis/decisions/d8_d10_checks.py
uv run --group finance python -I analysis/mateo/build_ext_data.py && uv run --group finance python -I analysis/mateo/esg_struct.py
uv run --group finance python -I -m alphaforge.finance.backtest.run --profile mateo_cad_esg --mode rolling --horizon 10
```

- Dans un checkout, le moteur cherche les profils par id dans son dossier `profiles/` puis dans `scripts/backtest/profiles/`,
  et écrit ses traces dans `scripts/backtest/results/<id>/` (surcharges : `ALPHAFORGE_BT_PROFILES`,
  `ALPHAFORGE_BT_RESULTS`).
- Les études Mateo et P14 travaillent sur une copie dérivée des données (`analysis/<étude>/data_ext/`, non versionnée,
  créée par leur `build_ext_data.py`) en fixant `ALPHAFORGE_BT_DATA` avant d'importer le moteur.
- Certaines études lisent des traces brutes (`results/<run>/…`, non versionnées) : relancer d'abord les jobs indiqués
  dans leur docstring ou dans `analysis/<étude>/jobs*.txt`.
- Les rapprochements avec l'analyse réglementaire locale (`croisement/common.py`, `p12/reconcile.py`, `p14/recon.py`,
  `p35/fx_stats.py`) lisent le dossier `relation-profils-actifs` hors dépôt : `ALPHAFORGE_REG_DIR=<chemin>`.

## Reconstruire les données

Les parquets de `src/alphaforge/data/long/` ne sont pas versionnés (yfinance : redistribution interdite ; Moody's,
OCDE : droit d'auteur). Depuis `app/agents/` :

```bash
uv run --group finance --group backtest-data python -I -m alphaforge.finance.backtest.build_data
```

Le build de référence a `data_sha256 = 008f122d5da4f8f7` (`src/alphaforge/data/long/data_version.json`) ; une
reconstruction hors ligne depuis les mêmes bruts (`--offline`) redonne des parquets identiques octet pour octet.

## Rapports

Les rapports d'étude sont dans le repo **brain**, sous `references/backtest/` (`index.md`, `amira.md`, `mateo.md`,
`robert.md`, `p12-julien.md`, `p14-tyler.md`, `p35-denise.md`, `croisement-amira-mateo-robert.md`,
`decisions-a-profil-reglementaire.md`, `decisions-b-construction-portefeuille.md` ; anciennement
`research/backtest/reports/`). Ils citent les anciens chemins de `research/backtest/` (PR #4) :

| cité dans les rapports | emplacement actuel (`app/agents/…`) |
|---|---|
| `research/backtest/engine/<module>.py`, `engine.<module>` | `src/alphaforge/finance/backtest/<module>.py`, `alphaforge.finance.backtest.<module>` |
| `research/backtest/data/build_data.py` | `src/alphaforge/finance/backtest/build_data.py` |
| `research/backtest/data/processed/…`, `data/SOURCES.md` | `src/alphaforge/data/long/…`, `src/alphaforge/data/long/SOURCES.md` |
| `research/backtest/data/raw/…` | `src/alphaforge/data/long/raw/…` (non versionné) |
| `research/backtest/profiles/example.yaml` | `src/alphaforge/finance/backtest/profiles/example.yaml` |
| `research/backtest/profiles/<id>.yaml` | `scripts/backtest/profiles/<id>.yaml` |
| `research/backtest/analysis/…` | `scripts/backtest/analysis/…` |
| `research/backtest/results/…` | `scripts/backtest/results/…` |
| `research/backtest/tests/…` | `tests/finance/backtest/…` |
| `.venv/bin/python -I -m engine.run …` | `uv run --group finance python -I -m alphaforge.finance.backtest.run …` |

Les traces déjà versionnées gardent leur `engine_sha256` d'origine ; une trace produite après la migration a un autre
`engine_sha256` (les imports ont changé, pas les calculs : mêmes sorties sur le profil `example`) et le même
`data_sha256`.
