"""Dépose les données longues du moteur de backtest dans le bucket des bases, pour le runtime ``portfolio``.

Usage (identifiants AWS de l'équipe dans l'environnement) :
    uv run --group finance python scripts/finance/upload_long_data.py --bucket <ALPHAFORGE_BUCKET> [--data-dir DIR]

Les parquets (non versionnés, voir src/alphaforge/data/long/SOURCES.md) sont reconstruits localement par
``python -m alphaforge.finance.backtest.build_data`` puis déposés sous ``runtime/data/long/`` avec un
``manifest.json`` (sha256 de chaque fichier, data_sha256 du build). Le runtime vérifie ces sha256 au démarrage
(``alphaforge.finance.debate.longdata``). Rien n'est exécuté ni redistribué hors du compte de l'équipe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

PREFIX = "runtime/data/long/"


def main() -> None:
    from alphaforge.finance.backtest.paths import LONG_PARQUETS, data_dir

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bucket", default=os.environ.get("ALPHAFORGE_BUCKET"), required=False)
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--region", default=os.environ.get("ALPHAFORGE_REGION", "us-east-1"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.bucket:
        ap.error("--bucket (ou ALPHAFORGE_BUCKET) est requis")
    src = args.data_dir or data_dir()
    files = {}
    for name in LONG_PARQUETS:
        path = src / name
        if not path.is_file():
            raise SystemExit(f"absent : {path} (lancer python -m alphaforge.finance.backtest.build_data)")
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    version = json.loads((src / "data_version.json").read_text()) if (src / "data_version.json").is_file() else {}
    manifest = {"files": files, "data_sha256": version.get("data_sha256"), "built_utc": version.get("built_utc")}
    print(json.dumps(manifest, indent=1))
    if args.dry_run:
        return
    import boto3

    s3 = boto3.client("s3", region_name=args.region)
    for name in LONG_PARQUETS:
        s3.put_object(Bucket=args.bucket, Key=PREFIX + name, Body=(src / name).read_bytes())
    s3.put_object(
        Bucket=args.bucket,
        Key=PREFIX + "manifest.json",
        Body=json.dumps(manifest).encode(),
        ContentType="application/json",
    )
    print(f"déposé : s3://{args.bucket}/{PREFIX} ({len(files)} parquets + manifest.json)")


if __name__ == "__main__":
    main()
