"""Default locations of the backtest engine (standard library only: importable without numpy/pandas).

- processed monthly dataset: ``alphaforge/data/long/`` (parquets not versioned, see SOURCES.md there);
  override ``ALPHAFORGE_BT_DATA``. Raw downloads (untrusted, not versioned) go to ``<data dir>/raw/``.
- official starter dataset: ``alphaforge/data/starter/``; override ``ALPHAFORGE_STARTER_DIR``.
- profile YAML files given by id: ``finance/backtest/profiles/`` (``example.yaml``); override
  ``ALPHAFORGE_BT_PROFILES`` (``os.pathsep``-separated list) or ``load_profile(..., profiles_dir=...)`` /
  ``--profiles-dir``.
- run traces: ``./backtest-results/<profile id>/``, relative to the current directory and ignored by git;
  override ``ALPHAFORGE_BT_RESULTS`` or ``run_profile(..., out_dir=...)`` / ``--out``. The engine never writes
  inside the package.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent  # alphaforge/finance/backtest
ALPHAFORGE_DIR = PACKAGE_DIR.parents[1]  # alphaforge

DEFAULT_DATA_DIR = ALPHAFORGE_DIR / "data" / "long"
DEFAULT_STARTER_DIR = ALPHAFORGE_DIR / "data" / "starter"
PROFILES_DIR = PACKAGE_DIR / "profiles"
# Processed files written by build_data (not versioned).
LONG_PARQUETS = ("monthly_returns.parquet", "inflation_monthly.parquet", "fx_monthly.parquet",
                 "lookthrough_us_mkt.parquet")


def data_dir() -> Path:
    """Processed dataset directory. Read at each call: ``data.DATA_DIR`` and ``build_data`` read it once, when they
    are first imported (a script may set ``ALPHAFORGE_BT_DATA`` before importing the engine to use a derived copy)."""
    return Path(os.environ.get("ALPHAFORGE_BT_DATA") or DEFAULT_DATA_DIR)


def starter_dir() -> Path:
    """Official starter dataset directory (committed in the app, byte-identical to the organisers' copy)."""
    return Path(os.environ.get("ALPHAFORGE_STARTER_DIR") or DEFAULT_STARTER_DIR)


def profile_dirs() -> list[Path]:
    """Directories searched (in order) for ``<id>.yaml`` when a profile is given by id."""
    env = os.environ.get("ALPHAFORGE_BT_PROFILES")
    if env:
        return [Path(p) for p in env.split(os.pathsep) if p]
    return [PROFILES_DIR]


def results_dir() -> Path:
    """Root directory of run traces (``<root>/<profile id>/<stamp>_*.json``)."""
    env = os.environ.get("ALPHAFORGE_BT_RESULTS")
    if env:
        return Path(env)
    return Path.cwd() / "backtest-results"


def long_data_available(modules: tuple[str, ...] = ("numpy", "pandas")) -> bool:
    """True when the processed parquets are in ``data_dir()`` and ``modules`` are importable (used to skip tests)."""
    if any(importlib.util.find_spec(m) is None for m in modules):
        return False
    return all((data_dir() / f).is_file() for f in LONG_PARQUETS)
