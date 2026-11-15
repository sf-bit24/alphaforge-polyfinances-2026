"""Overlays bornés, porte de validation, DSR/PBO — données SYNTHÉTIQUES, mandat générique (seuils arbitraires,
aucun n'est tiré d'une fiche persona). Sans catalogue de l'engine : projection (d) sautée (``project=False``)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from alphaforge.finance.backtest import validation_dsr as V
from alphaforge.finance.contracts import PolicySpec
from alphaforge.finance.evolution.config import load_config
from alphaforge.finance.evolution.overlays import gate as G
from alphaforge.finance.evolution.overlays.base import apply_overlays, context_from, equity_share, linear_breaches
from alphaforge.finance.evolution.overlays.gate import MIN_PBO_TRIALS, default_grid, evaluate_gate
from alphaforge.finance.evolution.overlays.registry import REGISTRY, build_overlays
from alphaforge.finance.evolution.overlays.relative_strength import RelativeStrength
from alphaforge.finance.evolution.overlays.stops import StopLoss, TrailingStop
from alphaforge.finance.evolution.overlays.trend import TrendTilt

CFG = load_config()
NOW = datetime(2026, 11, 15, tzinfo=UTC)
CLS = {"SPY": "etf_equity", "XIU.TO": "etf_equity", "QQQ": "etf_equity", "NVDA": "equity_single",
       "BTC-USD": "crypto", "XBB.TO": "etf_bond", "ZST.TO": "etf_bond", "GLD": "commodity"}
TAGS = {"ZST.TO": ["cash_like"]}
TARGET = {"SPY": 0.25, "XIU.TO": 0.15, "QQQ": 0.10, "NVDA": 0.05, "BTC-USD": 0.02, "XBB.TO": 0.28, "ZST.TO": 0.10,
          "GLD": 0.05}
E_MIN, E_CAP = 0.45, 0.65
EQ = {"SPY", "XIU.TO", "QQQ", "NVDA", "BTC-USD"}


def lim(rid, kind, sel, **k):
    return dict(rule_id=rid, kind=kind, selector=sel, derived_from="demo:generique", **k)


def policy() -> PolicySpec:
    return PolicySpec(
        policy_id="demo", profile_id="demo", profile_version=1, created_utc=NOW, universe=list(CLS),
        limits=[lim("alloc.growth", "group_weight", {"classes": ["equity_us", "equity_ca", "etf_equity", "sector_us",
                                                                   "equity_single", "crypto"]}, min=E_MIN, max=E_CAP),
                lim("alloc.cash_like", "group_weight", {"tags_any": ["cash_like", "cash"]}, max=0.30),
                lim("alloc.crypto", "group_weight", {"classes": ["crypto"]}, max=0.05)])


def returns(n=60, seed=0, drift=None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-31", periods=n, freq="ME")
    r = pd.DataFrame(rng.normal(0.005, 0.04, (n, len(CLS))), index=idx, columns=list(CLS))
    if drift is not None:
        for a in EQ:
            r[a] = drift + rng.normal(0, 0.002, n)
    return r


def ctx(r, as_of=None, target=TARGET, weights=None, **kw):
    as_of = as_of or r.index[-1]
    return context_from(policy(), as_of, r, target, weights or target, CLS, cfg=CFG, asset_tags=TAGS, **kw)


def test_sets_derived():
    c = ctx(returns())
    assert c.equity_assets == frozenset(EQ)
    assert c.satellites == {"NVDA", "BTC-USD"} and c.core_etfs == {"SPY", "XIU.TO", "QQQ"}
    assert c.cash_like == {"ZST.TO"} and (c.e_min, c.e_cap) == (E_MIN, E_CAP)


def test_bounds_random_cases():
    rng = np.random.default_rng(42)
    s, core_min = CFG.overlays.common["max_equity_shift"], CFG.overlays.common["core_etf_min"]
    ovs = build_overlays(CFG)
    active = {o.name for o in ovs}
    for k in range(200):
        r = returns(n=40, seed=k)
        raw = rng.dirichlet(np.ones(len(CLS)))
        tgt = dict(zip(CLS, raw, strict=True))
        weights = dict(zip(CLS, rng.dirichlet(np.ones(len(CLS))), strict=True))
        c = ctx(r, target=tgt, weights=weights, need_floor_cad=float(rng.uniform(0, 1e5)), value_cad=1e5,
                entry_prices={"NVDA": 5.0}, peaks={"BTC-USD": 5.0})
        out, states, facts = apply_overlays(c, ovs, active, project=False)
        w = np.array(list(out.values()))
        assert abs(w.sum() - 1) < 1e-9 and (w >= -1e-12).all()
        eq0, eq1 = equity_share(tgt, EQ), equity_share(out, EQ)
        lo, hi = max(E_MIN, eq0 - s), min(E_CAP, eq0 + s)
        if lo <= hi:
            assert lo - 1e-9 <= eq1 <= hi + 1e-9
        else:                                   # la base est hors bande : le profil l'emporte
            assert E_MIN - 1e-9 <= eq1 <= E_CAP + 1e-9
        core = sum(out[a] for a in ("SPY", "XIU.TO", "QQQ"))
        assert core >= core_min * eq1 - 1e-9
        assert len(states) == len(ovs) and all(st.fact_ids is not None for st in states)


def test_stops_only_satellites():
    r = returns()
    r.loc[r.index[-3:], ["NVDA", "BTC-USD"]] = -0.30      # krach des satellites
    r.loc[r.index[-3:], ["SPY"]] = -0.30                    # un cœur aussi : jamais stoppé
    c = ctx(r, entry_prices={"NVDA": 1e6, "BTC-USD": 1e6, "SPY": 1e6})
    for ov in (StopLoss(), TrailingStop()):
        sig = ov.compute(c)
        neg = {a for a, v in sig.delta.items() if v < 0}
        assert neg == {"NVDA", "BTC-USD"}
        assert all(a in c.core_etfs for a, v in sig.delta.items() if v > 0)
        assert abs(sum(sig.delta.values())) < 1e-12
    # soldé et sous la moyenne : reste à 0 ; au-dessus : retour permis
    w0 = {**TARGET, "NVDA": 0.0}
    assert StopLoss().compute(ctx(r, weights=w0)).delta.get("NVDA", 0) < 0
    up = returns(drift=0.02)
    assert "NVDA" not in StopLoss().compute(ctx(up, weights=w0)).delta


def test_relative_strength_keeps_equity_share():
    r = returns()
    r["SPY"], r["QQQ"], r["XIU.TO"] = 0.03, -0.02, 0.0
    sig = RelativeStrength().compute(ctx(r))
    assert sig.delta["QQQ"] < 0 and sig.delta["SPY"] > 0 and "XIU.TO" not in sig.delta
    assert abs(sum(sig.delta.values())) < 1e-12
    assert set(sig.delta) <= {"SPY", "XIU.TO", "QQQ"}


@pytest.mark.parametrize("drift,sign", [(0.02, 1.0), (-0.02, -1.0)])
def test_trend_sign(drift, sign):
    sig = TrendTilt().compute(ctx(returns(drift=drift)))
    assert sig.signal == sign
    assert np.sign(sum(v for a, v in sig.delta.items() if a in EQ)) == sign
    out, states, _ = apply_overlays(ctx(returns(drift=drift)), [TrendTilt()], {"trend_tilt"}, project=False)
    st = states[0]
    assert st.active and abs(equity_share(out, EQ) - equity_share(TARGET, EQ)) <= 0.10 + 1e-9


def test_point_in_time():
    r = returns(n=80, seed=3)
    t = r.index[50]
    for name, cls in REGISTRY.items():
        a = cls().compute(ctx(r.loc[:t], as_of=t, need_floor_cad=5e4, value_cad=1e5))
        b = cls().compute(ctx(r, as_of=t, need_floor_cad=5e4, value_cad=1e5))
        assert a.delta == b.delta and a.signal == b.signal, name


def test_context_rejects_future_rows():
    from alphaforge.finance.evolution.overlays.base import OverlayContext
    r = returns()
    c = ctx(r, as_of=r.index[10])
    assert c.returns_upto.index.max() == r.index[10]
    with pytest.raises(ValueError):
        OverlayContext(**{**c.__dict__, "returns_upto": r})


def test_gate_rejects_later_month():
    r = returns(n=60)
    te = r.index[40]
    with pytest.raises(ValueError):
        evaluate_gate("trend_tilt", r, te, TARGET, policy(), CLS, CFG, months=list(r.index[:45]), asset_tags=TAGS)


def test_gate_runs_and_fails_short_history():
    r = returns(n=60)
    st, row = evaluate_gate("trend_tilt", r, r.index[-1], TARGET, policy(), CLS, CFG, asset_tags=TAGS)
    assert st.gate == "echoue" and not st.active and row.n_trials == 5   # 60 mois < min_train_months
    assert "testé, non retenu" in st.gate_reason_fr
    assert row.pbo is None or 0 <= row.pbo <= 1


def test_disabled_overlay():
    st, row = evaluate_gate("vol_target", returns(), returns().index[-1], TARGET, policy(), CLS, CFG)
    assert st.gate == "desactive" and not row.applied
    _, states, _ = apply_overlays(ctx(returns()), build_overlays(CFG), {"vol_target"}, project=False)
    vt = next(s for s in states if s.name == "vol_target")
    assert vt.gate == "desactive" and not vt.active and vt.delta == {}


def test_dsr_more_trials_lower():
    d = [V.deflated_sharpe(0.2, n, 120, 0.0, 3.0, 0.01) for n in (1, 5, 20, 100)]
    assert all(x > y for x, y in zip(d, d[1:], strict=False))
    assert 0 <= d[-1] <= 1
    assert V.expected_max_sharpe(1, 0.01) == 0.0


def test_pbo_range():
    rng = np.random.default_rng(1)
    noise = rng.normal(0, 0.01, (192, 8))
    p = V.pbo_cscv(noise, S=16)
    assert 0 <= p <= 1
    skill = noise.copy()
    skill[:, 0] += 0.02                                   # une stratégie vraiment meilleure partout
    assert V.pbo_cscv(skill, S=8) < 0.1


def test_linear_breaches():
    assert linear_breaches(TARGET, policy(), CLS, TAGS) == []
    assert set(linear_breaches({**TARGET, "BTC-USD": 0.2}, policy(), CLS, TAGS)) == {"alloc.crypto", "alloc.growth"}


# ---------------------------------------------------------------- déterminisme, porte : PBO exigé, essais totaux

def _determinism_payload(reverse: bool = False) -> str:
    """JSON (repr des flottants, ordre des clés compris) d'overlays bornés et d'une porte sur un cas synthétique."""
    def order(d):
        return dict(reversed(list(d.items()))) if reverse else dict(d)
    ovs = build_overlays(CFG)
    act = {o.name for o in ovs}
    rng = np.random.default_rng(7)
    out = []
    for k in range(20):
        r = returns(n=40, seed=k)
        tgt = order(dict(zip(CLS, rng.dirichlet(np.ones(len(CLS))), strict=True)))
        wts = order(dict(zip(CLS, rng.dirichlet(np.ones(len(CLS))), strict=True)))
        c = ctx(r, target=tgt, weights=wts, need_floor_cad=float(rng.uniform(0, 1e5)), value_cad=1e5,
                entry_prices={"NVDA": 5.0}, peaks={"BTC-USD": 5.0})
        w, states, facts = apply_overlays(c, ovs, act, project=False)
        out.append([[a, repr(v)] for a, v in w.items()])
        out.append([[st.name, [[a, repr(v)] for a, v in st.delta.items()]] for st in states])
        out.append([[f.fact_id, repr(f.value)] for f in facts])
    r = returns(n=40, seed=5)
    _, row = evaluate_gate("tsmom", r, r.index[-1], order(TARGET), policy(), CLS, CFG, asset_tags=TAGS)
    out.append([repr(row.dsr), repr(row.pbo), repr(row.sharpe), row.verdict_fr])
    return json.dumps(out, ensure_ascii=False)


def test_hashseed_determinism():
    """Même résultat au bit près quel que soit PYTHONHASHSEED (itérations triées, sommes exactes)."""
    code = (f"import sys; sys.path.insert(0, {str(Path(__file__).parent)!r}); "
            "import test_overlays as T; print(T._determinism_payload())")
    runs = [subprocess.run([sys.executable, "-c", code], env={**os.environ, "PYTHONHASHSEED": seed},
                           capture_output=True, text=True, check=True, timeout=300).stdout
            for seed in ("1", "2")]
    assert runs[0] and runs[0] == runs[1]
    assert _determinism_payload(reverse=True) == _determinism_payload()   # ni l'ordre d'insertion de l'appelant


def test_default_grids_allow_pbo():
    for name in CFG.overlays.order:
        if CFG.overlay(name).get("enabled", True):
            grid = default_grid(CFG, name)
            assert len(grid) >= MIN_PBO_TRIALS, name
            assert len({json.dumps(g, sort_keys=True) for g in grid}) == len(grid), name   # essais distincts


def _lenient_cfg():
    """Porte permissive (DSR ≥ 0, PBO ≤ 1, 12 mois) : seul le caractère calculable du PBO décide."""
    return CFG.model_copy(update={"gate": CFG.gate.model_copy(update={"min_dsr": 0.0, "max_pbo": 1.0,
                                                                     "min_train_months": 12})})


def test_gate_requires_pbo():
    r, cfg = returns(n=60, seed=2), _lenient_cfg()
    st, row = evaluate_gate("trend_tilt", r, r.index[-1], TARGET, policy(), CLS, cfg, asset_tags=TAGS)
    assert st.gate == "passe" and row.pbo is not None
    three = default_grid(cfg, "trend_tilt")[:3]
    st, row = evaluate_gate("trend_tilt", r, r.index[-1], TARGET, policy(), CLS, cfg, three, asset_tags=TAGS)
    assert st.gate == "echoue" and not st.active and row.pbo is None
    assert "PBO non calculable" in st.gate_reason_fr


def test_gate_n_trials_total():
    r, cfg = returns(n=60, seed=2), _lenient_cfg()
    _, own = evaluate_gate("trend_tilt", r, r.index[-1], TARGET, policy(), CLS, cfg, asset_tags=TAGS)
    _, tot = evaluate_gate("trend_tilt", r, r.index[-1], TARGET, policy(), CLS, cfg, asset_tags=TAGS,
                           n_trials_total=45)
    _, low = evaluate_gate("trend_tilt", r, r.index[-1], TARGET, policy(), CLS, cfg, asset_tags=TAGS,
                           n_trials_total=2)
    assert own.n_trials == 5 and tot.n_trials == 45 and low.n_trials == 5   # jamais moins que la grille
    assert tot.dsr < own.dsr and low.dsr == own.dsr
    assert "45 essais dont 5 de cet overlay" in tot.verdict_fr
    with pytest.raises(ValueError):
        evaluate_gate("trend_tilt", r, r.index[-1], TARGET, policy(), CLS, cfg, asset_tags=TAGS, n_trials_total=0)


def test_gate_pbo_aligned_on_dates(monkeypatch):
    """Préchauffages différents (lookback 10/12/14) : le PBO lit les mois communs, alignés par date."""
    r, cfg = returns(n=60, seed=4), _lenient_cfg()
    sims, mats = [], []
    real_sim, real_pbo = G._simulate, V.pbo_cscv

    def sim(*a, **k):
        out = real_sim(*a, **k)
        sims.append(out[1] - out[0])
        return out

    def pbo(m, *a, **k):
        mats.append(np.asarray(m))
        return real_pbo(m, *a, **k)

    monkeypatch.setattr(G, "_simulate", sim)
    monkeypatch.setattr(V, "pbo_cscv", pbo)
    evaluate_gate("tsmom", r, r.index[-1], TARGET, policy(), CLS, cfg, asset_tags=TAGS)
    starts = {s.index[0] for s in sims}
    assert len(starts) > 1                                           # préchauffages réellement différents
    common = sims[0].index
    for s in sims[1:]:
        common = common.intersection(s.index)
    expected = np.column_stack([s.loc[common].to_numpy() for s in sims])
    assert len(mats) == 1 and mats[0].shape == expected.shape and np.array_equal(mats[0], expected)
