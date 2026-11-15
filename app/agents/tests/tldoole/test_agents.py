"""A7 (lacunes) et A8 (scénario) : validation des sorties, modèle scripté."""

from __future__ import annotations

import copy

import pytest

from alphaforge.errors import AppError
from alphaforge.tldoole.concepts import load_catalog
from alphaforge.tldoole.detector import DetectionInput, GapReport, detect, rule_gaps
from alphaforge.tldoole.facts import FactBook
from alphaforge.tldoole.signals import Candidate, Evidence, InvestorMessage
from alphaforge.tldoole.storyboard import (
    StoryboardDraft,
    to_render_scene,
    write_storyboard,
)
from alphaforge.trace import Trace
from tests.conftest import ScriptedFactory


def detection_input() -> DetectionInput:
    catalog = load_catalog()
    messages = [InvestorMessage("m1", "Je ne comprends pas c'est quoi un FNB. Est-ce risqué ?", "a1:1", "t1", "fr")]
    candidates = {
        "volatilite": Candidate(
            "volatilite",
            0.65,
            "attitude_vs_reaction",
            [
                Evidence(
                    "answer",
                    "r_attitude_vs_reaction_1",
                    "base:q",
                    "t0",
                    field="risk_tolerance.risk_attitude",
                    value="large",
                )
            ],
        ),
        "fnb": Candidate(
            "fnb",
            0.85,
            "message_confusion",
            [Evidence("message", "m1", "a1:1", "t1", quote="Je ne comprends pas c'est quoi un FNB.")],
        ),
    }
    return DetectionInput(catalog, "fr", "beginner", messages, candidates)


def test_gap_report_checks_evidence():
    report = GapReport(detection_input())
    bad_quote = report.submit(
        [
            {
                "concept_id": "fnb",
                "confidence": 0.9,
                "reason": "r",
                "evidence": [{"ref": "m1", "quote": "un FNB c'est génial"}],
            }
        ]
    )
    assert bad_quote["status"] == "error" and "verbatim" in str(bad_quote)
    wrong_rule = report.submit(
        [{"concept_id": "fnb", "confidence": 0.9, "reason": "r", "evidence": [{"ref": "r_attitude_vs_reaction_1"}]}]
    )
    assert wrong_rule["status"] == "error"
    unknown = report.submit([{"concept_id": "nope", "confidence": 0.9, "reason": "r", "evidence": [{"ref": "m1"}]}])
    assert unknown["status"] == "error"
    ok = report.submit(
        [
            {
                "concept_id": "fnb",
                "confidence": 0.9,
                "reason": "Question directe.",
                "evidence": [{"ref": "m1", "quote": "c'est quoi un FNB"}],
            },
            {
                "concept_id": "volatilite",
                "confidence": 0.6,
                "reason": "Réponses contradictoires.",
                "evidence": [{"ref": "r_attitude_vs_reaction_1"}],
            },
        ]
    )
    assert ok == {"status": "ok", "gaps": 2}
    assert report.gaps[1].rule == "attitude_vs_reaction"


def test_a7_with_scripted_model_and_rule_fallback():
    data = detection_input()
    factory = ScriptedFactory(
        [
            [
                (
                    "tool",
                    "report_gaps",
                    {
                        "gaps": [
                            {
                                "concept_id": "fnb",
                                "confidence": 0.9,
                                "reason": "Question directe.",
                                "evidence": [{"ref": "m1", "quote": "c'est quoi un FNB"}],
                            }
                        ]
                    },
                )
            ]
        ]
    )
    gaps = detect(data, model_factory=factory, model_id="scripted", trace=Trace("fr"))
    assert [g.concept_id for g in gaps] == ["fnb"] and gaps[0].detector == "A7"
    assert factory.requests[0]["effort"] == "low"

    def broken(**_):
        raise AppError("model_error", "indisponible")

    fallback = detect(data, model_factory=broken, model_id="x", trace=Trace("fr"))
    assert [g.concept_id for g in fallback] == ["fnb", "volatilite"]
    assert all(g.detector == "rules" for g in fallback)
    covered = copy.copy(data)
    covered.covered = {"fnb": "ready"}
    assert [g.concept_id for g in rule_gaps(covered)] == ["volatilite"]


VALID_SCENES = [
    {
        "layout": "hook",
        "headline": "Un FNB, c'est quoi ?",
        "narration": "Vous vous demandez ce qu'est un FNB ? Voici l'essentiel en une minute, sans jargon.",
    },
    {
        "layout": "statement",
        "headline": "Un panier de placements",
        "body": "Une part = un morceau de tout le panier.",
        "narration": "Un FNB est un panier de placements. Une part vous donne un petit morceau de tout ce qu'il "
        "contient, en une seule transaction.",
    },
    {
        "layout": "compare",
        "headline": "Une action seule bouge plus",
        "fact": "f3",
        "narration": "Sur cinq ans, la volatilité annualisée de Shopify a été de 64,2 %, contre 13,1 % pour le "
        "FNB XIU. Le passé ne garantit pas l'avenir.",
    },
    {
        "layout": "outro",
        "headline": "À retenir",
        "items": ["Un FNB = un panier", "Moins agité qu'une action seule"],
        "narration": "À retenir : un FNB est un panier de placements, en général moins agité qu'une action seule.",
    },
]
QUIZ = {
    "question": "Que contient une part de FNB ?",
    "options": ["Une seule action", "Un morceau du panier"],
    "answer": 1,
    "explanation": "Une part donne un petit morceau de tout le panier.",
}


def facts_with_compare() -> FactBook:
    facts = FactBook("fr")
    facts.compare_assets(["SHOP.TO", "XIU.TO"], "annualized_volatility")
    return facts


def test_storyboard_accepts_cited_numbers_and_adds_disclaimer():
    concept = load_catalog().get("fnb")
    facts = facts_with_compare()
    draft = StoryboardDraft(concept, facts, locale="fr", level="beginner")
    outcome = draft.submit("Un FNB, c'est quoi ?", copy.deepcopy(VALID_SCENES), QUIZ)
    assert outcome["status"] == "ok", outcome
    board = draft.result
    assert board["facts_used"] == ["f3"]
    assert board["scenes"][-1]["narration"].endswith("pas un conseil financier.")
    scenes = draft.render_scenes()
    assert scenes[2].bars[0]["label"] == "Shopify (SHOP.TO)" and scenes[2].source.startswith("Source : ")


@pytest.mark.parametrize(
    "change, message",
    [
        (
            lambda s: s[2].update(narration="Shopify a fait 42 % de volatilité, un chiffre inventé pour le test."),
            "do not come from the facts",
        ),
        (lambda s: s[1].update(body="Je vous recommande d'acheter ce FNB dès aujourd'hui."), "do not advise"),
        (lambda s: s.reverse(), "first scene must use the hook"),
        (lambda s: s[2].update(fact="f9"), "unknown fact"),
        (lambda s: s.pop(2), "scenes must be a list"),
    ],
)
def test_storyboard_rejects_bad_scripts(change, message):
    concept = load_catalog().get("fnb")
    draft = StoryboardDraft(concept, facts_with_compare(), locale="fr", level="beginner")
    scenes = copy.deepcopy(VALID_SCENES)
    change(scenes)
    outcome = draft.submit("Titre", scenes, QUIZ)
    assert outcome["status"] == "error" and message in str(outcome), outcome


def test_number_scene_shows_the_fact_value():
    facts = FactBook("fr")
    facts.asset_stats("XIU.TO")
    scene = {
        "layout": "number",
        "headline": "La pire baisse",
        "fact": "f1.max_drawdown",
        "facts": ["f1"],
        "label": None,
        "items": [],
        "body": None,
        "narration": "x",
    }
    rendered = to_render_scene(scene, facts, "fr")
    assert rendered.number["text"] == facts.facts["f1"]["metrics"]["max_drawdown"]["text"]
    assert "–" in rendered.number["sublabel"]


def test_a8_with_scripted_model():
    concept = load_catalog().get("fnb")
    facts = FactBook("fr")
    script = [
        [("tool", "compare_assets", {"tickers": ["XIU.TO", "SHOP.TO"], "metric": "annualized_volatility"})],
        [
            (
                "tool",
                "submit_storyboard",
                {
                    "title": "Un FNB, c'est quoi ?",
                    "scenes": [{**s, "fact": "f3"} if s["layout"] == "compare" else s for s in VALID_SCENES],
                    "quiz": QUIZ,
                },
            )
        ],
    ]
    factory = ScriptedFactory(script)
    result = write_storyboard(
        concept,
        locale="fr",
        level="beginner",
        evidence=[],
        facts=facts,
        has_portfolio=False,
        simpler=False,
        previous_headlines=[],
        model_factory=factory,
        model_id="scripted",
        trace=Trace("fr"),
    )
    assert result.storyboard["title"] == "Un FNB, c'est quoi ?"
    assert result.storyboard["sources"][0]["resource"] == "starter:prices_daily.csv"
    assert factory.requests[0]["effort"] == "medium"
    tools = factory.models[0].calls[0]["tools"]
    assert "client_portfolio" not in tools and "submit_storyboard" in tools
