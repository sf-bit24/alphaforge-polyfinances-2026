"""Chargement des données longues et construction des « bassins » (pools) de rendements mensuels par famille.

Entrée : le dossier des données longues de ``alphaforge.finance.backtest.build_data`` (``alphaforge/data/long/`` ou
``ALPHAFORGE_BT_DATA``) (``monthly_returns.parquet`` au format long
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
from dataclasses import dataclass, field, replace
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    returns_path = root / "monthly_returns.parquet"
    inflation_path = root / "inflation_monthly.parquet"
    if not returns_path.exists():
        raise FileNotFoundError(f"{returns_path} introuvable")
    returns = pd.read_parquet(returns_path)
    returns["date"] = pd.to_datetime(returns["date"]).dt.normalize()
    inflation = pd.read_parquet(inflation_path) if inflation_path.exists() else pd.DataFrame(columns=["date"])
    if "date" in inflation:
        inflation["date"] = pd.to_datetime(inflation["date"]).dt.normalize()
    candidates = (returns_path, inflation_path, root / "data_version.json")
    files = {path.name: sha256_file(path) for path in candidates if path.exists()}
    version: dict = {}
    if (root / "data_version.json").exists():
        version = json.loads((root / "data_version.json").read_text(encoding="utf-8"))
    data_sha = str(version.get("data_sha256") or files[returns_path.name])
    slim_version = {
        k: version[k] for k in ("data_sha256", "built_utc", "last_complete_month", "n_rows") if k in version
    }
    return Inputs(returns, inflation, data_sha, files, slim_version, str(root))


@dataclass
class Pool:
    """Panneau mensuel rectangulaire d'une famille : ``returns[t, j]`` = rendement simple du bloc ``blocks[j]`` au
    mois t."""

    name: str
    family: str
    currency: str
    blocks: tuple[str, ...]
    dates: pd.DatetimeIndex
    returns: np.ndarray
    inflation: np.ndarray
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

        Déflation : si l'une des deux moyennes d'inflation est <= 0, ``s_infl`` serait nul, négatif ou infini (un
        facteur négatif inverserait le signe de chaque mois d'inflation). L'ancrage de l'inflation devient alors
        additif, ``infl'_t = infl_t + (moyenne récente − moyenne de la fenêtre)`` : même moyenne visée, écarts
        mensuels conservés. Signalé par ``infl_anchor = "additive"`` (``"scale"`` sinon). Ne touche que la base
        réelle; le cas multiplicatif habituel est inchangé (runs validés reproductibles).
        """
        if "CASH" not in self.blocks:
            raise ValueError("ancrage impossible sans bloc CASH")
        j = self.blocks.index("CASH")
        cash = self.returns[:, j]
        cash_scale = float(cash[-months:].mean() / cash.mean())  # s
        infl_recent, infl_window = float(self.inflation[-months:].mean()), float(self.inflation.mean())
        if infl_recent > 0 and infl_window > 0:
            infl_anchor, infl_scale = "scale", infl_recent / infl_window  # s_infl
            inflation = self.inflation * infl_scale
        else:
            infl_anchor, infl_scale = "additive", None
            inflation = self.inflation + (infl_recent - infl_window)
        returns = self.returns + (cash_scale - 1.0) * cash[:, None]
        returns[:, j] = cash_scale * cash
        pool = replace(
            self, returns=returns, inflation=inflation, sources=dict(self.sources), flag_counts=dict(self.flag_counts)
        )
        info = {
            "mean_adjust": f"cash_anchor_{months}m",
            "cash_scale": round(cash_scale, 4),
            "infl_anchor": infl_anchor,
            "infl_scale": round(infl_scale, 4) if infl_scale is not None else None,
            "cash_ann_window": round(float(cash.mean()) * 12, 5),
            "cash_ann_anchor": round(float(cash[-months:].mean()) * 12, 5),
            "infl_ann_window": round(float(self.inflation.mean()) * 12, 5),
            "infl_ann_anchor": round(float(self.inflation[-months:].mean()) * 12, 5),
        }
        return pool, info

    def take(self, indices: np.ndarray, name_suffix: str = "") -> Pool:
        """Pseudo-historique fait des mois ``indices`` (rééchantillonnage). Les dates deviennent fictives et
        consécutives (même dernier mois), pour que ``fitted_through`` reste celui du pool d'origine."""
        indices = np.asarray(indices, dtype=np.int64)
        dates = pd.date_range(end=self.dates[-1], periods=len(indices), freq="ME")
        return replace(
            self,
            name=self.name + name_suffix,
            dates=dates,
            returns=self.returns[indices].copy(),
            inflation=self.inflation[indices].copy(),
            sources=dict(self.sources),
            flag_counts={},
        )

    def _subset(self, indices: np.ndarray) -> Pool:
        return replace(
            self,
            dates=self.dates[indices],
            returns=self.returns[indices].copy(),
            inflation=self.inflation[indices].copy(),
            sources=dict(self.sources),
            flag_counts=dict(self.flag_counts),
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


def _block_assets(spec: dict, family: str, *, crypto: bool) -> dict[str, str]:
    """Bloc -> série du build long ; le bloc CRYPTO seulement si ``crypto``."""
    mapping = {block: asset for block, asset in spec["blocks"].items() if block != CRYPTO_BLOCK}
    if crypto:
        if CRYPTO_BLOCK not in spec["blocks"]:
            raise ValueError(f"famille {family} sans bloc CRYPTO")
        mapping[CRYPTO_BLOCK] = spec["blocks"][CRYPTO_BLOCK]
    return mapping


def _pivot(returns: pd.DataFrame, assets: list[str], values: str) -> pd.DataFrame:
    """Colonne ``values`` du format long, une ligne par date et une colonne par série de ``assets``."""
    return returns[returns["asset_id"].isin(assets)].pivot(index="date", columns="asset_id", values=values)


def _window_bounds(
    wide: pd.DataFrame, assets: list[str], family_start: str, end: str | None
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Intersection des historiques des séries, bornée par le début de la famille et par ``end``."""
    starts = [wide[asset].first_valid_index() for asset in assets]
    ends = [wide[asset].last_valid_index() for asset in assets]
    first_month = max([*starts, month_end(family_start)])
    last_month = min(ends)
    if end is not None:
        last_month = min(last_month, month_end(end))
    return first_month, last_month


def _checked_window(
    wide: pd.DataFrame, columns: list[str], first_month: pd.Timestamp, last_month: pd.Timestamp, family: str
) -> pd.DataFrame:
    """Mois ``first_month`` .. ``last_month`` des séries ``columns`` : un mois absent ou manquant est une erreur."""
    window = wide.loc[(wide.index >= first_month) & (wide.index <= last_month), columns]
    expected = pd.date_range(first_month, last_month, freq="ME")
    if len(window) != len(expected) or not np.array_equal(window.index.values, expected.values):
        raise ValueError(f"{family} : calendrier mensuel incomplet entre {first_month:%Y-%m} et {last_month:%Y-%m}")
    if window.isna().any().any():
        bad = window.columns[window.isna().any()].tolist()
        raise ValueError(f"{family} : mois manquants à l'intérieur de la fenêtre pour {bad}")
    return window


def _window_inflation(inflation: pd.DataFrame, column: str, dates: pd.Index, family: str) -> pd.Series:
    series = inflation.set_index("date")[column].reindex(dates) if column in inflation else None
    if series is None or series.isna().any():
        raise ValueError(f"{family} : inflation {column} manquante dans la fenêtre")
    return series


def _flag_counts(flags: pd.DataFrame, mapping: dict[str, str], blocks: tuple[str, ...]) -> dict[str, dict[str, int]]:
    """Drapeaux de qualité comptés par bloc ; une valeur peut en porter plusieurs, séparés par ``;``."""
    flag_counts: dict[str, dict[str, int]] = {}
    for block in blocks:
        counter: Counter[str] = Counter()
        for value in flags[mapping[block]].fillna(""):
            counter.update(token for token in str(value).split(";") if token)
        if counter:
            flag_counts[block] = dict(sorted(counter.items()))
    return flag_counts


def build_pool(inputs: Inputs, family: str, *, crypto: bool = False, end: str | None = None) -> Pool:
    """Construit le pool d'une famille. ``crypto=True`` ajoute le bloc CRYPTO et réduit la fenêtre à son historique.

    ``end`` (``YYYY-MM``) borne la fenêtre ; pour la validation hors échantillon, préférer ``Pool.truncate`` ou
    ``fit(..., fitted_through=...)`` qui font la même chose au moment de l'ajustement.
    """
    spec = FAMILY_SPECS[family]
    mapping = _block_assets(spec, family, crypto=crypto)
    blocks = tuple(block for block in BLOCKS if block in mapping)
    return_col = spec["return_col"]
    assets = list(mapping.values())
    wide = _pivot(inputs.returns, assets, return_col)
    flags = _pivot(inputs.returns, assets, "flag")
    missing_assets = [asset for asset in mapping.values() if asset not in wide.columns]
    if missing_assets:
        raise ValueError(f"séries absentes de l'entrée : {missing_assets}")
    first_month, last_month = _window_bounds(wide, assets, spec["start"], end)
    window = _checked_window(wide, [mapping[block] for block in blocks], first_month, last_month, family)
    infl_col = spec["inflation_col"]
    inflation = _window_inflation(inputs.inflation, infl_col, window.index, family)
    return Pool(
        name=f"{family}{'+CRYPTO' if crypto else ''}",
        family=family,
        currency=spec["currency"],
        blocks=blocks,
        dates=pd.DatetimeIndex(window.index),
        returns=window.to_numpy(dtype=np.float64),
        inflation=inflation.to_numpy(dtype=np.float64),
        hypothese=crypto,
        data_sha256=inputs.data_sha256,
        sources={block: f"{mapping[block]}.{return_col}" for block in blocks} | {"INFLATION": infl_col},
        flag_counts=_flag_counts(flags.loc[window.index], mapping, blocks),
    )
