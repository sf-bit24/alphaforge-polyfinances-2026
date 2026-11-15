"""Tick mensuel sur données SYNTHÉTIQUES (sans données longues) : moteur F1 → F4 et Judge remplacés par des stubs.

Univers fictif A/B/C, cibles et rendements arbitraires de test (aucun n'est tiré d'une fiche persona ni des marchés).
- ``build_fn`` : stub qui rend une cible fixe par niveau ;
- ``alphaforge.finance.policy.compile_profile`` : stub (importé dans ``tick`` à l'exécution) qui rend ``.level`` ;
- ``tick._judge`` : stub « approuvé » (le vrai Judge lit les parquets de l'engine).
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import alphaforge.finance.policy as policy_pkg
from alphaforge.finance.contracts import PolicySpec
from alphaforge.finance.contracts.evolution import TriggerFired
from alphaforge.finance.contracts.profile import Goal, Income, InvestorProfile, Score
from alphaforge.finance.evolution import tick as T
from alphaforge.finance.evolution.bands import band_width
from alphaforge.finance.evolution.config import load_config
from alphaforge.finance.evolution.drift import drift_metric, mark_to_market
from alphaforge.finance.evolution.history import HistoryStore, version_id
from alphaforge.finance.evolution.pit import LookaheadError, PitReturns

CFG = load_config()
CLIENT = "client-synthetique"
ORIGIN = date(2020, 1, 31)
M1, M2 = "2020-02-29", "2020-03-31"
ASSETS = ["A", "B", "C"]
V0 = 100_000.0
TARGET = {"A": 0.50, "B": 0.30, "C": 0.20}          # niveau N3 (stub)
TARGET_N2 = {"A": 0.30, "B": 0.40, "C": 0.30}       # niveau plus bas (stub)
TARGET_N4 = {"A": 0.80, "B": 0.10, "C": 0.10}       # niveau plus haut (stub)
BIG_DRIFT = {"A": 0.30, "B": -0.10, "C": 0.0}       # A et B sortent de leur bande
POLICY = PolicySpec(policy_id="test", profile_id="test", profile_version=1,
                    created_utc=datetime(2026, 11, 15, tzinfo=UTC), universe=ASSETS)
APPROVED = SimpleNamespace(approved=True, blocking_violations=())


def _profile() -> InvestorProfile:
    return InvestorProfile(
        profile_id="test", created_utc=datetime(2020, 1, 1, tzinfo=UTC), status="COMPLETE", age=45,
        knowledge_level="intermediaire",
        goals=[Goal(goal_id="long_terme", label="long terme", priority="souhait", horizon_years=15)],
        tolerance_declared=Score(value=60, confidence=0.7), tolerance_tested=Score(value=60, confidence=0.7),
        composure=Score(value=60), investable_wealth=V0, monthly_expenses=5_000, emergency_fund_months=6,
        income=Income(annual_amount=120_000, variability="stable"),
    )


class Engine:
    """Stub du moteur : ``level`` est le niveau que rend compile_profile ; build rend la cible de ce niveau."""

    def __init__(self) -> None:
        self.level = "N3"
        self.targets = {"N2": TARGET_N2, "N3": TARGET, "N4": TARGET_N4}
        self.build_calls: list[date] = []

    def compile(self, profile, as_of):
        return SimpleNamespace(level=self.level, policy=POLICY, horizon_years=None, trace=[])

    def build(self, profile, as_of) -> T.BuildOutcome:
        self.build_calls.append(as_of)
        return T.BuildOutcome(target=dict(self.targets[self.level]), policy=POLICY, level=self.level, decision=None)


@pytest.fixture
def engine(monkeypatch) -> Engine:
    eng = Engine()
    monkeypatch.setattr(T, "_judge", lambda *a, **k: APPROVED)
    monkeypatch.setattr(policy_pkg, "compile_profile", eng.compile)
    return eng


def _frame(moves: dict[str, dict[str, float]] | None = None, n: int = 24) -> pd.DataFrame:
    idx = pd.date_range("2020-01-31", periods=n, freq="ME")
    f = pd.DataFrame(0.0, index=idx, columns=ASSETS)
    for m, row in (moves or {}).items():
        for a, r in row.items():
            f.loc[pd.Timestamp(m), a] = r
    return f


def _random_frame(seed: int = 7, n: int = 24) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-31", periods=n, freq="ME")
    return pd.DataFrame(rng.normal(0.005, 0.04, (n, len(ASSETS))), index=idx, columns=ASSETS)


def _start(engine: Engine, frame: pd.DataFrame, cfg=CFG, history=None) -> T.Trajectory:
    return T.start(CLIENT, _profile(), ORIGIN, V0, PitReturns(frame, data_version="test"), cfg,
                   build_fn=engine.build, history=history)


def _drifted(r: dict[str, float], w=TARGET) -> tuple[dict[str, float], float]:
    wd, gross, _ = mark_to_market(w, {a: r.get(a, 0.0) for a in w})
    return wd, gross


# ---------------------------------------------------------------- (a) HOLD dans les bandes
def test_hold_when_inside_bands(engine):
    r = {"A": 0.01, "C": -0.01}
    traj = _start(engine, _frame({M1: r}))
    out = T.tick(traj, M1)
    ev, v = out.version.event, out.version
    wd, gross = _drifted(r)
    assert all(abs(wd[a] - TARGET[a]) <= band_width(TARGET[a], CFG.bands) for a in TARGET)  # prémisse
    assert ev.action == "HOLD"
    assert ev.trades == [] and ev.breaches == []
    assert ev.turnover_oneway == ev.turnover_twoway == ev.cost_cad == 0.0
    assert v.weights == pytest.approx(wd, abs=1e-12)               # poids dérivés, aucun mouvement
    assert v.value_cad == pytest.approx(V0 * (1 + gross), abs=0.01)
    assert v.target == pytest.approx(TARGET)
    assert ev.judge_before == ev.judge_after == "approuve"
    assert len(engine.build_calls) == 1                             # la cible n'est pas recalculée


def test_quiet_months_all_hold(engine):
    traj = _start(engine, _frame())
    outs = [T.tick(traj, m) for m in pd.date_range(M1, periods=6, freq="ME")]
    assert [o.version.event.action for o in outs] == ["HOLD"] * 6
    assert all(o.version.event.trades == [] for o in outs)
    assert traj.perf.costs_cad_cum == 0.0 and traj.value_cad == pytest.approx(V0)


# ---------------------------------------------------------------- (b) dérive forte -> retour à mi-chemin
def test_large_drift_rebalances_half_way(engine):
    assert CFG.bands.trade_mode == "half"
    traj = _start(engine, _frame({M1: BIG_DRIFT}))
    out = T.tick(traj, M1)
    ev, w = out.version.event, out.version.weights
    wd, gross = _drifted(BIG_DRIFT)
    value = V0 * (1 + gross)
    assert ev.action == "REBALANCE_TO_BANDS"
    assert ev.breaches == ["A", "B"]
    assert ev.drift == pytest.approx(drift_metric(wd, TARGET), abs=1e-9)
    for a in TARGET:
        lo, hi = sorted((wd[a], TARGET[a]))
        assert lo < w[a] < hi, a                                     # strictement entre dérivé et cible
        assert w[a] == pytest.approx(wd[a] + 0.5 * (TARGET[a] - wd[a]), abs=1e-9)
        assert abs(w[a] - TARGET[a]) <= band_width(TARGET[a], CFG.bands)  # revenu dans sa bande
    assert {t.asset_id for t in ev.trades} == set(TARGET)
    assert all(t.reason == "band" for t in ev.trades)
    assert sum(t.dw for t in ev.trades) == pytest.approx(0.0, abs=1e-12)
    for t in ev.trades:
        assert t.w_from == pytest.approx(wd[t.asset_id]) and t.amount_cad == pytest.approx(t.dw * value, abs=0.01)
    assert {f"ev.202002.bande.{a}" for a in ev.breaches} <= set(ev.fact_ids)


# ---------------------------------------------------------------- (c) apport vers les lignes sous-pondérées
def _holdings(weights: dict[str, float], value: float) -> dict[str, float]:
    return {a: weights.get(a, 0.0) * value for a in TARGET}


def test_contribution_goes_to_underweight_lines(engine):
    r = {"A": 0.04, "B": -0.04}
    flow = 1_000.0
    traj = _start(engine, _frame({M1: r}))
    out = T.tick(traj, M1, flow_cad=flow)
    ev, v = out.version.event, out.version
    wd, gross = _drifted(r)
    before = _holdings(wd, V0 * (1 + gross))
    after = _holdings(v.weights, v.value_cad)
    added = {a: after[a] - before[a] for a in TARGET}
    assert ev.action == "HOLD" and ev.trades == [] and ev.flow_cad == flow
    assert wd["A"] > TARGET["A"] and wd["B"] < TARGET["B"] and wd["C"] < TARGET["C"]  # prémisse
    assert added["A"] == pytest.approx(0.0, abs=0.05)               # la ligne sur-pondérée ne reçoit rien
    assert added["B"] > added["C"] > 0                              # la plus sous-pondérée reçoit le plus
    assert sum(added.values()) == pytest.approx(flow, abs=0.05)
    assert drift_metric(v.weights, TARGET) < drift_metric(wd, TARGET)  # l'apport réduit la dérive sans opération
    assert traj.perf.flows == [flow]


def test_contribution_pro_rata_when_disabled(engine):
    cfg = CFG.model_copy(update={"flows": CFG.flows.model_copy(update={"contribution_first": False})})
    r = {"A": 0.04, "B": -0.04}
    flow = 1_000.0
    traj = _start(engine, _frame({M1: r}), cfg=cfg)
    out = T.tick(traj, M1, flow_cad=flow)
    wd, gross = _drifted(r)
    added = {a: x - y for (a, x), y in zip(_holdings(out.version.weights, out.version.value_cad).items(),
                                          _holdings(wd, V0 * (1 + gross)).values(), strict=True)}
    for a in TARGET:
        assert added[a] == pytest.approx(flow * TARGET[a], abs=0.05)


# ---------------------------------------------------------------- (d) point-in-time
def test_tick_identical_with_or_without_future_months(engine):
    t = pd.Timestamp("2020-08-31")
    base = _random_frame()
    with_future = base.copy()
    with_future.loc[with_future.index > t, :] = 5.0                  # futur absurde : ne doit rien changer
    truncated = base.loc[:t]
    months = [m for m in truncated.index if m > pd.Timestamp(ORIGIN)]
    runs = []
    for frame in (with_future, truncated):
        traj = _start(engine, frame)
        runs.append([T.tick(traj, m, flow_cad=500.0 if m.month % 3 == 0 else 0.0) for m in months])
    for a, b in zip(*runs, strict=True):
        assert a.version.model_dump(mode="json") == b.version.model_dump(mode="json")
        assert [f.model_dump(mode="json") for f in a.facts] == [f.model_dump(mode="json") for f in b.facts]
        assert a.triggers == b.triggers and a.proxied == b.proxied


def test_tick_beyond_view_horizon_raises(engine):
    traj = _start(engine, _frame())
    traj.pit = traj.pit.with_horizon(M2)
    T.tick(traj, M1)
    T.tick(traj, M2)
    seq = traj.seq
    with pytest.raises(LookaheadError):
        T.tick(traj, "2020-04-30")
    assert traj.seq == seq                                            # rien n'a été écrit


# ---------------------------------------------------------------- (e) déclencheur bloquant
FIRED = TriggerFired(code="DRAWDOWN_LIMIT", blocking=True, value=0.3, threshold=0.2,
                     threshold_source="profile.max_acceptable_loss_pct", message_fr="Baisse au-delà du seuil (test).")


def test_blocking_trigger_requires_reprofile_without_trades(engine, monkeypatch):
    monkeypatch.setattr(T, "evaluate", lambda state, cfg: [FIRED])
    traj = _start(engine, _frame({M1: BIG_DRIFT}))
    out = T.tick(traj, M1)
    ev = out.version.event
    wd, _ = _drifted(BIG_DRIFT)
    assert ev.action == "REPROFILE_REQUIRED"
    assert ev.breaches == ["A", "B"]                                  # bandes dépassées, et pourtant...
    assert ev.trades == []                                            # ... aucune opération simulée
    assert ev.turnover_oneway == ev.turnover_twoway == ev.cost_cad == 0.0
    assert out.version.weights == pytest.approx(wd, abs=1e-12)
    assert traj.reprofile_pending
    assert out.triggers == [FIRED] and ev.triggers == [FIRED]
    assert "ev.202002.declencheur.DRAWDOWN_LIMIT" in {f.fact_id for f in out.facts}
    assert len(engine.build_calls) == 1


def test_blocking_trigger_wins_over_level_change(engine, monkeypatch):
    monkeypatch.setattr(T, "evaluate", lambda state, cfg: [FIRED])
    traj = _start(engine, _frame())
    engine.level = "N2"
    out = T.tick(traj, M1)
    assert out.version.event.action == "REPROFILE_REQUIRED"
    assert out.version.event.trades == [] and len(engine.build_calls) == 1


def test_level_drop_during_reprofile_is_applied_next_month(engine, monkeypatch):
    real = T.evaluate
    blocking = {"on": True}
    monkeypatch.setattr(T, "evaluate", lambda s, c: [*real(s, c), *([FIRED] if blocking["on"] else [])])
    traj = _start(engine, _frame())
    engine.level = "N2"
    assert T.tick(traj, M1).version.event.action == "REPROFILE_REQUIRED"
    blocking["on"] = False                                            # profil reconfirmé sans changement
    out = T.tick(traj, M2)
    assert out.version.target == pytest.approx(TARGET_N2)
    assert out.version.weights == pytest.approx(TARGET_N2, abs=1e-9)


# ---------------------------------------------------------------- (f) changement de niveau -> REOPTIMIZE
def test_level_drop_reoptimizes_fully_with_build_fn(engine):
    traj = _start(engine, _frame())
    engine.level = "N2"
    out = T.tick(traj, M1)
    ev, v = out.version.event, out.version
    assert ev.action == "REOPTIMIZE"
    assert engine.build_calls == [ORIGIN, date(2020, 2, 29)]
    assert v.weights == pytest.approx(TARGET_N2, abs=1e-12)          # d'un coup, sans budget de rotation
    assert v.target == pytest.approx(TARGET_N2)
    assert v.level == traj.level == "N2"
    assert all(t.reason == "glidepath" for t in ev.trades)
    full = sum(abs(TARGET_N2[a] - TARGET[a]) for a in TARGET)
    assert full > CFG.trading.max_turnover_tick and ev.turnover_twoway == pytest.approx(full)
    lvl = [t for t in out.triggers if t.code == "HORIZON_LEVEL_CHANGE"]
    assert lvl and lvl[0].value == "N2" and lvl[0].threshold == "N3" and not lvl[0].blocking
    nxt = T.tick(traj, M2)                                            # plus de changement : pas de re-calcul
    assert nxt.version.event.action == "HOLD" and len(engine.build_calls) == 2


def test_level_rise_glides_within_turnover_budget(engine):
    traj = _start(engine, _frame())
    engine.level = "N4"
    out = T.tick(traj, M1)
    ev, w = out.version.event, out.version.weights
    cap = CFG.trading.max_turnover_tick
    full = sum(abs(TARGET_N4[a] - TARGET[a]) for a in TARGET)
    assert ev.action == "REOPTIMIZE" and full > cap
    assert ev.turnover_twoway <= cap + 1e-9 and ev.turnover_twoway == pytest.approx(cap)
    k = cap / full
    for a in TARGET:
        assert w[a] == pytest.approx(TARGET[a] + k * (TARGET_N4[a] - TARGET[a]), abs=1e-9)
    assert out.version.target == pytest.approx(TARGET_N4)


# ---------------------------------------------------------------- (g) chaîne de versions
def test_version_chain(engine):
    hist = HistoryStore(CLIENT)
    frame = _random_frame(seed=3)
    traj = _start(engine, frame, history=hist)
    outs = [T.tick(traj, m, flow_cad=250.0) for m in frame.index[1:9]]
    for i, o in enumerate(outs):
        v = o.version
        assert v.seq == i
        assert v.parent_version_id == (None if i == 0 else outs[i - 1].version.version_id)
        assert v.version_id == version_id(CLIENT, i, v.as_of)
        assert v.event.event_id == f"ev-{v.version_id}"
        assert sum(v.weights.values()) == pytest.approx(1.0, abs=1e-9) and min(v.weights.values()) >= 0
        assert sum(v.target.values()) == pytest.approx(1.0, abs=1e-9)
        assert v.status == "FICTION" and v.data_version == "test" and v.config_hash == CFG.sha256
        assert v.policy_hash == outs[0].version.policy_hash
    assert [o.version.as_of for o in outs] == [m.date() for m in frame.index[1:9]]
    assert traj.seq == len(outs) - 1 and traj.last_version_id == outs[-1].version.version_id
    assert hist.verify() == (True, None)
    assert [v.version_id for v in hist.versions()] == [o.version.version_id for o in outs]


# ---------------------------------------------------------------- (h) coût
@pytest.mark.parametrize("bps", [10.0, 25.0])
def test_cost_is_bps_times_oneway_turnover_times_value(engine, bps):
    cfg = CFG.model_copy(update={"trading": CFG.trading.model_copy(update={"cost_bps": bps})})
    traj = _start(engine, _frame({M1: BIG_DRIFT}), cfg=cfg)
    out = T.tick(traj, M1)
    ev, v = out.version.event, out.version
    _, gross = _drifted(BIG_DRIFT)
    value = V0 * (1 + gross)
    ow = 0.5 * sum(abs(t.dw) for t in ev.trades)
    expected = bps / 1e4 * ow * value
    assert ev.trades and ow > 0
    assert ev.turnover_oneway == pytest.approx(ow, abs=1e-12)
    assert ev.turnover_twoway == pytest.approx(2 * ow, abs=1e-12)
    assert ev.cost_cad == pytest.approx(round(expected, 2), abs=1e-9)
    assert v.value_cad == pytest.approx(round(value - expected, 2), abs=1e-9)
    cost_fact = next(f for f in out.facts if f.fact_id == "ev.202002.cout")
    assert cost_fact.value == pytest.approx(round(expected, 6)) and cost_fact.unit == "CAD"
    assert traj.perf.costs_cad_cum == pytest.approx(expected)
