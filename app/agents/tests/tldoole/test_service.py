"""Runtime tldoole de bout en bout sur un magasin local : detect, produce, finalize, feed, feedback, request."""

from __future__ import annotations

import copy

import pytest

from alphaforge import okf
from alphaforge.errors import AppError
from alphaforge.tldoole import feed
from alphaforge.tldoole import service as service_module
from alphaforge.tldoole.service import TldooleService, TldooleSettings
from alphaforge.tldoole.storyboard import StoryboardDraft, StoryboardResult

from .conftest import FakeSfn, FakeVoice, make_client
from .test_agents import QUIZ, VALID_SCENES


def broken_model(**_):
    raise AppError("model_error", "pas de modèle dans les tests")


def scripted_storyboard(concept, *, locale, level, facts, **_):
    facts.compare_assets(["SHOP.TO", "XIU.TO"], "annualized_volatility")
    draft = StoryboardDraft(concept, facts, locale=locale, level=level)
    assert draft.submit("Un FNB, c'est quoi ?", copy.deepcopy(VALID_SCENES), QUIZ)["status"] == "ok"
    board = dict(draft.result)
    board["sources"] = [facts.facts["f3"]["source"]]
    board["render"] = draft.render_scenes()
    return StoryboardResult(board, facts)


@pytest.fixture
def svc(tldoole_settings, kb, monkeypatch):
    monkeypatch.setattr(service_module, "write_storyboard", scripted_storyboard)
    sfn = FakeSfn()
    service = TldooleService(
        tldoole_settings,
        kb,
        model_factory=broken_model,
        voice=FakeVoice(),
        sfn=sfn,
        options=TldooleSettings("arn:aws:states:us-east-1:111122223333:stateMachine:t", 2, 6, False),
    )
    service.fake_sfn = sfn
    return service


FACTS = {"risk_tolerance.risk_attitude": "large", "risk_tolerance.drop_reaction": "sell_all"}
MESSAGE = "Je ne comprends pas trop c'est quoi un FNB, mon beau-frère m'en parle tout le temps."


def test_health_and_errors(svc):
    assert svc.handle({"action": "health"})["role"] == "tldoole"
    assert svc.handle({"action": "nope"})["error"]["code"] == "unknown_action"
    assert svc.handle({"action": "feed", "client_id": "x"})["error"]["code"] == "bad_request"
    missing = svc.handle({"action": "feed", "client_id": "8f0c3a8e-5d7b-4e2a-9f51-2c6d3b1a7e90"})
    assert missing["error"]["code"] == "not_found"


def test_detect_produce_finalize_and_feed(svc, kb):
    client_id = make_client(kb, facts=FACTS, messages=[MESSAGE])
    detected = svc.handle({"action": "detect", "client_id": client_id, "run_id": "run-1", "wait": True})
    assert detected["ok"] and detected["marker"] == f"clients/{client_id}/tldoole/runs/run-1/detect.json"
    result = detected["result"]
    assert result["status"] == "ok"
    concepts = [vid.split("-")[1] for vid in result["video_ids"]]
    assert concepts == ["fnb", "volatilite"]
    gaps_doc = okf.parse(kb.get(feed.gaps_key(client_id)).text)
    assert gaps_doc.type == "Concept Gaps" and not okf.validate(gaps_doc)

    again = svc.handle({"action": "detect", "client_id": client_id, "run_id": "run-2", "wait": True})
    assert again["result"]["skipped"] == "no_new_signal"

    video_id = result["video_ids"][0]
    produced = svc.handle({"action": "produce", "client_id": client_id, "video_id": video_id, "wait": True})
    marker = produced["result"]
    assert marker["status"] == "ok", marker
    assert marker["settings"] is None  # magasin local : pas de MediaConvert
    prefix = feed.video_prefix(client_id, video_id)
    for name in (
        "scene-01.png",
        "scene-04.png",
        "background.png",
        "narration.mp3",
        "captions.srt",
        "captions.vtt",
        "caption-font.ttf",
        "storyboard.json",
        "fiche.md",
    ):
        assert kb.get(prefix + name) is not None, name

    finalized = svc.handle(
        {
            "action": "finalize",
            "client_id": client_id,
            "video_id": video_id,
            "job": {"status": "COMPLETE", "id": "job-1", "duration_ms": 12345},
        }
    )
    assert finalized["video"]["status"] == "ready" and finalized["video"]["duration_ms"] == 12345
    doc = okf.parse(kb.get(feed.video_doc_key(client_id, video_id)).text)
    assert doc.type == "Learning Video" and doc.frontmatter["status"] == "stable" and not okf.validate(doc)

    listing = svc.handle({"action": "feed", "client_id": client_id})
    assert listing["ok"] and listing["pending"] == 1
    card = next(v for v in listing["videos"] if v["video_id"] == video_id)
    assert card["quiz"] == {"question": QUIZ["question"], "options": QUIZ["options"]}  # sans la réponse
    assert card["why"][0]["quote"].startswith("Je ne comprends pas")
    assert {g["concept_id"] for g in listing["gaps"]} >= {"fnb", "volatilite"}


def test_feedback_unclear_starts_a_simpler_version(svc, kb):
    client_id = make_client(kb, facts=FACTS, messages=[MESSAGE])
    video_id = svc.handle({"action": "detect", "client_id": client_id, "run_id": "r", "wait": True})["result"][
        "video_ids"
    ][0]
    svc.handle({"action": "produce", "client_id": client_id, "video_id": video_id, "wait": True})
    svc.handle({"action": "finalize", "client_id": client_id, "video_id": video_id, "job": {"status": "COMPLETE"}})

    wrong = svc.handle({"action": "feedback", "client_id": client_id, "video_id": video_id, "quiz_answer": 0})
    assert wrong["quiz"] == {"correct": False, "answer": 1, "explanation": QUIZ["explanation"]}
    follow = wrong["follow_up"]
    assert follow["status"] == "queued" and follow["reason"] == "feedback" and follow["version"] == 2
    assert svc.fake_sfn.started[-1]["name"].startswith("feedback-")
    index = feed.load_index(kb, client_id)
    assert feed.find_video(index, follow["video_id"])["simpler"] is True
    assert index["gaps"]["fnb"]["status"] == "unclear"

    right = svc.handle({"action": "feedback", "client_id": client_id, "video_id": video_id, "quiz_answer": 1})
    assert right["quiz"]["correct"] is True and right["follow_up"] is None
    assert feed.load_index(kb, client_id)["gaps"]["fnb"]["status"] == "resolved"


def test_request_and_failures(svc, kb):
    client_id = make_client(kb, facts={"constraints.account_types": ["unknown"]})
    first = svc.handle({"action": "request", "client_id": client_id, "concept_id": "celi_reer"})
    assert first["created"] is True and first["video"]["status"] == "queued"
    assert svc.fake_sfn.started[-1]["input"].count("celi_reer") == 1
    second = svc.handle({"action": "request", "client_id": client_id, "concept_id": "celi_reer"})
    assert second["created"] is False and second["video"]["video_id"] == first["video"]["video_id"]
    assert (
        svc.handle({"action": "request", "client_id": client_id, "concept_id": "x"})["error"]["code"] == "bad_request"
    )

    video_id = first["video"]["video_id"]
    failed = svc.handle(
        {
            "action": "finalize",
            "client_id": client_id,
            "video_id": video_id,
            "job": {"status": "ERROR", "error": "boom"},
        }
    )
    assert failed["video"]["status"] == "failed" and failed["video"]["error"]["message"] == "boom"


def test_daily_limit(svc, kb):
    svc.options = TldooleSettings(svc.options.state_machine_arn, 2, 1, False)
    client_id = make_client(kb)
    assert svc.handle({"action": "request", "client_id": client_id, "concept_id": "fnb"})["ok"]
    limited = svc.handle({"action": "request", "client_id": client_id, "concept_id": "frais"})
    assert limited["error"]["code"] == "conflict"
