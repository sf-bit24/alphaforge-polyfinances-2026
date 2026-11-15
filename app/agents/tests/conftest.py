"""Fixtures communes : magasin local temporaire, services sans réseau ni AWS, modèle scripté pour Strands."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from strands.models import Model

from alphaforge.config import Settings
from alphaforge.profile.service import ProfileService
from alphaforge.store.local import LocalStore

BASE_ANSWERS = {
    "q_kn_invest_freq": "several_per_year",
    "q_kn_news": "weekly",
    "q_kn_products": ["etf", "stocks", "crypto"],
    "q_kn_self": "intermediate",
    "q_goal": "growth",
    "q_project_type": "home",
    "q_horizon": "gt10",
    "q_drop_reaction": "hold",
    "q_risk_attitude": "large",
    "q_emergency_fund": "6to12",
    "q_income_stability": "very_stable",
    "q_loss_impact": "none",
    "q_liquidity": "none",
    "q_withdrawal_pct": "lt10",
    "q_accounts": ["tfsa", "rrsp"],
    "q_currency": "cad_usd",
    "q_esg": 4,
    "q_exclusions": ["tobacco"],
    "q_interests": ["technology", "crypto"],
    "q_amount": "10k_50k",
    "q_existing_portfolio": False,
}


class ScriptedModel(Model):
    """Modèle factice : chaque appel rejoue le tour suivant du script (texte ou appels d'outils)."""

    def __init__(self, script: list[list[tuple[str, Any, Any]]]):
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []
        self.config: dict[str, Any] = {"model_id": "scripted"}

    def update_config(self, **model_config: Any) -> None:
        self.config.update(model_config)

    def get_config(self) -> Any:
        return self.config

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):  # pragma: no cover
        raise NotImplementedError
        yield  # noqa: B901

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs) -> AsyncGenerator[dict]:
        self.calls.append(
            {"messages": messages, "tools": [t["name"] for t in tool_specs or []], "system_prompt": system_prompt}
        )
        turn = self.script.pop(0) if self.script else [("text", "done", None)]
        yield {"messageStart": {"role": "assistant"}}
        uses_tool = False
        for index, (kind, name, payload) in enumerate(turn):
            if kind == "text":
                yield {"contentBlockDelta": {"delta": {"text": name}}}
                yield {"contentBlockStop": {}}
            else:
                uses_tool = True
                yield {
                    "contentBlockStart": {
                        "start": {"toolUse": {"toolUseId": f"t{len(self.calls)}_{index}", "name": name}}
                    }
                }
                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(payload)}}}}
                yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "tool_use" if uses_tool else "end_turn"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
                "metrics": {"latencyMs": 1},
            }
        }


class ScriptedFactory:
    """Fabrique de modèles qui distribue un script par agent créé, et garde les appels."""

    def __init__(self, *scripts: list[list[tuple[str, Any, Any]]]):
        self.scripts = list(scripts)
        self.models: list[ScriptedModel] = []
        self.requests: list[dict[str, Any]] = []

    def __call__(
        self, *, effort: str, guardrail: bool = False, max_tokens: int = 8000, guard_tagged: bool = False
    ) -> ScriptedModel:
        self.requests.append({"effort": effort, "guardrail": guardrail, "max_tokens": max_tokens})
        if guard_tagged:
            self.requests[-1]["guard_tagged"] = True
        model = ScriptedModel(self.scripts.pop(0) if self.scripts else [])
        self.models.append(model)
        return model


@pytest.fixture
def store(tmp_path):
    return LocalStore(tmp_path / "kb")


@pytest.fixture
def settings(tmp_path):
    return Settings.from_env(
        {
            "AGENT_ROLE": "profile",
            "ALPHAFORGE_STORE": "local",
            "ALPHAFORGE_LOCAL_DIR": str(tmp_path / "kb"),
            "ALPHAFORGE_RELEASE": "test1234",
            "ALPHAFORGE_ENV": "test",
        }
    )


def make_service(settings, store, factory=None, quote_fetcher=None, client_brain=False) -> ProfileService:
    def no_model(**_: Any):
        raise AssertionError("a deterministic action must not create a model")

    # La base du client écrite par A1 (fin du questionnaire) appelle un modèle de plus : désactivée par défaut
    # pour que les scripts des autres tests restent alignés; tests/test_client_brain.py l'active.
    return ProfileService(
        settings,
        store,
        model_factory=factory or no_model,
        quote_fetcher=quote_fetcher,
        write_client_brain=client_brain,
    )


def answer_base(service: ProfileService, client_id: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    answers = {**BASE_ANSWERS, **(overrides or {})}
    response = service.handle({"action": "session.resume", "client_id": client_id})
    guard = 0
    while response["stage"] == "base_questions":
        question = response["questions"][0]
        response = service.handle(
            {
                "action": "base.answer",
                "client_id": client_id,
                "question_id": question["id"],
                "value": answers[question["id"]],
            }
        )
        assert response["ok"], response
        guard += 1
        assert guard < 40
    return response
