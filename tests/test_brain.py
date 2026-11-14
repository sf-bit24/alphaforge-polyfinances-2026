from pathlib import Path

import pandas as pd

from brain.agents import Brain
from brain.models import Asset, load_persona


def brain():
    rows = pd.read_csv(Path("data/raw/assets_universe.csv")).to_dict("records")
    return Brain([Asset(**r) for r in rows])


def test_personas_load():
    assert load_persona("amira").name == "Amira"
    assert load_persona("mateo").constraints.esg_required


def test_governance_refuses_all_in_crypto_for_mateo():
    d = brain().recommend(load_persona("mateo"), "tout investir en crypto")
    assert d.portfolio.refused
    assert any(e.agent == "GovernanceAgent" for e in d.trace)


def test_recommendation_is_bounded():
    d = brain().recommend(load_persona("robert"))
    assert sum(a.weight for a in d.portfolio.allocations) == 1
    assert all(a.weight >= 0 for a in d.portfolio.allocations)
