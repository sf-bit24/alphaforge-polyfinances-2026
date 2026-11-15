"""Amorçage des données longues du moteur de backtest dans le runtime ``portfolio``.

Les parquets reconstruits (``alphaforge/data/long/*.parquet``) ne sont pas versionnés (conditions de certaines
sources, voir ``data/long/SOURCES.md``). Ils sont déposés une fois dans le bucket, sous ``runtime/data/long/``, par
``scripts/finance/upload_long_data.py``, avec un ``manifest.json`` (sha256 de chaque fichier). Au démarrage, le
runtime copie les métadonnées versionnées du paquet et télécharge les parquets dans un répertoire temporaire, vérifie
leurs sha256, puis fixe ``ALPHAFORGE_BT_DATA`` AVANT le premier import du moteur (``backtest.data`` lit ce chemin
une seule fois).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

from alphaforge.finance.backtest.paths import DAILY_PARQUETS, DEFAULT_DATA_DIR, LONG_PARQUETS, long_data_available
from alphaforge.store import Store

logger = logging.getLogger("alphaforge.portfolio")

KEY_PREFIX = "runtime/data/long/"
MANIFEST = "manifest.json"
TARGET = Path(os.environ.get("ALPHAFORGE_BT_DATA_CACHE") or Path(tempfile.gettempdir()) / "alphaforge-long")


class LongDataError(RuntimeError):
    pass


def ensure_long_data(store: Store, prefix: str = KEY_PREFIX, target: Path = TARGET) -> Path:
    """Rend les données longues disponibles ; renvoie le répertoire utilisé. Idempotent."""
    if long_data_available():
        return Path(os.environ.get("ALPHAFORGE_BT_DATA") or DEFAULT_DATA_DIR)
    manifest_obj = store.get(prefix + MANIFEST)
    if manifest_obj is None:
        raise LongDataError(f"données longues absentes : {prefix}{MANIFEST} introuvable dans le magasin")
    manifest = json.loads(manifest_obj.text)
    target.mkdir(parents=True, exist_ok=True)
    for meta in DEFAULT_DATA_DIR.iterdir():  # métadonnées versionnées dans le paquet (assets.csv, data_version.json…)
        if meta.is_file() and meta.suffix in (".csv", ".json", ".md"):
            shutil.copy2(meta, target / meta.name)
    for name in LONG_PARQUETS:
        expected = (manifest.get("files") or {}).get(name)
        obj = store.get(prefix + name)
        if obj is None or not expected:
            raise LongDataError(f"données longues incomplètes : {prefix}{name}")
        digest = hashlib.sha256(obj.body).hexdigest()
        if digest != expected:
            raise LongDataError(f"sha256 inattendu pour {name} : {digest[:12]} au lieu de {expected[:12]}")
        (target / name).write_bytes(obj.body)
    # Données quotidiennes (alphaforge.market) : facultatives, prises seulement si le manifeste les déclare toutes.
    if all((manifest.get("files") or {}).get(n) for n in DAILY_PARQUETS):
        for name in DAILY_PARQUETS:
            obj = store.get(prefix + name)
            digest = hashlib.sha256(obj.body).hexdigest() if obj is not None else None
            if digest != manifest["files"][name]:
                raise LongDataError(f"données quotidiennes absentes ou altérées : {prefix}{name}")
            (target / name).write_bytes(obj.body)
        if manifest.get("daily"):
            version_path = target / "data_version.json"
            version = json.loads(version_path.read_text()) if version_path.is_file() else {}
            version["daily"] = manifest["daily"]
            version_path.write_text(json.dumps(version, indent=2, default=str))
    os.environ["ALPHAFORGE_BT_DATA"] = str(target)
    logger.info("long data ready in %s (data_sha256=%s)", target, manifest.get("data_sha256"))
    return target
