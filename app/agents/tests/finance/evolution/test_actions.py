"""Actions du runtime d'évolution : validation stricte, enveloppe, marqueurs d'erreur, source de marché.

Aucune donnée longue ici : le chargeur de profil et les rendements sont des bouchons qui ne touchent jamais aux
parquets (le rejeu réel est couvert par ``test_data_actions.py``). SIMULATION SEULEMENT."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from alphaforge.errors import AppError
from alphaforge.finance.contracts.evolution import EVENT_LABEL, PortfolioVersion, RebalanceEvent
from alphaforge.finance.evolution import actions as A
from alphaforge.finance.evolution.actions import (
    handle_replay,
    handle_replay_summary,
    handle_tick,
    load_pit,
    params_key,
    replay_marker_key,
    tick_marker_key,
    version_key,
)
from alphaforge.finance.evolution.history import HistoryStore, MemoryStore, version_id
from alphaforge.finance.evolution.pit import PitReturns

from ..policy._personas import robert


class _NoPit:
    """Rendements interdits : tout accès prouve qu'une requête invalide a touché aux données."""

    def __getattr__(self, name):
        raise AssertionError(f"accès aux rendements interdit ({name})")


def _never(client_id):
    raise AssertionError("le profil ne doit pas être chargé")


def _missing(client_id):
    raise KeyError(client_id)


def _tick(payload, store, loader=_never):
    return handle_tick(payload, store=store, pit=_NoPit(), profile_loader=loader)


def _replay(payload, store, loader=_never):
    return handle_replay(payload, store=store, pit=_NoPit(), profile_loader=loader)


def _assert_error(resp, code="bad_request"):
    assert resp["ok"] is False
    assert resp["error"]["code"] == code and resp["error"]["message"]
    assert resp["simulation_only"] is True and resp["label"] == EVENT_LABEL
    assert "release" in resp


TICK = {"action": "evolution.tick", "client_id": "robert", "month": "2022-04", "run_id": "exec-1"}
REPLAY = {"action": "evolution.replay", "client_id": "robert", "run_id": "exec-1"}


# ------------------------------------------------------------------------------------------- tick
@pytest.mark.parametrize("run_id", ["", "a/b", "x" * 65, "run id", 12, None])
def test_tick_bad_run_id_no_marker(run_id):
    store = MemoryStore()
    _assert_error(_tick({**TICK, "run_id": run_id}, store))
    assert store.list("staging/") == []          # clé du marqueur inconnue : rien n'est écrit


@pytest.mark.parametrize("month", ["2022-4", "2022-13", "2022-00", "22-04", "2022-04-30", 202204])
def test_tick_bad_month(month):
    store = MemoryStore()
    _assert_error(_tick({**TICK, "month": month}, store))
    assert store.list("staging/") == []          # mois invalide : chemin du marqueur inconnu


def test_tick_unknown_key_writes_error_marker():
    store = MemoryStore()
    resp = _tick({**TICK, "source": "scheduler"}, store)
    _assert_error(resp)
    assert resp["error"]["details"]["unknown"] == ["source"]
    marker = store.get_json(tick_marker_key("exec-1", "2022-04"))
    assert marker["status"] == "error" and marker["error"].startswith("bad_request:")
    assert marker["run_id"] == "exec-1" and marker["client_id"] == "robert" and marker["month"] == "2022-04"
    assert marker["simulation_only"] is True and marker["label"] == EVENT_LABEL


@pytest.mark.parametrize("client_id", [None, "", "   ", "a/b", "..", "a..b", "-x", 7])
def test_tick_bad_client_id(client_id):
    store = MemoryStore()
    payload = {**TICK, "client_id": client_id} if client_id is not None else {k: v for k, v in TICK.items()
                                                                             if k != "client_id"}
    _assert_error(_tick(payload, store))
    marker = store.get_json(tick_marker_key("exec-1", "2022-04"))
    assert marker["status"] == "error" and marker["client_id"] is None


@pytest.mark.parametrize("extra", [{"value_cad": 0}, {"value_cad": -5.0}, {"value_cad": True}, {"value_cad": "1e6"},
                                   {"value_cad": float("inf")}, {"monthly_flow_cad": float("nan")},
                                   {"monthly_flow_cad": "100"}, {"overlays": "yes"}, {"overlays": 1},
                                   {"persona_label": ""}, {"persona_label": "x" * 121},
                                   {"action": "evolution.replay"}])
def test_tick_bad_optional_fields(extra):
    _assert_error(_tick({**TICK, **extra}, MemoryStore()))


def test_tick_not_a_dict():
    _assert_error(_tick(["evolution.tick"], MemoryStore()))


def test_tick_missing_client_not_found():
    store = MemoryStore()
    resp = _tick(TICK, store, loader=_missing)
    _assert_error(resp, "not_found")
    assert store.get_json(tick_marker_key("exec-1", "2022-04"))["status"] == "error"
    assert store.list("clients/") == []


def test_tick_without_initial_value():
    resp = _tick(TICK, MemoryStore(), loader=lambda cid: robert(investable_wealth=None))
    _assert_error(resp)
    assert resp["error"]["details"]["field"] == "value_cad"


def test_tick_already_done_for_run_id():
    store = MemoryStore()
    store.put_json(tick_marker_key("exec-1", "2022-04"), {"status": "ok", "error": None, "run_id": "exec-1",
                                                          "client_id": "robert", "month": "2022-04", "seq": 5})
    resp = _tick(TICK, store)                    # ni profil ni données : la machine relance une étape finie
    assert resp["ok"] is True and resp["already_done"] is True and resp["seq"] == 5
    assert resp["simulation_only"] is True and resp["label"] == EVENT_LABEL


# ------------------------------------------------------------------------------------------- replay
@pytest.mark.parametrize("field,value", [("start", "2021-1"), ("end", "2021-13"), ("start", 2021)])
def test_replay_bad_window_writes_marker(field, value):
    store = MemoryStore()
    _assert_error(_replay({**REPLAY, field: value}, store))
    marker = store.get_json(replay_marker_key("exec-1"))
    assert marker["status"] == "error" and marker["run_id"] == "exec-1"


def test_replay_unknown_key_and_month_key():
    store = MemoryStore()
    resp = _replay({**REPLAY, "month": "2022-04"}, store)      # « month » n'appartient qu'au tick
    _assert_error(resp)
    assert resp["error"]["details"]["unknown"] == ["month"]


def test_replay_missing_run_id_no_marker():
    store = MemoryStore()
    _assert_error(_replay({k: v for k, v in REPLAY.items() if k != "run_id"}, store))
    assert store.list("staging/") == []


def test_replay_missing_client_not_found():
    store = MemoryStore()
    _assert_error(_replay(REPLAY, store, loader=_missing), "not_found")
    assert store.get_json(replay_marker_key("exec-1"))["error"].startswith("not_found:")


def test_replay_without_initial_value():
    _assert_error(_replay(REPLAY, MemoryStore(), loader=lambda cid: robert(investable_wealth=None)))


# ------------------------------------------------------------------------------------------- synthèse
def test_summary_empty_history():
    resp = handle_replay_summary({"action": "evolution.replay_summary", "client_id": "robert"}, store=MemoryStore())
    assert resp["ok"] is True and resp["n_versions"] == 0 and resp["chain_ok"] is True
    assert resp["last_value_cad"] is None and resp["n_events_by_action"] == {}
    assert resp["simulation_only"] is True and resp["label"] == EVENT_LABEL


@pytest.mark.parametrize("payload", [{}, {"client_id": "a/b"}, {"client_id": "robert", "month": "2022-04"},
                                     {"client_id": "robert", "run_id": "bad id"}])
def test_summary_validation(payload):
    _assert_error(handle_replay_summary(payload, store=MemoryStore()))


# ------------------------------------------------------------------------------------------- source de marché
def _tiny_pit() -> PitReturns:
    idx = pd.date_range("2021-01-31", periods=4, freq="ME")
    return PitReturns(pd.DataFrame({"A": [0.01, -0.02, 0.0, 0.03]}, index=idx), "sha-mini")


def test_load_pit_csv_local_file(tmp_path):
    path = tmp_path / "pit.csv.gz"
    _tiny_pit().to_csv_gz(path)
    pit = load_pit(None, {"ALPHAFORGE_MARKET_URI": str(path)})            # source « csv » implicite avec une URI
    assert pit.data_version == "sha-mini" and pit.last_month == pd.Timestamp("2021-04-30")


def test_load_pit_csv_from_store():
    store = MemoryStore()
    store.put("general/donnees/pit.csv.gz", _tiny_pit().to_csv_gz())
    for uri in ("s3://bucket/general/donnees/pit.csv.gz", "general/donnees/pit.csv.gz"):
        pit = load_pit(store, {"ALPHAFORGE_MARKET_SOURCE": "csv", "ALPHAFORGE_MARKET_URI": uri})
        assert pit.assets == ["A"] and pit.data_version == "sha-mini"


@pytest.mark.parametrize("env,code", [({"ALPHAFORGE_MARKET_SOURCE": "csv"}, "internal"),
                                      ({"ALPHAFORGE_MARKET_SOURCE": "excel"}, "internal"),
                                      ({"ALPHAFORGE_MARKET_URI": "s3://bucket/absent.csv.gz"}, "not_found"),
                                      ({"ALPHAFORGE_MARKET_URI": "s3://bucket"}, "internal")])
def test_load_pit_errors(env, code):
    with pytest.raises(AppError) as exc:
        load_pit(MemoryStore(), env)
    assert exc.value.code == code


# ------------------------------------------------------------------------------------------- marqueur ok définitif
OK_MARKER = {"status": "ok", "error": None, "run_id": "exec-1", "client_id": "robert", "month": "2022-04", "seq": 5}


def test_error_after_success_keeps_ok_marker():
    """Invocation en double (relance sur States.Timeout) : l'autre a réussi pendant qu'elle tournait, puis elle
    échoue. L'erreur revient à l'appelant, le marqueur ok reste intact."""
    store = MemoryStore()

    def concurrent_success_then_fail(client_id):
        store.put_json(tick_marker_key("exec-1", "2022-04"), OK_MARKER)   # l'autre invocation finit maintenant
        raise KeyError(client_id)

    resp = _tick(TICK, store, loader=concurrent_success_then_fail)
    _assert_error(resp, "not_found")
    assert store.get_json(tick_marker_key("exec-1", "2022-04")) == OK_MARKER


class _StaleRead(MemoryStore):
    """Les ``hidden`` premières lectures de ``key`` voient un objet absent (lecture faite avant l'écriture
    concurrente) : seule l'écriture conditionnelle protège alors le marqueur."""

    def __init__(self, key, hidden):
        super().__init__()
        self.key, self.hidden = key, hidden

    def get(self, key):
        if key == self.key and self.hidden > 0:
            self.hidden -= 1
            return None
        return super().get(key)


def test_marker_conditional_put_does_not_overwrite_concurrent_ok():
    key = tick_marker_key("exec-1", "2022-04")
    store = _StaleRead(key, hidden=1)
    store.put_json(key, OK_MARKER)
    A._write_marker(A._Ctx(store, None, None), key, {"status": "error", "error": "conflict: x"})
    assert store.get_json(key) == OK_MARKER     # if_none_match échoue, relecture : ok → abandon


def test_marker_error_then_ok_then_error():
    key = replay_marker_key("exec-1")
    ctx = A._Ctx(MemoryStore(), None, None)
    A._write_marker(ctx, key, {"status": "error", "error": "internal: a"})
    A._write_marker(ctx, key, {"status": "error", "error": "internal: b"})      # une erreur remplace une erreur
    assert ctx.store.get_json(key)["error"] == "internal: b"
    A._write_marker(ctx, key, {"status": "ok", "error": None, "seq": 1})        # un succès remplace une erreur
    A._write_marker(ctx, key, {"status": "error", "error": "conflict: c"})
    A._write_marker(ctx, key, {"status": "ok", "error": None, "seq": 2})        # premier succès définitif
    doc = ctx.store.get_json(key)
    assert doc["status"] == "ok" and doc["seq"] == 1 and doc["simulation_only"] is True


# ------------------------------------------------------------------------------------------- flux mensuel
@pytest.mark.parametrize("handler", [_tick, _replay])
def test_withdrawal_larger_than_value_rejected_early(handler):
    payload = {**(TICK if handler is _tick else REPLAY), "value_cad": 1_000.0, "monthly_flow_cad": -1_000.01}
    resp = handler(payload, MemoryStore())                  # ni profil ni données touchés
    _assert_error(resp)
    assert resp["error"]["details"]["field"] == "monthly_flow_cad"


@pytest.mark.parametrize("handler", [_tick, _replay])
def test_withdrawal_larger_than_profile_value_rejected(handler):
    payload = {**(TICK if handler is _tick else REPLAY), "monthly_flow_cad": -1_000_000.0}
    resp = handler(payload, MemoryStore(), loader=lambda cid: robert())    # 900 000 $ (profil de test)
    _assert_error(resp)                                     # avant tout accès aux rendements (_NoPit)
    assert resp["error"]["details"] == {"field": "monthly_flow_cad", "monthly_flow_cad": -1_000_000.0,
                                        "value_cad": 900_000.0}


def test_withdrawal_equal_to_value_passes_validation():
    resp = _tick({**TICK, "value_cad": 1_000.0, "monthly_flow_cad": -1_000.0}, MemoryStore(), loader=_missing)
    _assert_error(resp, "not_found")                        # validation passée : le profil est cherché


# ------------------------------------------------------------------------------------------- paramètres sans version
PARAMS = {"origin": "2022-03", "value_cad": 900_000.0, "monthly_flow_cad": 0.0, "overlays": False,
          "created_by_run_id": "exec-0"}


@pytest.mark.parametrize("extra,field", [({"month": "2022-06"}, "origin"), ({"value_cad": 1_000.0}, "value_cad"),
                                         ({"overlays": True}, "overlays")])
def test_tick_params_without_history_must_match(extra, field):
    """Arrêt après ``trajectoire.json`` et avant le premier ajout : les paramètres restent la définition."""
    store = MemoryStore()
    store.put_json(params_key("robert"), PARAMS)
    resp = _tick({**TICK, **extra}, store)                  # ni profil ni données touchés
    _assert_error(resp, "conflict")
    assert resp["error"]["details"]["reason"] == "trajectory_params"
    assert resp["error"]["details"]["fields"] == [field]
    assert store.get_json(params_key("robert")) == PARAMS


def test_ensure_params_idempotent_and_conflict():
    ctx = A._Ctx(MemoryStore(), None, None)
    p = {k: PARAMS[k] for k in A._PARAM_FIELDS}
    A._ensure_params(ctx, "robert", p, "run-a")
    A._ensure_params(ctx, "robert", p, "run-b")             # mêmes paramètres : accepté, rien n'est réécrit
    assert ctx.store.get_json(params_key("robert"))["created_by_run_id"] == "run-a"
    with pytest.raises(AppError) as exc:
        A._ensure_params(ctx, "robert", {**p, "value_cad": 1.0}, "run-c")
    assert exc.value.code == "conflict" and exc.value.details["reason"] == "trajectory_exists"


# ------------------------------------------------------------------------------------------- réparation de l'index
CID = "robert"


def _version(seq: int, parent: str | None, month: int, value: float = 10_000.0) -> PortfolioVersion:
    """Version synthétique (poids, niveau et hashes arbitraires de test)."""
    as_of = date(2024, month, 28)
    vid = version_id(CID, seq, as_of)
    ev = RebalanceEvent(event_id=f"ev-{vid}", month=as_of, action="HOLD", drift=0.01)
    return PortfolioVersion(version_id=vid, parent_version_id=parent, seq=seq, client_id=CID, profile_version=1,
                            as_of=as_of, weights={"EQ": 0.6, "BD": 0.4}, value_cad=value,
                            target={"EQ": 0.6, "BD": 0.4}, level="N2", policy_hash="p" * 8,
                            data_version="test", config_hash="c" * 8, event=ev)


def _chain(n: int) -> list[PortfolioVersion]:
    out, parent = [], None
    for s in range(n):
        out.append(_version(s, parent, s + 1, 10_000.0 + 100 * s))
        parent = out[-1].version_id
    return out


def _crash_before_index(store, v: PortfolioVersion, *, with_md: bool = False) -> None:
    """Arrêt simulé dans ``HistoryStore.append`` : le .json (et éventuellement le .md) écrit, pas l'index."""
    store.put_json(version_key(v), v.model_dump(mode="json"))
    if with_md:
        store.put_text(version_key(v).removesuffix(".json") + ".md", "résumé d'avant l'arrêt")


@pytest.mark.parametrize("n_before", [0, 2])
@pytest.mark.parametrize("with_md", [False, True])
def test_append_repairs_index_after_crash(n_before, with_md):
    chain = _chain(n_before + 2)
    hist = HistoryStore(CID, MemoryStore())
    for v in chain[:n_before]:
        hist.append(v)
    orphan = chain[n_before]
    _crash_before_index(hist.store, orphan, with_md=with_md)
    assert A._append(hist, orphan) is True                  # réparé, pas d'erreur « version déjà écrite »
    assert hist.verify() == (True, None) and len(hist.index()) == n_before + 1
    md = hist.store.get(version_key(orphan).removesuffix(".json") + ".md").text
    assert (md == "résumé d'avant l'arrêt") is with_md      # .md réécrit s'il manque, jamais écrasé
    ref = HistoryStore(CID, MemoryStore())                  # même entrée d'index qu'un ajout sans arrêt
    for v in chain[:n_before + 1]:
        ref.append(v)
    assert hist.index() == ref.index()
    assert A._append(hist, chain[n_before + 1]) is False    # la chaîne continue normalement
    assert hist.verify() == (True, None)


def test_append_orphan_with_other_content_is_drift():
    chain = _chain(3)
    hist = HistoryStore(CID, MemoryStore())
    for v in chain[:2]:
        hist.append(v)
    _crash_before_index(hist.store, chain[2].model_copy(update={"value_cad": 1.0}))
    before = hist.store.get(version_key(chain[2])).body
    with pytest.raises(AppError) as exc:
        A._append(hist, chain[2])
    assert exc.value.code == "conflict" and exc.value.details["reason"] == "history_drift"
    assert exc.value.details["stored_version_hash"] != exc.value.details["replayed_version_hash"]
    assert len(hist.index()) == 2 and hist.store.get(version_key(chain[2])).body == before


def test_append_orphan_out_of_sequence_refused():
    chain = _chain(3)
    hist = HistoryStore(CID, MemoryStore())
    hist.append(chain[0])
    _crash_before_index(hist.store, chain[2])               # seq 2 alors que la tête est seq 0
    with pytest.raises(AppError) as exc:
        A._append(hist, chain[2])
    assert exc.value.details["reason"] == "history_append" and len(hist.index()) == 1


# ---------------------------------------------------------------- personas de démonstration (PR #47)
def test_persona_maps_to_demo_client_id():
    from alphaforge.finance.evolution import actions as A

    req = A._parse({"action": A.ACTION_REPLAY, "persona": "amira", "run_id": "r1"}, A.ACTION_REPLAY,
                   A.REPLAY_KEYS, ("client_id", "run_id"))
    assert req.client_id == "demo-amira" and req.persona == "amira"


def test_demo_client_id_from_state_machine_is_a_persona():
    from alphaforge.finance.evolution import actions as A

    req = A._parse({"action": A.ACTION_REPLAY, "client_id": "demo-robert", "run_id": "r1"}, A.ACTION_REPLAY,
                   A.REPLAY_KEYS, ("client_id", "run_id"))
    assert req.persona == "robert"


@pytest.mark.parametrize("payload", [
    {"persona": "amira", "client_id": "c1", "run_id": "r1"},
    {"persona": "inconnue", "run_id": "r1"},
])
def test_persona_misuse_is_refused(payload):
    from alphaforge.errors import AppError
    from alphaforge.finance.evolution import actions as A

    with pytest.raises(AppError) as exc:
        A._parse({"action": A.ACTION_REPLAY, **payload}, A.ACTION_REPLAY, A.REPLAY_KEYS, ("client_id", "run_id"))
    assert exc.value.code == "bad_request"
