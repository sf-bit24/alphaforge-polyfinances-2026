import numpy as np
import pytest

from engine.constraints import ConstraintSet

ASSETS = ["US_MKT", "US_IND_BUSEQ", "UST_10Y", "GOLD", "UST_TBILL"]


def cfg(**k):
    base = {"default_bounds": [0, 1], "asset_bounds": {"GOLD": [0.05, 0.15]}, "class_max_weight": {},
            "exclude": {"assets": [], "tags": [], "classes": []},
            "groups": [{"name": "tech", "exposure": "tech", "max": 0.30},
                       {"name": "def", "tags_any": ["defensive"], "min": 0.30}], "exposure_overrides": {}}
    base.update(k)
    return base


@pytest.mark.parametrize("seed", range(10))
def test_projection_is_feasible_and_sums_to_one(seed):
    cs = ConstraintSet(ASSETS, cfg(), date="2020-12")
    w0 = np.random.default_rng(seed).normal(size=len(ASSETS))
    w = cs.project(w0)
    assert w.sum() == pytest.approx(1.0, abs=1e-9)
    assert cs.is_feasible(w), cs.violations(w)


def test_lookthrough_counts_market_tech_share():
    cs = ConstraintSet(ASSETS, cfg(), date="2020-12")
    vec = cs.groups[0][1]
    assert vec[1] == 1.0          # BusEq sector = 100 % tech
    assert 0 < vec[0] < 0.6       # US_MKT = BusEq market-cap share at that date
    w = cs.project(np.array([0.0, 0.0, 0.0, 0.0, 0.0]) + np.array([0.9, 0.1, 0, 0, 0]))
    assert vec @ w <= 0.30 + 1e-6


def test_exclusions_by_tag_and_class():
    cs = ConstraintSet(["US_MKT", "US_IND_ENRGY", "BTC-USD", "UST_TBILL"],
                       cfg(asset_bounds={}, groups=[], exclude={"assets": [], "tags": ["fossil_fuel"], "classes": ["crypto"]}))
    w = cs.project(np.array([0.25, 0.25, 0.25, 0.25]))
    assert w[1] == pytest.approx(0) and w[2] == pytest.approx(0)
    assert set(cs.excluded) == {"US_IND_ENRGY", "BTC-USD"}


def test_infeasible_raises():
    cs = ConstraintSet(ASSETS, cfg(groups=[{"name": "def", "tags_any": ["defensive"], "min": 0.9},
                                           {"name": "eq", "assets": ["US_MKT"], "min": 0.5}]))
    with pytest.raises(ValueError):
        cs.feasible_point()
