"""Couche de rejeu LLM : tests sans réseau (faux transport)."""
from __future__ import annotations

import json
from typing import Literal

import pytest
from pydantic import BaseModel

from alphaforge.finance.llm import FileStore, LLMOutputError, LLMRequest, ReplayMiss, converse_kwargs, llm_call


class Verdict(BaseModel):
    verdict: Literal["soutien", "objection"]
    motif: str


def fake(texts):
    calls = []

    def transport(kw):
        calls.append(kw)
        t = texts[min(len(calls) - 1, len(texts) - 1)]
        return {"output": {"message": {"content": [{"text": t}]}}, "stopReason": "end_turn",
                "usage": {"inputTokens": 1, "outputTokens": 1}}
    transport.calls = calls
    return transport


def req(**k):
    base = dict(model_id="us.anthropic.claude-opus-5-5", system="s",
                messages=({"role": "user", "content": [{"text": "q"}]},), output_model=Verdict,
                effort="low", node_id="lentille_risque", round=1, data_version="d1", policy_version="p1")
    base.update(k)
    return LLMRequest(**base)


def test_record_then_replay_is_identical_without_calling_model(tmp_path):
    store = FileStore(tmp_path)
    tr = fake([json.dumps({"verdict": "objection", "motif": "CVaR"})])
    first = llm_call(req(), store, mode="record", transport=tr)
    again = llm_call(req(), store, mode="replay", transport=fake(["NE DOIT PAS SERVIR"]))
    assert not first.replayed and again.replayed
    assert again.parsed == first.parsed and again.text == first.text and len(tr.calls) == 1


def test_replay_miss_never_calls_model(tmp_path):
    tr = fake(["{}"])
    with pytest.raises(ReplayMiss):
        llm_call(req(), FileStore(tmp_path), mode="replay", transport=tr)
    assert tr.calls == []


def test_key_depends_on_node_round_and_versions():
    keys = {req().key(), req(node_id="lentille_horizon").key(), req(round=2).key(),
            req(data_version="d2").key(), req(policy_version="p2").key(), req(effort="high").key()}
    assert len(keys) == 6
    assert req().key() == req().key()


def test_draft_guardrail_rejected():
    with pytest.raises(ValueError, match="DRAFT"):
        req(guardrail=("gr-123", "DRAFT"))


def test_invalid_output_bounded_attempts(tmp_path):
    tr = fake(["pas du json", json.dumps({"verdict": "peut-etre", "motif": "x"})])
    with pytest.raises(LLMOutputError):
        llm_call(req(), FileStore(tmp_path), mode="record", transport=tr, max_attempts=2)
    assert len(tr.calls) == 2


def test_retry_then_success_records_attempts(tmp_path):
    tr = fake(["oups", json.dumps({"verdict": "soutien", "motif": "ok"})])
    r = llm_call(req(), FileStore(tmp_path), mode="record", transport=tr)
    assert r.parsed.verdict == "soutien" and len(r.record["attempts"]) == 2


def test_store_never_overwrites(tmp_path):
    s = FileStore(tmp_path)
    assert s.put_once("ab" * 32, {"x": 1}) and not s.put_once("ab" * 32, {"x": 2})
    assert s.get("ab" * 32) == {"x": 1}


def test_converse_request_shape():
    kw = converse_kwargs(req(guardrail=("gr-1", "3")))
    assert kw["outputConfig"]["effort"] == "low"
    assert kw["outputConfig"]["textFormat"]["type"] == "json_schema"
    assert json.loads(kw["outputConfig"]["textFormat"]["structure"]["jsonSchema"]["schema"])["title"] == "Verdict"
    assert kw["guardrailConfig"] == {"guardrailIdentifier": "gr-1", "guardrailVersion": "3"}
    assert "temperature" not in kw["inferenceConfig"]


def test_strands_replay_model_records_and_replays(tmp_path, monkeypatch):
    import asyncio

    from strands.models.bedrock import BedrockModel

    from alphaforge.finance.llm.strands_replay import ReplayModel

    calls = []

    async def fake_stream(self, messages, *a, **k):
        calls.append(1)
        for ev in ({"messageStart": {"role": "assistant"}},
                   {"contentBlockDelta": {"delta": {"text": "ok"}}},
                   {"messageStop": {"stopReason": "end_turn"}}):
            yield ev
    monkeypatch.setattr(BedrockModel, "stream", fake_stream)
    store = FileStore(tmp_path)

    async def collect(mode, node="n1", rnd=1):
        m = ReplayModel(node_id=node, store=store, mode=mode, model_id="us.anthropic.claude-haiku-5-5",
                        versions={"data": "d1"})
        msgs = [{"role": "user", "content": [{"text": "q"}]}]
        return [ev async for ev in m.stream(msgs, invocation_state={"debate_round": rnd})], m

    rec, _ = asyncio.run(collect("record"))
    rep, m = asyncio.run(collect("replay"))
    assert rec == rep and m.last_replayed and len(calls) == 1
    with pytest.raises(ReplayMiss):
        asyncio.run(collect("replay", rnd=2))          # autre tour = autre clé
    with pytest.raises(ValueError, match="temperature"):
        ReplayModel(node_id="x", store=store, model_id="m", temperature=0.0)


def test_filestore_publishes_atomically(tmp_path):
    s = FileStore(tmp_path)
    assert s.put_once("cd" * 32, {"x": 1})
    files = [p.name for p in tmp_path.rglob("*")]
    assert not any(n.endswith(".tmp") for n in files) and s.get("cd" * 32) == {"x": 1}


def test_index_metadata_for_both_record_formats():
    from alphaforge.finance.llm.core import _meta
    assert _meta({"request": {"model_id": "m", "node_id": "n"}}, "model_id") == "m"
    assert _meta({"request": {"config": {"model_id": "m2"}, "node_id": "n2"}}, "model_id") == "m2"
    assert _meta({"request": {}}, "node_id") == "inconnu"


def test_replay_model_concurrent_miss_yields_stored_winner(monkeypatch):
    import asyncio

    from strands.models.bedrock import BedrockModel

    from alphaforge.finance.llm.strands_replay import ReplayModel

    async def fake_stream(self, messages, *a, **k):
        yield {"contentBlockDelta": {"delta": {"text": "moi"}}}
    monkeypatch.setattr(BedrockModel, "stream", fake_stream)

    class RacingStore:                       # un autre appel a publié entre notre lecture et notre écriture
        def __init__(self):
            self.calls = 0

        def get(self, key):
            self.calls += 1
            return None if self.calls == 1 else {"events": [{"contentBlockDelta": {"delta": {"text": "gagnant"}}}]}

        def put_once(self, key, record):
            return False

    m = ReplayModel(node_id="n", store=RacingStore(), mode="record", model_id="us.anthropic.claude-haiku-5-5")

    async def collect():
        return [ev async for ev in m.stream([{"role": "user", "content": [{"text": "q"}]}])]
    evs = asyncio.run(collect())
    assert evs == [{"contentBlockDelta": {"delta": {"text": "gagnant"}}}] and m.last_replayed
