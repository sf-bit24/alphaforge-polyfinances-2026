"""Ancrage Bedrock Guardrails énoncé par énoncé (explain.grounding_check) : sans AWS, avec un client factice."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from alphaforge.finance.contracts.decision import ConstraintCheck, Explanation, Statement
from alphaforge.finance.debate.explain import (
    GROUNDING_SOURCE_MAX,
    grounding_check,
    grounding_context,
    grounding_source,
    keep_grounded,
    merge_grounding,
)
from alphaforge.finance.debate.facts import FactBook
from alphaforge.finance.debate.okf_bridge import OkfMarketStore
from alphaforge.store.local import LocalStore


def _book() -> FactBook:
    book = FactBook("dec-test")
    with book.step("s0.policy_compiler", tool="compile_profile") as ev:
        book.add("level", "Niveau de risque effectif", "N0", "niveau", dataset="risk_levels.yaml")
        book.add("r1.cvar_m", "CVaR 95 % mensuelle (historique)", 0.005, "%", dataset="starter")
        ev.output_summary = "niveau N0 : la plus prudente de la tolérance et de la capacité"
    return book


def _expl(why: str = "CVaR mensuelle 0,5 %.") -> Explanation:
    return Explanation(
        data_used=[Statement(text_fr="Profil de risque effectif : niveau N0.", fact_ids=["level"])],
        why=[Statement(text_fr=why, fact_ids=["r1.cvar_m"])],
        limits=[Statement(text_fr="Objection maintenue par la lentille « diversity » au second tour.")],
        what_would_change=[],
    )


class FakeGuardrail:
    """Client bedrock-runtime factice : score fixé par texte vérifié, seuil 0,75 comme le guardrail cadre."""

    def __init__(self, scores: dict[str, float], fail: frozenset[str] | set[str] = frozenset()):
        self.scores, self.fail, self.calls = scores, fail, []

    def apply_guardrail(self, **kw):
        content = {q: c["text"]["text"] for c in kw["content"] for q in c["text"]["qualifiers"]}
        self.calls.append(content)
        lines = content["guard_content"].split("\n")  # une section : un énoncé par ligne
        if any(line in self.fail for line in lines):
            raise RuntimeError("throttled")
        score = min(self.scores.get(line, 0.99) for line in lines)  # un énoncé non ancré fait baisser la section
        blocked = score < 0.75
        return {
            "action": "GUARDRAIL_INTERVENED" if blocked else "NONE",
            "assessments": [
                {
                    "contextualGroundingPolicy": {
                        "filters": [
                            {
                                "type": "GROUNDING",
                                "threshold": 0.75,
                                "score": score,
                                "action": "BLOCKED" if blocked else "NONE",
                            },
                            {"type": "RELEVANCE", "threshold": 0.1, "score": 0.97, "action": "NONE"},
                        ]
                    }
                }
            ],
        }


def test_each_statement_is_checked_against_its_own_cited_facts_first():
    book = _book()
    st = _expl().why[0]
    src = grounding_source(book, st, "Limite risk.cvar_m : …", [("general/methodologie/m.md", "La méthode.")])
    assert (
        src.index("CVaR 95 % mensuelle (historique) : 0,5 % (FAIT)") < src.index("Décision :") < src.index("# general/")
    )
    assert "Niveau de risque effectif" not in src  # un fait non cité n'est pas une source de cet énoncé
    long_doc = [("general/methodologie/long.md", "x" * (GROUNDING_SOURCE_MAX * 2))]
    assert (
        len(grounding_source(book, st, "", long_doc)) == GROUNDING_SOURCE_MAX
    )  # la méthodologie est coupée en dernier


def test_context_is_what_the_decision_records():
    book = _book()
    checks = [
        ConstraintCheck(
            rule_id="alloc.crypto:max", description_fr="alloc.crypto niveau N0", derived_from="risk_levels.yaml"
        )
    ]
    ctx = grounding_context(book, checks, {"risk": "soutien", "diversity": "objection_maintenue"})
    assert "Limite alloc.crypto:max : alloc.crypto niveau N0 ; dérivée de : risk_levels.yaml" in ctx
    assert "Étape compile_profile : niveau N0 : la plus prudente de la tolérance et de la capacité" in ctx
    assert "Verdict de la lentille « diversity » au second tour : objection_maintenue" in ctx


def test_per_statement_actions_and_summary():
    book, expl = _book(), _expl()
    fake = FakeGuardrail({expl.limits[0].text_fr: 0.43})
    g = grounding_check(book, expl, "gr1", "3", client=fake, docs=[("general/methodologie/m.md", "La méthode.")])
    assert len(fake.calls) == 3 and all(c["query"] == "Expliquer la proposition de portefeuille" for c in fake.calls)
    assert {c["guard_content"] for c in fake.calls} == {
        s.text_fr for sec in ("data_used", "why", "limits") for s in getattr(expl, sec)
    }
    assert g["action"] == "GUARDRAIL_INTERVENED" and g["method"] == "per_statement"
    assert (g["checked"], g["below"], g["errors"], g["min_score"], g["threshold"]) == (3, 1, 0, 0.43, 0.75)
    assert g["sources"] == ["general/methodologie/m.md"]
    [low] = [r for r in g["statements"] if r["action"] == "GUARDRAIL_INTERVENED"]
    assert (low["section"], low["index"], low["score"]) == ("limits", 0, 0.43)


def test_call_errors_are_reported_without_failing_the_decision():
    book, expl = _book(), _expl()
    g = grounding_check(book, expl, "gr1", "3", client=FakeGuardrail({}, fail={expl.why[0].text_fr}))
    assert (g["action"], g["checked"], g["errors"]) == ("NONE", 2, 1)
    every = {s.text_fr for sec in ("data_used", "why", "limits") for s in getattr(expl, sec)}
    assert grounding_check(book, expl, "gr1", "3", client=FakeGuardrail({}, fail=every))["action"] == "ERROR"


def test_no_guardrail_no_check_and_draft_is_refused():
    assert grounding_check(_book(), _expl(), None, None) is None
    with pytest.raises(ValueError, match="DRAFT"):
        grounding_check(_book(), _expl(), "gr1", "DRAFT", client=FakeGuardrail({}))


def test_an_ungrounded_rephrasing_goes_back_to_its_template_and_is_rechecked():
    book, template = _book(), _expl()
    rephrased = _expl(why="La CVaR mensuelle, 0,5 %, montre un portefeuille sûr.")  # « sûr » : affirmation non sourcée
    fake = FakeGuardrail({rephrased.why[0].text_fr: 0.2, template.limits[0].text_fr: 0.5})
    first = grounding_check(book, rephrased, "gr1", "3", client=fake)
    kept, reverted = keep_grounded(rephrased, template, first)
    assert reverted == [("why", 0)]  # la limite non ancrée est déjà un gabarit : elle reste, signalée
    assert kept.why[0] == template.why[0] and kept.limits[0] == template.limits[0]
    again = grounding_check(book, kept, "gr1", "3", client=fake, only=set(reverted))
    assert len(fake.calls) == 4  # seul le gabarit remis est revérifié
    merged = merge_grounding(first, again)
    assert (merged["below"], merged["checked"]) == (1, 3)
    assert {(r["section"], r["action"]) for r in merged["statements"]} >= {
        ("why", "NONE"),
        ("limits", "GUARDRAIL_INTERVENED"),
    }


def test_keep_grounded_without_result_changes_nothing():
    expl = _expl()
    assert keep_grounded(expl, expl, None) == (expl, [])


def test_methodology_is_read_once_and_stays_out_of_the_data_version(tmp_path):
    store = LocalStore(tmp_path)
    store.put_text(
        "general/methodologie/b.md",
        "---\ntype: Methodology\ntitle: B\n---\n\nLa tolérance place, la capacité plafonne.\n",
    )
    store.put_text("general/methodologie/a.md", "Sans frontmatter.\n")
    store.put_text("general/methodologie/notes.txt", "ignoré")
    market = OkfMarketStore(store)
    docs = market.methodology()
    assert docs == [
        ("general/methodologie/a.md", "Sans frontmatter."),
        ("general/methodologie/b.md", "La tolérance place, la capacité plafonne."),
    ]
    assert market.inputs == {} and set(market.grounding_inputs) == {k for k, _ in docs}
    store.put_text("general/methodologie/c.md", "Ajouté après.")
    assert market.methodology() == docs  # lu une fois par décision (reset() pour relire)


def test_unreadable_methodology_gives_no_source_and_no_failure():
    class Broken(SimpleNamespace):
        def list(self, prefix, limit=None):
            raise PermissionError("AccessDenied")

    market = OkfMarketStore(Broken(bucket=None))
    assert market.methodology() == []
    assert market.grounding_inputs["general/methodologie/"].startswith("erreur:")


def test_calls_are_paced_under_the_text_unit_quota():
    """Le quota d'ancrage se compte en unités de texte par seconde : chaque appel réserve un créneau à sa taille."""
    import time

    from alphaforge.finance.debate.explain import _TextUnitPacer

    pacer = _TextUnitPacer(1000.0)
    t0 = time.monotonic()
    pacer.wait(50_000)  # 50 unités : passe tout de suite
    first = time.monotonic() - t0
    pacer.wait(1)  # attend la fin du créneau du premier appel
    assert first < 0.03 and time.monotonic() - t0 >= 0.045


def _two_why(second: str = "Plafond d'exposition tech (look-through) : 4,8 %.") -> Explanation:
    expl = _expl()
    return expl.model_copy(update={"why": [*expl.why, Statement(text_fr=second, fact_ids=["level"])]})


def test_a_grounded_section_is_checked_in_one_call():
    book, expl = _book(), _two_why()
    fake = FakeGuardrail({})
    g = grounding_check(book, expl, "gr1", "3", client=fake)
    assert len(fake.calls) == 3  # trois sections, la section « why » de deux énoncés en un seul appel
    why_call = next(c for c in fake.calls if "\n" in c["guard_content"])
    assert why_call["guard_content"] == "\n".join(x.text_fr for x in expl.why)
    assert why_call["grounding_source"].count("(FAIT)") == 2  # les faits cités par les deux énoncés
    assert [(r["section"], r["index"], r["scope"]) for r in g["statements"]] == [
        ("data_used", 0, "statement"),
        ("why", 0, "section"),
        ("why", 1, "section"),
        ("limits", 0, "statement"),
    ]


def test_a_section_the_guardrail_blocks_is_rechecked_statement_by_statement():
    bad = "La CVaR prouve que le portefeuille est sûr."
    book, expl = _book(), _two_why(bad)
    fake = FakeGuardrail({bad: 0.3})
    g = grounding_check(book, expl, "gr1", "3", client=fake)
    assert len(fake.calls) == 5  # trois sections, puis les deux énoncés de « why » un par un
    rows = {(r["section"], r["index"]): r for r in g["statements"]}
    assert rows[("why", 0)]["action"] == "NONE" and rows[("why", 1)]["action"] == "GUARDRAIL_INTERVENED"
    assert rows[("why", 1)]["scope"] == "statement" and (g["below"], g["checked"]) == (1, 4)
