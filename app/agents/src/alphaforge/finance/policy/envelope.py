"""Enveloppe historique ENV(e) : pire de 3 histoires a la part actions e (grille 5 %).

ENV(e, col) = max sur les familles {CAD77, CAD71, USD46} ; demi-cash (HC) si e <= 10, sinon G5.
Meme definition que research/calibration/review/v02.py (envof / ref), portee ici sans pandas au
moment de l'execution : les valeurs sont figees dans ``envelope_v02.yaml`` (fichier de donnees
versionne, sha256 des CSV source inclus). ``build_from_calibration`` regenere ce fichier.
SIMULATION SEULEMENT.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import yaml

ENVELOPE_FILE = Path(__file__).with_name("envelope_v02.yaml")
COLUMNS = ("vol", "cvar95_m", "cvar95_12m", "mdd", "y2022")
G5_FAMILIES = ("CAD77_main", "CAD71_USeq", "USD46")
HC_FAMILIES = ("CAD77_hc", "CAD71_hc", "USD46_hc")
HC_MAX_EQUITY = 10  # e <= 10 -> portefeuille de reference demi-cash (reference_portfolios.N0)


def build_from_calibration(out_dir: str | Path) -> dict:
    """Recalcule l'enveloppe depuis research/calibration/out (calib_grid5.csv, halfcash_env.csv)."""
    import pandas as pd

    out = Path(out_dir)
    files = {"G5": out / "calib_grid5.csv", "HC": out / "halfcash_env.csv"}

    def envof(df, fams):
        x = df[df["mix"].isin(fams)].copy()
        x["y2022"] = -x["y2022"]  # perte positive
        return x.groupby("eq")[list(COLUMNS)].max()

    g5 = envof(pd.read_csv(files["G5"]), G5_FAMILIES)
    hc = envof(pd.read_csv(files["HC"]), HC_FAMILIES)
    rows = {}
    for e in sorted(int(v) for v in g5.index):
        src = hc if e <= HC_MAX_EQUITY else g5
        rows[e] = {c: round(float(src.loc[e, c]), 6) for c in COLUMNS}
        rows[e]["family_set"] = "HC" if e <= HC_MAX_EQUITY else "G5"
    return {
        "version": "0.2.0",
        "definition": "ENV(e,col) = max des familles ; HC (CAD77_hc, CAD71_hc, USD46_hc) si e<=10, "
        "sinon G5 (CAD77_main, CAD71_USeq, USD46) ; y2022 en perte positive",
        "source_files": {
            k: {"path": f"research/calibration/out/{p.name}", "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for k, p in files.items()
        },
        "equity_pct": rows,
    }


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_envelope(path: str | Path | None = None) -> dict:
    return _load(str(path or ENVELOPE_FILE))


def env(e_pct: int, col: str, path: str | Path | None = None) -> float:
    return float(load_envelope(path)["equity_pct"][int(e_pct)][col])


def grid(path: str | Path | None = None) -> list[int]:
    return sorted(int(e) for e in load_envelope(path)["equity_pct"])
