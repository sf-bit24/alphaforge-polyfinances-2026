"""Tests F2-F4 sur les données réelles de l'engine (mandat GÉNÉRIQUE de démonstration :
seuils arbitraires, aucun n'est tiré d'une fiche persona)."""
from __future__ import annotations

import inspect
from datetime import UTC, datetime

import numpy as np
import pytest

from alphaforge.finance.contracts import Decision, Limit, PolicySpec
from alphaforge.finance.portfolio import (
    check,
    diversification_report,
    framed_alternative,
    horizon_report,
    lookthrough_report,
    optimize,
    returns_window,
    risk_report,
    stress_report,
)

AS_OF = "2026-10-31"
UNIVERSE = ["XIU.TO", "SPY", "QQQ", "XBB.TO", "ZST.TO", "GLD", "NVDA", "BTC-USD"]
NOW = datetime(2026, 11, 14, tzinfo=UTC)


def lim(rid, kind, sel, **k):
    return dict(rule_id=rid, kind=kind, selector=sel, derived_from="demo:generique", **k)


def policy(**over) -> PolicySpec:
    base = dict(
        policy_id="demo", profile_id="demo", profile_version=1, created_utc=NOW, universe=UNIVERSE,
        exposure_overrides={"QQQ": {"tech": {"value": 0.6, "source": "demo"}},
                            "XIU.TO": {"tech": {"value": 0.1, "source": "demo"}}},
        limits=[lim("max_titre", "asset_weight", {"classes": ["equity_single"]}, max=0.10),
                lim("max_crypto", "group_weight", {"classes": ["crypto"]}, max=0.03),
                lim("actions", "group_weight", {"tags_any": ["equity"]}, min=0.55, max=0.75),
                lim("tech_lt", "exposure", {"exposure_tag": "tech"}, max=0.25),
                lim("cvar_max", "risk", {"measure": "CVAR"}, max=0.06),
                lim("mdd_max", "risk", {"measure": "MDD"}, max=0.30)])
    base.update(over)
    return PolicySpec(**base)


@pytest.fixture(scope="module")
def opt():
    return optimize(policy(), AS_OF)


# ---------------------------------------------------------------- F2

def test_optimizer_feasible_and_valid(opt):
    assert opt.status == "optimal"
    w = np.array(list(opt.weights.values()))
    assert abs(w.sum() - 1) < 1e-6 and (w >= -1e-9).all()
    assert opt.expected_return_ann is None          # pas de μ historique brut


def test_judge_approves_optimizer_output(opt):
    rep = check(opt.weights, policy(), AS_OF)
    assert rep.approved, rep.blocking_violations


@pytest.mark.parametrize("measure,cap", [("VOL", 0.09), ("CDAR", 0.12)])
def test_risk_limits_consistent_between_f2_and_f4(measure, cap):
    p = policy(limits=policy().limits + [Limit(**lim("extra", "risk", {"measure": measure}, max=cap))])
    res = optimize(p, AS_OF)
    assert res.status == "optimal"
    assert check(res.weights, p, AS_OF).approved


def test_excluded_asset_gets_zero():
    p = policy(excluded={"NVDA": "demo:exclusion"})
    res = optimize(p, AS_OF)
    assert "NVDA" not in res.weights
    rep = check({**res.weights, "NVDA": 0.05}, p, AS_OF)
    assert not rep.approved and "univers[NVDA]" in rep.blocking_violations


def test_infeasible_names_culprit():
    p = policy(limits=policy().limits + [Limit(**lim("demande_crypto", "group_weight",
                                                     {"classes": ["crypto"]}, min=0.5))])
    res = optimize(p, AS_OF)
    assert res.status == "infeasible" and "demande_crypto" in res.infeasible_rules


def test_utility_requires_sourced_prior():
    with pytest.raises(ValueError, match="prior"):
        optimize(policy(objective="max_utility", risk_aversion=2.0), AS_OF)


def test_active_constraints_have_prices(opt):
    assert any(opt.active.values())
    assert all(opt.duals[k] > 0 for k, a in opt.active.items() if a)


# ---------------------------------------------------------------- F4

def test_judge_refuses_concentrated_request_and_frames_alternative():
    request = {"NVDA": 0.5, "SPY": 0.3, "ZST.TO": 0.2}          # demande hors mandat
    rep = check(request, policy(), AS_OF)
    assert rep.verdict == "refuse"
    assert any(v.startswith("max_titre[NVDA]") for v in rep.blocking_violations)
    alt, rep_alt, method = framed_alternative(request, policy(), AS_OF)
    assert alt is not None and rep_alt.approved, (method, rep_alt.blocking_violations)
    assert alt.get("NVDA", 0) <= 0.10 + 1e-4


def test_judge_has_no_override_parameter():
    params = set(inspect.signature(check).parameters)
    assert params == {"weights", "policy", "as_of", "window", "trace_id"}


def test_lowest_cap_wins():
    p = policy(limits=policy().limits + [Limit(**lim("max_crypto_bis", "group_weight",
                                                     {"classes": ["crypto"]}, max=0.01))])
    rep = check({"BTC-USD": 0.02, "SPY": 0.6, "ZST.TO": 0.38}, p, AS_OF)
    assert rep.superseded.get("max_crypto") == "max_crypto_bis"
    assert "max_crypto_bis:max" in rep.blocking_violations


def test_every_check_value_is_a_sourced_fact(opt):
    rep = check(opt.weights, policy(), AS_OF)
    ids = {f.fact_id for f in rep.facts}
    assert all(c.value_fact_id in ids for c in rep.checks)
    assert all(f.trace_id == rep.trace.trace_id and f.sources for f in rep.facts)


def test_decision_assembles_from_judge_output():
    rep = check({"NVDA": 0.5, "SPY": 0.3, "ZST.TO": 0.2}, policy(), AS_OF)
    v = rep.checks[-1].value_fact_id
    st = [{"text_fr": "test", "fact_ids": [v]}]
    d = Decision(decision_id="d", profile_id="demo", profile_version=1, created_utc=NOW,
                 kind="refus_encadre", facts=list(rep.facts), constraints=list(rep.checks),
                 explanation={"data_used": st, "why": st, "limits": st, "what_would_change": st},
                 trace=[rep.trace])
    assert d.kind == "refus_encadre"


# ---------------------------------------------------------------- F3

def test_risk_contributions_sum_to_totals(opt):
    win = returns_window(policy(), AS_OF)
    rr = risk_report(opt.weights, win)
    assert sum(rr.contrib_vol.values()) == pytest.approx(rr.vol_ann, rel=1e-6)
    assert sum(rr.contrib_cvar.values()) == pytest.approx(rr.cvar_m, rel=1e-6)


def test_no_future_data():
    win = returns_window(policy(), "2022-06-30")
    assert win.end <= np.datetime64("2022-06-30")


def test_lookthrough_flags_unknown_exposure():
    p = policy(exposure_overrides={})
    lt = lookthrough_report({"QQQ": 0.5, "SPY": 0.5}, p, ["tech"], AS_OF)
    assert "QQQ" in lt.unknown["tech"]


def test_diversification_and_clusters(opt):
    win = returns_window(policy(), AS_OF)
    d = diversification_report({"NVDA": 0.3, "QQQ": 0.3, "SPY": 0.4}, win)
    assert d.clusters and 1 <= d.effective_n_weights <= 3


def test_stress_coverage_is_honest():
    res = {s.episode: s for s in stress_report({"SPY": 0.6, "XBB.TO": 0.4})}
    assert res["2022_taux"].covered and res["2022_taux"].period_return is not None
    assert not res["1973_choc"].covered and res["1973_choc"].reason


def test_horizon_report():
    h = horizon_report({"SPY": 0.6, "XBB.TO": 0.4}, 3, AS_OF)
    assert h.n_windows > 0 and h.worst <= h.median


# ---------------------------------------------------------------- CVAR12M (contrôle seulement)

def test_cvar12m_is_control_only_and_uses_proxies():
    from alphaforge.finance.contracts import HistoryProxy
    p = policy(history_proxies={"SPY": HistoryProxy(proxy="US_MKT", source="demo : SPY suit le marché US"),
                                "XBB.TO": HistoryProxy(proxy="CA_GOV_10Y", source="demo : obligations CA")},
               limits=policy().limits + [Limit(**lim("cvar12m", "risk", {"measure": "CVAR12M"}, max=0.01))])
    res = optimize(p, AS_OF)
    assert res.status == "optimal" and not any(k.startswith("cvar12m") for k in res.duals)
    rep = check({"SPY": 0.6, "XBB.TO": 0.4}, p, AS_OF)
    assert "cvar12m:max" in rep.blocking_violations           # 1 % sur 12 mois : trop strict
    fact = next(f for f in rep.facts if f.fact_id.endswith("cvar12m:max"))
    assert fact.status == "HYPOTHESE" and "proxys" in fact.sources[0].processing


def test_loss_bounds_exclude_crypto_and_add_bound():
    from alphaforge.finance.contracts import HistoryProxy
    p = policy(history_proxies={"SPY": HistoryProxy(proxy="US_MKT", source="demo")},
               loss_bounds={"BTC-USD": 0.9}, loss_bounds_source="demo",
               limits=policy().limits + [Limit(**lim("c12", "risk", {"measure": "CVAR12M"}, max=0.5))])
    from alphaforge.finance.portfolio.analysis import long_history_returns
    lh = long_history_returns({"SPY": 0.98, "BTC-USD": 0.02}, p, AS_OF)
    assert lh.start < "1980" and lh.excluded == ["BTC-USD"] and lh.excluded_bound == pytest.approx(0.018)


def test_stress_2022_control_only():
    p = policy(limits=policy().limits + [Limit(**lim("s2022", "risk", {"measure": "STRESS_2022"}, max=0.05))])
    res = optimize(p, AS_OF)
    assert res.status == "optimal" and not any(k.startswith("s2022") for k in res.duals)
    rep = check({"SPY": 0.6, "XBB.TO": 0.4}, p, AS_OF)     # 60/40 a perdu plus de 5 % en 2022
    assert "s2022:max" in rep.blocking_violations
