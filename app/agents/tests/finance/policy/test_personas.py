"""Personas de la revue v0.2 (research/calibration/review/persona_v02.py, marge quotidienne 4 pts)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from alphaforge.finance.contracts import PolicySpec
from alphaforge.finance.policy import SpecificRequest, compile_profile
from alphaforge.finance.policy.compiler import DEFAULT_YAML

from ._personas import AS_OF, amira, mateo, robert


def lim(res, rid):
    return {x.rule_id: x for x in res.limits}[rid]


def test_amira_n4():
    r = compile_profile(amira(), AS_OF)
    assert r.decision_kind is None and r.status == "COMPLETE"
    assert r.capacity["C"] == pytest.approx(98.7, abs=0.05)
    assert r.tolerance["T"] == pytest.approx(71.5, abs=0.05)
    assert r.level == "N4" and r.level_from_R == "N4"
    assert r.l_star == pytest.approx(0.451, abs=5e-4) and r.e_cap == 0.80
    assert (lim(r, "alloc.growth").min, lim(r, "alloc.growth").max) == (0.6, 0.8)
    assert lim(r, "alloc.crypto").max == 0.02  # persona_v02 : crypto 0.0200
    assert lim(r, "conc.single_each").max == 0.05
    assert lim(r, "risk.cvar_m").max == pytest.approx(0.073 - 0.02 * 0.55)
    assert lim(r, "risk.cvar_12m").max == 0.195 and lim(r, "risk.mdd").max == 0.415


def test_mateo_n2_with_daily_buffer():
    r = compile_profile(mateo(), AS_OF)
    assert r.level == "N2"
    assert r.l_star == pytest.approx(0.25) and r.e_cap == 0.35
    # budgets_when_capped : arrondi_sup(ENV(35)) — identiques a persona_v02
    got = {k: lim(r, f"risk.{k}").max for k in ("vol", "cvar_m", "cvar_12m", "mdd", "stress_2022")}
    assert got == pytest.approx({"vol": 0.065, "cvar_m": 0.032, "cvar_12m": 0.07, "mdd": 0.19, "stress_2022": 0.115})
    assert lim(r, "conc.single_each").max == 0.03 and lim(r, "exp.tech").max == 0.185
    assert "envelope_v02.yaml#equity_pct.35.cvar95_m" in lim(r, "risk.cvar_m").source
    # menage : le conjoint (plus prudent) fixe T (regle min_tolerance)
    assert [c["who"] for c in r.tolerance["candidates"]] == ["personne", "conjoint"]
    assert r.tolerance["T"] == min(c["T"] for c in r.tolerance["candidates"])


def _yaml_with_buffer(tmp_path: Path, buf: float) -> Path:
    Y = yaml.safe_load(open(DEFAULT_YAML, encoding="utf-8"))
    Y["dollar_rule"]["daily_buffer"] = buf
    p = tmp_path / "risk_levels_buf.yaml"
    p.write_text(yaml.safe_dump(Y), encoding="utf-8")
    return p


def test_daily_buffer_effect_matches_review(tmp_path):
    """Revue, decision ouverte n°1 : la marge de 4 pts fait passer Mateo de N3 a N2 et Robert de N1 a N0."""
    y0 = _yaml_with_buffer(tmp_path, 0.0)
    solo = mateo(household=[], household_rule=None)
    assert compile_profile(solo, AS_OF).level == "N2"
    assert compile_profile(solo, AS_OF, yaml_path=y0).level == "N3"
    assert compile_profile(robert(), AS_OF, yaml_path=y0).level == "N1"


def test_robert_n0_sandbox_zero():
    req = SpecificRequest(ticker="NVDA", amount_cad=50_000)
    r = compile_profile(robert(), AS_OF, request=req)
    assert r.level == "N0" and r.level_from_R == "N2"
    assert r.capacity["C"] == pytest.approx(65.7, abs=0.05) and r.R == pytest.approx(41.0, abs=0.05)
    assert r.l_star == pytest.approx(120_000 / 900_000) and r.e_cap == 0.10
    assert lim(r, "conc.single_each").max == 0 and lim(r, "alloc.crypto").max == 0
    assert r.request.sandbox_max == 0 and r.request.applicable_max == 0
    assert r.request.outside_policy and r.request.requested_weight == pytest.approx(50_000 / 900_000)
    assert "constraints.request_outside" in r.emphasis_rules
    # composure 30 < 40 -> CDaR conditionnelle (tolerance.low_composure_cdar)
    assert lim(r, "risk.cdar_m").max == 0.015
    assert lim(r, "alloc.cash_like").min == 0.5
    # la demande n'est jamais approuvee par F1 : policy_with_request ajoute seulement le plafond
    pw = r.policy_with_request()
    assert {lim.rule_id: lim.max for lim in pw.limits}["sat.sandbox"] == 0


def test_example_n3_matches_yaml():
    """Exemple developpe du YAML (N3 plein, l_star ~ 0.349) : Amira avec perte declaree 35 %."""
    r = compile_profile(amira(max_acceptable_loss_pct=0.35), AS_OF)
    assert r.level == "N3" and r.e_cap == 0.60
    ex = yaml.safe_load(open(DEFAULT_YAML, encoding="utf-8"))["example_N3"]
    for rid, v in ex.items():
        lm = lim(r, rid)
        if isinstance(v, list):
            assert (lm.min, lm.max) == (v[0], v[1]), rid
        else:
            assert lm.max == pytest.approx(v), rid


@pytest.mark.parametrize("make", [amira, mateo, robert])
def test_policy_validates_and_sources(make):
    r = compile_profile(make(), AS_OF)
    PolicySpec.model_validate(r.policy.model_dump())
    ver = r.policy.limits[0].source.split("#")[0]
    assert ver == "risk_levels.yaml@0.2.0"
    for lim in r.policy.limits:
        assert lim.source and lim.source.startswith("risk_levels.yaml@0.2.0#"), lim.rule_id
        assert lim.derived_from
    for t in r.trace:
        assert set(t) == {"rule", "inputs", "output", "yaml_path"}
        assert t["yaml_path"].split("@")[0] in ("risk_levels.yaml", "emphasis.yaml", "envelope_v02.yaml", "profile"), t
    assert set(r.policy.loss_bounds) == {"BTC-USD", "ETH-USD"}
    assert r.policy.history_proxies["QQQ"].proxy == "US_IND_BUSEQ"
    assert r.policy.exposure_overrides["QQQ"]["tech"].value == 0.60
    assert r.policy.lookback_months == 597


@pytest.mark.parametrize("make", [amira, mateo, robert])
def test_determinism(make):
    a = compile_profile(make(), AS_OF)
    b = compile_profile(make(), AS_OF)
    assert a.policy.model_dump_json() == b.policy.model_dump_json()
    assert a.trace == b.trace and a.emphasis == b.emphasis
