"""Rendements mensuels point-in-time (PIT) pour le tick mensuel et le rejeu.

Garantie PIT : une vue bornée par ``with_horizon(t)`` ne laisse lire aucun mois postérieur à ``t``.
Toute tentative lève ``LookaheadError`` (un tick au mois t ne lit jamais t+1).

Format d'échange ``.csv.gz`` (export runtime, lu sans pyarrow) :

    # data_version=<sha>            <- ligne de commentaire optionnelle
    date,asset_id,return_cad,return_usd
    2024-01-31,US_MKT,0.0123,0.0101

Une valeur vide = rendement absent (NaN). Format long, une ligne par (mois, actif) observé.
"""
from __future__ import annotations

import csv
import gzip
import io
import math
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

CSV_HEADER = ["date", "asset_id", "return_cad", "return_usd"]
_VERSION_PREFIX = "# data_version="


class LookaheadError(ValueError):
    """Lecture d'un mois postérieur à l'horizon autorisé (biais d'anticipation)."""


def month_end(d) -> pd.Timestamp:
    """'2024-01', '2024-01-15', date, Timestamp -> Timestamp de fin de mois (normalisé, sans heure)."""
    return pd.Timestamp(d).to_period("M").to_timestamp(how="end").normalize()


def _norm_frame(frame: pd.DataFrame) -> pd.DataFrame:
    f = frame.copy()
    f.index = pd.DatetimeIndex([month_end(d) for d in f.index])
    f = f.sort_index()
    f.columns = [str(c) for c in f.columns]
    f = f.reindex(columns=sorted(f.columns))  # colonnes triées par asset_id : ordre stable entre sources
    f.columns.name = None
    return f.astype(float)


class PitReturns:
    """Matrice de rendements mensuels simples (lignes = fins de mois, colonnes = asset_id), NaN avant
    le début d'un actif. ``currency`` est la devise des rendements de ``frame``. ``alt`` (optionnel)
    contient les mêmes rendements dans l'autre devise (CAD <-> USD), conservé pour l'export."""

    def __init__(self, frame: pd.DataFrame, data_version: str, currency: str = "CAD",
                 alt: pd.DataFrame | None = None, horizon=None):
        self.currency = currency.upper()
        if self.currency not in ("CAD", "USD"):
            raise ValueError("currency doit être 'CAD' ou 'USD'")
        self._frame = _norm_frame(frame)
        self._alt = _norm_frame(alt) if alt is not None else None
        self.data_version = str(data_version)
        self._horizon = month_end(horizon) if horizon is not None else None

    # ------------------------------------------------------------------ vue et horizon
    @property
    def horizon(self) -> pd.Timestamp | None:
        """Dernier mois lisible (None = toute la matrice, usage hors tick : export, tests)."""
        return self._horizon

    def with_horizon(self, t) -> PitReturns:
        """Nouvelle vue (données partagées en lecture) qui refuse tout mois > ``t``.
        Un horizon ne peut qu'être resserré : élargir une vue déjà bornée lève LookaheadError."""
        t = month_end(t)
        if self._horizon is not None and t > self._horizon:
            raise LookaheadError(f"horizon {t.date()} au-delà de l'horizon de la vue {self._horizon.date()}")
        v = PitReturns.__new__(PitReturns)
        v.currency, v._frame, v._alt, v.data_version, v._horizon = (
            self.currency, self._frame, self._alt, self.data_version, t)
        return v

    def _check(self, t: pd.Timestamp) -> None:
        if self._horizon is not None and t > self._horizon:
            raise LookaheadError(f"lecture de {t.date()} interdite : horizon point-in-time {self._horizon.date()}")

    @property
    def frame(self) -> pd.DataFrame:
        """Copie de la matrice visible (bornée par l'horizon)."""
        f = self._frame if self._horizon is None else self._frame.loc[: self._horizon]
        return f.copy()

    @property
    def assets(self) -> list[str]:
        return list(self._frame.columns)

    @property
    def first_month(self) -> pd.Timestamp:
        return self._frame.index[0]

    @property
    def last_month(self) -> pd.Timestamp:
        """Dernier mois visible."""
        idx = self._frame.index if self._horizon is None else self._frame.index[self._frame.index <= self._horizon]
        return idx[-1]

    # ------------------------------------------------------------------ lecture
    def upto(self, t) -> pd.DataFrame:
        """Lignes d'index <= fin de mois de ``t`` (copie). LookaheadError si t > horizon."""
        t = month_end(t)
        self._check(t)
        return self._frame.loc[:t].copy()

    def month(self, t) -> pd.Series:
        """Rendements du mois ``t`` (NaN pour un actif non encore coté). KeyError si le mois est absent."""
        t = month_end(t)
        self._check(t)
        if t not in self._frame.index:
            raise KeyError(f"mois {t.date()} absent des données")
        return self._frame.loc[t].copy()

    def months(self, start, end) -> list[pd.Timestamp]:
        """Mois disponibles entre ``start`` et ``end`` inclus. LookaheadError si end > horizon."""
        s, e = month_end(start), month_end(end)
        self._check(e)
        idx = self._frame.index
        return list(idx[(idx >= s) & (idx <= e)])

    def prices(self, t, assets: Iterable[str] | None = None, months: int | None = None) -> pd.DataFrame:
        """Niveaux d'indice cumulés (base 1,0 au mois précédant la première ligne) construits UNIQUEMENT
        avec les rendements <= ``t``. ``months`` = nombre de derniers mois gardés (None = tout).
        La base 1,0 est posée sur la fenêtre retenue : seuls les ratios (moyenne mobile, momentum)
        ont un sens. NaN tant qu'un actif n'a pas de rendement."""
        R = self.upto(t)
        if assets is not None:
            R = R.reindex(columns=list(assets))
        if months is not None:
            R = R.iloc[-int(months):]
        return (1.0 + R).cumprod(skipna=True).where(R.notna())

    # ------------------------------------------------------------------ constructeurs
    @classmethod
    def from_engine(cls, assets: list[str] | None = None, currency: str = "CAD") -> PitReturns:
        """Charge les parquets du moteur de backtest (``finance.backtest.data``). Chaque actif est chargé
        séparément pour garder son propre début (NaN avant), au lieu de l'intersection de ``load_returns``.
        Si ``assets`` est None, les actifs sans donnée dans la devise sont ignorés."""
        from alphaforge.finance.backtest.data import data_version, load_assets, load_returns

        cur = currency.upper()
        other = "USD" if cur == "CAD" else "CAD"
        explicit = assets is not None
        ids = list(assets) if explicit else list(load_assets().index)

        def _load(ccy: str, must: bool) -> pd.DataFrame:
            cols = {}
            for a in ids:
                try:
                    cols[a] = load_returns([a], currency=ccy)[a]
                except ValueError:
                    if must:
                        raise
            return pd.DataFrame(cols).sort_index()

        main = _load(cur, explicit)
        alt = _load(other, False).reindex(columns=main.columns)
        return cls(main, data_version()["data_sha256"], cur, alt=alt)

    @classmethod
    def from_csv_gz(cls, path_or_bytes: str | Path | bytes, currency: str = "CAD") -> PitReturns:
        """Lit l'export ``.csv.gz`` (voir le docstring du module). Std-lib csv + pandas, sans pyarrow."""
        raw = path_or_bytes if isinstance(path_or_bytes, bytes | bytearray) else Path(path_or_bytes).read_bytes()
        text = gzip.decompress(bytes(raw)).decode("utf-8")
        lines = text.splitlines()
        version = ""
        if lines and lines[0].startswith("#"):
            first = lines.pop(0)
            if first.startswith(_VERSION_PREFIX):
                version = first[len(_VERSION_PREFIX):].strip()
        reader = csv.reader(lines)
        header = next(reader, None)
        if header != CSV_HEADER:
            raise ValueError(f"en-tête inattendu {header}, attendu {CSV_HEADER}")
        recs = {"CAD": [], "USD": []}
        for row in reader:
            if not row:
                continue
            d, a, rc, ru = row
            for ccy, v in (("CAD", rc), ("USD", ru)):
                if v.strip() != "":
                    recs[ccy].append((d, a, float(v)))

        def _wide(rs: list) -> pd.DataFrame:
            if not rs:
                return pd.DataFrame(dtype=float)
            df = pd.DataFrame(rs, columns=["date", "asset_id", "r"])
            df["date"] = pd.to_datetime(df["date"])
            return df.pivot(index="date", columns="asset_id", values="r").sort_index()

        cur = currency.upper()
        other = "USD" if cur == "CAD" else "CAD"
        main, alt = _wide(recs[cur]), _wide(recs[other])
        cols = sorted(set(main.columns) | set(alt.columns))
        idx = main.index.union(alt.index)
        main = main.reindex(index=idx, columns=cols)
        alt = alt.reindex(index=idx, columns=cols) if len(alt.columns) else None
        main.columns.name = None
        if alt is not None:
            alt.columns.name = None
        return cls(main, version, cur, alt=alt)

    def to_csv_gz(self, path: str | Path | None = None) -> bytes:
        """Écrit l'export ``.csv.gz`` (toute la matrice visible) ; renvoie les octets, et les écrit dans
        ``path`` s'il est fourni. Valeurs en ``repr`` float (aller-retour exact), lignes triées par
        (date, asset_id), lignes entièrement vides omises. Gzip à mtime=0 : sortie déterministe."""
        main = self.frame
        alt = self._alt
        if alt is not None and self._horizon is not None:
            alt = alt.loc[: self._horizon]
        cad, usd = (main, alt) if self.currency == "CAD" else (alt, main)
        buf = io.StringIO()
        if self.data_version:
            buf.write(f"{_VERSION_PREFIX}{self.data_version}\n")
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(CSV_HEADER)

        def _get(df: pd.DataFrame | None, d, a) -> str:
            if df is None or a not in df.columns or d not in df.index:
                return ""
            v = df.at[d, a]
            return "" if v is None or (isinstance(v, float) and math.isnan(v)) else repr(float(v))

        for d in main.index:
            ds = d.strftime("%Y-%m-%d")
            for a in sorted(main.columns):
                rc, ru = _get(cad, d, a), _get(usd, d, a)
                if rc or ru:
                    w.writerow([ds, a, rc, ru])
        data = gzip.compress(buf.getvalue().encode("utf-8"), mtime=0)
        if path is not None:
            Path(path).write_bytes(data)
        return data

    def __repr__(self) -> str:
        h = self._horizon.date() if self._horizon is not None else None
        return (f"PitReturns({self.currency}, {len(self._frame)} mois x {len(self._frame.columns)} actifs, "
                f"horizon={h}, data_version={self.data_version[:12]})")


__all__ = ["CSV_HEADER", "LookaheadError", "PitReturns", "month_end"]
