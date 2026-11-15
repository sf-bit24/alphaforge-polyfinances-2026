"""Mesures de performance (TWR, MWR, CAGR, drawdowns) et historique chaîné des versions (synthétique)."""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pytest

from alphaforge.finance.backtest import metrics as bt
from alphaforge.finance.contracts.evolution import PortfolioVersion, RebalanceEvent, Trade
from alphaforge.finance.evolution import performance as pf
from alphaforge.finance.evolution.history import GENESIS, HistoryError, HistoryStore, version_id

R = [0.02, -0.01, 0.03, -0.05, 0.04, 0.01, -0.02, 0.015, 0.0, 0.025, -0.03, 0.02,
     0.01, -0.015, 0.02, 0.005, -0.01, 0.03, 0.01, -0.02, 0.015, 0.0, 0.01, 0.02]


# --------------------------------------------------------------------------- performance

def test_twr_is_chain_linked_product():
    assert pf.twr_from_returns([0.10, -0.10]) == pytest.approx(1.1 * 0.9 - 1)   # -1 %
    assert pf.twr_from_returns(R) == pytest.approx(bt.cumulative_growth(R) - 1)
    assert pf.twr_from_returns([]) == 0.0


def test_twr_independent_of_flows():
    # Deux trajectoires mêmes rendements, flux différents : la valeur diffère, le TWR non.
    t1, t2 = pf.PerfTracker(1000), pf.PerfTracker(1000)
    v1 = v2 = 1000.0
    for i, r in enumerate(R):
        f2 = 5000.0 if i == 5 else (-300.0 if i == 15 else 0.0)
        v1, v2 = v1 * (1 + r), v2 * (1 + r) + f2
        t1.update(date(2020 + i // 12, i % 12 + 1, 1), r, v1)
        t2.update(date(2020 + i // 12, i % 12 + 1, 1), r, v2, flow_cad=f2)
    s1, s2 = t1.snapshot(), t2.snapshot()
    assert s1.value_cad != pytest.approx(s2.value_cad)
    assert s1.twr_cum == pytest.approx(s2.twr_cum)
    assert s1.max_drawdown == pytest.approx(s2.max_drawdown)


def test_annualize_none_under_12_months():
    assert pf.annualize(0.05, 11) is None
    assert pf.annualize(0.21, 24) == pytest.approx(0.10)
    assert pf.cagr(100, 110, 6) is None


def test_cagr_hand_example():
    assert pf.cagr(100.0, 121.0, 24) == pytest.approx(0.10)       # 1,21^(1/2) - 1
    assert pf.cagr(100.0, 100.0, 36) == pytest.approx(0.0)


def test_mwr_equals_twr_without_intermediate_flows():
    v_end = 1000.0 * (1 + pf.twr_from_returns(R))
    m = pf.mwr([1000.0] + [0.0] * (len(R) - 1), v_end)
    assert m == pytest.approx(pf.annualize(pf.twr_from_returns(R), len(R)), abs=1e-6)
    assert m == pytest.approx(bt.annualized_return(R), abs=1e-6)


def test_mwr_hand_example_and_none():
    # 100 placé, 121 deux ans plus tard : TRI mensuel 1,21^(1/24)-1, soit 10 % l'an.
    assert pf.mwr([100.0] + [0.0] * 23, 121.0) == pytest.approx(0.10, abs=1e-9)
    assert pf.mwr([100.0] * 6, 700.0) is None                      # < 12 mois : pas d'annualisation
    assert pf.mwr([100.0] + [0.0] * 23, -5.0) is None              # pas de changement de signe dans la plage


def test_mwr_below_twr_when_big_contribution_precedes_loss():
    r = [0.02] * 12 + [-0.01] * 12
    t = pf.PerfTracker(1000.0)
    v = 1000.0
    for i, x in enumerate(r):
        f = 20000.0 if i == 11 else 0.0                            # gros apport en fin de mois 12
        v = v * (1 + x) + f
        t.update(date(2020 + i // 12, i % 12 + 1, 1), x, v, flow_cad=f)
    s = t.snapshot()
    assert s.twr_ann > 0
    assert s.mwr_ann < s.twr_ann
    assert s.mwr_ann < 0                                           # l'essentiel du capital a subi la baisse


def test_hwm_and_drawdown_on_twr_index_match_metrics():
    idx = pf.twr_index(R)
    np.testing.assert_allclose(pf.drawdowns(idx)[1:], bt.drawdown_series(R), atol=1e-12)
    assert pf.drawdowns(idx).max() == pytest.approx(bt.max_drawdown(R))
    assert pf.max_drawdown_twr(R) == pytest.approx(bt.max_drawdown(R))
    np.testing.assert_allclose(pf.high_water_mark([1, 1.2, 1.1, 1.3]), [1, 1.2, 1.2, 1.3])
    np.testing.assert_allclose(pf.drawdowns([1, 1.2, 0.9, 1.3]), [0, 0, 0.25, 0])


def test_drawdown_vs_invested():
    np.testing.assert_allclose(pf.drawdown_vs_invested([90, 120, 0], [100, 100, 0]), [0.10, 0.0, 0.0])


def test_months_underwater():
    assert pf.months_underwater([1.0, 1.1, 1.0, 0.9, 1.2, 1.1]) == (1, 2)
    assert pf.months_underwater([1.0, 1.1, 1.2]) == (0, 0)
    _, best = pf.months_underwater(pf.twr_index(R))
    assert best == bt.max_underwater_months(R)


def test_cash_drag_approximation():
    w = [{"CASH": 0.10, "EQ": 0.90}, {"CASH": 0.20, "EQ": 0.80}]
    # poids moyen 0,15 × (moyenne 1,5 % - moyenne 0,25 %) × 12 = 0,0225
    assert pf.cash_drag(w, ["CASH"], [0.01, 0.02], [0.002, 0.003]) == pytest.approx(0.0225)
    assert pf.cash_drag([], ["CASH"], [], []) is None


def test_perf_tracker_snapshot_fields():
    t = pf.PerfTracker(1000.0, cash_assets=["CASH"])
    v = 1000.0
    for i in range(12):
        f = 100.0 if i == 5 else 0.0
        v = v * 1.01 + f
        t.update(date(2021, i + 1, 1), 0.01, v, flow_cad=f, turnover_oneway=0.02, cost_cad=1.5,
                 weights={"CASH": 0.05, "EQ": 0.95}, r_cash=0.002)
    s = t.snapshot()
    assert s.months == 12
    assert s.invested_cad == pytest.approx(1100.0)
    assert s.value_cad == pytest.approx(v)
    assert s.twr_cum == pytest.approx(1.01 ** 12 - 1)
    assert s.twr_ann == pytest.approx(1.01 ** 12 - 1)
    assert s.cagr == pytest.approx(s.twr_ann)
    assert s.mwr_ann == pytest.approx(s.twr_ann, abs=1e-6)        # rendement constant : TRI = TWR
    assert s.max_drawdown == 0.0 and s.current_drawdown == 0.0 and s.months_underwater == 0
    assert s.high_water_mark_cad == pytest.approx(v)
    assert s.turnover_oneway_cum == pytest.approx(0.24)
    assert s.costs_cad_cum == pytest.approx(18.0)
    assert s.cash_drag == pytest.approx(0.05 * (0.01 - 0.002) * 12)
    with pytest.raises(ValueError):
        t.update(date(2021, 12, 1), 0.0, v)                        # mois non croissant


def test_perf_tracker_under_one_year():
    t = pf.PerfTracker(500.0)
    t.update(date(2022, 1, 1), -0.10, 450.0)
    s = t.snapshot()
    assert s.twr_ann is None and s.mwr_ann is None and s.cagr is None
    assert s.current_drawdown == pytest.approx(0.10) and s.months_underwater == 1


# --------------------------------------------------------------------------- historique

CID = "client-demo"


def _version(seq: int, parent: str | None, month: int, value: float = 10000.0) -> PortfolioVersion:
    as_of = date(2024, month, 1)
    vid = version_id(CID, seq, as_of)
    trades = [Trade(asset_id="EQ", w_from=0.62, w_to=0.60, dw=-0.02, amount_cad=-200.0, reason="band"),
              Trade(asset_id="BD", w_from=0.38, w_to=0.40, dw=0.02, amount_cad=200.0, reason="band")]
    ev = RebalanceEvent(event_id=f"ev-{vid}", month=as_of, action="REBALANCE_TO_BANDS" if seq else "HOLD",
                        drift=0.02, trades=trades if seq else [], turnover_oneway=0.02 if seq else 0.0)
    return PortfolioVersion(version_id=vid, parent_version_id=parent, seq=seq, client_id=CID, profile_version=1,
                            as_of=as_of, weights={"EQ": 0.6, "BD": 0.4}, value_cad=value,
                            target={"EQ": 0.6, "BD": 0.4}, level="N2", policy_hash="p" * 8,
                            data_version="test", config_hash="c" * 8, event=ev)


def _fill(h: HistoryStore, n: int = 3) -> list[PortfolioVersion]:
    out, parent = [], None
    for s in range(n):
        v = _version(s, parent, s + 1, 10000.0 + 100 * s)
        h.append(v)
        out.append(v)
        parent = v.version_id
    return out


def test_version_id_deterministic():
    a = version_id(CID, 3, date(2024, 5, 31))
    assert a == version_id(CID, 3, date(2024, 5, 1))
    assert a.startswith("pv-") and a.endswith("-0003-202405") and len(a.split("-")[1]) == 8
    assert a != version_id("autre", 3, date(2024, 5, 1))


def test_history_append_and_verify_memory():
    h = HistoryStore(CID)
    vs = _fill(h)
    assert [v.version_id for v in h.versions()] == [v.version_id for v in vs]
    assert h.last() == vs[-1]
    idx = h.index()
    assert idx[0]["prev_hash"] == GENESIS and idx[1]["prev_hash"] == idx[0]["record_hash"]
    assert {"version_id", "seq", "as_of", "action", "level", "value_cad", "drift", "record_hash"} <= set(idx[0])
    assert h.verify() == (True, None)
    md = h.store.get(f"clients/{CID}/portefeuilles/0001-202402.md").text
    assert md.startswith("---\ntype: Portfolio Version") and "rééquilibrage illustratif" in md and "| EQ |" in md


def test_wrong_seq_or_parent_refused():
    h = HistoryStore(CID)
    vs = _fill(h, 2)
    with pytest.raises(HistoryError):
        h.append(_version(5, vs[-1].version_id, 3))                # séquence sautée
    with pytest.raises(HistoryError):
        h.append(_version(2, vs[0].version_id, 3))                 # mauvais parent
    with pytest.raises(HistoryError):
        h.append(_version(1, vs[0].version_id, 2))                 # rejouer une séquence existante
    with pytest.raises(HistoryError):
        HistoryStore(CID).append(_version(0, "pv-x", 1))           # première version avec un parent
    assert len(h.index()) == 2 and h.verify() == (True, None)


def test_tampering_breaks_verify_local(tmp_path):
    h = HistoryStore(CID, tmp_path)
    vs = _fill(h)
    path = tmp_path / "clients" / CID / "portefeuilles" / "0001-202402.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["value_cad"] = 999999.0
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert h.verify() == (False, vs[1].version_id)


def test_local_directory_round_trip(tmp_path):
    vs = _fill(HistoryStore(CID, tmp_path))
    h2 = HistoryStore(CID, str(tmp_path))                          # nouvelle instance, même répertoire
    assert h2.versions() == vs
    assert h2.verify() == (True, None)
    nxt = _version(3, vs[-1].version_id, 4)
    entry = h2.append(nxt)
    assert entry["seq"] == 3 and h2.last() == nxt
    files = sorted(p.name for p in (tmp_path / "clients" / CID / "portefeuilles").iterdir())
    assert files == ["0000-202401.json", "0000-202401.md", "0001-202402.json", "0001-202402.md",
                     "0002-202403.json", "0002-202403.md", "0003-202404.json", "0003-202404.md", "index.json"]
