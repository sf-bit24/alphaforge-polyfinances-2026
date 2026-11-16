"""Répartition de l'argent de bout en bout (``build_portfolio``, mode ``rules``) sur les trois profils FICTION.

Lit les données longues du moteur (NEEDS_ENGINE dans conftest.py) : ventilation look-through réelle de SPY et ESGV.
"""

from __future__ import annotations

import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")

from alphaforge.finance.backtest import data as bt_data  # noqa: E402
from alphaforge.finance.debate import allocation as al  # noqa: E402
from alphaforge.finance.debate.explain import verify  # noqa: E402
from alphaforge.finance.debate.facts import FactBook  # noqa: E402
from alphaforge.finance.debate.pipeline import DEFAULT_AS_OF, build_portfolio  # noqa: E402
from alphaforge.finance.observability.verify import verify_decision  # noqa: E402
from alphaforge.finance.personas import load  # noqa: E402


@pytest.fixture(scope="module", params=["amira", "mateo", "robert"])
def built(request):
    profile, si, _, _ = load(request.param)
    return profile, build_portfolio(profile, DEFAULT_AS_OF, mode="rules", style_inputs=si)


def test_allocation_matches_final_positions(built):
    profile, res = built
    alloc = res.allocation
    d = res.decision
    assert [p["asset_id"] for p in alloc["positions"]] == [p.asset_id for p in d.positions]
    for row, pos in zip(alloc["positions"], d.positions, strict=True):
        assert row["weight"] == pytest.approx(pos.weight, abs=1e-10) and 0.0 <= row["weight"] <= 1.0
    assert alloc["amount_cad"] == profile.investable_wealth
    for name in ("by_class", "by_currency", "by_sector"):
        assert sum(r["weight"] for r in alloc[name]) == pytest.approx(1.0, abs=1e-9)
        for r in alloc[name]:
            assert r["amount_cad"] == round(r["weight"] * profile.investable_wealth, 2)
            assert 0.0 <= r["weight"] <= 1.0
    assert 0.0 <= alloc["sector_coverage"] <= 1.0
    known = sum(r["weight"] for r in alloc["by_sector"] if r["key"] != "non_ventile")
    assert alloc["sector_coverage"] == pytest.approx(known)


def test_facts_are_in_decision_and_statement_verifies(built):
    _, res = built
    d = res.decision
    facts = {f.fact_id: f for f in d.facts}
    alloc = res.allocation
    for name in ("positions", "by_class", "by_currency", "by_sector"):
        assert all(r["fact_id"] in facts for r in alloc[name])
    st = next(s for s in d.explanation.data_used if s.text_fr.startswith("Répartition de l'argent"))
    assert st.fact_ids == [r["fact_id"] for r in alloc["by_class"]]
    book = FactBook(d.decision_id)
    book.facts = facts
    assert verify(book, st) == []
    assert verify_decision(d).ok


def test_lookthrough_uses_real_engine_data():
    lt = al.load_lookthrough(["SPY", "ESGV", "QQQ", "XIU.TO"], DEFAULT_AS_OF)
    assert set(lt.shares) == {"SPY", "ESGV"}  # QQQ, XIU.TO : pas de répartition dans les données, non ventilés
    for shares in lt.shares.values():
        assert sum(shares.values()) == pytest.approx(1.0, abs=1e-9)
    assert lt.month == "2026-09-30"


def test_kf_mapping_follows_catalogue_tags():
    cat = bt_data.load_assets()
    for col, key in al.KF_SECTOR.items():
        tags = cat.at[col, "tag_list"]
        assert key in tags, (col, key, tags)
