"""Fabrique de CompileResult à la main (sans moteur) pour les tests purs de l'étape 0."""

from __future__ import annotations

from datetime import UTC, datetime

from alphaforge.finance.contracts import Limit, PolicySpec, Selector
from alphaforge.finance.policy.models import CompileResult

UNIVERSE = ["XIU.TO", "SPY", "XBB.TO", "ZST.TO", "FTS.TO", "JNJ", "NVDA", "RY.TO", "CNQ.TO", "AAPL"]


def lim(rid, kind, sel, mn=None, mx=None, blocking=True):
    return Limit(
        rule_id=rid,
        kind=kind,
        selector=Selector(**sel),
        min=mn,
        max=mx,
        blocking=blocking,
        derived_from="test",
        source="test",
    )


def make_comp(
    level="N4",
    level_from_R="N4",
    R=71.5,
    T=71.5,
    C=98.7,
    status="COMPLETE",
    e_min=0.6,
    e_cap=0.8,
    crypto=0.02,
    each=0.05,
    total=0.14,
    tech=0.4075,
    horizon=20.0,
    l_star=0.451,
    cdar=False,
):
    limits = [
        lim(
            "alloc.growth",
            "group_weight",
            {"classes": ["equity_us", "equity_ca", "etf_equity", "sector_us", "equity_single", "crypto"]},
            e_min,
            e_cap,
        ),
        lim("alloc.crypto", "group_weight", {"classes": ["crypto"]}, None, crypto),
        lim("conc.single_each", "asset_weight", {"classes": ["equity_single"]}, None, each),
        lim("conc.single_total", "group_weight", {"classes": ["equity_single"]}, None, total),
        lim("exp.tech", "exposure", {"exposure_tag": "tech"}, None, tech),
        lim("risk.cvar_m", "risk", {"measure": "CVAR"}, None, 0.062),
        lim("risk.mdd", "risk", {"measure": "MDD"}, None, 0.415),
    ]
    if cdar:
        limits.append(lim("risk.cdar_m", "risk", {"measure": "CDAR"}, None, 0.015))
    policy = PolicySpec(
        policy_id="p-test",
        profile_id="test",
        profile_version=1,
        created_utc=datetime(2026, 9, 30, tzinfo=UTC),
        universe=list(UNIVERSE),
        limits=limits,
    )
    return CompileResult(
        policy=policy,
        level=level,
        R=R,
        capacity={"C": C},
        tolerance={"T": T},
        decision_kind=None,
        emphasis={},
        trace=[],
        missing_defaults=[],
        status=status,
        level_from_R=level_from_R,
        horizon_years=horizon,
        l_star=l_star,
        e_cap=e_cap,
        limits=limits,
    )


def amira():
    return make_comp()


def mateo():
    return make_comp(
        level="N2",
        level_from_R="N2",
        R=32.0,
        T=32.0,
        C=85.3,
        e_min=0.25,
        e_cap=0.35,
        crypto=0.0,
        each=0.03,
        total=0.0775,
        tech=0.185,
        horizon=9.0,
        l_star=0.25,
    )


def robert():
    return make_comp(
        level="N0",
        level_from_R="N2",
        R=41.0,
        T=41.0,
        C=65.7,
        e_min=0.0,
        e_cap=0.10,
        crypto=0.0,
        each=0.0,
        total=0.0,
        tech=0.06,
        horizon=7.0,
        l_star=0.1333,
        cdar=True,
    )
