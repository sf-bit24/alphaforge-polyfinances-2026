"""Runtime ``portfolio`` : amorçage des données longues (runtime/data/long/) avant le premier import du moteur."""

import hashlib
import json
import os

import pytest

from alphaforge.errors import AppError
from alphaforge.finance.debate import longdata
from alphaforge.store.local import LocalStore


@pytest.fixture
def store(tmp_path):
    return LocalStore(tmp_path / "kb")


@pytest.fixture
def no_local_data(monkeypatch):
    monkeypatch.setattr(longdata, "long_data_available", lambda: False)
    # setitem d'abord : la variable est retirée à la fin du test, même si ensure_long_data l'a posée entre-temps.
    monkeypatch.setitem(os.environ, "ALPHAFORGE_BT_DATA", "")
    monkeypatch.delenv("ALPHAFORGE_BT_DATA")


def publish(store, files, digests=None):
    for name, body in files.items():
        store.put(longdata.KEY_PREFIX + name, body, content_type="application/octet-stream")
    digests = digests or {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}
    manifest = json.dumps({"files": digests, "data_sha256": "x"}).encode()
    store.put(longdata.KEY_PREFIX + longdata.MANIFEST, manifest, content_type="application/json")


def test_long_data_downloaded_and_verified(store, tmp_path, no_local_data):
    files = {n: f"contenu {n}".encode() for n in longdata.LONG_PARQUETS}
    publish(store, files)
    target = longdata.ensure_long_data(store, target=tmp_path / "long")
    assert all((target / n).read_bytes() == b for n, b in files.items())
    assert (target / "assets.csv").is_file()  # métadonnées versionnées copiées du paquet
    assert json.loads((target / "data_version.json").read_text())
    assert os.environ["ALPHAFORGE_BT_DATA"] == str(target)


def test_long_data_with_wrong_sha_is_refused(store, tmp_path, no_local_data):
    files = {n: b"vrai" for n in longdata.LONG_PARQUETS}
    publish(store, files, {n: "0" * 64 for n in files})
    with pytest.raises(longdata.LongDataError, match="sha256"):
        longdata.ensure_long_data(store, target=tmp_path / "long")


def test_missing_manifest_is_a_clear_app_error(store, no_local_data):
    pytest.importorskip("cvxpy")  # sans le groupe finance, l'erreur est « moteur absent » (test_portfolio_service)
    from alphaforge.portfolio_service import FinanceEngine

    with pytest.raises(AppError) as exc:
        FinanceEngine(store).load()
    assert exc.value.code == "internal" and "runtime/data/long/" in exc.value.message
