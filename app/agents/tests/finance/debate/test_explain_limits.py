"""Première limite de l'explication : la période des données est sourcée par des Facts, jamais écrite à la main."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from alphaforge.finance.contracts.decision import Explanation, Statement
from alphaforge.finance.debate import explain
from alphaforge.finance.debate.explain import skeleton, verify, verify_fr
from alphaforge.finance.debate.facts import FactBook

WINDOW = "rendements mensuels CAD 2011-03-31..2026-09-30 (187 mois)"  # écrit par tools.risk_evidence
ENGINE = "alphaforge.finance.backtest (rendements mensuels, data/long)"


def _book(processing: str | None = WINDOW) -> FactBook:
    book = FactBook("dec-test")
    with book.step("s0.policy_compiler", tool="compile_profile"):
        book.add("level", "Niveau de risque effectif", "N1", "niveau", dataset="risk_levels.yaml")
    with book.step("lens.risk", tool="evidence", inputs={"label": "r2"}):
        book.add("r2.cvar_m", "CVaR 95 % mensuelle (historique)", 0.021, "%", dataset=ENGINE, processing=processing)
        book.add("r2.mdd", "Baisse maximale historique (fenêtre)", 0.081, "%", dataset=ENGINE, processing=processing)
    return book


def _limit(book: FactBook) -> Statement:
    expl = skeleton(
        book, kind="proposition", level_fid="level", cand="r2", active_fids=[], applied=[], counterfactual_stmts=[]
    )
    return expl.limits[0]


def test_the_period_is_the_measured_window_and_cites_its_facts():
    book = _book()
    limit = _limit(book)
    assert limit.text_fr == (
        "Les chiffres décrivent le passé (2011-2026 pour les titres réels, proxys longs étiquetés HYPOTHESE) : "
        "ils ne prédisent pas les rendements futurs."
    )
    assert limit.fact_ids == ["r2.window.first_year", "r2.window.last_year"] and limit.label == "HYPOTHESE"
    first, last = (book.facts[i] for i in limit.fact_ids)
    assert (first.value, last.value, first.unit, first.status) == (2011, 2026, "année", "FAIT")
    # Même provenance que les mesures : l'étape qui a lu la fenêtre, le même jeu de données.
    assert first.trace_id == last.trace_id == book.facts["r2.cvar_m"].trace_id
    assert first.sources[0].dataset == ENGINE and "2011-03-31..2026-09-30" in first.sources[0].processing
    assert verify(book, limit) == []


def test_a_rephrasing_that_keeps_the_years_now_passes_the_verifier():
    book = _book()
    limit = _limit(book)
    kept = Statement(
        text_fr="Ces résultats viennent du passé (2011-2026, titres réels) : ils ne disent rien de l'avenir.",
        fact_ids=limit.fact_ids,
        label=limit.label,
    )
    assert verify(book, kept) == []
    # Avant : l'énoncé ne citait aucun fait, la même reformulation était rejetée.
    assert verify(book, kept.model_copy(update={"fact_ids": []})) == ["nombres non sourcés : ['2011', '2026']"]
    assert verify_fr(book, kept.model_copy(update={"fact_ids": []})) == ["nombres non sourcés : 2011, 2026"]
    # Une année qui n'est pas celle des données reste rejetée.
    wrong = kept.model_copy(update={"text_fr": "Ces résultats viennent du passé (2018-2026)."})
    assert verify(book, wrong) == ["nombres non sourcés : ['2018']"]


def test_rephrase_keeps_the_llm_wording_of_the_first_limit(monkeypatch):
    """Bout en bout sans Bedrock : la reformulation de limits[0] qui recopie les années n'est plus remplacée."""
    import strands

    book = _book()
    expl = skeleton(
        book, kind="proposition", level_fid="level", cand="r2", active_fids=[], applied=[], counterfactual_stmts=[]
    )
    reworded = "Ces chiffres décrivent le passé (2011-2026 pour les titres réels) ; ils ne prédisent rien."

    class FakeAgent:
        def __init__(self, **_):
            pass

        def __call__(self, prompt, structured_output_model=None):
            new = expl.model_dump()
            new["limits"][0]["text_fr"] = reworded
            return SimpleNamespace(structured_output=Explanation(**new))

    monkeypatch.setattr(strands, "Agent", FakeAgent)
    out, report = explain.rephrase(book, expl, "debutant", model_factory=lambda *_: None)
    assert out.limits[0].text_fr == reworded and out.limits[0].fact_ids == expl.limits[0].fact_ids
    assert not any(line.startswith("1er énoncé de « Quelles limites ? »") for line in report), report


@pytest.mark.parametrize("processing", [None, "contribution d'Euler à la CVaR mensuelle"])
def test_without_a_recorded_window_no_year_is_written(processing):
    book = _book(processing)
    n_facts = len(book.facts)
    limit = _limit(book)
    assert limit.text_fr == (
        "Les chiffres décrivent le passé (titres réels, proxys longs étiquetés HYPOTHESE) : "
        "ils ne prédisent pas les rendements futurs."
    )
    assert limit.fact_ids == [] and len(book.facts) == n_facts and verify(book, limit) == []


def test_the_window_facts_are_recorded_once():
    book = _book()
    first = _limit(book)
    n_facts = len(book.facts)
    assert _limit(book) == first and len(book.facts) == n_facts
