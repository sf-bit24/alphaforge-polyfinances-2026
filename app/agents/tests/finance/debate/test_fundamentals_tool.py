"""Outil ``fundamentals_evidence`` des lentilles diversité et contraintes (numpy requis par ``tools``, pas les données
longues). Sans magasin OKF, les listes d'outils, donc les clés de rejeu LLM, ne changent pas."""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")

from alphaforge.finance.debate.facts import FactBook  # noqa: E402
from alphaforge.finance.debate.okf_bridge import OkfMarketStore  # noqa: E402
from alphaforge.finance.debate.tools import LensContext, strands_tools  # noqa: E402
from alphaforge.store.local import LocalStore  # noqa: E402

from ..strategy._okf_docs import SOCIETES  # noqa: E402

AS_OF = date(2026, 9, 30)
BEFORE = {
    "timeline": ["horizon_distribution", "stress_episodes"],
    "risk": ["stress_episodes", "horizon_distribution"],
    "diversity": ["exposure", "esg_evidence"],
    "constraints": ["exposure", "esg_evidence"],
}


def _ctx(evidence_fn=None) -> LensContext:
    return LensContext(None, None, {}, AS_OF, FactBook("dec-tool"), label="r1", evidence_fn=evidence_fn)


def _names(lens, ctx):
    return [t.tool_name for t in strands_tools(lens, ctx)]


@pytest.fixture
def market(tmp_path):
    store = LocalStore(tmp_path)
    store.put_text("general/societes/atd.md", (SOCIETES / "atd.md").read_text(encoding="utf-8"))
    return OkfMarketStore(store)


def test_tool_lists_unchanged_without_an_evidence_function():
    assert {lens: _names(lens, _ctx()) for lens in BEFORE} == BEFORE


def test_fundamentals_tool_added_to_diversity_and_constraints_only(market):
    ctx = _ctx(market.evidence)
    got = {lens: _names(lens, ctx) for lens in BEFORE}
    assert got["timeline"] == BEFORE["timeline"] and got["risk"] == BEFORE["risk"]
    for lens in ("diversity", "constraints"):
        assert got[lens] == [*BEFORE[lens], "fundamentals_evidence"]


def test_tool_absorbs_restamped_facts(market):
    ctx = _ctx(market.evidence)
    tool = next(t for t in strands_tools("diversity", ctx) if t.tool_name == "fundamentals_evidence")
    shown = tool("atd.to")
    ids = [x["fact_id"] for x in shown]
    assert ids and all(i.startswith("okf.fund.ATD.TO.") for i in ids)
    step = ctx.book.trace[-1]
    assert step.agent == "lens.diversity" and step.tool == "fundamentals_evidence"
    assert all(ctx.book.facts[i].trace_id == step.trace_id for i in ids)
    assert tool("CSU.TO") == []  # pas couverte : liste vide
