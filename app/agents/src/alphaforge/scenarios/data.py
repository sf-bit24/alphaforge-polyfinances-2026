"""Chargement des données longues et construction des « bassins » (pools) de rendements mensuels par famille.

Entrée : le dossier ``data/processed`` du build long (``monthly_returns.parquet`` au format long
``date, asset_id, return_usd, return_cad, source, flag``, ``inflation_monthly.parquet``, ``data_version.json``).
Le chemin est un paramètre (``--input`` du job) : aucun chemin n'est codé en dur.

Un *pool* est un panneau rectangulaire (mois × blocs) sans trou, plus l'inflation du même mois. Les générateurs ne
voient que des pools. Règles explicites (voir README.md, « Données ») :

- fenêtre = intersection des historiques des blocs de la famille, bornée par ``start`` de la famille ;
- un mois manquant **à l'intérieur** de la fenêtre est une erreur (aucun comblement silencieux) ; aucun cas
  dans le build de référence ;
- les drapeaux de qualité (``flag``) sont conservés et comptés par bloc dans ``pool.flag_counts`` ;
- CRYPTO (BTC-USD, depuis 2014-10) forme un pool séparé, plus court, marqué ``hypothese=True``.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .schema import BLOCKS

# Correspondance bloc -> série du build long, par famille. Choix documentés dans README.md.
FAMILY_SPECS: dict[str, dict] = {
    "CAD77": {
        "currency": "CAD",
        "return_col": "return_cad",
        "inflation_col": "infl_ca",
        "start": "1977-01",
        "blocks": {
            "CA_EQ": "CA_EQ",
            "US_MKT": "US_MKT",
            "BONDS": "CA_GOV_10Y",
            "CASH": "CA_TBILL",
            "GOLD": "GOLD",
            "CRYPTO": "BTC-USD",
        },
    },
    "CAD71": {
        # Ni CA_EQ (Ken French Canada commence en 1977-01) ni GOLD (non investissable aux É.-U. avant 1975,
        # prix officiel fixe jusqu'en 1971-08) : voir SOURCES.md du build long.
        "currency": "CAD",
        "return_col": "return_cad",
        "inflation_col": "infl_ca",
        "start": "1971-01",
        "blocks": {"US_MKT": "US_MKT", "BONDS": "CA_GOV_10Y", "CASH": "CA_TBILL"},
    },
    "USD1926": {
        # GOLD exclu : avant 1960, série annuelle répétée chaque mois ; non investissable de 1933 à 1974.
        "currency": "USD",
        "return_col": "return_usd",
        "inflation_col": "infl_us",
        "start": "1926-01",
        "blocks": {"US_MKT": "US_MKT", "BONDS": "UST_10Y", "CASH": "UST_TBILL"},
    },
}
CRYPTO_BLOCK = "CRYPTO"


def month_end(value: str) -> pd.Timestamp:
    """``"YYYY-MM"`` (ou une date) -> dernier jour du mois civil."""
    return (pd.Timestamp(value).to_period("M").to_timestamp(how="end")).normalize()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Inputs:
    returns: pd.DataFrame
    inflation: pd.DataFrame
    data_sha256: str
    files_sha256: dict[str, str]
    data_version: dict
    input_dir: str


def load_inputs(input_dir: str | Path) -> Inputs:
    """Lit les fichiers du build long. ``data_sha256`` vient de ``data_version.json`` (identifiant du build) ;
    à défaut, c'est le sha256 de ``monthly_returns.parquet``."""
    root = Path(input_dir)
    ret_path = root / "monthly_returns.parquet"
    inf_path = root / "inflation_monthly.parquet"
    if not ret_path.exists():
        raise FileNotFoundError(f"{ret_path} introuvable")
    returns = pd.read_parquet(ret_path)
    returns["date"] = pd.to_datetime(returns["date"]).dt.normalize()
    inflation = pd.read_parquet(inf_path) if inf_path.exists() else pd.DataFrame(columns=["date"])
    if "date" in inflation:
        inflation["date"] = pd.to_datetime(inflation["date"]).dt.normalize()
    files = {p.name: _sha256_file(p) for p in (ret_path, inf_path, root / "data_version.json") if p.exists()}
    version: dict = {}
    if (root / "data_version.json").exists():
        version = json.loads((root / "data_version.json").read_text(encoding="utf-8"))
    data_sha = str(version.get("data_sha256") or files[ret_path.name])
    slim_version = {
        k: version[k] for k in ("data_sha256", "built_utc", "last_complete_month", "n_rows") if k in version
    }
    return Inputs(returns, inflation, data_sha, files, slim_version, str(root))


@dataclass
class Pool:
    """Panneau mensuel rectangulaire d'une famille : ``R[t, j]`` = rendement simple du bloc ``blocks[j]`` au mois t."""

    name: str
    family: str
    currency: str
    blocks: tuple[str, ...]
    dates: pd.DatetimeIndex
    R: np.ndarray
    infl: np.ndarray
    hypothese: bool
    data_sha256: str
    sources: dict[str, str] = field(default_factory=dict)
    flag_counts: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.dates)

    @property
    def window_start(self) -> str:
        return self.dates[0].strftime("%Y-%m")

    @property
    def fitted_through(self) -> str:
        return self.dates[-1].strftime("%Y-%m")

    def truncate(self, fitted_through: str | None) -> Pool:
        """Pool limité aux mois <= ``fitted_through`` (``YYYY-MM``). Copie : l'original n'est pas modifié."""
        if fitted_through is None:
            return self
        cut = month_end(fitted_through)
        keep = np.asarray(self.dates <= cut)
        if keep.sum() < 24:
            raise ValueError(f"{self.name} : moins de 24 mois avant {fitted_through}")
        return self._subset(np.flatnonzero(keep))

    def anchor_cash(self, months: int = 12) -> tuple[Pool, dict]:
        """Ancrage du niveau des taux sur les ``months`` derniers mois de la fenêtre (aucune donnée postérieure).

        ``s = moyenne(CASH, derniers mois) / moyenne(CASH, fenêtre)`` ; chaque mois t :
        ``CASH'_t = s·CASH_t`` et, pour les autres blocs, ``r'_t = r_t + (s − 1)·CASH_t``. Les rendements
        excédentaires sur le cash (donc primes, volatilités et corrélations des excès) sont conservés mois par mois ;
        seul le niveau du cash change. L'inflation est mise à l'échelle de la même façon avec ses propres moyennes
        (``s_infl``), pour que les rendements réels restent cohérents.
        """
        if "CASH" not in self.blocks:
            raise ValueError("ancrage impossible sans bloc CASH")
        j = self.blocks.index("CASH")
        cash = self.R[:, j]
        s = float(cash[-months:].mean() / cash.mean())
        s_infl = float(self.infl[-months:].mean() / self.infl.mean()) if self.infl.mean() != 0 else 1.0
        R = self.R + (s - 1.0) * cash[:, None]
        R[:, j] = s * cash
        pool = Pool(
            self.name,
            self.family,
            self.currency,
            self.blocks,
            self.dates,
            R,
            self.infl * s_infl,
            self.hypothese,
            self.data_sha256,
            dict(self.sources),
            dict(self.flag_counts),
        )
        info = {
            "mean_adjust": f"cash_anchor_{months}m",
            "cash_scale": round(s, 4),
            "infl_scale": round(s_infl, 4),
            "cash_ann_window": round(float(cash.mean()) * 12, 5),
            "cash_ann_anchor": round(float(cash[-months:].mean()) * 12, 5),
            "infl_ann_window": round(float(self.infl.mean()) * 12, 5),
            "infl_ann_anchor": round(float(self.infl[-months:].mean()) * 12, 5),
        }
        return pool, info

    def take(self, idx: np.ndarray, name_suffix: str = "") -> Pool:
        """Pseudo-historique fait des mois ``idx`` (rééchantillonnage). Les dates deviennent fictives et consécutives
        (même dernier mois), pour que ``fitted_through`` reste celui du pool d'origine."""
        idx = np.asarray(idx, dtype=np.int64)
        dates = pd.date_range(end=self.dates[-1], periods=len(idx), freq="ME")
        return Pool(
            self.name + name_suffix,
            self.family,
            self.currency,
            self.blocks,
            dates,
            self.R[idx].copy(),
            self.infl[idx].copy(),
            self.hypothese,
            self.data_sha256,
            dict(self.sources),
            {},
        )

    def _subset(self, idx: np.ndarray) -> Pool:
        return Pool(
            self.name,
            self.family,
            self.currency,
            self.blocks,
            self.dates[idx],
            self.R[idx].copy(),
            self.infl[idx].copy(),
            self.hypothese,
            self.data_sha256,
            dict(self.sources),
            dict(self.flag_counts),
        )

    def describe(self) -> dict:
        return {
            "pool": self.name,
            "family": self.family,
            "currency": self.currency,
            "blocks": list(self.blocks),
            "sources": self.sources,
            "window_start": self.window_start,
            "window_end": self.fitted_through,
            "n_months": self.n,
            "hypothese": self.hypothese,
            "flag_counts": self.flag_counts,
        }


def build_pool(inputs: Inputs, family: str, *, crypto: bool = False, end: str | None = None) -> Pool:
    """Construit le pool d'une famille. ``crypto=True`` ajoute le bloc CRYPTO et réduit la fenêtre à son historique.

    ``end`` (``YYYY-MM``) borne la fenêtre ; pour la validation hors échantillon, préférer ``Pool.truncate`` ou
    ``fit(..., fitted_through=...)`` qui font la même chose au moment de l'ajustement.
    """
    spec = FAMILY_SPECS[family]
    mapping = {b: a for b, a in spec["blocks"].items() if b != CRYPTO_BLOCK}
    if crypto:
        if CRYPTO_BLOCK not in spec["blocks"]:
            raise ValueError(f"famille {family} sans bloc CRYPTO")
        mapping[CRYPTO_BLOCK] = spec["blocks"][CRYPTO_BLOCK]
    blocks = tuple(b for b in BLOCKS if b in mapping)
    col = spec["return_col"]
    df = inputs.returns
    wide = df[df["asset_id"].isin(list(mapping.values()))].pivot(index="date", columns="asset_id", values=col)
    flags = df[df["asset_id"].isin(list(mapping.values()))].pivot(index="date", columns="asset_id", values="flag")
    missing_assets = [a for a in mapping.values() if a not in wide.columns]
    if missing_assets:
        raise ValueError(f"séries absentes de l'entrée : {missing_assets}")

    starts = [wide[a].first_valid_index() for a in mapping.values()]
    ends = [wide[a].last_valid_index() for a in mapping.values()]
    lo = max([*starts, month_end(spec["start"])])
    hi = min(ends)
    if end is not None:
        hi = min(hi, month_end(end))
    window = wide.loc[(wide.index >= lo) & (wide.index <= hi), [mapping[b] for b in blocks]]
    expected = pd.date_range(lo, hi, freq="ME")
    if len(window) != len(expected) or not np.array_equal(window.index.values, expected.values):
        raise ValueError(f"{family} : calendrier mensuel incomplet entre {lo:%Y-%m} et {hi:%Y-%m}")
    if window.isna().any().any():
        bad = window.columns[window.isna().any()].tolist()
        raise ValueError(f"{family} : mois manquants à l'intérieur de la fenêtre pour {bad}")

    infl_col = spec["inflation_col"]
    infl = inputs.inflation.set_index("date")[infl_col].reindex(window.index) if infl_col in inputs.inflation else None
    if infl is None or infl.isna().any():
        raise ValueError(f"{family} : inflation {infl_col} manquante dans la fenêtre")

    flag_counts: dict[str, dict[str, int]] = {}
    fwin = flags.loc[window.index]
    for block in blocks:
        counter: Counter[str] = Counter()
        for value in fwin[mapping[block]].fillna(""):
            for token in str(value).split(";"):
                if token:
                    counter[token] += 1
        if counter:
            flag_counts[block] = dict(sorted(counter.items()))

    name = f"{family}{'+CRYPTO' if crypto else ''}"
    return Pool(
        name=name,
        family=family,
        currency=spec["currency"],
        blocks=blocks,
        dates=pd.DatetimeIndex(window.index),
        R=window.to_numpy(dtype=np.float64),
        infl=infl.to_numpy(dtype=np.float64),
        hypothese=crypto,
        data_sha256=inputs.data_sha256,
        sources={b: f"{mapping[b]}.{col}" for b in blocks} | {"INFLATION": infl_col},
        flag_counts=flag_counts,
    )
