import pytest

# The engine needs the `finance` dependency group (numpy, pandas, scipy), not installed by a plain `uv sync`.
pytest.importorskip("numpy")
pytest.importorskip("pandas")
pytest.importorskip("scipy")

import copy

import numpy as np
import pandas as pd

from alphaforge.finance.backtest.backtest import ConstraintProvider, evaluate, run_window
from alphaforge.finance.backtest.data import load_inflation, load_returns
from alphaforge.finance.backtest.oracle import oracle_window
from alphaforge.finance.backtest.profile import validate
from alphaforge.finance.backtest.run import run_profile
from alphaforge.finance.backtest.strategies import build_strategy
from alphaforge.finance.backtest.windows import Window


def test_example_profile_loads(example_profile):
    assert example_profile["id"] == "example"
    assert len(example_profile["strategies"]) == 9


def test_invalid_profile_rejected(prof):
    prof["universe"] = ["US_MKT", "NOPE"]
    with pytest.raises(ValueError):
        validate(prof)


@pytest.fixture(scope="module")
def setup(example_profile):
    p = example_profile
    R = load_returns(p["universe"], "1926-07", None, p["currency"])
    infl = load_inflation(p["currency"])
    prov = ConstraintProvider(p["universe"], p["constraints"])
    start = pd.Timestamp("1970-01-31")
    w = Window(start, R.index[R.index.get_loc(start) + 119], 120)
    return p, R, infl, prov, w


def test_all_strategies_respect_constraints(setup):
    p, R, infl, prov, w = setup
    for spec in p["strategies"]:
        res = run_window(R, infl, w, build_strategy(spec), p, prov)
        W = res["weights"]
        assert np.allclose(W.sum(axis=1), 1.0, atol=1e-6), spec["name"]
        assert res["traded"].iloc[0]
        for d, row in W[res["traded"]].iterrows():  # constraints are enforced at every trade date
            cs = prov.at(R.index[R.index.get_loc(d) - 1])
            assert cs.is_feasible(row.values, 1e-4), (spec["name"], d, cs.violations(row.values))
        assert res["metrics"]["drift_months_outside_constraints"] >= 0


def test_oracle_is_hindsight_and_beats_fixed_mixes(setup):
    p, R, infl, prov, w = setup
    o = oracle_window(R, infl, w, p, prov)
    assert o["hindsight"] is True and "non investissable" in o["label"]
    assert not o["constraint_violations"]
    X = R.loc[w.start:w.end]
    cs = prov.for_window(w)
    inf, rf = infl.reindex(X.index).values, X[p["cash_asset"]].values
    for seed in range(5):
        alt = cs.project(np.random.default_rng(seed).dirichlet(np.ones(len(R.columns))))
        m = evaluate(X.values @ alt, inf, rf, p)
        pen = 0 if not m["risk_breaches"] else 1
        if pen == 0:
            assert o["metrics"]["score"] >= m["score"] - 1e-6


def test_run_profile_end_to_end(prof, tmp_path):
    prof["strategies"] = prof["strategies"][:2]
    res = run_profile(prof, mode="non_overlapping", horizon=5, start="1990-01", end="2019-12", oracle=True,
                      out_dir=tmp_path, verbose=False)
    rows = res["rows"]
    assert set(rows["strategy"]) == {"static_60_40", "static_diversified", "ORACLE"}
    assert rows.loc[rows["strategy"] == "ORACLE", "hindsight"].all()
    assert len(res["windows"]) == 6
    import json
    tr = json.loads(open(res["trace_path"]).read())
    assert tr["data_version"]["data_sha256"] and tr["engine_sha256"] and tr["seed"] == 42
    assert all(r["hindsight"] for r in tr["results"] if r["strategy"] == "ORACLE")


def test_progress_reaches_one_at_last_scheduled_decision():
    from alphaforge.finance.backtest.backtest import _progress
    assert _progress("annual", 0, 120) == 0.0
    assert _progress("annual", 108, 120) == 1.0          # last annual trade of a 10-year window
    assert _progress("quarterly", 117, 120) == 1.0
    assert _progress("monthly", 119, 120) == 1.0
    assert _progress("bands", 119, 120) == 1.0
    assert _progress("never", 0, 120) == 0.0
    assert _progress("annual", 0, 12) == 0.0             # single decision -> stays on start weights


@pytest.mark.parametrize("freq", ["annual", "quarterly", "monthly"])
def test_glidepath_reaches_end_weights(setup, freq):
    """Regression: the last trade of a glidepath must target end_weights (was 90 % of the way
    with annual rebalancing because progress was i / n)."""
    p, R, infl, prov, w = setup
    spec = copy.deepcopy(next(s for s in p["strategies"] if s["type"] == "glidepath"))
    spec["rebalancing"] = {"frequency": freq}
    res = run_window(R, infl, w, build_strategy(spec), p, prov)
    traded = res["weights"][res["traded"]]
    first, last = traded.index[0], traded.index[-1]
    assets = list(R.columns)

    def vec(d):
        return np.array([float(d.get(a, 0.0)) for a in assets])

    cs_first = prov.at(R.index[R.index.get_loc(first) - 1])
    cs_last = prov.at(R.index[R.index.get_loc(last) - 1])
    assert np.allclose(traded.iloc[0].values, cs_first.project(vec(spec["params"]["start_weights"])), atol=1e-6)
    assert np.allclose(traded.iloc[-1].values, cs_last.project(vec(spec["params"]["end_weights"])), atol=1e-6)
