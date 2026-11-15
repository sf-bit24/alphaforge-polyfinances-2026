"""Expert → chercheurs → A6, routage et synthèse d'A0, et contrat des runtimes de recherche."""

import hashlib
import json
import time

import pytest

from alphaforge.collect import supervisor
from alphaforge.config import Settings
from alphaforge.research import expert as expert_mod
from alphaforge.research import items as items_mod
from alphaforge.research import researcher as researcher_mod
from alphaforge.research import router as router_mod
from alphaforge.research.launcher import Launcher, session_id
from alphaforge.research.packs import SUBJECTS, pack_hosts
from alphaforge.research.service import ResearchService
from alphaforge.research.web import ResearchWeb
from alphaforge.trace import Trace

from ..conftest import ScriptedFactory
from .conftest import KALSHI_MARKET, VALET_FX

VALET_URL = "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?recent=3"


def rid(url, body):
    return hashlib.sha256(url.encode() + b"\n\n" + json.dumps(body).encode()).hexdigest()[:16]


def settings_for(role, tmp_path, **extra):
    return Settings.from_env(
        {
            "AGENT_ROLE": role,
            "ALPHAFORGE_STORE": "local",
            "ALPHAFORGE_LOCAL_DIR": str(tmp_path / "kb"),
            "ALPHAFORGE_RELEASE": "r1",
            **extra,
        }
    )


class FakeApp:
    def __init__(self):
        self.started, self.completed = [], []

    def add_async_task(self, name, metadata=None):
        self.started.append(name)
        return len(self.started)

    def complete_async_task(self, task_id):
        self.completed.append(task_id)


def fx_finding(store, *, researcher="r1", run_id="run1"):
    """Un vrai constat de série, consigné par un chercheur sur une réponse archivée."""
    web = ResearchWeb(store=store, allowed_hosts=pack_hosts(["rates-fx-commodities"]))
    brief = researcher_mod.parse_brief(
        {
            "run_id": run_id,
            "subject": "E2",
            "researcher": researcher,
            "objective": "FX",
            "packs": ["rates-fx-commodities"],
        }
    )
    run = researcher_mod.ResearcherRun(brief=brief, store=store, web=web, deadline=time.monotonic() + 30)
    archived = web.fetch(VALET_URL)
    run.record_series(
        {
            "label": "USD/CAD",
            "claim": "Le dollar américain vaut 1,4257 $ CA au 13 novembre 2026.",
            "response_id": archived.response_id,
            "rows": "observations",
            "date_field": "d",
            "value_field": "FXUSDCAD.v",
            "series_id": "FXUSDCAD",
        }
    )
    return run.findings[0]


class FakeLauncher(Launcher):
    def __init__(self, store, findings_by_mission):
        super().__init__(store, poll_seconds=0.01)
        self.findings_by_mission = findings_by_mission
        self.started = []

    def start(self, brief):
        self.started.append(brief)

    def run(self, briefs, timeout):
        for brief in briefs:
            self.start(brief)
        out = []
        for brief in briefs:
            findings = self.findings_by_mission(brief)
            out.append(
                {
                    "brief": brief,
                    "launched": True,
                    "marker": {"status": "ok", "summary": "ok", "gaps": [], "findings_key": None},
                    "findings": findings,
                }
            )
        return out


def expert_job(code="E2", mode="sweep", depth="quick", **kw):
    return expert_mod.ExpertJob(
        run_id="run1",
        subject=SUBJECTS[code],
        mode=mode,
        question=kw.get("question"),
        sub_question=None,
        issuers=kw.get("issuers", []),
        themes=[],
        since="2026-11-01",
        as_of=kw.get("as_of"),
        depth=depth,
        max_researchers=kw.get("max_researchers", 3),
    )


# ----------------------------------------------------------------------------- expert
def test_expert_spawn_caps_rounds_and_packs(store, fake_http):
    fake_http.add("https://www.bankofcanada.ca/valet/observations/", VALET_FX)
    finding = fx_finding(store)
    launcher = FakeLauncher(store, lambda brief: [finding] if brief["researcher"] == "r1" else [])
    run = expert_mod.ExpertRun(
        job=expert_job(max_researchers=4),
        store=store,
        launcher=launcher,
        knowledge=None,
        deadline=time.monotonic() + 60,
    )
    first = run.spawn(
        [
            {"objective": "Courbe canadienne", "packs": ["rates-fx-commodities"]},
            {"objective": "Hors sujet", "packs": ["attention"]},
            {"objective": "Change", "packs": ["rates-fx-commodities"]},
            {"objective": "Or", "packs": ["rates-fx-commodities"]},
            {"objective": "Pétrole", "packs": ["rates-fx-commodities"]},
        ]
    )
    assert first["status"] == "ok" and first["round"] == 1
    assert [b["researcher"] for b in launcher.started] == ["r1", "r2"]
    assert all(b["packs"] == ["rates-fx-commodities"] for b in launcher.started)
    assert any(r["reason"] == "au-delà du plafond" for r in first["refused"])
    assert any("paquets" in r["reason"] for r in first["refused"])
    assert first["findings"][0]["finding_id"] == "E2-r1-f01" and first["researchers_left"] == 2
    second = run.spawn([{"objective": "Lacune", "packs": ["rates-fx-commodities"]}])
    assert second["round"] == 2 and launcher.started[-1]["researcher"] == "r3"
    third = run.spawn([{"objective": "Encore", "packs": ["rates-fx-commodities"]}])
    assert third["status"] == "error" and "tours" in third["reason"]
    staged = run.stage([{"finding_id": "E2-r1-f01", "summary": "Le dollar américain vaut 1,4257 $ CA."}])
    assert staged["staged"][0]["item_id"].startswith("series-")
    refused = run.stage([{"finding_id": "E2-r1-f01", "summary": "Le dollar a bondi de 12 %."}])
    assert refused["staged"] == [] and "non fondés" in refused["refused"][0]
    item = store.get_json(run.staged["E2-r1-f01"])
    assert item["kind"] == "series" and item["data"]["provenance"]["archive_key"].startswith("archive/")
    assert item["data"]["provenance"]["attribution_text"] == "Source : Banque du Canada"


def test_session_ids_are_long_enough_and_distinct():
    a, b = session_id("run1", "E2", "r1"), session_id("run1", "E2", "r2")
    assert len(a) >= 33 and a != b and a.startswith("run1-E2-r1")


# ----------------------------------------------------------------------------- chaîne locale
def test_local_chain_expert_spawns_a_researcher_session_and_a6_writes(store, fake_http, tmp_path):
    fake_http.add("https://www.bankofcanada.ca/valet/observations/", VALET_FX)
    factory = ScriptedFactory(
        # expert E2
        [
            [
                (
                    "tool",
                    "spawn_researchers",
                    {"missions": [{"objective": "USD/CAD quotidien", "packs": ["rates-fx-commodities"]}]},
                )
            ],
            [
                (
                    "tool",
                    "stage_items",
                    {"selections": [{"finding_id": "E2-r1-f01", "summary": "USD/CAD à 1,4257 le 13 novembre."}]},
                )
            ],
            [("tool", "finish", {"note": "ok"})],
        ],
        # chercheur r1
        [
            [("tool", "fetch", {"url": VALET_URL})],
            [
                (
                    "tool",
                    "record_series",
                    {
                        "label": "USD/CAD",
                        "claim": "Le dollar américain vaut 1,4257 $ CA au 13 novembre 2026.",
                        "response_id": rid(VALET_URL, VALET_FX),
                        "rows": "observations",
                        "date_field": "d",
                        "value_field": "FXUSDCAD.v",
                        "series_id": "FXUSDCAD",
                    },
                )
            ],
            [("tool", "finish", {"summary": "lu"})],
        ],
    )
    app = FakeApp()
    service = ResearchService(settings_for("expert", tmp_path), store, app, model_factory=factory)
    service.launcher().poll_seconds = 0.05
    response = service.handle({"action": "research", "run_id": "run1", "subject": "E2", "mode": "sweep"})
    assert response["ok"] and response["marker"] == "staging/run1/experts/E2/_done.json"
    service.wait(response["marker"], timeout=60)
    marker = store.get_json(response["marker"])
    assert marker["status"] == "ok", marker
    assert marker["spawned"] == 1 and marker["items"] == 1 and marker["rounds"] == 1
    researcher_marker = store.get_json("staging/run1/researchers/E2-r1/_done.json")
    assert researcher_marker["status"] == "ok" and researcher_marker["findings"] == 1
    assert researcher_marker["role"] == "researcher"
    result = supervisor.curate(
        run_id="run1", store=store, trace=Trace("fr"), model_factory=ScriptedFactory(), model_id="scripted"
    )
    assert result["written"] == ["general/donnees/fxusdcad/2026-11-13.md"], result
    document = store.get_text(result["written"][0]).text
    assert "Source : Banque du Canada" in document and "1.4257" in document


# ----------------------------------------------------------------------------- A6
def stage(store, item, subject="E2"):
    key = f"staging/run1/experts/{subject}/{item['id']}.json"
    store.put_json(key, item)
    return key


def test_a6_rejects_tampered_values_quarantine_and_robots(store, fake_http):
    fake_http.add("https://www.bankofcanada.ca/valet/observations/", VALET_FX)
    finding = fx_finding(store)
    good = items_mod.build_item(
        {
            **finding,
            "kind": "fact",
            "values": {"value": "1.4257"},
            "locators": {"value": "observations[2].FXUSDCAD.v"},
            "series_spec": None,
        },
        summary="USD/CAD à 1,4257.",
    )
    stage(store, good)
    tampered = json.loads(json.dumps(good))
    tampered["id"] = "fact-tampered"
    tampered["data"]["values"]["value"] = "1.5000"
    tampered["summary"] = "USD/CAD à 1,5."
    stage(store, tampered)
    quarantined = json.loads(json.dumps(good))
    quarantined["id"] = "fact-quarantined"
    quarantined["data"]["provenance"]["host_status"] = "quarantined"
    stage(store, quarantined)
    no_robots = json.loads(json.dumps(good))
    no_robots["id"] = "fact-norobots"
    no_robots["data"]["provenance"]["robots_ok_at_fetch"] = False
    stage(store, no_robots)
    result = supervisor.curate(
        run_id="run1", store=store, trace=Trace("fr"), model_factory=ScriptedFactory(), model_id="scripted"
    )
    reasons = {r["key"].rsplit("/", 1)[-1]: r["reason"] for r in result["rejected"]}
    assert len(result["written"]) == 1 and result["written"][0].startswith("general/faits/usd-cad/2026-11-13-")
    assert "différente de l'archive" in reasons["fact-tampered.json"]
    assert "quarantaine" in reasons["fact-quarantined.json"]
    assert "robots" in reasons["fact-norobots.json"]
    assert result["quarantined"] == 1
    assert store.get_json("staging/run1/supervisor/quarantine.json")["items"][0]["id"] == "fact-quarantined"
    document = store.get_text(result["written"][0]).text
    assert "type: Fact" in document and "Licence : Conditions de la Banque du Canada" in document


def test_a6_market_signal_keeps_rules_and_quality_tier(store, fake_http):
    fake_http.add("https://external-api.kalshi.com/trade-api/v2/markets/", KALSHI_MARKET)
    web = ResearchWeb(store=store, allowed_hosts=pack_hosts(["market-implied"]))
    brief = researcher_mod.parse_brief(
        {"run_id": "run1", "subject": "E6", "researcher": "r1", "objective": "BdC", "packs": ["market-implied"]}
    )
    run = researcher_mod.ResearcherRun(brief=brief, store=store, web=web, deadline=time.monotonic() + 30)
    archived = web.fetch("https://external-api.kalshi.com/trade-api/v2/markets/KXCBDECISIONCANADA-26DEC-H25")
    run.record_finding(
        {
            "kind": "signal",
            "label": "Hausse de 25 pb de la BdC le 9 décembre",
            "claim": "Les acheteurs offrent 51 cents et les vendeurs 52 cents pour une hausse de 25 pb.",
            "response_id": archived.response_id,
            "fields": {
                "value": "market.yes_bid",
                "bid": "market.yes_bid",
                "ask": "market.yes_ask",
                "volume": "market.volume",
                "resolution_rules": "market.rules_primary",
            },
            "observation_date": "2026-11-14",
        }
    )
    item = items_mod.build_item(run.findings[0])
    assert item["data"]["market"]["quality_tier"] == "high" and "25 bps" in item["data"]["market"]["resolution_rules"]
    stage(store, item, "E6")
    result = supervisor.curate(
        run_id="run1", store=store, trace=Trace("fr"), model_factory=ScriptedFactory(), model_id="scripted"
    )
    assert len(result["written"]) == 1 and result["written"][0].startswith("general/signaux/")
    text = store.get_text(result["written"][0]).text
    assert "Règles de résolution, telles quelles" in text and "type: Market Signal" in text
    assert "pas un signal d'achat" in text
    # Compagnon de la Knowledge Base écrit avec le document (CONTRACTS.md 5.1).
    meta = store.get_json(result["written"][0] + ".metadata.json")
    assert meta["metadataAttributes"]["type"]["value"] == {"type": "STRING", "stringValue": "Market Signal"}


# ----------------------------------------------------------------------------- A0
def test_keyword_routing_and_cap_sharing():
    picked = router_mod.keyword_route("Contexte ESG sur les émissions d'Enbridge", ["ENB.TO"], [])
    assert [p["subject"] for p in picked][:2] == ["E3", "E4"]
    shared = router_mod.share_caps(picked, "deep")
    assert all(s["max_researchers"] == min(10, 24 // len(picked)) for s in shared)
    assert router_mod.keyword_route("rien de précis", [], [])[0]["subject"] == "E1"


def test_route_falls_back_to_keywords_and_compose_writes_a_grounded_brief(store, fake_http, tmp_path):
    fake_http.add("https://www.bankofcanada.ca/valet/observations/", VALET_FX)
    job = {
        "run_id": "run1",
        "question": "Où en est le taux de change USD/CAD?",
        "issuers": [],
        "themes": ["change"],
        "as_of": None,
        "depth": "quick",
        "since": "2026-11-01",
    }
    routed = router_mod.route(job=job, store=store, trace=Trace("fr"), model_factory=ScriptedFactory(), model_id="s")
    assert routed["plan"]["subjects"][0]["subject"] == "E2" and routed["warnings"]
    finding = fx_finding(store)
    item = items_mod.build_item(finding, summary="USD/CAD à 1,4257 le 13 novembre.")
    stage(store, item)
    store.put_json("staging/run1/experts/E2/brief.json", {"subject": "E2", "text": "USD/CAD à 1,4257.", "gaps": []})
    with pytest.raises(Exception, match="synthèse"):
        router_mod.compose(
            run_id="run1",
            store=store,
            trace=Trace("fr"),
            model_factory=ScriptedFactory(
                [[("tool", "write_brief", {"title": "x", "text": "12 %", "citations": [item["id"]]})]]
            ),
            model_id="s",
        )
    composed = router_mod.compose(
        run_id="run1",
        store=store,
        trace=Trace("fr"),
        model_factory=ScriptedFactory(
            [
                [
                    (
                        "tool",
                        "write_brief",
                        {
                            "title": "Taux de change USD/CAD en novembre 2026",
                            "text": "Le dollar américain valait 1,4257 $ CA le 13 novembre 2026 (Banque du Canada).",
                            "citations": [item["id"]],
                            "gaps": ["aucune donnée intrajournalière"],
                        },
                    )
                ]
            ]
        ),
        model_id="s",
    )
    brief = store.get_json(composed["brief_key"])
    assert brief["kind"] == "brief" and brief["data"]["citations"] == [item["id"]]
    result = supervisor.curate(
        run_id="run1", store=store, trace=Trace("fr"), model_factory=ScriptedFactory(), model_id="scripted"
    )
    briefs = [k for k in result["written"] if k.startswith("general/recherches/")]
    assert len(briefs) == 1, result
    text = store.get_text(briefs[0]).text
    assert "type: Research Brief" in text and "donnees/fxusdcad/2026-11-13.md" in text
    assert "jamais un conseil personnalisé" in text


# ----------------------------------------------------------------------------- contrat des runtimes
@pytest.mark.parametrize(
    ("role", "payload", "code"),
    [
        ("expert", {"action": "research", "run_id": "r1", "subject": "E9"}, "bad_request"),
        ("expert", {"action": "research", "run_id": "r1", "subject": "E1", "mode": "both"}, "bad_request"),
        ("expert", {"action": "research", "run_id": "r1", "subject": "E1", "mode": "question"}, "bad_request"),
        ("expert", {"action": "research", "run_id": "../x", "subject": "E1"}, "bad_request"),
        ("expert", {"action": "route", "run_id": "r1"}, "unknown_action"),
        ("researcher", {"action": "research", "run_id": "r1", "subject": "E1", "researcher": "x1"}, "bad_request"),
        (
            "researcher",
            {
                "action": "research",
                "run_id": "r1",
                "subject": "E1",
                "researcher": "r1",
                "objective": "o",
                "packs": ["attention"],
            },
            "bad_request",
        ),
        ("router", {"action": "route", "run_id": "r1"}, "bad_request"),
        ("router", {"action": "route", "run_id": "r1", "question": "q", "depth": "huge"}, "bad_request"),
    ],
)
def test_research_runtimes_validate_requests(store, tmp_path, role, payload, code):
    app = FakeApp()
    service = ResearchService(settings_for(role, tmp_path), store, app, model_factory=ScriptedFactory())
    response = service.handle(payload)
    assert response["ok"] is False and response["error"]["code"] == code
    assert app.started == []


def test_research_runtimes_answer_health(store, tmp_path):
    for role in ("router", "expert", "researcher"):
        service = ResearchService(settings_for(role, tmp_path), store, None, model_factory=ScriptedFactory())
        assert service.handle({"action": "health"}) == {"ok": True, "release": "r1", "role": role, "env": "local"}


def test_server_builds_research_services(store, tmp_path):
    from alphaforge.server import build_service

    for role in ("router", "expert", "researcher"):
        service = build_service(settings_for(role, tmp_path), None, store)
        assert isinstance(service, ResearchService) and service.role == role


def test_expert_uses_agentcore_when_the_researcher_arn_is_set(store, tmp_path):
    from alphaforge.research.launcher import AgentCoreLauncher, LocalLauncher

    arn = "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/alphaforge_sandbox_researcher-abc"
    remote = ResearchService(
        settings_for("expert", tmp_path, ALPHAFORGE_RESEARCHER_ARN=arn), store, None, model_factory=ScriptedFactory()
    )
    assert isinstance(remote.launcher(), AgentCoreLauncher) and remote.launcher().runtime_arn == arn
    local = ResearchService(settings_for("expert", tmp_path), store, None, model_factory=ScriptedFactory())
    assert isinstance(local.launcher(), LocalLauncher)


def test_agentcore_launcher_invokes_one_session_per_researcher(store):
    from alphaforge.research.launcher import AgentCoreLauncher

    class Body:
        def read(self):
            return b'{"ok": true, "accepted": true}'

    class Client:
        def __init__(self):
            self.calls = []

        def invoke_agent_runtime(self, **kwargs):
            self.calls.append(kwargs)
            return {"response": Body()}

    client = Client()
    launcher = AgentCoreLauncher(store, runtime_arn="arn:x", region="us-east-1", client=client, poll_seconds=0.01)
    briefs = [{"run_id": "run1", "subject": "E3", "researcher": f"r{i}", "objective": "o"} for i in (1, 2)]
    for brief in briefs:
        store.put_json(
            f"staging/run1/researchers/E3-{brief['researcher']}/_done.json", {"status": "ok", "findings_key": None}
        )
    results = launcher.run(briefs, timeout=1)
    sessions = {c["runtimeSessionId"] for c in client.calls}
    assert len(sessions) == 2 and all(len(s) >= 33 for s in sessions)
    assert json.loads(client.calls[0]["payload"])["action"] == "research"
    assert all(r["marker"]["status"] == "ok" for r in results)


def test_researcher_runtime_arn_is_resolved_by_name():
    from alphaforge.research.launcher import resolve_runtime_arn

    class Control:
        def __init__(self):
            self.pages = [
                {"agentRuntimes": [{"agentRuntimeName": "x_profile", "agentRuntimeArn": "arn:p"}], "nextToken": "t"},
                {"agentRuntimes": [{"agentRuntimeName": "x_researcher", "agentRuntimeArn": "arn:r"}]},
            ]

        def list_agent_runtimes(self, **kwargs):
            return self.pages.pop(0)

    assert resolve_runtime_arn("x_researcher", "us-east-1", Control()) == "arn:r"
    with pytest.raises(RuntimeError, match="introuvable"):
        resolve_runtime_arn("absent", "us-east-1", type("C", (), {"list_agent_runtimes": lambda self, **k: {}})())


def test_quote_documents_are_filed_under_their_symbol(fake_http, store):
    fake_http.add("https://www.bankofcanada.ca/valet/observations/", VALET_FX)
    finding = fx_finding(store)
    quote = {**finding, "kind": "quote", "values": {"value": "1.4257", "symbol": "COAX26"}, "issuers": []}
    item = items_mod.build_item(quote)
    assert item["data"]["symbol"] == "COAX26"


def test_brief_citing_an_item_already_in_the_base_links_the_existing_document(store, fake_http):
    fake_http.add("https://www.bankofcanada.ca/valet/observations/", VALET_FX)
    item = items_mod.build_item(fx_finding(store), summary="USD/CAD à 1,4257 le 13 novembre.")
    store.put_text("general/donnees/fxusdcad/2026-11-13.md", "---\ntype: Data Series\n---\n")
    stage(store, item)
    brief = {
        "id": "brief-x",
        "kind": "brief",
        "title": "USD/CAD en novembre 2026",
        "url": None,
        "source": "AlphaForge AI (A0, synthèse de recherche)",
        "published_at": "2026-11-15T00:00:00Z",
        "observed_at": None,
        "retrieved_at": "2026-11-15T00:00:00Z",
        "language": "fr",
        "tickers": [],
        "summary": "x",
        "data": {
            "text": "Le dollar américain valait 1,4257 $ CA le 13 novembre 2026.",
            "citations": [item["id"]],
            "question": "q",
            "subjects": ["E2"],
            "gaps": [],
        },
    }
    store.put_json("staging/run1/router/brief-x.json", brief)
    result = supervisor.curate(
        run_id="run1", store=store, trace=Trace("fr"), model_factory=ScriptedFactory(), model_id="scripted"
    )
    briefs = [k for k in result["written"] if k.startswith("general/recherches/")]
    assert len(briefs) == 1, result["rejected"]
    assert "donnees/fxusdcad/2026-11-13.md" in store.get_text(briefs[0]).text
