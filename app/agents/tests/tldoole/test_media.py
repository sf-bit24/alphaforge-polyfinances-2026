"""Voix, sous-titres, montage MediaConvert et écrans : sans réseau."""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image

from alphaforge.tldoole import captions, montage, render
from alphaforge.tldoole.concepts import load_catalog
from alphaforge.tldoole.voice import (
    VoiceError,
    build_ssml,
    mp3_duration_ms,
    parse_speech_marks,
    spoken_text,
)

from .conftest import mp3_frames


def test_mp3_duration_counts_frames_and_skips_id3():
    assert mp3_duration_ms(mp3_frames(100)) == 2400
    id3 = b"ID3\x04\x00\x00\x00\x00\x00\x0a" + bytes(10)
    assert mp3_duration_ms(id3 + mp3_frames(50)) == 1200
    assert mp3_duration_ms(b"not audio") == 0


def test_ssml_marks_each_scene_and_escapes_text():
    ssml = build_ssml(["Un FNB, c'est quoi ?", "Rendement < risque & frais"])
    assert ssml.startswith('<speak><mark name="s1"/>')
    assert '<break time="450ms"/><mark name="s2"/>' in ssml
    assert "&lt; risque &amp; frais" in ssml
    assert spoken_text("\u221216,4\u00a0%") == "-16,4 %"
    assert spoken_text("Le XIU a reculé de \u221216,4 % entre avr. 2022 et oct. 2022.") == (
        "Le XIU a reculé de 16,4 % entre avril 2022 et octobre 2022."
    )
    assert spoken_text("It fell by \u221216.4% from Apr. 2022.") == "It fell by 16.4% from April 2022."
    with pytest.raises(VoiceError):
        build_ssml(["x" * 6000])


def test_speech_marks_keep_punctuation_and_skip_tags():
    ssml = build_ssml(["On démêle ça.", "Un FNB, c'est un panier."])
    marks = "\n".join(
        json.dumps(m)
        for m in [
            {"time": 25, "type": "ssml", "start": 7, "end": 24, "value": "s1"},
            {"time": 25, "type": "word", "start": 24, "end": 26, "value": "On"},
            {"time": 162, "type": "word", "start": 27, "end": 35, "value": "démêle"},
            {"time": 500, "type": "word", "start": 36, "end": 39, "value": "ça"},
            {"time": 900, "type": "word", "start": 40, "end": 61, "value": '<break time="450ms"/>'},
            {"time": 1349, "type": "ssml", "start": 61, "end": 78, "value": "s2"},
            {"time": 1755, "type": "word", "start": 78, "end": 80, "value": "Un"},
            {"time": 1942, "type": "word", "start": 81, "end": 84, "value": "FNB"},
        ]
    )
    starts, words = parse_speech_marks(marks, 2, ssml=ssml)
    assert starts == [0, 1349]
    assert [w.text for w in words] == ["On", "démêle", "ça.", "Un", "FNB,"]
    with pytest.raises(VoiceError):
        parse_speech_marks(marks, 3, ssml=ssml)


def test_captions_break_at_punctuation_and_format():
    from alphaforge.tldoole.voice import Word

    words = [
        Word(0, "Un"),
        Word(200, "FNB,"),
        Word(500, "c'est"),
        Word(700, "un"),
        Word(900, "panier"),
        Word(1100, "de"),
        Word(1300, "placements."),
        Word(3000, "Fin."),
    ]
    cues = captions.build_cues(words, total_ms=4000)
    assert [c.text for c in cues] == ["Un FNB,", "c'est un panier de", "placements.", "Fin."]
    assert cues[1].end_ms == 1300 and cues[2].end_ms < 3000
    srt = captions.to_srt(cues)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:00,500\nUn FNB,\n")
    assert captions.to_vtt(cues).startswith("WEBVTT\n\n00:00:00.000 --> ")


def test_montage_settings_layer_scenes_with_crossfades():
    keys = ["clients/c/tldoole/videos/v/scene-01.png", "clients/c/tldoole/videos/v/scene-02.png"]
    places, total = montage.placements(keys, [0, 5000], 9100)
    assert total == 10000 and places[1].end_ms == 10000
    settings = montage.job_settings(
        bucket="b",
        background_key="k/background.png",
        audio_key="k/narration.mp3",
        captions_key="k/captions.srt",
        scenes=places,
        total_ms=total,
        output_key_base="clients/c/tldoole/videos/v/video",
        caption_font_key="k/caption-font.ttf",
    )
    entry = settings["Inputs"][0]
    assert entry["VideoGenerator"]["Duration"] == 10000
    assert entry["VideoGenerator"]["Width"] == 1080 and entry["VideoGenerator"]["Height"] == 1920
    images = entry["ImageInserter"]["InsertableImages"]
    assert [i["Layer"] for i in images] == [1, 2]
    assert images[0]["Duration"] == 5000 + montage.FADE_MS and images[1]["FadeIn"] == montage.FADE_MS
    assert images[1]["StartTime"] == "00:00:05:00"
    output = settings["OutputGroups"][0]
    assert (
        output["OutputGroupSettings"]["FileGroupSettings"]["Destination"] == "s3://b/clients/c/tldoole/videos/v/video"
    )
    burnin = output["Outputs"][0]["CaptionDescriptions"][0]["DestinationSettings"]["BurninDestinationSettings"]
    assert {burnin[k] for k in ("FontFileRegular", "FontFileBold", "FontFileItalic", "FontFileBoldItalic")} == {
        "s3://b/k/caption-font.ttf"
    }
    assert output["Outputs"][0]["ContainerSettings"]["Mp4Settings"]["MoovPlacement"] == "PROGRESSIVE_DOWNLOAD"
    with pytest.raises(ValueError):
        montage.job_settings(
            bucket="b",
            background_key="x",
            audio_key="x",
            captions_key="x",
            scenes=places,
            total_ms=total,
            output_key_base="v/video.mp4",
            caption_font_key="x",
        )


def test_timecode():
    assert montage.timecode(0) == "00:00:00:00"
    assert montage.timecode(61_500) == "00:01:01:15"
    assert montage.timecode(999) == "00:00:00:29"


@pytest.mark.parametrize(
    "scene",
    [
        render.Scene("hook", "Un FNB, c'est quoi ?", body="En une minute."),
        render.Scene("statement", "Un panier", body="Une part = un morceau de tout le panier."),
        render.Scene(
            "number",
            "XIU.TO",
            number={"text": "−16,4 %", "label": "Baisse maximale", "sublabel": "avr. 2022 → oct. 2022"},
            source="Source : jeu de départ, 2021-11-12 → 2026-11-12",
        ),
        render.Scene(
            "chart",
            "Cinq ans",
            chart={
                "values": [100, 95, 120, 110, 190],
                "title": "Valeur de 100 $",
                "start_label": "nov. 2021",
                "end_label": "nov. 2026",
                "end_text": "190 $",
                "highlight": [2, 3],
            },
        ),
        render.Scene(
            "compare",
            "Une action seule bouge plus",
            bars=[
                {"label": "Shopify (SHOP.TO)", "value": 0.64, "text": "64,2 %"},
                {"label": "XIU.TO", "value": 0.13, "text": "13,1 %"},
            ],
        ),
        render.Scene("list", "Les risques", items=["Les actifs peuvent baisser", "Les frais", "La liquidité"]),
        render.Scene("outro", "À retenir", items=["Un panier", "Moins agité"]),
    ],
)
def test_every_layout_renders_a_vertical_png(scene):
    png = render.render_scene(scene, render.Frame(concept_label="FNB"), index=1, total=6)
    image = Image.open(io.BytesIO(png))
    assert image.size == (1080, 1920) and image.mode == "RGB"


def test_typeset_keeps_french_punctuation_on_the_line():
    assert render.typeset("Un FNB, c'est quoi ?") == "Un FNB, c'est quoi\u00a0?"
    assert render.typeset("2021 \u2192 2026") == "2021 \u2013 2026"
    face = render.font(92, True)
    assert render.wrap("c'est quoi ?", face, 300)[-1].endswith("quoi ?")


def test_catalog_texts_have_every_glyph():
    catalog = load_catalog()
    text = "".join(
        c.text(field, locale) + "".join(c.points(locale))
        for c in catalog.concepts.values()
        for locale in ("fr", "en")
        for field in ("label", "title")
    )
    assert render.missing_glyphs(render.typeset(text)) == []
    assert render.missing_glyphs(render.typeset(text), bold=True) == []
