"""Narration des vidéos tldoole : Amazon Polly, moteur neural, une seule synthèse par vidéo.

Le texte des scènes est enchaîné dans un document SSML, avec une marque ``<mark name="sN"/>`` au début de
chaque scène et une courte pause entre deux scènes. Deux appels à ``SynthesizeSpeech`` sur le même SSML :
l'audio MP3, puis les marques de parole (``ssml`` pour le début des scènes, ``word`` pour les sous-titres).

Le moteur ``generative`` ne renvoie pas de marques de parole : on reste sur ``neural`` (Gabrielle en fr-CA,
Joanna en en-US). La durée exacte de l'audio se lit dans les trames MP3 (``mp3_duration_ms``), sans estimation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape

import boto3
from botocore.config import Config

VOICES = {"fr": ("Gabrielle", "fr-CA"), "en": ("Joanna", "en-US")}
ENGINE = "neural"
SAMPLE_RATE = "24000"
SCENE_PAUSE_MS = 450
MAX_SSML_CHARS = 5800  # SynthesizeSpeech : 6 000 caractères au plus, balises comprises

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class VoiceError(Exception):
    pass


@dataclass(frozen=True)
class Word:
    time_ms: int
    text: str


@dataclass(frozen=True)
class Narration:
    audio: bytes
    duration_ms: int
    scene_starts_ms: list[int]
    words: list[Word]
    voice: str
    language: str


# Abréviations de mois des écrans (facts.fmt_month), dites en entier.
_MONTHS_SPOKEN = {
    "janv.": "janvier",
    "févr.": "février",
    "avr.": "avril",
    "juil.": "juillet",
    "sept.": "septembre",
    "oct.": "octobre",
    "nov.": "novembre",
    "déc.": "décembre",
    "Jan.": "January",
    "Feb.": "February",
    "Mar.": "March",
    "Apr.": "April",
    "Aug.": "August",
    "Sept.": "September",
    "Oct.": "October",
    "Nov.": "November",
    "Dec.": "December",
}
_MONTH_PATTERN = re.compile(r"(?<![\w.])(" + "|".join(re.escape(m) for m in _MONTHS_SPOKEN) + r")(?=\s|$)")
# « a reculé de −16,4 % » se dit « a reculé de 16,4 % » : pas de double négation après un verbe de baisse.
_DECLINE = re.compile(
    r"\b((?:recul|baiss|chut|perd|fond|dropp|fell|fall|declin|lost|lose)\w*(?:\s+(?:de|d'environ|by|of))?\s+)-(?=\d)",
    re.IGNORECASE,
)


def spoken_text(text: str) -> str:
    """Texte prêt pour SSML : sans caractères de contrôle, mois en toutes lettres, signe moins ASCII sauf
    après un verbe de baisse, espaces normalisés."""
    text = _CONTROL.sub(" ", text or "")
    text = text.replace("\u2212", "-").replace("\u00a0", " ").replace("\u202f", " ")
    text = _MONTH_PATTERN.sub(lambda m: _MONTHS_SPOKEN[m.group(1)], text)
    text = _DECLINE.sub(r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def build_ssml(narrations: list[str], *, pause_ms: int = SCENE_PAUSE_MS) -> str:
    parts = ["<speak>"]
    for index, text in enumerate(narrations, start=1):
        if index > 1:
            parts.append(f'<break time="{int(pause_ms)}ms"/>')
        parts.append(f'<mark name="s{index}"/>{escape(spoken_text(text))}')
    parts.append("</speak>")
    ssml = "".join(parts)
    if len(ssml) > MAX_SSML_CHARS:
        raise VoiceError(f"narration too long for one synthesis ({len(ssml)} > {MAX_SSML_CHARS} characters)")
    return ssml


_PUNCTUATION = ".,;:!?\u2026\u00bb"
_SPACED = "?!:;\u00bb"  # précédés d'une espace insécable en français


def _trailing_punctuation(source: bytes, end: int) -> str:
    """Ponctuation qui suit un mot dans le SSML (Polly ne la met pas dans la marque du mot)."""
    tail = source[end : end + 12].decode("utf-8", errors="ignore").lstrip(" \u00a0\u202f")
    punct = ""
    for char in tail:
        if char not in _PUNCTUATION:
            break
        punct += char
    return punct


def parse_speech_marks(
    raw: bytes | str, scenes: int, *, ssml: str | None = None, locale: str = "fr"
) -> tuple[list[int], list[Word]]:
    """Lit les marques de parole (une ligne JSON par marque) : débuts de scène et mots.

    Avec ``ssml``, chaque mot reprend la ponctuation qui le suit dans le texte (positions ``end`` en octets),
    pour couper les sous-titres en fin de phrase.
    """
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    source = ssml.encode("utf-8") if ssml else b""
    starts: dict[int, int] = {}
    words: list[Word] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        mark = json.loads(line)
        kind = mark.get("type")
        if kind == "ssml":
            match = re.fullmatch(r"s(\d+)", str(mark.get("value", "")))
            if match:
                starts[int(match.group(1))] = int(mark.get("time", 0))
        elif kind == "word":
            value = str(mark.get("value", "")).strip()
            if not value or value.startswith("<"):  # Polly marque aussi les balises (<break/>) comme des mots
                continue
            if source and isinstance(mark.get("end"), int):
                punct = _trailing_punctuation(source, mark["end"])
                if punct:
                    spaced = locale == "fr" and punct[0] in _SPACED
                    value = value + ("\u00a0" if spaced else "") + punct
            words.append(Word(int(mark.get("time", 0)), value))
    if sorted(starts) != list(range(1, scenes + 1)):
        raise VoiceError(f"speech marks list scenes {sorted(starts)}, expected 1..{scenes}")
    ordered = [starts[i] for i in range(1, scenes + 1)]
    if ordered[0] != 0:
        ordered[0] = 0
    if any(b < a for a, b in zip(ordered, ordered[1:], strict=False)):
        raise VoiceError("scene marks are not in order")
    return ordered, words


# --------------------------------------------------------------------------- durée MP3
_BITRATES_V1_L3 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
_BITRATES_V2_L3 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)
_SAMPLE_RATES = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


def mp3_duration_ms(data: bytes) -> int:
    """Durée d'un flux MPEG Layer III, en comptant ses trames (CBR ou VBR); 0 si aucune trame."""
    index = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        size = (data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F)
        index = 10 + size
    samples = 0
    rate = 0
    end = len(data)
    while index + 4 <= end:
        b1, b2 = data[index + 1], data[index + 2]
        if data[index] != 0xFF or (b1 & 0xE0) != 0xE0:
            index += 1
            continue
        version = (b1 >> 3) & 0x03  # 3 : MPEG-1, 2 : MPEG-2, 0 : MPEG-2.5
        layer = (b1 >> 1) & 0x03  # 1 : Layer III
        bitrate_index = (b2 >> 4) & 0x0F
        rate_index = (b2 >> 2) & 0x03
        padding = (b2 >> 1) & 0x01
        if version == 1 or layer != 1 or bitrate_index in (0, 15) or rate_index == 3:
            index += 1
            continue
        sample_rate = _SAMPLE_RATES[version][rate_index]
        if version == 3:
            frame_length = 144000 * _BITRATES_V1_L3[bitrate_index] // sample_rate + padding
            per_frame = 1152
        else:
            frame_length = 72000 * _BITRATES_V2_L3[bitrate_index] // sample_rate + padding
            per_frame = 576
        if frame_length < 4:
            index += 1
            continue
        samples += per_frame
        rate = sample_rate
        index += frame_length
    return round(samples * 1000 / rate) if rate else 0


class Voice:
    def __init__(self, region: str, *, client: Any | None = None):
        self.client = client or boto3.client(
            "polly",
            region_name=region,
            config=Config(retries={"max_attempts": 4, "mode": "standard"}, connect_timeout=5, read_timeout=60),
        )

    def narrate(self, narrations: list[str], locale: str) -> Narration:
        if not narrations:
            raise VoiceError("no narration")
        voice, language = VOICES.get(locale, VOICES["fr"])
        ssml = build_ssml(narrations)
        common = {"Engine": ENGINE, "VoiceId": voice, "LanguageCode": language, "TextType": "ssml", "Text": ssml}
        audio = self.client.synthesize_speech(OutputFormat="mp3", SampleRate=SAMPLE_RATE, **common)
        audio_bytes = audio["AudioStream"].read()
        marks = self.client.synthesize_speech(OutputFormat="json", SpeechMarkTypes=["ssml", "word"], **common)
        starts, words = parse_speech_marks(marks["AudioStream"].read(), len(narrations), ssml=ssml, locale=locale)
        duration = mp3_duration_ms(audio_bytes)
        if duration <= 0:
            raise VoiceError("Polly returned no audio frames")
        return Narration(
            audio=audio_bytes,
            duration_ms=duration,
            scene_starts_ms=starts,
            words=words,
            voice=voice,
            language=language,
        )
