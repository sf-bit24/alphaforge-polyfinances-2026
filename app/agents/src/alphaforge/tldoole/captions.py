"""Sous-titres des vidéos tldoole, calés sur les marques de mots de Polly.

Les mots sont regroupés en courtes répliques (quatre mots, 26 caractères au plus, coupure après une
ponctuation), à la manière des vidéos courtes. Une réplique dure jusqu'au début de la suivante; avant une
pause (changement de scène) ou en fin de vidéo, sa durée est estimée d'après sa longueur.
MediaConvert incruste le fichier SRT; le WebVTT sert de piste accessible dans l'interface.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .voice import Word

MAX_WORDS = 4
MAX_CHARS = 26
MS_PER_CHAR = 75
MIN_CUE_MS = 450
PAUSE_MS = 900
_BREAK_AFTER = (".", ",", ";", ":", "!", "?", "»", "…")


@dataclass(frozen=True)
class Cue:
    start_ms: int
    end_ms: int
    text: str


def _estimate(text: str) -> int:
    return max(MIN_CUE_MS, len(text) * MS_PER_CHAR)


def build_cues(words: Sequence[Word], *, total_ms: int) -> list[Cue]:
    groups: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        candidate = " ".join(w.text for w in [*current, word])
        if current and (len(current) >= MAX_WORDS or len(candidate) > MAX_CHARS):
            groups.append(current)
            current = []
        current.append(word)
        if word.text.endswith(_BREAK_AFTER):
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    cues: list[Cue] = []
    for index, group in enumerate(groups):
        text = " ".join(w.text for w in group)
        start = group[0].time_ms
        next_start = groups[index + 1][0].time_ms if index + 1 < len(groups) else total_ms
        last_word = group[-1].time_ms
        estimated_end = last_word + _estimate(group[-1].text)
        if next_start - last_word > PAUSE_MS:
            end = min(next_start, max(estimated_end, start + MIN_CUE_MS))
        else:
            end = next_start
        end = min(max(end, start + 1), total_ms)
        if end <= start:
            continue
        cues.append(Cue(start, end, text))
    return cues


def _clock(ms: int, separator: str) -> str:
    ms = max(0, int(ms))
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{millis:03d}"


def to_srt(cues: Sequence[Cue]) -> str:
    blocks = [
        f"{index}\n{_clock(cue.start_ms, ',')} --> {_clock(cue.end_ms, ',')}\n{cue.text}\n"
        for index, cue in enumerate(cues, start=1)
    ]
    return "\n".join(blocks)


def to_vtt(cues: Sequence[Cue]) -> str:
    blocks = ["WEBVTT\n"]
    blocks.extend(f"{_clock(cue.start_ms, '.')} --> {_clock(cue.end_ms, '.')}\n{cue.text}\n" for cue in cues)
    return "\n".join(blocks)
