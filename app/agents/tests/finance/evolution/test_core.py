"""Briques de l'évolution : PIT, dérive, bandes, flux, mouvements (données synthétiques seulement)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alphaforge.finance.evolution.bands import band_width, breaches, rebalance_to_bands
from alphaforge.finance.evolution.config import Bands
from alphaforge.finance.evolution.drift import active_weights, drift_metric, mark_to_market
from alphaforge.finance.evolution.pit import LookaheadError, PitReturns, month_end
from alphaforge.finance.evolution.rebalance import apply_flow, cost_cad, plan_trades, turnover

BANDS = Bands(abs=0.05, rel=0.25, min_abs=0.005, trade_mode="half")


@pytest.fixture
def pit() -> PitReturns:
    idx = pd.date_range("2020-01-31", periods=24, freq="ME")
    rng = np.random.default_rng(1)
    f = pd.DataFrame(rng.normal(0.005, 0.03, (24, 3)), index=idx, columns=["A", "B", "C"])
    f.loc[idx[:6], "C"] = np.nan  # C commence plus tard
    alt = f * 0.9
    return PitReturns(f, "sha-test", "CAD", alt=alt)


# ---------------------------------------------------------------- PIT
def test_month_end():
    assert month_end("2024-02-10") == pd.Timestamp("2024-02-29")


def test_lookahead_after_horizon(pit):
    v = pit.with_horizon("2020-12-15")
    assert v.horizon == pd.Timestamp("2020-12-31")
    v.month("2020-12-31")
    with pytest.raises(LookaheadError):
        v.month("2021-01-31")
    with pytest.raises(LookaheadError):
        v.upto("2021-01-31")
    with pytest.raises(LookaheadError):
        v.months("2020-01-31", "2021-03-31")
    with pytest.raises(LookaheadError):
        v.with_horizon("2021-06-30")
    assert v.frame.index.max() == pd.Timestamp("2020-12-31")
    up = pit.upto("2020-06-30")
    assert up.index.max() == pd.Timestamp("2020-06-30") and len(up) == 6


def test_prices_only_past(pit):
    t = "2020-12-31"
    p1 = pit.prices(t, ["A", "B"])
    modified = pit.frame.copy()
    modified.loc["2021-01-31":, :] = 0.5  # futur modifié : ne doit rien changer
    p2 = PitReturns(modified, "x").prices(t, ["A", "B"])
    pd.testing.assert_frame_equal(p1, p2)
    exp = (1 + pit.upto(t)["A"]).cumprod()
    np.testing.assert_allclose(p1["A"].values, exp.values)
    assert len(pit.prices(t, months=3)) == 3
    assert pit.prices(t)["C"].iloc[:6].isna().all()


def test_csv_gz_roundtrip(pit, tmp_path):
    p = tmp_path / "r.csv.gz"
    data = pit.to_csv_gz(p)
    assert p.read_bytes() == data
    back = PitReturns.from_csv_gz(p)
    assert back.data_version == "sha-test" and back.currency == "CAD"
    pd.testing.assert_frame_equal(back.frame, pit.frame, check_freq=False)
    usd = PitReturns.from_csv_gz(data, currency="USD")
    pd.testing.assert_frame_equal(usd.frame, pit.frame * 0.9, check_freq=False)
    assert back.to_csv_gz() == data  # déterministe


def test_csv_header_checked():
    import gzip
    with pytest.raises(ValueError):
        PitReturns.from_csv_gz(gzip.compress(b"date,asset,r\n"))


# ---------------------------------------------------------------- dérive
def test_mark_to_market_hand_example():
    w = {"A": 0.6, "B": 0.4, "C": 0.0}
    out, gross, missing = mark_to_market(w, {"A": 0.10, "B": -0.05, "C": float("nan")})
    assert gross == pytest.approx(0.6 * 0.10 + 0.4 * -0.05)
    assert out["A"] == pytest.approx(0.6 * 1.10 / 1.04)
    assert out["B"] == pytest.approx(0.4 * 0.95 / 1.04)
    assert set(out) == set(w) and sum(out.values()) == pytest.approx(1.0)
    assert missing == []
    wv, rv = np.array([0.6, 0.4]), np.array([0.10, -0.05])
    np.testing.assert_allclose([out["A"], out["B"]], wv * (1 + rv) / (1 + wv @ rv))
    _, _, missing = mark_to_market({"A": 0.5, "B": 0.5}, {"A": 0.1})
    assert missing == ["B"]


def test_drift_metric_example():
    w, t = {"A": 0.7, "B": 0.3}, {"A": 0.6, "B": 0.3, "C": 0.1}
    assert drift_metric(w, t) == pytest.approx(0.1)
    assert active_weights(w, t) == pytest.approx({"A": 0.1, "B": 0.0, "C": -0.1})


# ---------------------------------------------------------------- bandes
def test_band_width_rules():
    assert band_width(0.60, BANDS) == pytest.approx(0.05)    # abs plus petite
    assert band_width(0.10, BANDS) == pytest.approx(0.025)   # rel plus petite
    assert band_width(0.01, BANDS) == pytest.approx(0.005)   # plancher min_abs
    assert band_width(0.0, BANDS) == pytest.approx(0.005)


def test_breaches_and_zero_target():
    t = {"A": 0.6, "B": 0.4}
    assert breaches({"A": 0.64, "B": 0.36}, t, BANDS) == []
    assert breaches({"A": 0.66, "B": 0.34}, t, BANDS) == ["A", "B"]
    assert breaches({"A": 0.597, "B": 0.397, "Z": 0.006}, t, BANDS) == ["Z"]
    assert breaches({"A": 0.598, "B": 0.398, "Z": 0.004}, t, BANDS) == []


def test_no_breach_unchanged():
    w, t = {"A": 0.62, "B": 0.38}, {"A": 0.6, "B": 0.4}
    assert rebalance_to_bands(w, t, BANDS) == w


def test_half_mode_closer_and_inside():
    t = {"A": 0.6, "B": 0.3, "C": 0.1}
    w = {"A": 0.68, "B": 0.24, "C": 0.08}   # écarts < 2 × bande
    br = breaches(w, t, BANDS)
    assert br == ["A", "B"]
    new = rebalance_to_bands(w, t, BANDS, mode="half")
    for a in t:
        assert abs(new[a] - t[a]) < abs(w[a] - t[a])
    for a in br:
        assert abs(new[a] - t[a]) <= band_width(t[a], BANDS)
    assert sum(new.values()) == pytest.approx(1.0)


def test_full_mode_is_target():
    t = {"A": 0.6, "B": 0.4}
    assert rebalance_to_bands({"A": 0.7, "B": 0.3, "Z": 0.0}, t, BANDS, mode="full") == pytest.approx(
        {"A": 0.6, "B": 0.4, "Z": 0.0})


def test_edge_mode_lands_on_edge():
    t = {"A": 0.6, "B": 0.3, "C": 0.1}
    w = {"A": 0.70, "B": 0.22, "C": 0.08}
    new = rebalance_to_bands(w, t, BANDS, mode="edge")
    assert new["A"] == pytest.approx(0.65)
    assert sum(new.values()) == pytest.approx(1.0)
    assert breaches(new, t, BANDS) == [] or new["A"] == pytest.approx(0.65)
    assert new["B"] > w["B"] and new["C"] >= w["C"]


@pytest.mark.parametrize("mode", ["half", "edge", "full"])
def test_random_weights_valid(mode):
    rng = np.random.default_rng(0)
    for _ in range(200):
        n = int(rng.integers(2, 8))
        names = [f"X{i}" for i in range(n)]
        t = rng.dirichlet(np.ones(n))
        t[rng.random(n) < 0.2] = 0.0
        if t.sum() == 0:
            t[0] = 1.0
        t /= t.sum()
        w = rng.dirichlet(np.ones(n) * 0.5)
        new = rebalance_to_bands(dict(zip(names, w, strict=True)), dict(zip(names, t, strict=True)), BANDS, mode)
        vals = np.array(list(new.values()))
        assert (vals >= 0).all()
        assert vals.sum() == pytest.approx(1.0, abs=1e-9)
        assert set(new) == set(names)


# ---------------------------------------------------------------- flux et mouvements
def test_contribution_goes_to_underweights_first():
    w, t = {"A": 0.7, "B": 0.3}, {"A": 0.6, "B": 0.4}
    new, V = apply_flow(w, 10_000.0, 1_000.0, t)
    assert V == pytest.approx(11_000.0)
    # B manque 0,4·11 000 − 3 000 = 1 400 > 1 000 : tout va à B
    assert new["A"] == pytest.approx(7_000 / 11_000)
    assert new["B"] == pytest.approx(4_000 / 11_000)
    pro, _ = apply_flow(w, 10_000.0, 1_000.0, t, contribution_first=False)
    assert turnover(new, t)[0] < turnover(pro, t)[0]
    assert sum(new.values()) == pytest.approx(1.0)


def test_contribution_all_underweight_reaches_target():
    new, V = apply_flow({"A": 0.7, "B": 0.3}, 10_000.0, 5_000.0, {"A": 0.6, "B": 0.4})
    # manques : A = 0,6·15 000 − 7 000 = 2 000, B = 0,4·15 000 − 3 000 = 3 000 ; total = apport -> cible
    assert new == pytest.approx({"A": 0.6, "B": 0.4})


def test_withdrawal_from_overweights():
    w, t = {"A": 0.7, "B": 0.3}, {"A": 0.6, "B": 0.4}
    new, V = apply_flow(w, 10_000.0, -1_000.0, t)
    assert V == pytest.approx(9_000.0)
    assert new["B"] * V == pytest.approx(3_000.0)   # excès de A = 7 000 − 5 400 = 1 600 >= 1 000
    big, V2 = apply_flow(w, 10_000.0, -20_000.0, t)
    assert V2 == 0.0
    allout, V3 = apply_flow(w, 10_000.0, -9_000.0, t)
    assert V3 == pytest.approx(1_000.0) and sum(allout.values()) == pytest.approx(1.0)
    assert min(allout.values()) >= 0


def test_plan_trades_filter_and_sum():
    wf = {"A": 0.50, "B": 0.30, "C": 0.20}
    wt = {"A": 0.45, "B": 0.345, "C": 0.205}
    trades, eff = plan_trades(wf, wt, 10_000.0, "band", min_trade_cad=100.0)
    assert [t.asset_id for t in trades] == ["A", "B"]      # C : 0,005 × 10 000 = 50 $ < 100 $
    assert eff["C"] == pytest.approx(0.20)
    assert sum(eff.values()) == pytest.approx(1.0)
    # résidu 1 − (0,45 + 0,345 + 0,20) = 0,005 absorbé par A (plus gros mouvement) -> 0,455
    assert trades[0].w_to == pytest.approx(0.455) and trades[0].amount_cad == pytest.approx(-450.0)
    assert all(t.reason == "band" for t in trades)
    none, eff2 = plan_trades(wf, wt, 10_000.0, "band", min_trade_cad=1e6)
    assert none == [] and eff2 == wf


def test_turnover_and_cost():
    one, two = turnover({"A": 0.6, "B": 0.4}, {"A": 0.5, "B": 0.5})
    assert (one, two) == pytest.approx((0.1, 0.2))
    assert cost_cad(0.1, 100_000.0, 10.0) == pytest.approx(10.0)
