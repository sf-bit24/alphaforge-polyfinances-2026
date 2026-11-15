"""Garanties de monotonie : degrader une entree ne releve jamais le niveau ni un plafond de risque.

Plafonds compares (« qui augmentent le risque quand ils montent ») : max de alloc.growth, alloc.crypto,
alloc.long_duration, alloc.gold, conc.etf_equity_each, conc.single_each, conc.single_total, exp.tech,
risk.cvar_12m, risk.mdd, risk.vol, risk.stress_2022, risk.cdar_m, bias.familiarite.employer, le bac a sable,
et le budget CVaR TOTAL risk.cvar_m + cvar_m_proxy * w_crypto (voir README : la deduction crypto du YAML
peut faire monter risk.cvar_m seul de ~0.1 pt quand le plafond crypto baisse ; le budget total, lui, baisse).
Non compares : alloc.cash_like.max et conc.etf_bond_each (plafonds DEFENSIFS : ils s'elargissent quand le
niveau baisse, ce qui est plus prudent).
"""

from __future__ import annotations

import pytest

from alphaforge.finance.contracts.profile import Debt, Goal, HouseholdMember, Score
from alphaforge.finance.policy import LV, SpecificRequest, compile_profile

from ._personas import AS_OF, amira, bias, mateo, robert

CAPS = [
    "alloc.growth",
    "alloc.crypto",
    "alloc.long_duration",
    "alloc.gold",
    "conc.etf_equity_each",
    "conc.single_each",
    "conc.single_total",
    "exp.tech",
    "risk.cvar_12m",
    "risk.mdd",
    "risk.vol",
    "risk.stress_2022",
    "risk.cdar_m",
    "bias.familiarite.employer",
]
REQ = SpecificRequest(ticker="NVDA", amount_cad=5_000)
INF = float("inf")


def caps(res) -> dict[str, float]:
    by = {lim.rule_id: lim for lim in res.limits}
    out = {k: by[k].max if k in by else INF for k in CAPS}
    # limites conditionnelles absentes = pas de plafond (INF) ; si presentes plus tard, elles resserrent
    out["growth_min"] = by["alloc.growth"].min
    out["cvar_total"] = by["risk.cvar_m"].max + 0.55 * by["alloc.crypto"].max
    out["sandbox"] = res.request.sandbox_max if res.request else 0.0
    out["level"] = LV.index(res.level)
    return out


def assert_not_looser(base, worse, label):
    b, w = caps(base), caps(worse)
    for k in b:
        assert w[k] <= b[k] + 1e-12, f"{label}: {k} {b[k]} -> {w[k]}"


def run(p):
    return compile_profile(p, AS_OF, request=REQ)


def _goals(make, h):
    g = make().goals[0]
    return [Goal(**{**g.model_dump(), "horizon_years": h})]


PERSONAS = {"amira": amira, "mateo": mateo, "robert": robert}


def degradations(name, make):
    p = make()
    E = p.emergency_fund_months
    h0 = p.goals[0].horizon_years
    yield (
        "horizon",
        [
            make(goals=_goals(make, h))
            for h in sorted({h0, 15, 10, 9.9, 7, 5, 4.9, 3, 2, 0.9, 0.2}, reverse=True)
            if h <= h0
        ],
    )
    yield (
        "declared_loss",
        [
            make(max_acceptable_loss_pct=x)
            for x in (None, 0.6, 0.45, 0.40, 0.35, 0.30, 0.25, 0.2, 0.17, 0.135, 0.13, 0.10, 0.0)
        ],
    )
    yield (
        "emergency",
        [make(emergency_fund_months=x) for x in sorted({E, 6, 4, 3, 2, 1, 0.5, 0}, reverse=True) if x <= E],
    )
    yield (
        "debt",
        [
            make(debts=list(p.debts) + extra)
            for extra in (
                [],
                [Debt(label="marge", balance=20_000, annual_rate=0.05)],
                [Debt(label="marge", balance=60_000, annual_rate=0.05)],
                [
                    Debt(label="marge", balance=60_000, annual_rate=0.05),
                    Debt(label="carte", balance=5_000, annual_rate=0.20),
                ],
            )
        ],
    )
    yield (
        "knowledge",
        [make(knowledge_level=k) for k in ("avance", "intermediaire", "debutant")] + [make(knowledge_level=None)],
    )
    yield (
        "capacity_assessed",
        [make(capacity_assessed=None)] + [make(capacity_assessed=Score(value=v)) for v in (100, 80, 60, 40, 20, 0)],
    )
    yield "composure", [make(composure=Score(value=v)) for v in (90, 60, 45, 39, 20, 0)]
    yield "flags", [make(consistency_flags=["x"] * n) for n in range(5)]
    yield (
        "household",
        [
            make(
                household=list(p.household) + [HouseholdMember(role=f"m{i}", tolerance=Score(value=v, confidence=0.9))]
            )
            for i, v in enumerate((90, 50, 30, 10))
        ],
    )


@pytest.mark.parametrize("name", list(PERSONAS))
def test_degradation_chains(name):
    make = PERSONAS[name]
    for label, chain in degradations(name, make):
        res = [run(p) for p in chain]
        for a, b in zip(res, res[1:]):
            assert_not_looser(a, b, f"{name}/{label}")


@pytest.mark.parametrize("name", list(PERSONAS))
@pytest.mark.parametrize("label", ["FOMO", "surconfiance", "aversion_perte", "familiarite"])
def test_biases_only_tighten(name, label):
    make = PERSONAS[name]
    base = make(employer_equity=[{"ticker": "RY.TO", "value": 10_000}])
    worse = make(employer_equity=[{"ticker": "RY.TO", "value": 10_000}], biases=[bias(label)])
    assert_not_looser(run(base), run(worse), f"{name}+{label}")


def test_surconfiance_never_raises_even_when_tested_is_higher():
    p = mateo(
        household=[],
        tolerance_declared=Score(value=40, confidence=0.9),
        tolerance_tested=Score(value=80, confidence=0.9),
    )
    t0 = compile_profile(p, AS_OF).tolerance["T"]
    t1 = compile_profile(
        mateo(
            household=[],
            tolerance_declared=p.tolerance_declared,
            tolerance_tested=p.tolerance_tested,
            biases=[bias("surconfiance", "cognitif")],
        ),
        AS_OF,
    ).tolerance["T"]
    assert t1 <= t0


def test_aversion_adds_cdar():
    r = compile_profile(amira(biases=[bias("aversion aux pertes")]), AS_OF)
    by = {lim.rule_id: lim for lim in r.limits}
    assert by["risk.cdar_m"].max == 0.073 and by["risk.cdar_m"].derived_from == "profile.biases[aversion_perte]"


def test_familiarite_caps_employer_and_tech():
    base = compile_profile(amira(employer_equity=[{"ticker": "SHOP.TO", "value": 5_000}]), AS_OF)
    fam = compile_profile(
        amira(employer_equity=[{"ticker": "SHOP.TO", "value": 5_000}], biases=[bias("familiarite", "cognitif")]), AS_OF
    )
    by = {lim.rule_id: lim for lim in fam.limits}
    assert by["bias.familiarite.employer"].max == 0.025 and by["bias.familiarite.employer"].selector.assets == [
        "SHOP.TO"
    ]
    assert by["exp.tech"].max < {lim.rule_id: lim for lim in base.limits}["exp.tech"].max


def test_capacity_assessed_only_lowers():
    free = compile_profile(amira(), AS_OF).capacity["C"]
    assert compile_profile(amira(capacity_assessed=Score(value=100)), AS_OF).capacity["C"] == free
    assert compile_profile(amira(capacity_assessed=Score(value=20)), AS_OF).capacity["C"] == 20


def test_household_min_rule():
    solo = compile_profile(mateo(household=[]), AS_OF)
    duo = compile_profile(mateo(), AS_OF)
    assert duo.tolerance["T"] <= solo.tolerance["T"]
    assert duo.tolerance["T"] == pytest.approx(min(c["T"] for c in duo.tolerance["candidates"]))
    hi = compile_profile(
        mateo(household=[HouseholdMember(role="conjoint", tolerance=Score(value=99, confidence=1))]), AS_OF
    )
    assert hi.tolerance["T"] == pytest.approx(solo.tolerance["T"])  # un membre plus audacieux ne releve rien


def test_debutant_caps():
    r = compile_profile(amira(knowledge_level="debutant"), AS_OF)
    by = {lim.rule_id: lim.max for lim in r.limits}
    assert by["conc.single_each"] == 0.02
    assert by["alloc.crypto"] == 0.0  # crypto_vehicle etf_only : aucun FNB crypto dans le starter
    assert compile_profile(amira(knowledge_level=None), AS_OF).missing_defaults[0].startswith("knowledge_level")
