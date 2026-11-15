"""Montage MediaConvert d'une vidéo tldoole : réglages du job, construits par le code.

Une seule entrée, sans fichier vidéo :

- ``VideoGenerator`` crée la piste vidéo (1080 × 1920, 30 i/s) sur le fond de la charte, pour la durée exacte
  de la narration;
- ``ImageInserter`` superpose l'écran de chaque scène à l'instant où Polly commence à la dire, avec un fondu
  enchaîné (chaque scène reste sous la suivante le temps du fondu);
- la narration MP3 de Polly est la piste audio (``ExternalAudioFileInput``);
- les sous-titres SRT, calés sur les mots, sont incrustés (``BURN_IN``) en Atkinson Hyperlegible grasse.

Sortie : un MP4 H.264 + AAC, ``moov`` en tête pour la lecture progressive dans le navigateur.
Step Functions soumet ce job (``mediaconvert:createJob.sync``) avec le rôle MediaConvert de Terraform :
le runtime ne passe aucun rôle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FPS = 30
FADE_MS = 280
TAIL_MS = 900  # silence final : la dernière scène reste lisible après la dernière phrase
CAPTION_FONT_SIZE = 64
CAPTION_Y = 1370


@dataclass(frozen=True)
class Placement:
    image_key: str
    start_ms: int
    end_ms: int


def timecode(ms: int, fps: int = FPS) -> str:
    """Horodatage MediaConvert ``HH:MM:SS:FF`` (source de timecode ``ZEROBASED``)."""
    ms = max(0, int(ms))
    total_seconds, rest = divmod(ms, 1000)
    frame = min(fps - 1, round(rest * fps / 1000))
    hours, rest_s = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rest_s, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frame:02d}"


def placements(image_keys: list[str], scene_starts_ms: list[int], audio_ms: int) -> tuple[list[Placement], int]:
    """Fenêtre d'affichage de chaque écran et durée totale de la vidéo."""
    if len(image_keys) != len(scene_starts_ms) or not image_keys:
        raise ValueError("one image per scene start is required")
    total = audio_ms + TAIL_MS
    result = []
    for index, (key, start) in enumerate(zip(image_keys, scene_starts_ms, strict=True)):
        end = scene_starts_ms[index + 1] if index + 1 < len(scene_starts_ms) else total
        result.append(Placement(key, start, end))
    return result, total


def s3_url(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"


def job_settings(
    *,
    bucket: str,
    background_key: str,
    audio_key: str,
    captions_key: str,
    scenes: list[Placement],
    total_ms: int,
    output_key_base: str,
    caption_font_key: str,
    width: int = 1080,
    height: int = 1920,
) -> dict[str, Any]:
    """Réglages ``Settings`` d'un job ``CreateJob`` (le rôle et les métadonnées sont ajoutés par Step Functions)."""
    if output_key_base.endswith("/") or "." in output_key_base.rsplit("/", 1)[-1]:
        raise ValueError("output_key_base is a key without extension, e.g. clients/<id>/tldoole/videos/<v>/video")
    insertable = []
    for layer, scene in enumerate(scenes, start=1):
        first = layer == 1
        duration = scene.end_ms - scene.start_ms + (FADE_MS if layer < len(scenes) else 0)
        insertable.append(
            {
                "ImageInserterInput": s3_url(bucket, scene.image_key),
                "ImageX": 0,
                "ImageY": 0,
                "Width": width,
                "Height": height,
                "Layer": min(layer, 99),
                "Opacity": 100,
                "StartTime": timecode(scene.start_ms),
                "Duration": max(1, duration),
                "FadeIn": 0 if first else FADE_MS,
                "FadeOut": 0,
            }
        )
    return {
        "TimecodeConfig": {"Source": "ZEROBASED"},
        "Inputs": [
            {
                "VideoGenerator": {
                    "Duration": int(total_ms),
                    "Width": width,
                    "Height": height,
                    "FramerateNumerator": FPS,
                    "FramerateDenominator": 1,
                    "SampleRate": 48000,
                    "Channels": 2,
                    "ImageInput": s3_url(bucket, background_key),
                },
                "TimecodeSource": "ZEROBASED",
                "AudioSelectors": {
                    "Audio Selector 1": {
                        "ExternalAudioFileInput": s3_url(bucket, audio_key),
                        "DefaultSelection": "DEFAULT",
                    }
                },
                "CaptionSelectors": {
                    "Captions Selector 1": {
                        "SourceSettings": {
                            "SourceType": "SRT",
                            "FileSourceSettings": {"SourceFile": s3_url(bucket, captions_key)},
                        }
                    }
                },
                "ImageInserter": {"InsertableImages": insertable},
            }
        ],
        "OutputGroups": [
            {
                "Name": "File Group",
                "OutputGroupSettings": {
                    "Type": "FILE_GROUP_SETTINGS",
                    "FileGroupSettings": {"Destination": s3_url(bucket, output_key_base)},
                },
                "Outputs": [
                    {
                        "ContainerSettings": {
                            "Container": "MP4",
                            "Mp4Settings": {"MoovPlacement": "PROGRESSIVE_DOWNLOAD"},
                        },
                        "VideoDescription": {
                            "Width": width,
                            "Height": height,
                            "ScalingBehavior": "DEFAULT",
                            "CodecSettings": {
                                "Codec": "H_264",
                                "H264Settings": {
                                    "RateControlMode": "QVBR",
                                    "QvbrSettings": {"QvbrQualityLevel": 8},
                                    "MaxBitrate": 4_000_000,
                                    "CodecProfile": "HIGH",
                                    "CodecLevel": "AUTO",
                                    "FramerateControl": "SPECIFIED",
                                    "FramerateNumerator": FPS,
                                    "FramerateDenominator": 1,
                                    "GopSize": 2,
                                    "GopSizeUnits": "SECONDS",
                                    "SceneChangeDetect": "TRANSITION_DETECTION",
                                },
                            },
                        },
                        "AudioDescriptions": [
                            {
                                "AudioSourceName": "Audio Selector 1",
                                "CodecSettings": {
                                    "Codec": "AAC",
                                    "AacSettings": {
                                        "Bitrate": 128000,
                                        "CodingMode": "CODING_MODE_2_0",
                                        "SampleRate": 48000,
                                    },
                                },
                            }
                        ],
                        "CaptionDescriptions": [
                            {
                                "CaptionSelectorName": "Captions Selector 1",
                                "DestinationSettings": {
                                    "DestinationType": "BURN_IN",
                                    "BurninDestinationSettings": {
                                        # MediaConvert exige les quatre styles dès qu'une police est
                                        # fournie : la police grasse les sert tous (sous-titres en gras).
                                        "FontFileRegular": s3_url(bucket, caption_font_key),
                                        "FontFileBold": s3_url(bucket, caption_font_key),
                                        "FontFileItalic": s3_url(bucket, caption_font_key),
                                        "FontFileBoldItalic": s3_url(bucket, caption_font_key),
                                        "FontSize": CAPTION_FONT_SIZE,
                                        "FontColor": "WHITE",
                                        "FontOpacity": 255,
                                        "OutlineColor": "BLACK",
                                        "OutlineSize": 4,
                                        "ShadowColor": "BLACK",
                                        "ShadowOpacity": 120,
                                        "ShadowXOffset": 2,
                                        "ShadowYOffset": 4,
                                        "BackgroundColor": "NONE",
                                        "Alignment": "CENTERED",
                                        "YPosition": CAPTION_Y,
                                        "FontResolution": 96,
                                        "TeletextSpacing": "PROPORTIONAL",
                                    },
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }
