"""Exporte les rendements mensuels longs au format lu par le runtime (``PitReturns.from_csv_gz``).

Usage (depuis app/agents) :
    uv run python -I scripts/export_pit.py [--out build/market/pit_<data_sha>.csv.gz] [--assets A,B,...]

Format (fixe, contrat avec ``alphaforge.finance.evolution.pit``) :
- CSV compresse gzip, premiere ligne facultative ``# data_version=<sha>`` ;
- en-tete ``date,asset_id,return_cad,return_usd`` ;
- ``date`` = fin de mois ISO AAAA-MM-JJ ; une ligne par (mois, actif) dont au moins un rendement existe
  (l'autre devise reste vide : pas de rendement CAD avant les donnees USDCAD de 1971-02, pas de rendement
  USD des actifs CAD avant cette date ; aucun remplissage de change, ``fx_fill="none"``) ;
- tri par date puis asset_id.

Le fichier gzip est deterministe (mtime 0, sans nom) : meme jeu de donnees -> meme sha256.
Un manifeste JSON est ecrit a cote. Aucun envoi vers S3 : la commande ``aws s3 cp`` est seulement affichee.
Licence : une partie des donnees vient de yfinance/Stooq (recherche seulement, pas de redistribution publique).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from alphaforge.finance.backtest.data import DATA_DIR, data_version, load_assets, load_returns

AGENTS_DIR = Path(__file__).resolve().parents[1]  # app/agents
HEADER = ["date", "asset_id", "return_cad", "return_usd"]
LICENCE = "yfinance/Stooq: recherche seulement, pas de redistribution publique"


def _series(asset: str, currency: str) -> pd.Series:
    """Rendements mensuels d'un actif dans une devise ; vide si la devise n'a aucune donnee."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = load_returns([asset], currency=currency, fx_fill="none")
    except ValueError:
        return pd.Series(dtype="float64", name=asset)
    return df[asset]


def build_frame(assets: list[str]) -> pd.DataFrame:
    parts = []
    for a in assets:
        cad = _series(a, "CAD").rename("return_cad")
        usd = _series(a, "USD").rename("return_usd")
        both = pd.concat([cad, usd], axis=1, sort=True).dropna(how="all")
        if both.empty:
            continue
        both.index.name = "date"
        both = both.reset_index()
        both.insert(1, "asset_id", a)
        parts.append(both)
    if not parts:
        raise SystemExit("aucun rendement exporte")
    out = pd.concat(parts, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    return out.sort_values(["date", "asset_id"], kind="mergesort").reset_index(drop=True)[HEADER]


def write_gz(df: pd.DataFrame, path: Path, data_sha: str) -> bytes:
    text = io.StringIO()
    text.write(f"# data_version={data_sha}\n")
    df.to_csv(text, index=False, lineterminator="\n")
    raw = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as gz:
        gz.write(text.getvalue().encode("utf-8"))
    blob = raw.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return blob


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="fichier de sortie (defaut : build/market/pit_<data_sha>.csv.gz sous app/agents)",
    )
    ap.add_argument(
        "--assets", default=None, help="liste d'asset_id separes par des virgules (defaut : tout le catalogue)"
    )
    args = ap.parse_args(argv)

    version = data_version()
    data_sha = version["data_sha256"]
    catalogue = list(load_assets().index)
    assets = [a.strip() for a in args.assets.split(",") if a.strip()] if args.assets else catalogue
    unknown = sorted(set(assets) - set(catalogue))
    if unknown:
        ap.error(f"asset_id inconnus : {unknown}")

    out = args.out or AGENTS_DIR / "build" / "market" / f"pit_{data_sha}.csv.gz"
    df = build_frame(assets)
    blob = write_gz(df, out, data_sha)
    sha = hashlib.sha256(blob).hexdigest()

    manifest = {
        "file": out.name,
        "format": "gzip csv; '# data_version=<sha>' puis date,asset_id,return_cad,return_usd; tri date, asset_id",
        "rows": int(len(df)),
        "assets": int(df["asset_id"].nunique()),
        "asset_ids": sorted(df["asset_id"].unique().tolist()),
        "first_month": df["date"].iloc[0],
        "last_month": df["date"].iloc[-1],
        "rows_missing_cad": int(df["return_cad"].isna().sum()),
        "rows_missing_usd": int(df["return_usd"].isna().sum()),
        "fx_fill": "none",
        "bytes": len(blob),
        "sha256": sha,
        "data_version": version,
        "source_dir": str(DATA_DIR),
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "licence": LICENCE,
    }
    manifest_path = out.with_name(out.name.removesuffix(".csv.gz") + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(
        f"{out} : {manifest['rows']} lignes, {manifest['assets']} actifs, "
        f"{manifest['first_month']} -> {manifest['last_month']}, {len(blob)} octets, sha256 {sha}"
    )
    print(f"manifeste : {manifest_path}")
    print("Envoi (non effectue, a lancer a la main ; licence : pas de redistribution publique) :")
    print(f"  aws s3 cp {out} s3://<bucket>/market/{out.name}")
    print(f"  aws s3 cp {manifest_path} s3://<bucket>/market/{manifest_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
