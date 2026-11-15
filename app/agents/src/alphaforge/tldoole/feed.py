"""État tldoole d'un investisseur, dans sa base OKF (``clients/<client_id>/tldoole/``).

- ``index.json`` : lacunes détectées, vidéos et leur statut, dernière détection. Écrit en concurrence
  optimiste (``If-Match`` sur l'ETag) : la détection, la production, la finalisation et les retours de
  l'investisseur peuvent s'y croiser sans s'écraser.
- ``lacunes.md`` : document OKF ``Concept Gaps``, chaque lacune avec sa preuve (citation, réponse, drapeau).
- ``videos/<video_id>/fiche.md`` : document OKF ``Learning Video`` (scénario, quiz, sources des chiffres).
- ``videos/<video_id>/`` : écrans PNG, narration MP3, sous-titres SRT et WebVTT, puis ``video.mp4`` écrit
  par MediaConvert; ``_produced.json`` est le marqueur que Step Functions sonde.
"""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Callable
from typing import Any, TypeVar

from .. import clock, okf
from ..store import ConflictError, Store
from .concepts import Catalog

T = TypeVar("T")
STATUSES = ("queued", "scripting", "rendering", "ready", "failed")
ACTIVE = ("queued", "scripting", "rendering")
VERDICTS = ("understood", "unclear")
VIDEO_ID = re.compile(r"^v\d{8}t\d{6}-[a-z0-9_]{2,40}-[0-9a-f]{4}$")
INDEX_VERSION = 1


def base_prefix(client_id: str) -> str:
    return f"clients/{client_id}/tldoole/"


def index_key(client_id: str) -> str:
    return base_prefix(client_id) + "index.json"


def gaps_key(client_id: str) -> str:
    return base_prefix(client_id) + "lacunes.md"


def video_prefix(client_id: str, video_id: str) -> str:
    return base_prefix(client_id) + f"videos/{video_id}/"


def video_doc_key(client_id: str, video_id: str) -> str:
    return video_prefix(client_id, video_id) + "fiche.md"


def produced_marker_key(client_id: str, video_id: str) -> str:
    return video_prefix(client_id, video_id) + "_produced.json"


def detect_marker_key(client_id: str, run_id: str) -> str:
    return base_prefix(client_id) + f"runs/{run_id}/detect.json"


def new_video_id(concept_id: str) -> str:
    stamp = clock.utcnow().strftime("%Y%m%dt%H%M%S")
    return f"v{stamp}-{concept_id}-{secrets.token_hex(2)}"


def empty_index(client_id: str) -> dict[str, Any]:
    return {
        "version": INDEX_VERSION,
        "client_id": client_id,
        "updated_at": clock.iso(),
        "gaps": {},
        "videos": [],
        "detection": {"journal_entries": 0, "messages": 0, "at": None, "candidates": []},
    }


def load_index(store: Store, client_id: str) -> dict[str, Any]:
    obj = store.get(index_key(client_id))
    return json.loads(obj.text) if obj else empty_index(client_id)


def update_index[T](
    store: Store, client_id: str, mutate: Callable[[dict[str, Any]], T], *, attempts: int = 6
) -> tuple[dict[str, Any], T]:
    """Lit, modifie et réécrit l'index; recommence si un autre écrivain est passé entre-temps."""
    key = index_key(client_id)
    for _ in range(attempts):
        obj = store.get(key)
        index = json.loads(obj.text) if obj else empty_index(client_id)
        result = mutate(index)
        index["updated_at"] = clock.iso()
        try:
            if obj is None:
                store.put_json(key, index, if_none_match=True)
            else:
                store.put_json(key, index, if_match=obj.etag)
            return index, result
        except ConflictError:
            continue
    raise ConflictError(key)


def find_video(index: dict[str, Any], video_id: str) -> dict[str, Any] | None:
    return next((v for v in index.get("videos") or [] if v.get("video_id") == video_id), None)


def videos_today(index: dict[str, Any]) -> int:
    today = clock.today().isoformat()
    return sum(1 for v in index.get("videos") or [] if str(v.get("created_at", "")).startswith(today))


def concept_state(index: dict[str, Any]) -> dict[str, str]:
    """État par concept, vu par A7 : vidéo en cours, prête, comprise ou encore floue."""
    states: dict[str, str] = {}
    for video in index.get("videos") or []:
        concept_id = video.get("concept_id")
        feedback = (video.get("feedback") or {}).get("verdict")
        status = video.get("status")
        if status in ACTIVE:
            state = "in_progress"
        elif feedback == "understood":
            state = "understood"
        elif feedback == "unclear":
            state = "unclear"
        elif status == "ready":
            state = "ready"
        else:
            continue
        previous = states.get(concept_id)
        if previous in ("in_progress", "understood") and state not in ("in_progress",):
            continue
        states[concept_id] = state
    return states


def new_video(
    *,
    concept_id: str,
    label: str,
    title: str,
    level: str,
    locale: str,
    reason: str,
    evidence: list[dict[str, Any]],
    version: int = 1,
    simpler: bool = False,
) -> dict[str, Any]:
    now = clock.iso()
    return {
        "video_id": new_video_id(concept_id),
        "concept_id": concept_id,
        "label": label,
        "title": title,
        "status": "queued",
        "level": level,
        "locale": locale,
        "reason": reason,  # detected, request, feedback
        "version": version,
        "simpler": simpler,
        "evidence": evidence[:3],
        "created_at": now,
        "updated_at": now,
        "duration_ms": None,
        "quiz": None,
        "sources": [],
        "feedback": None,
        "error": None,
        "job_id": None,
    }


def set_video(index: dict[str, Any], video_id: str, **fields: Any) -> dict[str, Any] | None:
    video = find_video(index, video_id)
    if video is None:
        return None
    video.update(fields)
    video["updated_at"] = clock.iso()
    return video


# --------------------------------------------------------------------------- documents OKF
def evidence_sources(client_id: str, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for item in evidence:
        if item.get("kind") == "message":
            out.append(
                {
                    "id": f"journal-{item.get('provenance', 'a1')}-{item.get('ref', '')}",
                    "title": f"Message de l'investisseur ({item.get('provenance')})",
                    "resource": f"clients/{client_id}/journal.md",
                    "observed_at": item.get("at"),
                }
            )
        elif item.get("kind") == "answer":
            out.append(
                {
                    "id": f"journal-{item.get('field')}",
                    "title": f"Réponse {item.get('field')} ({item.get('provenance')})",
                    "resource": f"clients/{client_id}/journal.md",
                    "observed_at": item.get("at"),
                }
            )
        elif item.get("kind") == "portfolio":
            out.append(
                {
                    "id": "client-existing-portfolio",
                    "title": "Drapeaux du portefeuille existant (A2)",
                    "resource": f"clients/{client_id}/portefeuille-existant.md",
                }
            )
    unique: dict[str, dict[str, Any]] = {}
    for source in out:
        unique.setdefault(source["id"], {k: v for k, v in source.items() if v is not None})
    return list(unique.values())


def write_gaps_doc(store: Store, client_id: str, index: dict[str, Any], catalog: Catalog, locale: str) -> str:
    en = locale == "en"
    gaps = list((index.get("gaps") or {}).values())
    lines = [
        "# " + ("Concepts to clarify" if en else "Concepts à éclaircir"),
        "",
        (
            "Detected by A7 from the investor's own words and answers; each gap cites its evidence."
            if en
            else "Repérés par A7 dans les mots et les réponses de l'investisseur; chaque lacune cite sa preuve."
        ),
        "",
        "| "
        + " | ".join(
            [
                "Concept",
                "Confidence" if en else "Confiance",
                "Status" if en else "Statut",
                "Evidence" if en else "Preuve",
            ]
        )
        + " |",
        "| --- | --- | --- | --- |",
    ]
    sources: list[dict[str, Any]] = []
    for gap in sorted(gaps, key=lambda g: g.get("detected_at") or "", reverse=True):
        concept = catalog.get(gap.get("concept_id"))
        label = concept.text("label", locale) if concept else gap.get("concept_id")
        proof = "; ".join(
            (f"« {e['quote']} »" if e.get("quote") else f"{e.get('field')} = {e.get('value')}")
            for e in gap.get("evidence") or []
        ).replace("|", "\\|")
        lines.append(f"| {label} | {gap.get('confidence')} | {gap.get('status')} | {proof[:200]} |")
        sources.extend(evidence_sources(client_id, gap.get("evidence") or []))
    unique = list({s["id"]: s for s in sources}.values())
    doc = okf.new_doc(
        type="Concept Gaps",
        title="Concepts to clarify" if en else "Concepts à éclaircir",
        description="Lacunes de compréhension repérées par A7, avec leurs preuves, et vidéos tldoole associées.",
        tags=["tldoole", "lacunes", "profil-investisseur"],
        owners=["alphaforge-a7"],
        sensitivity="client",
        generated_by="agent:A7",
        at=clock.iso(),
        status="draft",
        sources=unique,
        data={"gaps": gaps},
        body="\n".join(lines) + "\n",
    )
    return store.put_text(gaps_key(client_id), okf.render(doc))


def write_video_doc(store: Store, client_id: str, video: dict[str, Any], storyboard: dict[str, Any] | None) -> str:
    locale = video.get("locale") or "fr"
    en = locale == "en"
    lines = [f"# {video.get('title')}", ""]
    why = [f"« {e['quote']} »" for e in video.get("evidence") or [] if e.get("quote")]
    if why:
        lines += [("Why this video: " if en else "Pourquoi cette vidéo : ") + " ".join(why), ""]
    if storyboard:
        lines.append("## " + ("Transcript" if en else "Transcription"))
        lines.append("")
        for number, scene in enumerate(storyboard.get("scenes") or [], start=1):
            lines.append(f"{number}. **{scene.get('headline')}** — {scene.get('narration')}")
        lines.append("")
    if video.get("sources"):
        lines.append("## Sources")
        lines.append("")
        lines.extend(f"- {s.get('title')} (`{s.get('resource')}`)" for s in video["sources"])
        lines.append("")
    data = {
        k: video.get(k)
        for k in (
            "video_id",
            "concept_id",
            "level",
            "locale",
            "status",
            "version",
            "reason",
            "duration_ms",
            "job_id",
            "quiz",
        )
    }
    if storyboard:
        data["scenes"] = [
            {k: s.get(k) for k in ("layout", "headline", "narration", "fact", "facts")}
            for s in storyboard.get("scenes") or []
        ]
    doc = okf.new_doc(
        type="Learning Video",
        title=str(video.get("title") or video.get("label")),
        description="Vidéo tldoole : explication courte d'un concept, chiffres calculés par le code et cités.",
        tags=["tldoole", "video", video.get("concept_id") or "concept"],
        owners=["alphaforge-a8"],
        sensitivity="client",
        generated_by="agent:A8",
        at=clock.iso(),
        status="stable" if video.get("status") == "ready" else "draft",
        sources=list(video.get("sources") or []) + evidence_sources(client_id, video.get("evidence") or []),
        data=data,
        body="\n".join(lines),
    )
    return store.put_text(video_doc_key(client_id, video["video_id"]), okf.render(doc))


# --------------------------------------------------------------------------- vue de l'interface
class Presigner:
    """URL de lecture signées (S3) des vidéos prêtes; aucune en développement local."""

    def __init__(self, bucket: str | None, region: str, *, client: Any | None = None, expires: int = 3600):
        self.bucket = bucket
        self.region = region
        self.expires = expires
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.bucket)

    def url(self, key: str, content_type: str | None = None) -> str | None:
        if not self.enabled:
            return None
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                region_name=self.region,
                config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
            )
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": key}
        if content_type:
            params["ResponseContentType"] = content_type
        return self._client.generate_presigned_url("get_object", Params=params, ExpiresIn=self.expires)


def video_card(client_id: str, video: dict[str, Any], presigner: Presigner | None) -> dict[str, Any]:
    prefix = video_prefix(client_id, video["video_id"])
    ready = video.get("status") == "ready"
    quiz = video.get("quiz") or None
    card = {
        "video_id": video["video_id"],
        "concept_id": video.get("concept_id"),
        "label": video.get("label"),
        "title": video.get("title"),
        "status": video.get("status"),
        "level": video.get("level"),
        "locale": video.get("locale"),
        "reason": video.get("reason"),
        "version": video.get("version", 1),
        "created_at": video.get("created_at"),
        "updated_at": video.get("updated_at"),
        "duration_ms": video.get("duration_ms"),
        "why": [
            {k: e.get(k) for k in ("kind", "quote", "field", "value", "provenance", "at") if e.get(k) is not None}
            for e in video.get("evidence") or []
        ],
        "quiz": {"question": quiz["question"], "options": quiz["options"]} if quiz else None,
        "sources": video.get("sources") or [],
        "feedback": video.get("feedback"),
        "error": video.get("error"),
        "doc_key": video_doc_key(client_id, video["video_id"]),
        "video_url": None,
        "poster_url": None,
        "captions_url": None,
    }
    if presigner is not None and presigner.enabled:
        if video.get("status") in ("rendering", "ready"):
            card["poster_url"] = presigner.url(prefix + "scene-01.png", "image/png")
        if ready:
            card["video_url"] = presigner.url(prefix + "video.mp4", "video/mp4")
            card["captions_url"] = presigner.url(prefix + "captions.vtt", "text/vtt")
    return card
