"""Ex-ante strategies must not change when FUTURE data changes."""
import pytest

# The engine needs the `finance` dependency group (numpy, pandas, scipy), not installed by a plain `uv sync`.
pytest.importorskip("numpy")
pytest.importorskip("pandas")
pytest.importorskip("scipy")

import copy

import numpy as np
import pandas as pd

from alphaforge.finance.backtest.backtest import ConstraintProvider, run_window
from alphaforge.finance.backtest.data import load_inflation, load_returns
from alphaforge.finance.backtest.strategies import build_strategy
from alphaforge.finance.backtest.windows import Window


@pytest.fixture(scope="module")
def data(example_profile):
    p = example_profile
    R = load_returns(p["universe"], "1926-07", None, p["currency"])
    return R, load_inflation(p["currency"])


def test_no_lookahead_all_strategies(example_profile, data):
    p = copy.deepcopy(example_profile)
    R, infl = data
    start = pd.Timestamp("1990-01-31")
    pos = R.index.get_loc(start)
    w = Window(start, R.index[pos + 59], 60)
    k = 30  # perturb every return from the k-th month of the window onward
    R2 = R.copy()
    rng = np.random.default_rng(0)
    R2.iloc[pos + k:] = R2.iloc[pos + k:] + rng.normal(0, 0.05, R2.iloc[pos + k:].shape)
    prov = ConstraintProvider(p["universe"], p["constraints"])
    changed = set()
    for spec in p["strategies"]:
        for rb in ({"frequency": "monthly"}, None):
            s_spec = dict(spec, rebalancing=rb or spec.get("rebalancing"))
            a = run_window(R, infl, w, build_strategy(s_spec), p, prov)["weights"]
            b = run_window(R2, infl, w, build_strategy(s_spec), p, prov)["weights"]
            # weights held in month t are decided with returns < t, so months <= k are identical
            np.testing.assert_allclose(a.iloc[: k + 1].values, b.iloc[: k + 1].values, atol=1e-12,
                                       err_msg=f"look-ahead in {spec['name']}")
            if spec["type"] in ("min_variance", "risk_parity", "trend_filter", "momentum") and rb:
                changed.add(spec["name"])
                # sanity: the perturbation must be able to change LATER decisions (test is not vacuous)
                assert not np.allclose(a.iloc[k + 2:].values, b.iloc[k + 2:].values), spec["name"]
    assert changed


def test_strategy_sees_only_past(example_profile, data):
    """The history passed to a strategy ends strictly before the decision month."""
    p = example_profile
    R, infl = data
    seen = []

    class Spy:
        name, rebalancing, window_dependent, min_history = "spy", {"frequency": "monthly"}, True, 0

        def target(self, hist, ctx):
            seen.append((hist.index.max(), ctx.date))
            return np.full(len(ctx.assets), 1 / len(ctx.assets))

    start = pd.Timestamp("2000-01-31")
    w = Window(start, R.index[R.index.get_loc(start) + 11], 12)
    run_window(R, infl, w, Spy(), p, ConstraintProvider(p["universe"], p["constraints"]))
    assert len(seen) == 12 and all(h < d for h, d in seen)
