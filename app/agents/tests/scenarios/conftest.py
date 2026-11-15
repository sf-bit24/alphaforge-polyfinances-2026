"""Données synthétiques au format du build long (``data/processed``) : aucun fichier sous licence dans le dépôt.

Les tests du volet B n'ont besoin que de numpy, pandas et pyarrow (groupe ``scenarios``) ; ils sont ignorés si
ces paquets manquent. Le test d'intégration sur les vraies données lit ``ALPHAFORGE_SCENARIOS_DATA`` s'il est posé.
"""

from __future__ import annotations

import json

import pytest

try:  # groupe optionnel « scenarios » : sans lui, ces tests ne sont pas collectés
    import numpy as np
    import pandas as pd
    import pyarrow  # noqa: F401
except ImportError:  # pragma: no cover
    collect_ignore_glob = ["test_*.py"]


def _series(rng, n, mu, sigma, ar=0.0):
    x = np.empty(n)
    prev = 0.0
    for t in range(n):
        prev = ar * prev + rng.normal(0.0, sigma)
        x[t] = mu + prev
    return x


@pytest.fixture(scope="session")
def synthetic_dir(tmp_path_factory):
    """Dossier ``processed`` synthétique : 1960-01..2024-12, deux régimes de volatilité, BTC depuis 2014-10."""
    rng = np.random.default_rng(123)
    dates = pd.date_range("1960-01-31", "2024-12-31", freq="ME")
    n = len(dates)
    regime = (np.sin(np.arange(n) / 40.0) > 0.6).astype(float)  # périodes agitées persistantes
    vol = 0.035 + 0.04 * regime
    mkt = rng.normal(0.007, 1.0, n) * vol
    ca = 0.8 * mkt + rng.normal(0.0, 0.02, n)
    bonds = 0.004 + _series(rng, n, 0.0, 0.012, ar=0.3) - 0.1 * mkt
    cash = np.clip(0.003 + _series(rng, n, 0.0, 0.0003, ar=0.98), 0.0, None)
    gold = rng.normal(0.004, 0.045, n)
    infl = 0.0025 + _series(rng, n, 0.0, 0.002, ar=0.6)
    fx = np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    fx_ret = fx / np.concatenate([[fx[0]], fx[:-1]]) - 1.0
    rows = []

    def add(asset, r_local, ccy, start=None, flag=""):
        for t, d in enumerate(dates):
            if start is not None and d < pd.Timestamp(start):
                continue
            r = float(r_local[t])
            if ccy == "USD":
                r_usd, r_cad = r, (1 + r) * (1 + fx_ret[t]) - 1
            else:
                r_cad, r_usd = r, (1 + r) / (1 + fx_ret[t]) - 1
            rows.append((d, asset, r_usd, r_cad, "synthetic", flag if t % 7 == 0 else ""))

    add("US_MKT", mkt, "USD")
    add("UST_10Y", bonds, "USD", flag="monthly_avg_yield")
    add("UST_TBILL", cash * 0.9, "USD")
    add("CA_EQ", ca, "CAD", start="1977-01-31")
    add("CA_GOV_10Y", bonds * 1.05, "CAD", flag="monthly_avg_yield")
    add("CA_TBILL", cash, "CAD", flag="proxy_interbank_rate")
    add("GOLD", gold, "USD")
    add("BTC-USD", rng.normal(0.04, 0.2, n), "USD", start="2014-10-31")
    df = pd.DataFrame(rows, columns=["date", "asset_id", "return_usd", "return_cad", "source", "flag"])
    root = tmp_path_factory.mktemp("processed")
    df.to_parquet(root / "monthly_returns.parquet", index=False)
    pd.DataFrame({"date": dates, "infl_us": infl, "infl_ca": infl * 1.02, "flag_us": ""}).to_parquet(
        root / "inflation_monthly.parquet", index=False
    )
    (root / "data_version.json").write_text(json.dumps({"data_sha256": "synthetic0001", "n_rows": len(df)}))
    return root


@pytest.fixture(scope="session")
def inputs(synthetic_dir):
    from alphaforge.scenarios.data import load_inputs

    return load_inputs(synthetic_dir)


@pytest.fixture(scope="session")
def pool77(inputs):
    from alphaforge.scenarios.data import build_pool

    return build_pool(inputs, "CAD77")
