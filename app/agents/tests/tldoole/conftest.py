"""Fixtures de tldoole : client fictif dans un magasin local, voix Polly simulée, Step Functions simulée."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from alphaforge.config import Settings
from alphaforge.profile.questionnaire import default_questionnaire
from alphaforge.profile.state import ClientSession
from alphaforge.store.local import LocalStore
from alphaforge.tldoole.voice import Narration, Word
from alphaforge.trace import Trace


def mp3_frames(count: int) -> bytes:
    """Trames MPEG-2 Layer III, 24 kHz, 48 kbit/s, sans remplissage : 144 octets et 576 échantillons chacune."""
    frame = bytes([0xFF, 0xF3, 0x64, 0xC4]) + bytes(140)
    return frame * count


class FakeVoice:
    """Narration simulée : un mot toutes les 300 ms, une scène après l'autre."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str]] = []

    def narrate(self, narrations: list[str], locale: str) -> Narration:
        self.calls.append((narrations, locale))
        words, starts, time_ms = [], [], 0
        for text in narrations:
            starts.append(time_ms)
            for word in text.split():
                words.append(Word(time_ms, word))
                time_ms += 300
            time_ms += 450
        frames = time_ms * 24000 // 576 // 1000 + 1
        return Narration(
            audio=mp3_frames(frames),
            duration_ms=round(frames * 576 * 1000 / 24000),
            scene_starts_ms=starts,
            words=words,
            voice="Gabrielle",
            language="fr-CA",
        )


class FakeSfn:
    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []

    def start_execution(self, **kwargs: Any) -> dict[str, Any]:
        self.started.append(kwargs)
        return {"executionArn": f"arn:aws:states:us-east-1:111122223333:execution:m:{kwargs['name']}"}


@pytest.fixture
def kb(tmp_path) -> LocalStore:
    return LocalStore(tmp_path / "kb")


@pytest.fixture
def tldoole_settings(tmp_path) -> Settings:
    return Settings.from_env(
        {
            "AGENT_ROLE": "tldoole",
            "ALPHAFORGE_STORE": "local",
            "ALPHAFORGE_LOCAL_DIR": str(tmp_path / "kb"),
            "ALPHAFORGE_RELEASE": "test1234",
            "ALPHAFORGE_ENV": "test",
        }
    )


def make_client(
    store: LocalStore, *, facts: dict[str, Any] | None = None, messages: list[str] | None = None, locale: str = "fr"
) -> str:
    client_id = str(uuid.uuid4())
    questionnaire = default_questionnaire()
    session = ClientSession.create(client_id, locale, questionnaire)
    for field_id, value in (facts or {}).items():
        session.set_fact(field_id, value, "base:q_test")
    for turn, text in enumerate(messages or [], start=1):
        session.journal_message(text, locale, f"a1:{turn}")
    session.commit(store, questionnaire, Trace(locale))
    return client_id
