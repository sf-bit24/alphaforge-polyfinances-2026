"""Suite de l'issue #78, après la vérification de bout en bout en mode LLM : les motifs de rejet d'un amendement, les
libellés de l'outil ``horizon_distribution`` et le rapport de reformulation n'ont ni identifiant interne ni ``repr``
Python, et leurs nombres sont écrits à la française. Purs, sauf l'outil (numpy, puis données longues)."""

from __future__ import annotations

import json
import re
from datetime import date
from types import SimpleNamespace

import pytest

from alphaforge.finance.backtest.paths import long_data_available
from alphaforge.finance.contracts.decision import Explanation, Statement
from alphaforge.finance.debate.explain import rephrase, verify
from alphaforge.finance.debate.facts import FactBook
from alphaforge.finance.debate.merge import apply_amendments
from alphaforge.finance.debate.schemas import Amendment, LensReport

from .finance.strategy._helpers import make_comp

REPR = re.compile(r"\[.*\]|'[\w.\[\]]+'")  # liste Python ou chaîne entre apostrophes droites
KNOWN = {"r1.cvar_m"}


def _merge(*amendments: Amendment):
    report = LensReport(lens="risk", amendments=list(amendments))
    return apply_amendments(make_comp().policy, [report], {"risk": 1.0}, KNOWN)[1]


def _tighten(target="risk.cvar_m", value=0.05, evidence=("r1.cvar_m",)) -> Amendment:
    return Amendment(
        kind="tighten_limit", target=target, value=value, reason_fr="test", evidence_fact_ids=list(evidence)
    )


def test_unknown_evidence_is_rejected_without_its_identifier():
    log = _merge(_tighten(evidence=["risk.cdar_m"]))
    assert [x.status for x in log] == ["rejete"]
    why = log[0].why_fr
    assert why == "preuve inconnue : le fait cité est introuvable dans la décision"
    assert "risk.cdar_m" not in why and not REPR.search(why)
    assert log[0].amendment.evidence_fact_ids == ["risk.cdar_m"]  # l'identifiant reste, pour l'audit
    two = _merge(_tighten(evidence=["risk.cdar_m", "r9.absent"]))[0].why_fr
    assert two == "preuve inconnue : 2 faits cités sont introuvables dans la décision"


def test_other_rejections_name_no_rule_id_and_write_percentages():
    unknown = _merge(_tighten(target="risk.inexistante"))[0].why_fr
    assert unknown == "limite inconnue : la limite visée n'est pas dans le mandat"
    floor = _merge(_tighten(value=0.01))[0].why_fr  # plancher anti-cliquet : 0,6 × 6,2 %
    assert floor == "sous le plancher anti-cliquet (3,7 %) ou sous le minimum"
    for why in (unknown, floor):
        assert "risk." not in why and not REPR.search(why)


def _book() -> FactBook:
    book = FactBook("dec-test")
    with book.step("test"):
        book.add("f", "Part", 0.123, "%", dataset="test")
    return book


def test_verify_fr_reports_the_same_problems_as_sentences():
    from alphaforge.finance.debate.explain import verify_fr

    book = _book()
    st = Statement(text_fr="La part est de 12,3 %, soit 50 titres depuis 2018.", fact_ids=["f", "absent"])
    assert verify(book, st) == ["fact_id inconnu : absent", "nombres non sourcés : ['2018', '50']"]  # inchangé
    assert verify_fr(book, st) == ["fait cité introuvable dans la décision", "nombres non sourcés : 2018, 50"]
    one = Statement(text_fr="La part est de 12,3 % sur 12,5 ans.", fact_ids=["f"])
    assert verify_fr(book, one) == ["nombre non sourcé : 12,5"]
    ok = Statement(text_fr="La part est de 12,3 %.", fact_ids=["f"])
    assert verify(book, ok) == [] and verify_fr(book, ok) == []


def test_kept_template_line_has_no_index_nor_list():
    from alphaforge.finance.debate.explain import kept_template_fr

    line = kept_template_fr("why", 3, ["nombre non sourcé : 50"])
    assert line == (
        "4e énoncé de « Pourquoi ce choix ? » : reformulation écartée (nombre non sourcé : 50), gabarit conservé."
    )
    assert kept_template_fr("limits", 0, ["nombres non sourcés : 2018, 2026"]).startswith(
        "1er énoncé de « Quelles limites ? » : "
    )


class _Rephraser:
    """Modèle de reformulation factice : récrit le 1er énoncé de « Pourquoi ce choix ? » avec un nombre non sourcé."""

    def __init__(self, **_):
        pass

    def __call__(self, prompt, structured_output_model):
        data = json.loads(prompt)
        data["why"][0]["text_fr"] = "La part est de 12,3 %, soit 50 titres."
        return SimpleNamespace(structured_output=structured_output_model.model_validate(data))


def test_rephrase_report_is_a_french_sentence(monkeypatch):
    monkeypatch.setattr("strands.Agent", _Rephraser)
    book = _book()
    why = Statement(text_fr="La part est de 12,3 %.", fact_ids=["f"])
    expl = Explanation(data_used=[why], why=[why], limits=[], what_would_change=[])
    out, report = rephrase(book, expl, "debutant", model_factory=lambda *_: None)
    assert out.why[0].text_fr == "La part est de 12,3 %."  # le gabarit est gardé
    assert report == [
        "1er énoncé de « Pourquoi ce choix ? » : reformulation écartée (nombre non sourcé : 50), gabarit conservé."
    ]


def test_horizon_label_writes_years_in_french():
    pytest.importorskip("numpy")
    from alphaforge.finance.debate.tools import years_fr

    assert [years_fr(y) for y in (7.0, 1.0, 2.5, 10, 1.5)] == ["7 ans", "1 an", "2,5 ans", "10 ans", "1,5 an"]


@pytest.mark.skipif(not long_data_available(), reason="données longues du moteur absentes")
def test_horizon_distribution_tool_labels_its_facts_in_french():
    from alphaforge.finance.debate.tools import LensContext, strands_tools

    ctx = LensContext(None, None, {"SPY": 0.6, "AGG": 0.4}, date(2026, 9, 30), FactBook("dec-tool"), label="r1")
    tool = next(t for t in strands_tools("timeline", ctx) if t.tool_name == "horizon_distribution")
    tool(7.0)
    labels = {f.label_fr for f in ctx.book.facts.values()}
    assert {"Pire rendement sur 7 ans", "Part des fenêtres de 7 ans en perte"} <= labels
    assert not any(re.search(r"\d\.\d", label) for label in labels)
