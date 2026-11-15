"""Actions du runtime d'évolution sur les données longues (sautées sans elles) : rejeu de Robert (profil de test
HYPOTHESE) sur une fenêtre courte, marqueurs, déterminisme du digest et reprise d'un tick par rejeu.

Overlays désactivés pour la vitesse. SIMULATION SEULEMENT : aucun ordre, aucun conseil."""
from __future__ import annotations

import pytest

from alphaforge.finance.contracts.evolution import EVENT_LABEL, ReplayResult, TickResult
from alphaforge.finance.evolution.actions import (
    handle_replay,
    handle_replay_summary,
    handle_tick,
    params_key,
    replay_marker_key,
    tick_marker_key,
    version_key,
)
from alphaforge.finance.evolution.history import HistoryStore, MemoryStore
from alphaforge.finance.evolution.pit import PitReturns

from ..policy._personas import robert

CID = "robert"


@pytest.fixture(scope="module")
def pit() -> PitReturns:
    full = PitReturns.from_engine()
    return PitReturns(full.frame.loc[:"2022-12-31"], full.data_version)     # petite matrice : 5 ans suffisent


def _loader(client_id):
    return robert()


def _replay(store, pit, run_id, start="2021-10", end="2022-03", **extra):
    payload = {"action": "evolution.replay", "client_id": CID, "run_id": run_id, "start": start, "end": end,
               "overlays": False, **extra}
    return handle_replay(payload, store=store, pit=pit, profile_loader=_loader)


def _tick(store, pit, run_id, month, **extra):
    payload = {"action": "evolution.tick", "client_id": CID, "run_id": run_id, "month": month, **extra}
    return handle_tick(payload, store=store, pit=pit, profile_loader=_loader)


@pytest.fixture
def seeded(pit):
    store = MemoryStore()
    resp = _replay(store, pit, "rejeu-1")
    assert resp["ok"] is True, resp
    return store, resp


def test_replay_writes_history_result_and_marker(seeded):
    store, resp = seeded
    assert resp["n_versions"] == 5 and resp["window"] == ["2021-10", "2022-03"]
    assert resp["simulation_only"] is True and resp["label"] == EVENT_LABEL
    assert sum(resp["n_events_by_action"].values()) == 5
    marker = store.get_json(replay_marker_key("rejeu-1"))
    assert marker["status"] == "ok" and marker["error"] is None
    for k in ("run_id", "client_id", "digest", "n_versions", "n_events_by_action", "result_key"):
        assert marker[k] == resp[k]
    assert resp["result_key"] == "clients/robert/portefeuilles/rejeux/rejeu-1.json"
    result = ReplayResult.model_validate(store.get_json(resp["result_key"]))
    assert result.digest == resp["digest"] and result.run_id == "rejeu-1"
    hist = HistoryStore(CID, store)
    assert hist.verify() == (True, None) and len(hist.versions()) == 5
    assert all(v.event.label == EVENT_LABEL for v in hist.versions())
    params = store.get_json(params_key(CID))
    assert params["origin"] == "2021-10" and params["value_cad"] == 900_000 and params["overlays"] is False


def test_replay_digest_stable(seeded, pit):
    store, first = seeded
    again = _replay(store, pit, "rejeu-2")                 # même trajectoire : idempotent, rien d'ajouté
    assert again["ok"] is True and again["digest"] == first["digest"] and again["history"]["appended"] == 0
    fresh = _replay(MemoryStore(), pit, "rejeu-3")
    assert fresh["digest"] == first["digest"]
    retry = _replay(store, pit, "rejeu-1")                 # même run_id : étape déjà finie, aucun recalcul
    assert retry["already_done"] is True and retry["digest"] == first["digest"]
    assert len(HistoryStore(CID, store).index()) == 5


def test_replay_other_trajectory_conflict(seeded, pit):
    store, _ = seeded
    resp = _replay(store, pit, "rejeu-4", start="2021-06")
    assert resp["ok"] is False and resp["error"]["code"] == "conflict"
    assert resp["error"]["details"]["reason"] == "trajectory_exists"
    assert store.get_json(replay_marker_key("rejeu-4"))["status"] == "error"
    assert len(HistoryStore(CID, store).index()) == 5


def test_tick_resumes_next_month(seeded, pit):
    store, _ = seeded
    resp = _tick(store, pit, "mois-1", "2022-04")
    assert resp["ok"] is True, resp
    assert resp["seq"] == 5 and resp["n_versions"] == 6 and resp["already_done"] is False
    assert resp["simulation_only"] is True and resp["label"] == EVENT_LABEL
    marker = store.get_json(tick_marker_key("mois-1", "2022-04"))
    assert marker["status"] == "ok" and marker["version_id"] == resp["version_id"] and "result" not in marker
    tick_res = TickResult.model_validate(store.get_json(resp["result_key"]))
    assert tick_res.version.version_id == resp["version_id"] and str(tick_res.version.as_of) == "2022-04-30"
    hist = HistoryStore(CID, store)
    assert hist.verify() == (True, None) and len(hist.index()) == 6
    # le tick repris = le 6e mois d'un rejeu complet de la même trajectoire
    full = _replay(MemoryStore(), pit, "rejeu-5", end="2022-04")
    assert full["digest"] == resp["digest"]

    # même mois : idempotent (planification de démonstration), rien n'est ajouté
    same = _tick(store, pit, "mois-2", "2022-04")
    assert same["ok"] is True and same["already_done"] is True and same["n_versions"] == 6

    for month in ("2022-06", "2022-02"):                   # mois non consécutifs
        bad = _tick(store, pit, "mois-3", month)
        assert bad["ok"] is False and bad["error"]["code"] == "bad_request"
        assert store.get_json(tick_marker_key("mois-3", month))["status"] == "error"
    assert len(hist.index()) == 6 and hist.verify() == (True, None)

    summary = handle_replay_summary({"action": "evolution.replay_summary", "client_id": CID, "run_id": "x"},
                                    store=store)
    assert summary["ok"] is True and summary["n_versions"] == 6 and summary["chain_ok"] is True
    assert summary["last_as_of"] == "2022-04-30" and summary["last_level"] == tick_res.version.level
    assert summary["last_value_cad"] == tick_res.version.value_cad
    assert sum(summary["n_events_by_action"].values()) == 6


def test_tick_rejects_changed_params(seeded, pit):
    store, _ = seeded
    resp = _tick(store, pit, "mois-4", "2022-04", overlays=True)
    assert resp["ok"] is False and resp["error"]["details"]["reason"] == "trajectory_params"


def test_tick_history_drift(seeded, pit):
    store, _ = seeded
    other = PitReturns(pit.frame, "autre-version-des-donnees")   # mêmes rendements, autre version : digest différent
    resp = _tick(store, other, "mois-5", "2022-04")
    assert resp["ok"] is False and resp["error"]["code"] == "conflict"
    assert resp["error"]["details"]["reason"] == "history_drift"
    assert store.get_json(tick_marker_key("mois-5", "2022-04"))["status"] == "error"
    assert len(HistoryStore(CID, store).index()) == 5


def test_tick_from_empty_history(pit):
    store = MemoryStore()
    first = _tick(store, pit, "t-1", "2021-11", overlays=False)   # origine = 2021-10
    assert first["ok"] is True and first["seq"] == 0, first
    assert store.get_json(params_key(CID))["origin"] == "2021-10"
    second = _tick(store, pit, "t-2", "2021-12")
    assert second["ok"] is True and second["seq"] == 1
    full = _replay(MemoryStore(), pit, "rejeu-6", end="2021-12")
    assert full["digest"] == second["digest"]
    assert HistoryStore(CID, store).verify() == (True, None)


# ------------------------------------------------------------------------------------------- reprise après un arrêt
class _CrashOnce(MemoryStore):
    """« Plante » (RuntimeError) à la première écriture d'une clé finissant par ``suffix`` : arrêt simulé du
    runtime entre deux écritures."""

    def __init__(self, suffix):
        super().__init__()
        self.suffix, self.crashed = suffix, False

    def put(self, key, body, **kwargs):
        if not self.crashed and key.endswith(self.suffix):
            self.crashed = True
            raise RuntimeError(f"arrêt simulé avant {key}")
        return super().put(key, body, **kwargs)


@pytest.fixture(scope="module")
def reference(pit):
    """Rejeu complet 2021-10 → 2022-04 : la 6e version (2022-04) que régénère toute reprise."""
    store = MemoryStore()
    resp = _replay(store, pit, "reference", end="2022-04")
    assert resp["ok"] is True, resp
    return HistoryStore(CID, store).versions(), resp


def test_tick_repairs_index_after_crash(seeded, pit, reference):
    store, _ = seeded
    versions, full = reference
    v5 = versions[5]
    store.put_json(version_key(v5), v5.model_dump(mode="json"))     # .json écrit, arrêt avant .md et index
    resp = _tick(store, pit, "mois-r", "2022-04")
    assert resp["ok"] is True and resp["seq"] == 5 and resp["n_versions"] == 6, resp
    assert resp["digest"] == full["digest"]
    hist = HistoryStore(CID, store)
    assert hist.verify() == (True, None) and len(hist.index()) == 6
    assert store.exists(version_key(v5).removesuffix(".json") + ".md")
    assert store.get_json(tick_marker_key("mois-r", "2022-04"))["status"] == "ok"


def test_tick_orphan_other_content_is_drift(seeded, pit, reference):
    store, _ = seeded
    v5 = reference[0][5]
    store.put_json(version_key(v5), v5.model_copy(update={"value_cad": v5.value_cad + 1}).model_dump(mode="json"))
    resp = _tick(store, pit, "mois-d", "2022-04")
    assert resp["ok"] is False and resp["error"]["code"] == "conflict"
    assert resp["error"]["details"]["reason"] == "history_drift"
    assert len(HistoryStore(CID, store).index()) == 5


def test_replay_resumes_after_crash_before_index(pit, seeded):
    _, first = seeded
    store = _CrashOnce("index.json")                                 # 1er ajout : .json et .md écrits, pas l'index
    crashed = _replay(store, pit, "rejeu-c")
    assert crashed["ok"] is False and crashed["error"]["code"] == "internal"
    assert store.get_json(params_key(CID))["origin"] == "2021-10"   # paramètres écrits avant le premier ajout
    assert HistoryStore(CID, store).index() == []
    retry = _replay(store, pit, "rejeu-c")                           # relance de la machine, même run_id
    assert retry["ok"] is True and retry["history"] == {"n_versions": 5, "appended": 5}, retry
    assert retry["digest"] == first["digest"]
    assert HistoryStore(CID, store).verify() == (True, None)
    assert store.get_json(replay_marker_key("rejeu-c"))["status"] == "ok"


def test_tick_resumes_after_crash_before_first_append(pit):
    store = _CrashOnce("0000-202111.json")                           # arrêt après trajectoire.json, avant la v0
    crashed = _tick(store, pit, "t-c", "2021-11", overlays=False)
    assert crashed["ok"] is False and crashed["error"]["code"] == "internal"
    params = store.get_json(params_key(CID))
    assert params["origin"] == "2021-10" and params["created_by_run_id"] == "t-c"
    other = _tick(store, pit, "t-o", "2021-11", overlays=True)       # autres paramètres : refusés, même sans version
    assert other["ok"] is False and other["error"]["details"]["reason"] == "trajectory_params"
    moved = _replay(store, pit, "r-o", start="2021-06")
    assert moved["ok"] is False and moved["error"]["details"]["reason"] == "trajectory_exists"
    retry = _tick(store, pit, "t-c", "2021-11")                      # paramètres identiques repris
    assert retry["ok"] is True and retry["seq"] == 0, retry
    assert store.get_json(params_key(CID)) == params
    full = _replay(MemoryStore(), pit, "rejeu-7", end="2021-11")
    assert full["digest"] == retry["digest"]
