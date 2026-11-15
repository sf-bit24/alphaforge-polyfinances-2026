"""Compléments de tails.py pour l'étape 0 (strategy.yaml#sectors) : titres et industries Ken French absents
de tails_monthly.csv. Écrit tests/finance/fixtures/calibration/tails_sectors.csv sans toucher aux autres fixtures.

Usage (données longues requises) :
    ALPHAFORGE_BT_DATA=<dossier processed> python -m scripts.calibration.tails_sectors  # depuis app/agents
ou  python scripts/calibration/tails_sectors.py
Simulation seulement : ces mesures décrivent le passé (baisse maximale mensuelle composée, en CAD et en USD).
"""

from __future__ import annotations

import json
import os
import pathlib

import numpy as np
import pandas as pd

from alphaforge.finance.backtest import metrics as M
from alphaforge.finance.backtest.data import load_returns
from alphaforge.finance.backtest.paths import data_dir

NAMES = [
    "TD.TO",
    "CNR.TO",
    "FTS.TO",
    "ATD.TO",
    "US_IND_UTILS",
    "US_IND_HLTH",
    "US_IND_NODUR",
    "US_IND_SHOPS",
    "US_IND_OTHER",
    "US_IND_MONEY",
    "US_IND_ENRGY",
    "US_IND_BUSEQ",
]
OUT = pathlib.Path(
    os.environ.get("CALIB_OUT", pathlib.Path(__file__).resolve().parents[2] / "tests/finance/fixtures/calibration")
)


def main() -> pd.DataFrame:
    rows = []
    for cur in ("CAD", "USD"):
        for n in NAMES:
            try:
                r = load_returns([n], currency=cur)[n]
            except Exception:  # noqa: S112 - actif absent des données longues
                continue
            v = r.values
            rows.append(
                {
                    "asset": n,
                    "cur": cur,
                    "start": f"{r.index[0]:%Y-%m}",
                    "end": f"{r.index[-1]:%Y-%m}",
                    "n": len(v),
                    "vol": M.volatility(v),
                    "mdd": M.max_drawdown(v),
                    "worst_month": float(np.min(v)),
                }
            )
    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "tails_sectors.csv", index=False)
    ver = json.loads((data_dir() / "data_version.json").read_text())["data_sha256"]
    (OUT / "tails_sectors_meta.json").write_text(json.dumps({"data_sha256": ver, "names": NAMES}, indent=2) + "\n")
    return df


if __name__ == "__main__":
    print(main().to_string(index=False))
