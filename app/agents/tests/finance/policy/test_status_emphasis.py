"""Statuts (INCOMPLETE, PROTECTION), emphase, enveloppe."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from alphaforge.finance.contracts.profile import Goal
from alphaforge.finance.policy import SpecificRequest, compile_profile
from alphaforge.finance.policy import envelope as ENV
from alphaforge.finance.policy.compiler import DEFAULT_YAML, ceil_step

from ._personas import AS_OF, amira, bias, robert

Y = yaml.safe_load(open(DEFAULT_YAML, encoding="utf-8"))


def by(res):
    return {lim.rule_id: lim for lim in res.limits}


def test_incomplete_position_attente():
    p = amira(status="INCOMPLETE", missing_info=["tolerance_tested"])
    r = compile_profile(p, AS_OF, request=SpecificRequest(ticker="BTC-USD", weight=0.01))
    assert r.decision_kind == "position_attente" and r.status == "INCOMPLETE"
    assert r.policy is not None
    assert r.level in ("N0", "N1", "N2")  # status.INCOMPLETE.level_cap = N2
    b = by(r)
    assert b["conc.single_each"].max == 0 and b["conc.single_total"].max == 0 and b["alloc.crypto"].max == 0
    assert r.request.sandbox_max == 0 and r.request.outside_policy
    assert "status.INCOMPLETE" in b["conc.single_each"].source


def test_low_confidence_counts_as_incomplete():
    r = compile_profile(amira(confidence=0.5), AS_OF)
    assert r.status == "INCOMPLETE" and r.level == "N2"


def test_incomplet_without_wealth():
    p = amira(status="INCOMPLETE", investable_wealth=None, missing_info=["investable_wealth"])
    r = compile_profile(p, AS_OF)
    # Chaque profil reçoit un mandat : le statut le resserre (niveau plafonné, valeurs prudentes par défaut).
    assert r.decision_kind == "incomplet" and r.policy is not None
    assert LV_idx(r.level) <= 2
    assert any(m.startswith("investable_wealth") for m in r.missing_defaults)
    assert r.policy.missing_defaults == r.missing_defaults


def LV_idx(L):
    return int(L[1])


def test_protection_status():
    r = compile_profile(robert(status="PROTECTION"), AS_OF)
    assert r.level == "N0" and r.decision_kind == "protection" and r.policy is not None
    b = by(r)
    assert b["conc.single_each"].max == 0 and b["alloc.crypto"].max == 0
    assert {lim.rule_id for lim in r.policy.limits} >= {"conc.single_each", "alloc.crypto"}  # le mandat les porte
    assert any(t["rule"] == "status.PROTECTION.human_referral" and t["output"] is True for t in r.trace)


def test_protection_from_dollar_rule():
    # l* = 0.10 < min_e L_plan(e) = 0.1299 (e = 10 %) -> aucun e admissible
    r = compile_profile(robert(max_acceptable_loss_cad=90_000), AS_OF)
    assert r.decision_kind == "protection" and r.level == "N0" and r.policy is not None
    assert any(t["rule"] == "dollar_rule.protection" for t in r.trace)
    assert r.e_cap == 0  # aucune part d'actions ne tient dans l* : le mandat n'en admet aucune


def test_buckets_cap_whole_policy_when_all_goals_are_short_besoin():
    g = Goal(goal_id="maison", label="mise de fonds", priority="besoin", horizon_years=2, amount=50_000)
    r = compile_profile(amira(goals=[g]), AS_OF)
    assert r.level == "N0" and r.buckets[0]["level_cap"] == "N0"


def test_short_bucket_does_not_cap_risk_bucket():
    gs = [amira().goals[0], Goal(goal_id="voyage", label="voyage", priority="envie", horizon_years=2, amount=5_000)]
    r = compile_profile(amira(goals=gs), AS_OF)
    assert r.level == "N4" and [b["goal_id"] for b in r.buckets] == ["voyage"]
    assert "timeline.horizon_lt_5y" in r.emphasis_rules


def test_emphasis_normalized_and_rules():
    r = compile_profile(robert(biases=[bias("FOMO")]), AS_OF, request=SpecificRequest(ticker="NVDA", amount_cad=50_000))
    assert sum(r.emphasis.values()) == pytest.approx(1.0)
    assert set(r.emphasis) == {"timeline", "risk", "diversity", "constraints"}
    assert {"risk.emotional_bias", "constraints.request_outside", "timeline.recurring_withdrawal"} <= set(
        r.emphasis_rules
    )
    assert r.request.sandbox_only and r.request.cooldown_days == 3
    plain = compile_profile(amira(debts=[], preferences={"tilts": []}), AS_OF)
    assert plain.emphasis == {k: 0.25 for k in ("timeline", "risk", "diversity", "constraints")}


def test_near_cutoff_is_reported_only():
    r = compile_profile(amira(), AS_OF)
    assert r.near_cutoff is (min(abs(r.R - c) for c in Y["levels"]["R_cutoffs"]) < Y["levels"]["hysteresis"])


def test_legal_and_value_filters_exclude():
    p = amira(
        legal_constraints=[{"kind": "employeur", "detail": "periode d'interdiction", "tickers": ["RY.TO"]}],
        preferences={
            "tilts": ["crypto"],
            "value_filters": [{"rule": "fossiles", "per_ticker": {"XOM": "exclu", "ENB.TO": "zone_grise"}}],
        },
    )
    r = compile_profile(p, AS_OF, request=SpecificRequest(ticker="XOM", amount_cad=1_000))
    assert set(r.policy.excluded) == {"RY.TO", "XOM", "ENB.TO"}
    assert r.request.applicable_max == 0 and r.request.outside_policy
    assert {"constraints.legal", "diversity.value_filters"} <= set(r.emphasis_rules)


# ---------------------------------------------------------------- enveloppe


def test_envelope_matches_yaml_levels():
    rnd = Y["measurement"]["rounding"]
    cols = {"vol": "vol", "cvar_m": "cvar95_m", "cvar_12m": "cvar95_12m", "mdd": "mdd", "s2022": "y2022"}
    for L in ("N0", "N1", "N2", "N3", "N4", "N5"):
        e = int(round(Y["levels"][L]["equity"][1] * 100))
        for k, col in cols.items():
            assert ceil_step(ENV.env(e, col), rnd[k]) == pytest.approx(Y["levels"][L][k]), (L, k)
        assert ENV.env(e, "mdd") + Y["dollar_rule"]["daily_buffer"] == pytest.approx(Y["levels"][L]["L_plan"], abs=6e-4)


def test_envelope_monotone_from_10pct():
    """Budgets ENV(e) non decroissants pour e >= 10 (e_cap < 10 est impossible : L_plan(10) est le minimum)."""
    g = [e for e in ENV.grid() if e >= 10]
    for col in ("vol", "cvar95_m", "cvar95_12m", "mdd", "y2022"):
        vals = [ENV.env(e, col) for e in g]
        # 10 -> 15 change de famille (HC -> G5) : croissance verifiee aussi
        assert all(b >= a for a, b in zip(vals, vals[1:])), col
    lp = {e: ENV.env(e, "mdd") for e in ENV.grid()}
    assert min(lp, key=lp.get) == 10


CALIB_OUT = Path(__file__).resolve().parents[1] / "fixtures" / "calibration"


@pytest.mark.skipif(not (CALIB_OUT / "calib_grid5.csv").exists(), reason="CSV de calibration absents")
def test_envelope_regenerates_from_csv():
    pytest.importorskip("pandas")  # build_from_calibration lit les CSV avec pandas (groupe finance)
    fresh = ENV.build_from_calibration(CALIB_OUT)
    assert fresh["equity_pct"] == ENV.load_envelope()["equity_pct"]
    assert fresh["source_files"] == ENV.load_envelope()["source_files"]
