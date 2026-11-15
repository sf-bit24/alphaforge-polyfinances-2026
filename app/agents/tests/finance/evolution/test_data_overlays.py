"""Intégration sur les données longues de l'engine (sautée sans elles) : overlays + projection (d) réelle,
porte de validation sur l'historique avant la fenêtre. Mandat GÉNÉRIQUE (seuils arbitraires de démonstration)."""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from alphaforge.finance.backtest import data as bt_data
from alphaforge.finance.contracts import PolicySpec
from alphaforge.finance.evolution.config import load_config
from alphaforge.finance.evolution.overlays.base import apply_overlays, context_from, equity_share, linear_breaches
from alphaforge.finance.evolution.overlays.gate import evaluate_gate
from alphaforge.finance.evolution.overlays.registry import build_overlays

CFG = load_config()
UNI = ["US_MKT", "CA_EQ", "SPY", "XIU.TO", "XBB.TO", "ZST.TO", "CA_TBILL", "UST_10Y", "NVDA"]
TARGET = {"US_MKT": 0.25, "CA_EQ": 0.15, "SPY": 0.10, "XIU.TO": 0.05, "NVDA": 0.03, "XBB.TO": 0.22,
          "UST_10Y": 0.10, "CA_TBILL": 0.10}


def lim(rid, kind, sel, **k):
    return dict(rule_id=rid, kind=kind, selector=sel, derived_from="demo:generique", **k)


def policy():
    return PolicySpec(policy_id="demo", profile_id="demo", profile_version=1, created_utc=datetime(2026, 11, 15,
                      tzinfo=UTC), universe=UNI,
                      limits=[lim("alloc.growth", "group_weight", {"classes": ["equity_us", "equity_ca", "etf_equity",
                              "sector_us", "equity_single", "crypto"]}, min=0.45, max=0.65),
                              lim("alloc.cash_like", "group_weight", {"tags_any": ["cash_like", "cash"]}, max=0.30),
                              lim("max_titre", "asset_weight", {"classes": ["equity_single"]}, max=0.05)])


def test_overlays_with_projection():
    cat = bt_data.load_assets()
    cls = {a: cat.at[a, "asset_class"] for a in UNI}
    r = bt_data.load_returns(UNI, start="1990-01-31", end="2024-12-31")
    as_of = pd.Timestamp("2022-09-30")
    c = context_from(policy(), as_of, r, TARGET, TARGET, cls, cfg=CFG)
    assert "CA_TBILL" in c.cash_like
    ovs = build_overlays(CFG)
    out, states, facts = apply_overlays(c, ovs, {o.name for o in ovs})
    assert linear_breaches(out, policy(), cls) == []
    eq = equity_share(out, c.equity_assets)
    assert 0.45 - 1e-6 <= eq <= 0.65 + 1e-6 and abs(eq - equity_share(TARGET, c.equity_assets)) <= 0.10 + 1e-6
    assert any(f.fact_id == "ov.bounds.equity_after" for f in facts)


def test_gate_before_window():
    cat = bt_data.load_assets()
    cls = {a: cat.at[a, "asset_class"] for a in UNI}
    tgt = {"US_MKT": 0.35, "CA_EQ": 0.20, "UST_10Y": 0.30, "CA_TBILL": 0.15}
    r = bt_data.load_returns(list(tgt), start="1960-01-31", end="2024-12-31")
    st, row = evaluate_gate("trend_tilt", r, "2015-12-31", tgt, policy(), cls, CFG)
    assert st.gate in ("passe", "echoue") and row.n_trials == 5
    assert row.dsr is None or 0 <= row.dsr <= 1
