"""Base OKF du client écrite par A1 avec ses skills (client-brain-init, client-brain-update), modèle scripté."""

import shutil

import pytest

from alphaforge import okf
from alphaforge.profile import brain
from alphaforge.profile.questionnaire import default_questionnaire
from alphaforge.profile.state import ClientSession, index_key, profile_key

from .conftest import ScriptedFactory, answer_base, make_service


def write(
    path, cites, title="Horizon de placement", body="# Horizon\n\n## Ce que l'investisseur a dit\n\n- 10 ans et plus"
):
    return (
        "tool",
        "write_document",
        {
            "path": path,
            "title": title,
            "description": "Ce que l'investisseur a dit de son horizon.",
            "tags": ["horizon"],
            "cites": cites,
            "body": body,
        },
    )


def finish(summary="Notes écrites."):
    return ("tool", "finish", {"summary": summary})


INIT_SCRIPT = [
    [
        write("dimensions/horizon.md", ["horizon.horizon_band", "horizon.horizon_years"]),
        write("dimensions/capacite.md", ["risk_capacity.emergency_fund"], title="Capacité à prendre du risque"),
        write("synthese.md", ["horizon.horizon_band", "risk_capacity.emergency_fund"], title="Synthèse du profil"),
    ],
    [finish()],
]


def ready_client(service, store):
    """Questions de base, puis les deux faits qui font passer la complétude au-dessus du seuil."""
    client_id = service.handle({"action": "session.start", "locale": "fr"})["client_id"]
    answer_base(service, client_id)
    profile = okf.parse(store.get(profile_key(client_id)).text)
    profile.data["facts"]["horizon.horizon_years"] = {"value": 20, "provenance": "a1:1", "at": "2026-11-14T00:00:00Z"}
    profile.data["facts"]["risk_capacity.max_loss_cad"] = {
        "value": 1000,
        "provenance": "a1:1",
        "at": "2026-11-14T00:00:00Z",
    }
    store.put_text(profile_key(client_id), okf.render(profile))
    return client_id


def stop(service, client_id):
    response = service.handle({"action": "followup.reply", "client_id": client_id, "stop": True})
    assert response["ok"], response
    return response


def test_skills_are_loaded_from_the_package():
    init = brain.load_skill(brain.INIT_SKILL)
    update = brain.load_skill(brain.UPDATE_SKILL)
    assert init.name == "client-brain-init" and "dimensions/horizon.md" in init.body
    assert update.name == "client-brain-update" and "client-brain-init" in update.body
    assert len(brain.skills_version()) == 12


def test_end_of_questionnaire_invokes_a1_with_the_init_skill(settings, store):
    factory = ScriptedFactory(INIT_SCRIPT)
    service = make_service(settings, store, factory, client_brain=True)
    client_id = ready_client(service, store)
    response = stop(service, client_id)
    assert response["stage"] == "complete"
    model = factory.models[0]
    assert '<skill name="client-brain-init">' in model.calls[0]["system_prompt"]
    assert model.calls[0]["tools"] == ["write_document", "read_document", "delete_document", "finish"]
    context = model.calls[0]["messages"][0]["content"][0]["text"]
    assert '"skill": "client-brain-init"' in context and '"field": "horizon.horizon_band"' in context

    note = okf.parse(store.get(f"clients/{client_id}/dimensions/horizon.md").text)
    assert okf.validate(note) == []
    assert note.frontmatter["type"] == "Profile Note" and note.frontmatter["sensitivity"] == "client"
    assert note.frontmatter["generated"]["by"] == "agent:A1"
    assert [s["resource"] for s in note.frontmatter["sources"]] == ["base:q_horizon", "a1:1"]
    assert note.data["skill"] == "client-brain-init" and note.data["skills_version"] == brain.skills_version()
    assert note.body.startswith("# Horizon")

    stored = okf.parse(store.get(profile_key(client_id)).text).data["brain"]
    assert [d["path"] for d in stored["documents"]] == [
        "dimensions/capacite.md",
        "dimensions/horizon.md",
        "synthese.md",
    ]
    index = store.get(index_key(client_id)).text
    assert "[Synthèse du profil](synthese.md)" in index and "(dimensions/horizon.md)" in index
    listed = service.handle({"action": "kb.list", "prefix": f"clients/{client_id}/"})["items"]
    assert {i["key"].split(f"{client_id}/")[1] for i in listed} >= {"synthese.md", "dimensions/horizon.md"}
    titles = [s["title"] for s in response["trace"]]
    assert "Notes de Yan ajoutées à vos documents personnels" in titles


def test_a1_completion_also_invokes_the_skill(settings, store):
    complete_turn = [
        [("tool", "finish_turn", {"message": "Le profil est complet.", "questions": [], "profile_complete": True})]
    ]
    factory = ScriptedFactory(complete_turn, INIT_SCRIPT)
    service = make_service(settings, store, factory, client_brain=True)
    client_id = ready_client(service, store)
    response = service.handle({"action": "followup.reply", "client_id": client_id})
    assert response["ok"] and response["stage"] == "complete"
    assert len(factory.models) == 2 and "<skill" in factory.models[1].calls[0]["system_prompt"]
    assert store.get(f"clients/{client_id}/synthese.md") is not None


def test_the_code_keeps_its_own_documents_and_checks_each_note(settings, store):
    q = default_questionnaire()
    session = ClientSession.create("8f0c3a8e-5d7b-4e2a-9f51-2c6d3b1a7e90", "fr", q)
    session.set_fact("horizon.horizon_band", "gt10", "base:q_horizon")
    session.set_fact("objective.goal_detail", "Une maison", "a1:2", confirmed=False)
    turn = brain.BrainTurn(session, store, skill=brain.INIT_SKILL, version="v")
    for path in (
        "profil.md",
        "journal.md",
        "index.md",
        "portefeuille-existant.md",
        "traces/x.md",
        "../x.md",
        "/abs.md",
        "Dimensions/x.md",
        "a/b/c/d.md",
        "notes.txt",
    ):
        assert (
            turn._write(brain.NoteDraft(path, "Titre", "Une description.", [], ["horizon.horizon_band"], "x"))["status"]
            == "error"
        ), path
    unconfirmed = turn._write(
        brain.NoteDraft("objectif.md", "Objectif", "Une description.", [], ["objective.goal_detail"], "x")
    )
    assert "unknown" in unconfirmed["reason"]  # une valeur à confirmer n'entre pas dans la base
    assert (
        turn._write(
            brain.NoteDraft("horizon.md", "Horizon", "Une description.", ["Pas Un Slug"], ["horizon.horizon_band"], "x")
        )["status"]
        == "error"
    )
    assert (
        turn._write(brain.NoteDraft("horizon.md", "Horizon", "Une description.", [], ["horizon.horizon_band"], "# H"))[
            "status"
        ]
        == "ok"
    )
    assert "synthese.md" in turn._finish("x")["reason"]
    assert (
        turn._write(
            brain.NoteDraft("synthese.md", "Synthèse", "Une description.", [], ["horizon.horizon_band"], "# S")
        )["status"]
        == "ok"
    )
    assert turn._finish("Deux notes.")["status"] == "ok"
    assert (
        turn._write(brain.NoteDraft("autre.md", "Autre", "Une description.", [], ["horizon.horizon_band"], "x"))[
            "status"
        ]
        == "error"
    )


def test_update_skill_rewrites_changed_notes_and_retires_the_others(settings, store):
    update_script = [
        [
            write(
                "dimensions/horizon.md", ["horizon.horizon_band", "horizon.horizon_years"], body="# Horizon\n\n15 ans"
            ),
            ("tool", "delete_document", {"path": "dimensions/capacite.md"}),
        ],
        [finish("Horizon réécrit, capacité retirée.")],
    ]
    factory = ScriptedFactory(INIT_SCRIPT, update_script)
    service = make_service(settings, store, factory, client_brain=True)
    client_id = ready_client(service, store)
    stop(service, client_id)
    # Une nouvelle réponse après la complétude change un fait, puis le profil repasse à complete.
    profile = okf.parse(store.get(profile_key(client_id)).text)
    profile.data["facts"]["horizon.horizon_years"]["value"] = 15
    profile.data["stage"] = "followups"
    store.put_text(profile_key(client_id), okf.render(profile))
    stop(service, client_id)
    model = factory.models[1]
    assert '<skill name="client-brain-update">' in model.calls[0]["system_prompt"]
    assert 'role="structure"' in model.calls[0]["system_prompt"]  # la structure vient du skill init
    context = model.calls[0]["messages"][0]["content"][0]["text"]
    assert '"changed_fields": [\n  "horizon.horizon_years"\n ]' in context and '"skill_changed": false' in context
    assert okf.parse(store.get(f"clients/{client_id}/dimensions/horizon.md").text).body.startswith(
        "# Horizon\n\n15 ans"
    )
    retired = okf.parse(store.get(f"clients/{client_id}/dimensions/capacite.md").text)
    assert retired.data["retired"] is True and okf.validate(retired) == []
    listed = {i["key"] for i in service.handle({"action": "kb.list", "prefix": f"clients/{client_id}/"})["items"]}
    assert f"clients/{client_id}/dimensions/capacite.md" not in listed
    assert "dimensions/capacite.md" not in store.get(index_key(client_id)).text
    paths = [d["path"] for d in okf.parse(store.get(profile_key(client_id)).text).data["brain"]["documents"]]
    assert paths == ["dimensions/horizon.md", "synthese.md"]


def test_no_change_means_no_model_call(settings, store):
    factory = ScriptedFactory(INIT_SCRIPT)
    service = make_service(settings, store, factory, client_brain=True)
    client_id = ready_client(service, store)
    stop(service, client_id)
    profile = okf.parse(store.get(profile_key(client_id)).text)
    profile.data["stage"] = "followups"
    store.put_text(profile_key(client_id), okf.render(profile))
    again = stop(service, client_id)
    assert len(factory.models) == 1
    assert "Notes de Yan déjà à jour" in [s["title"] for s in again["trace"]]


def test_changing_a_skill_triggers_the_update(tmp_path):
    directory = tmp_path / "skills"
    shutil.copytree(brain.SKILLS_DIR, directory)
    q = default_questionnaire()
    session = ClientSession.create("8f0c3a8e-5d7b-4e2a-9f51-2c6d3b1a7e90", "fr", q)
    session.set_fact("horizon.horizon_band", "gt10", "base:q_horizon")
    version = brain.skills_version(directory)
    assert brain.pending_skill(session, version=version)[0] == brain.INIT_SKILL
    session.data["brain"] = {
        "skills_version": version,
        "values": session.values(),
        "documents": [{"path": "synthese.md", "title": "Synthèse", "cites": [], "skills_version": version}],
    }
    assert brain.pending_skill(session, version=version) == (None, [])
    skill = directory / "client-brain-init" / "SKILL.md"
    skill.write_text(
        skill.read_text(encoding="utf-8").replace("dimensions/", "profil-par-dimension/"), encoding="utf-8"
    )
    assert brain.pending_skill(session, version=brain.skills_version(directory))[0] == brain.UPDATE_SKILL


@pytest.mark.parametrize("script", [[[("text", "rien", None)], [("text", "toujours rien", None)]], None])
def test_a_failed_skill_never_blocks_completion(settings, store, script):
    if script is None:

        def factory(**_):
            model = ScriptedFactory([])(effort="low")

            async def stream(*args, **kwargs):
                raise RuntimeError("bedrock down")
                yield  # noqa: B901

            model.stream = stream
            return model
    else:
        factory = ScriptedFactory(script)
    service = make_service(settings, store, factory, client_brain=True)
    client_id = ready_client(service, store)
    response = stop(service, client_id)
    assert response["stage"] == "complete"
    assert "Notes de Yan non écrites" in [s["title"] for s in response["trace"]]
    assert store.get(f"clients/{client_id}/synthese.md") is None
    assert "brain" not in okf.parse(store.get(profile_key(client_id)).text).data
