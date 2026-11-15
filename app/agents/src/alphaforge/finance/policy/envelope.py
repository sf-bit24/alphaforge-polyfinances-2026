"""Enveloppe historique ENV(e) : pire de 3 histoires a la part actions e (grille 5 %).

ENV(e, col) = max sur les familles {CAD77, CAD71, USD46} ; demi-cash (HC) si e <= 10, sinon G5.
Meme definition que app/agents/scripts/calibration/review/v02.py (envof / ref), portee ici sans pandas au
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


def _family_envelope(calibration, families: tuple[str, ...]):
    """Pire valeur de chaque colonne, par part d'actions, parmi les familles retenues."""
    selected = calibration[calibration["mix"].isin(families)].copy()
    selected["y2022"] = -selected["y2022"]  # perte positive
    return selected.groupby("eq")[list(COLUMNS)].max()


def build_from_calibration(calibration_dir: str | Path) -> dict:
    """Recalcule l'enveloppe depuis tests/finance/fixtures/calibration (calib_grid5.csv, halfcash_env.csv)."""
    import pandas as pd

    directory = Path(calibration_dir)
    files = {"G5": directory / "calib_grid5.csv", "HC": directory / "halfcash_env.csv"}
    grid_envelope = _family_envelope(pd.read_csv(files["G5"]), G5_FAMILIES)
    half_cash_envelope = _family_envelope(pd.read_csv(files["HC"]), HC_FAMILIES)
    rows = {}
    for equity_pct in sorted(int(value) for value in grid_envelope.index):
        family_envelope = half_cash_envelope if equity_pct <= HC_MAX_EQUITY else grid_envelope
        rows[equity_pct] = {column: round(float(family_envelope.loc[equity_pct, column]), 6) for column in COLUMNS}
        rows[equity_pct]["family_set"] = "HC" if equity_pct <= HC_MAX_EQUITY else "G5"
    return {
        "version": "0.2.0",
        "definition": "ENV(e,col) = max des familles ; HC (CAD77_hc, CAD71_hc, USD46_hc) si e<=10, "
        "sinon G5 (CAD77_main, CAD71_USeq, USD46) ; y2022 en perte positive",
        "source_files": {
            name: {
                "path": f"app/agents/tests/finance/fixtures/calibration/{path.name}",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for name, path in files.items()
        },
        "equity_pct": rows,
    }


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def load_envelope(path: str | Path | None = None) -> dict:
    return _load(str(path or ENVELOPE_FILE))


def env(equity_pct: int, column: str, path: str | Path | None = None) -> float:
    return float(load_envelope(path)["equity_pct"][int(equity_pct)][column])


def grid(path: str | Path | None = None) -> list[int]:
    return sorted(int(equity_pct) for equity_pct in load_envelope(path)["equity_pct"])
