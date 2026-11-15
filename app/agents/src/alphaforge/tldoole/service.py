"""Runtime ``tldoole`` : des vidéos courtes sur les concepts que l'investisseur ne comprend pas encore.

Actions (CONTRACTS.md, section 8) :

- ``detect`` (Step Functions) : A7 juge le journal du profil, crée les vidéos à produire; tâche asynchrone,
  marqueur ``clients/<id>/tldoole/runs/<run_id>/detect.json``.
- ``produce`` (Step Functions) : A8 écrit le scénario, le code dessine les écrans, Polly dit la narration;
  tâche asynchrone, marqueur ``videos/<video_id>/_produced.json`` qui porte les réglages MediaConvert.
- ``finalize`` (Step Functions) : statut final après le job MediaConvert.
- ``feed``, ``feedback``, ``request`` (interface) : le fil vidéo, le retour « compris / encore flou » et le
  quiz, la demande explicite d'une vidéo. ``feedback`` et ``request`` lancent la machine Step Functions.

Les tâches longues tournent en arrière-plan comme tâches asynchrones de ``BedrockAgentCoreApp`` (``/ping`` à
``HealthyBusy``), comme les collecteurs; ``"wait": true`` les exécute dans la requête (développement, tests).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .. import clock, okf
from ..agentkit import ModelFactory, bedrock_model_factory
from ..config import Settings
from ..errors import AppError, error_response, ok_response, pick
from ..profile.state import (
    ClientSession,
    is_client_id,
    load_journal_entries,
    portfolio_key,
)
from ..store import ConflictError, Store
from ..trace import Trace
from . import captions, feed, montage, render
from .concepts import Catalog, load_catalog
from .detector import DetectionInput, detect
from .facts import FactBook
from .signals import (
    RULE_THRESHOLD,
    investor_messages,
    latest_answers,
    merge,
    message_candidates,
    rule_candidates,
)
from .storyboard import write_storyboard
from .voice import Voice

logger = logging.getLogger("alphaforge.tldoole")
LEVELS = ("beginner", "intermediate", "advanced")
RUN_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
MAX_VERSIONS = 3
DISCLAIMERS = {
    "fr": "Simulation éducative · pas un conseil financier",
    "en": "Educational simulation · not financial advice",
}


@dataclass(frozen=True)
class TldooleSettings:
    state_machine_arn: str | None
    max_per_run: int
    max_per_day: int
    inline_produce: bool

    @classmethod
    def from_env(cls) -> TldooleSettings:
        def number(name: str, default: int) -> int:
            try:
                return max(0, int(os.environ.get(name) or default))
            except ValueError:
                return default

        return cls(
            state_machine_arn=(os.environ.get("ALPHAFORGE_TLDOOLE_STATE_MACHINE_ARN") or "").strip() or None,
            max_per_run=number("ALPHAFORGE_TLDOOLE_MAX_PER_RUN", 2),
            max_per_day=number("ALPHAFORGE_TLDOOLE_MAX_PER_DAY", 6),
            inline_produce=(os.environ.get("ALPHAFORGE_TLDOOLE_INLINE") or "").lower() in ("1", "true", "yes"),
        )


class GuardrailCheck:
    """Garde-fou du cadre responsable appliqué au texte final des vidéos (``ApplyGuardrail``, sortie)."""

    def __init__(self, settings: Settings, client: Any | None = None):
        self.guardrail_id = settings.guardrail_id
        self.version = settings.guardrail_version or "DRAFT"
        self.region = settings.region
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.guardrail_id)

    def check(self, texts: list[str], trace: Trace) -> None:
        if not self.enabled:
            return
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        with trace.step(
            "guardrail",
            "guardrail",
            trace.t("Garde-fou sur le scénario", "Guardrail on the script"),
            inputs={"texts": len(texts)},
        ) as info:
            response = self._client.apply_guardrail(
                guardrailIdentifier=self.guardrail_id,
                guardrailVersion=self.version,
                source="OUTPUT",
                content=[{"text": {"text": text[:4000]}} for text in texts if text],
            )
            action = response.get("action")
            info["outputs"] = {"action": action}
        if action == "GUARDRAIL_INTERVENED":
            raise AppError(
                "guardrail_blocked",
                trace.t(
                    "Le garde-fou a bloqué ce scénario; aucune vidéo n'est produite.",
                    "The guardrail blocked this script; no video is produced.",
                ),
            )


class TldooleService:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        app: Any | None = None,
        *,
        model_factory: ModelFactory | None = None,
        voice: Any | None = None,
        presigner: feed.Presigner | None = None,
        sfn: Any | None = None,
        guardrail: GuardrailCheck | None = None,
        kb_search: Any | None = None,
        catalog: Catalog | None = None,
        options: TldooleSettings | None = None,
    ):
        self.settings = settings
        self.store = store
        self.app = app
        self.model_factory = model_factory if model_factory is not None else bedrock_model_factory(settings)
        self.voice = voice or Voice(settings.region)
        self.presigner = presigner or feed.Presigner(
            settings.bucket if settings.store == "s3" else None, settings.region
        )
        self._sfn = sfn
        self.guardrail = guardrail or GuardrailCheck(settings)
        if kb_search is None and settings.kb_id:
            from ..profile.kb import KnowledgeSearch

            kb_search = KnowledgeSearch(settings)
        self.kb_search = kb_search
        self.catalog = catalog or load_catalog()
        self.options = options or TldooleSettings.from_env()
        self._running: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self.actions: dict[str, Callable[[dict[str, Any], Trace], dict[str, Any]]] = {
            "health": self.health,
            "detect": self.detect,
            "produce": self.produce,
            "finalize": self.finalize,
            "feed": self.feed,
            "feedback": self.feedback,
            "request": self.request,
        }

    # ------------------------------------------------------------------ enveloppe
    def handle(self, payload: Any) -> dict[str, Any]:
        release = self.settings.release
        if not isinstance(payload, dict):
            return error_response(release, AppError("bad_request", "Le corps doit être un objet JSON."))
        locale = "en" if payload.get("locale") == "en" else "fr"
        trace = Trace(locale)
        action = payload.get("action")
        handler = self.actions.get(action) if isinstance(action, str) else None
        if handler is None:
            return error_response(
                release,
                AppError(
                    "unknown_action",
                    pick(locale, f"Action inconnue : {action}.", f"Unknown action: {action}."),
                    {"action": action},
                ),
            )
        try:
            return ok_response(release, **handler(payload, trace))
        except AppError as exc:
            return error_response(release, exc)
        except ConflictError:
            return error_response(
                release,
                AppError(
                    "conflict",
                    pick(
                        locale,
                        "L'état tldoole a changé pendant la requête. Réessayez.",
                        "The tldoole state changed during the request. Try again.",
                    ),
                ),
            )
        except Exception:
            logger.exception("tldoole action failed: %s", action)
            return error_response(release, AppError("internal", pick(locale, "Erreur interne.", "Internal error.")))

    def health(self, payload: dict[str, Any], trace: Trace) -> dict[str, Any]:
        return {"role": "tldoole", "env": self.settings.env}

    # ------------------------------------------------------------------ entrées
    def _client_id(self, payload: dict[str, Any], trace: Trace) -> str:
        client_id = payload.get("client_id")
        if not is_client_id(client_id):
            raise AppError("bad_request", trace.t("client_id doit être un UUID v4.", "client_id must be a UUID v4."))
        return client_id

    def _session(self, client_id: str, trace: Trace) -> ClientSession:
        session = ClientSession.load(self.store, client_id)
        if session is None:
            raise AppError("not_found", trace.t("Client introuvable.", "Client not found."), {"client_id": client_id})
        return session

    def _run_id(self, payload: dict[str, Any], trace: Trace) -> str:
        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not 1 <= len(run_id) <= 80 or set(run_id) - RUN_ID_CHARS:
            raise AppError("bad_request", trace.t("run_id invalide.", "Invalid run_id."))
        return run_id

    def _video_id(self, payload: dict[str, Any], trace: Trace) -> str:
        video_id = payload.get("video_id")
        if not isinstance(video_id, str) or not feed.VIDEO_ID.match(video_id):
            raise AppError("bad_request", trace.t("video_id invalide.", "Invalid video_id."))
        return video_id

    # ------------------------------------------------------------------ arrière-plan
    def _spawn(
        self,
        key: str,
        marker_key: str,
        payload: dict[str, Any],
        job: Callable[[Trace], dict[str, Any]],
        *,
        locale: str,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        response = {"accepted": True, "marker": marker_key, **extra}
        if payload.get("wait") is True:
            self._background(key, marker_key, job, None, locale, extra)
            return {**response, "result": self.store.get_json(marker_key)}
        with self._lock:
            running = self._running.get(key)
            if running is not None and running.is_alive():
                return {**response, "already_running": True}
            existing = self.store.get_json(marker_key)
            if existing is not None and existing.get("status") == "ok":
                return {**response, "already_done": True}
            task_id = self.app.add_async_task(f"tldoole:{key}", extra) if self.app else None
            thread = threading.Thread(
                target=self._background,
                args=(key, marker_key, job, task_id, locale, extra),
                name=f"alphaforge-tldoole-{key}",
                daemon=True,
            )
            self._running[key] = thread
            thread.start()
        return response

    def _background(
        self,
        key: str,
        marker_key: str,
        job: Callable[[Trace], dict[str, Any]],
        task_id: int | None,
        locale: str,
        extra: dict[str, Any],
    ) -> None:
        started_at = clock.iso()
        trace = Trace(locale)
        try:
            try:
                marker = {"status": "ok", "error": None, **job(trace)}
            except AppError as exc:
                marker = {"status": "error", "error": {"code": exc.code, "message": exc.message}}
            except Exception as exc:
                logger.exception("tldoole task %s failed", key)
                marker = {"status": "error", "error": {"code": "internal", "message": f"{type(exc).__name__}"}}
            document = {
                **extra,
                **marker,
                "started_at": started_at,
                "finished_at": clock.iso(),
                "release": self.settings.release,
                "trace": trace.steps[-80:],
            }
            try:
                self.store.put_json(marker_key, document)
            except Exception:
                logger.exception("could not write tldoole marker %s", marker_key)
        finally:
            if self.app is not None and task_id is not None:
                self.app.complete_async_task(task_id)
            with self._lock:
                self._running.pop(key, None)

    def wait(self, key: str, timeout: float | None = None) -> None:
        thread = self._running.get(key)
        if thread is not None:
            thread.join(timeout)

    # ------------------------------------------------------------------ profil de l'investisseur
    def _level(self, session: ClientSession) -> str:
        values = session.values()
        level = None
        try:
            from ..profile import rules
            from ..profile.questionnaire import default_questionnaire

            level = rules.knowledge_level(default_questionnaire(), values)
        except Exception:  # le profil n'a pas encore assez de réponses
            level = None
        if level not in LEVELS:
            level = values.get("knowledge.self_assessment")
        return level if level in LEVELS else "beginner"

    def _portfolio(self, client_id: str) -> dict[str, Any] | None:
        obj = self.store.get(portfolio_key(client_id))
        if obj is None:
            return None
        try:
            view = okf.parse(obj.text).data.get("view")
        except okf.OkfError:
            return None
        if isinstance(view, dict) and view.get("status") == "confirmed" and isinstance(view.get("exposures"), dict):
            return view
        return None

    # ------------------------------------------------------------------ detect
    def detect(self, payload: dict[str, Any], trace: Trace) -> dict[str, Any]:
        client_id = self._client_id(payload, trace)
        run_id = self._run_id(payload, trace)
        session = self._session(client_id, trace)
        marker = feed.detect_marker_key(client_id, run_id)
        return self._spawn(
            f"detect:{client_id}:{run_id}",
            marker,
            payload,
            lambda t: self.run_detect(client_id, session.locale, t),
            locale=session.locale,
            extra={"client_id": client_id, "run_id": run_id},
        )

    def run_detect(self, client_id: str, locale: str, trace: Trace) -> dict[str, Any]:
        trace.locale = locale
        session = self._session(client_id, trace)
        level = self._level(session)
        with trace.step("storage", "store", trace.t("Lecture du journal", "Journal read")) as info:
            entries = load_journal_entries(self.store, client_id, limit=400)
            index = feed.load_index(self.store, client_id)
            portfolio = self._portfolio(client_id)
            info["outputs"] = {
                "entries": len(entries),
                "videos": len(index.get("videos") or []),
                "portfolio": portfolio is not None,
            }
        messages = investor_messages(entries)
        answers = latest_answers(entries)
        with trace.step("deterministic", "A7", trace.t("Signaux déterministes", "Deterministic signals")) as info:
            candidates = merge(
                [
                    *message_candidates(self.catalog, messages),
                    *rule_candidates(self.catalog, answers, portfolio, level, portfolio_key=portfolio_key(client_id)),
                ]
            )
            info["outputs"] = {c.concept_id: f"{c.rule} {c.score:.2f}" for c in candidates.values()}
        detection = index.get("detection") or {}
        seen_messages = int(detection.get("messages") or 0)
        new_refs = {m.ref for m in messages[seen_messages:]}
        seen_candidates = set(detection.get("candidates") or [])
        covered = feed.concept_state(index)

        def is_fresh(candidate) -> bool:
            from_new_message = any(e.ref in new_refs for e in candidate.evidence)
            if candidate.concept_id in covered and not from_new_message:
                return False
            return from_new_message or f"{candidate.concept_id}:{candidate.rule}" not in seen_candidates

        fresh = {k: c for k, c in candidates.items() if is_fresh(c)}
        signature = sorted(f"{c.concept_id}:{c.rule}" for c in candidates.values())
        if not fresh:
            trace.add(
                "deterministic",
                "A7",
                trace.t("Rien de nouveau depuis la dernière détection", "Nothing new since the last detection"),
            )
            feed.update_index(
                self.store,
                client_id,
                lambda ix: ix.update(
                    detection={
                        "journal_entries": len(entries),
                        "messages": len(messages),
                        "at": clock.iso(),
                        "candidates": signature,
                    }
                ),
            )
            return {"client_id": client_id, "video_ids": [], "gaps": [], "skipped": "no_new_signal"}

        data = DetectionInput(self.catalog, locale, level, messages[-12:], fresh, covered)
        gaps = detect(data, model_factory=self.model_factory, model_id=self.settings.model_id, trace=trace)
        new_message_refs = new_refs

        def decide(index: dict[str, Any]) -> list[str]:
            created: list[str] = []
            states = feed.concept_state(index)
            budget_day = self.options.max_per_day - feed.videos_today(index)
            for gap in sorted(gaps, key=lambda g: g.confidence, reverse=True):
                concept = self.catalog.get(gap.concept_id)
                record = index.setdefault("gaps", {}).get(gap.concept_id) or {"detected_at": clock.iso()}
                record.update(gap.to_dict(), updated_at=clock.iso())
                record.setdefault("status", "open")
                index["gaps"][gap.concept_id] = record
                state = states.get(gap.concept_id)
                renewed = any(e.get("ref") in new_message_refs for e in gap.evidence)
                if gap.confidence < RULE_THRESHOLD or concept is None:
                    continue
                if state == "in_progress" or (state in ("ready", "understood", "unclear") and not renewed):
                    continue
                if len(created) >= self.options.max_per_run or budget_day - len(created) <= 0:
                    record["status"] = "waiting"
                    continue
                versions = [v for v in index.get("videos") or [] if v.get("concept_id") == gap.concept_id]
                video = feed.new_video(
                    concept_id=gap.concept_id,
                    label=concept.text("label", locale),
                    title=concept.text("title", locale),
                    level=level,
                    locale=locale,
                    reason="detected",
                    evidence=gap.evidence,
                    version=len(versions) + 1,
                    simpler=bool(versions),
                )
                index.setdefault("videos", []).insert(0, video)
                record["status"] = "video"
                record["video_id"] = video["video_id"]
                created.append(video["video_id"])
            index["detection"] = {
                "journal_entries": len(entries),
                "messages": len(messages),
                "at": clock.iso(),
                "candidates": signature,
            }
            return created

        with trace.step("storage", "store", trace.t("Lacunes et vidéos enregistrées", "Gaps and videos saved")) as info:
            index, created = feed.update_index(self.store, client_id, decide)
            feed.write_gaps_doc(self.store, client_id, index, self.catalog, locale)
            info["outputs"] = {"gaps": [g.concept_id for g in gaps], "videos": created}
        return {"client_id": client_id, "video_ids": created, "gaps": [g.to_dict() for g in gaps]}

    # ------------------------------------------------------------------ produce
    def produce(self, payload: dict[str, Any], trace: Trace) -> dict[str, Any]:
        client_id = self._client_id(payload, trace)
        video_id = self._video_id(payload, trace)
        index = feed.load_index(self.store, client_id)
        video = feed.find_video(index, video_id)
        if video is None:
            raise AppError("not_found", trace.t("Vidéo introuvable.", "Video not found."), {"video_id": video_id})
        marker = feed.produced_marker_key(client_id, video_id)
        return self._spawn(
            f"produce:{client_id}:{video_id}",
            marker,
            payload,
            lambda t: self.run_produce(client_id, video_id, t),
            locale=video.get("locale") or "fr",
            extra={"client_id": client_id, "video_id": video_id},
        )

    def run_produce(self, client_id: str, video_id: str, trace: Trace) -> dict[str, Any]:
        index, video = feed.update_index(
            self.store, client_id, lambda ix: feed.set_video(ix, video_id, status="scripting", error=None)
        )
        if video is None:
            raise AppError("not_found", "Vidéo introuvable.", {"video_id": video_id})
        try:
            return self._produce(client_id, video, index, trace)
        except AppError as exc:
            self._fail(client_id, video_id, exc.code, exc.message)
            raise
        except Exception as exc:
            self._fail(client_id, video_id, "internal", type(exc).__name__)
            raise

    def _fail(self, client_id: str, video_id: str, code: str, message: str) -> None:
        try:
            index, video = feed.update_index(
                self.store,
                client_id,
                lambda ix: feed.set_video(
                    ix, video_id, status="failed", error={"code": code, "message": message[:300]}
                ),
            )
            if video:
                feed.write_video_doc(self.store, client_id, video, None)
        except Exception:
            logger.exception("could not mark video %s failed", video_id)

    def _produce(self, client_id: str, video: dict[str, Any], index: dict[str, Any], trace: Trace) -> dict[str, Any]:
        locale = video.get("locale") or "fr"
        trace.locale = locale
        concept = self.catalog.get(video["concept_id"])
        if concept is None:
            raise AppError("bad_request", trace.t("Concept inconnu.", "Unknown concept."))
        portfolio = self._portfolio(client_id)
        facts = FactBook(locale, client_portfolio=portfolio, client_portfolio_key=portfolio_key(client_id))
        previous = [
            v.get("title")
            for v in index.get("videos") or []
            if v.get("concept_id") == concept.id and v.get("video_id") != video["video_id"]
        ]
        result = write_storyboard(
            concept,
            locale=locale,
            level=video.get("level") or "beginner",
            evidence=video.get("evidence") or [],
            facts=facts,
            has_portfolio=portfolio is not None,
            simpler=bool(video.get("simpler")),
            previous_headlines=[p for p in previous if p],
            model_factory=self.model_factory,
            model_id=self.settings.model_id,
            trace=trace,
            kb_search=self.kb_search,
        )
        board = result.storyboard
        scenes = board["scenes"]
        self.guardrail.check([s["narration"] for s in scenes] + [board["quiz"]["question"]], trace)
        feed.update_index(
            self.store,
            client_id,
            lambda ix: feed.set_video(ix, video["video_id"], status="rendering", title=board["title"]),
        )

        with trace.step(
            "tool",
            "polly",
            trace.t("Narration Polly", "Polly narration"),
            inputs={"scenes": len(scenes), "locale": locale},
        ) as info:
            narration = self.voice.narrate([s["narration"] for s in scenes], locale)
            info["outputs"] = {
                "voice": narration.voice,
                "duration_ms": narration.duration_ms,
                "words": len(narration.words),
            }
        prefix = feed.video_prefix(client_id, video["video_id"])
        image_keys = [f"{prefix}scene-{i:02d}.png" for i in range(1, len(scenes) + 1)]
        placements, total_ms = montage.placements(image_keys, narration.scene_starts_ms, narration.duration_ms)
        cues = captions.build_cues(narration.words, total_ms=total_ms)
        frame = render.Frame(
            concept_label=concept.text("label", locale),
            locale=locale,
            accent=concept.accent,
            disclaimer=DISCLAIMERS.get(locale, DISCLAIMERS["fr"]),
        )
        with trace.step(
            "deterministic",
            "A8",
            trace.t("Écrans dessinés par le code", "Screens drawn by code"),
            inputs={"scenes": len(scenes)},
        ) as info:
            pngs = [
                render.render_scene(scene, frame, index=i, total=len(scenes)) for i, scene in enumerate(board["render"])
            ]
            info["outputs"] = {"bytes": sum(len(p) for p in pngs)}
        storyboard_json = {k: v for k, v in board.items() if k != "render"}
        storyboard_json["timing"] = {"scene_starts_ms": narration.scene_starts_ms, "total_ms": total_ms}
        with trace.step(
            "storage", "store", trace.t("Éléments de la vidéo écrits", "Video assets written"), prefix
        ) as info:
            for key, png in zip(image_keys, pngs, strict=True):
                self.store.put(key, png, content_type="image/png")
            self.store.put(prefix + "background.png", render.background_png(), content_type="image/png")
            self.store.put(prefix + "narration.mp3", narration.audio, content_type="audio/mpeg")
            self.store.put_text(prefix + "captions.srt", captions.to_srt(cues), content_type="application/x-subrip")
            self.store.put_text(prefix + "captions.vtt", captions.to_vtt(cues), content_type="text/vtt")
            self.store.put(prefix + "caption-font.ttf", render.FONT_BOLD.read_bytes(), content_type="font/ttf")
            self.store.put_json(prefix + "storyboard.json", storyboard_json)
            info["outputs"] = {"objects": len(image_keys) + 6}

        settings = None
        if self.settings.store == "s3" and self.settings.bucket:
            settings = montage.job_settings(
                bucket=self.settings.bucket,
                background_key=prefix + "background.png",
                audio_key=prefix + "narration.mp3",
                captions_key=prefix + "captions.srt",
                scenes=placements,
                total_ms=total_ms,
                output_key_base=prefix + "video",
                caption_font_key=prefix + "caption-font.ttf",
            )
        sources = board["sources"] + self.catalog.source_entries(concept)

        def finish(ix: dict[str, Any]) -> dict[str, Any] | None:
            return feed.set_video(
                ix,
                video["video_id"],
                status="rendering",
                title=board["title"],
                duration_ms=total_ms,
                quiz=board["quiz"],
                sources=sources,
            )

        _, updated = feed.update_index(self.store, client_id, finish)
        if updated:
            feed.write_video_doc(self.store, client_id, updated, storyboard_json)
        trace.add(
            "deterministic",
            "mediaconvert",
            trace.t("Réglages du montage prêts", "Montage settings ready"),
            None,
            outputs={
                "inputs": 1,
                "images": len(placements),
                "duration_ms": total_ms,
                "available": settings is not None,
            },
        )
        return {
            "client_id": client_id,
            "video_id": video["video_id"],
            "duration_ms": total_ms,
            "settings": settings,
            "output_key": prefix + "video.mp4",
        }

    # ------------------------------------------------------------------ finalize
    def finalize(self, payload: dict[str, Any], trace: Trace) -> dict[str, Any]:
        client_id = self._client_id(payload, trace)
        video_id = self._video_id(payload, trace)
        job = payload.get("job") if isinstance(payload.get("job"), dict) else {}
        status = str(job.get("status") or "").upper()
        if status == "COMPLETE":
            duration = job.get("duration_ms")
            fields: dict[str, Any] = {"status": "ready", "error": None, "job_id": job.get("id")}
            if isinstance(duration, int) and duration > 0:
                fields["duration_ms"] = duration
        else:
            message = str(job.get("error") or status or "échec du montage")[:300]
            fields = {
                "status": "failed",
                "error": {"code": "render_failed", "message": message},
                "job_id": job.get("id"),
            }

        def apply(index: dict[str, Any]) -> dict[str, Any] | None:
            video = feed.find_video(index, video_id)
            if video is None or video.get("status") == "ready":
                return video
            if video.get("status") == "failed" and fields["status"] == "failed":
                return video
            return feed.set_video(index, video_id, **fields)

        _, video = feed.update_index(self.store, client_id, apply)
        if video is None:
            raise AppError("not_found", trace.t("Vidéo introuvable.", "Video not found."), {"video_id": video_id})
        storyboard = self.store.get_json(feed.video_prefix(client_id, video_id) + "storyboard.json")
        feed.write_video_doc(self.store, client_id, video, storyboard)
        trace.add(
            "storage",
            "store",
            trace.t("Vidéo finalisée", "Video finalised"),
            video_id,
            outputs={"status": video.get("status")},
        )
        return {
            "client_id": client_id,
            "video": feed.video_card(client_id, video, self.presigner),
            "trace": trace.steps,
        }

    # ------------------------------------------------------------------ interface
    def feed(self, payload: dict[str, Any], trace: Trace) -> dict[str, Any]:
        client_id = self._client_id(payload, trace)
        session = self._session(client_id, trace)
        trace.locale = session.locale
        index = feed.load_index(self.store, client_id)
        videos = [feed.video_card(client_id, v, self.presigner) for v in index.get("videos") or []]
        gaps = []
        for gap in (index.get("gaps") or {}).values():
            concept = self.catalog.get(gap.get("concept_id"))
            gaps.append(
                {
                    "concept_id": gap.get("concept_id"),
                    "label": concept.text("label", session.locale) if concept else gap.get("concept_id"),
                    "status": gap.get("status"),
                    "confidence": gap.get("confidence"),
                    "reason": gap.get("reason"),
                    "detector": gap.get("detector"),
                    "video_id": gap.get("video_id"),
                    "detected_at": gap.get("detected_at"),
                }
            )
        catalog = [
            {"concept_id": c.id, "label": c.text("label", session.locale), "title": c.text("title", session.locale)}
            for c in self.catalog.concepts.values()
        ]
        return {
            "client_id": client_id,
            "locale": session.locale,
            "videos": videos,
            "gaps": sorted(gaps, key=lambda g: g.get("detected_at") or "", reverse=True),
            "pending": sum(1 for v in videos if v["status"] in feed.ACTIVE),
            "catalog": catalog,
        }

    def _start_execution(self, client_id: str, video_ids: list[str], source: str, trace: Trace) -> str | None:
        arn = self.options.state_machine_arn
        if not arn:
            if self.options.inline_produce:
                for video_id in video_ids:
                    self.produce({"client_id": client_id, "video_id": video_id}, trace)
                return None
            trace.add(
                "deterministic",
                "A8",
                trace.t(
                    "Machine Step Functions absente : vidéo en attente", "No Step Functions machine: video stays queued"
                ),
            )
            return None
        if self._sfn is None:
            import boto3

            self._sfn = boto3.client("stepfunctions", region_name=self.settings.region)
        name = f"{source}-{video_ids[0]}"[:80]
        with trace.step(
            "tool", "A8", trace.t("Production lancée (Step Functions)", "Production started (Step Functions)"), name
        ) as info:
            response = self._sfn.start_execution(
                stateMachineArn=arn,
                name=name,
                input=json.dumps({"source": source, "client_id": client_id, "video_ids": video_ids}),
            )
            info["outputs"] = {"execution": response.get("executionArn", "").rsplit(":", 1)[-1]}
        return response.get("executionArn")

    def request(self, payload: dict[str, Any], trace: Trace) -> dict[str, Any]:
        client_id = self._client_id(payload, trace)
        session = self._session(client_id, trace)
        locale = session.locale
        trace.locale = locale
        concept = self.catalog.get(payload.get("concept_id"))
        if concept is None:
            raise AppError(
                "bad_request",
                trace.t("concept_id inconnu.", "Unknown concept_id."),
                {"concept_ids": self.catalog.ids()},
            )
        level = self._level(session)

        def add(index: dict[str, Any]) -> tuple[dict[str, Any], bool]:
            active = next(
                (
                    v
                    for v in index.get("videos") or []
                    if v.get("concept_id") == concept.id and v.get("status") in feed.ACTIVE
                ),
                None,
            )
            if active:
                return active, False
            if feed.videos_today(index) >= self.options.max_per_day:
                raise AppError(
                    "conflict",
                    trace.t(
                        "Limite quotidienne de vidéos atteinte. Revenez demain.",
                        "Daily video limit reached. Come back tomorrow.",
                    ),
                )
            versions = [v for v in index.get("videos") or [] if v.get("concept_id") == concept.id]
            video = feed.new_video(
                concept_id=concept.id,
                label=concept.text("label", locale),
                title=concept.text("title", locale),
                level=level,
                locale=locale,
                reason="request",
                evidence=[{"kind": "request", "provenance": "tldoole:request", "at": clock.iso()}],
                version=len(versions) + 1,
                simpler=False,
            )
            index.setdefault("videos", []).insert(0, video)
            return video, True

        _, (video, created) = feed.update_index(self.store, client_id, add)
        if created:
            self._start_execution(client_id, [video["video_id"]], "request", trace)
        return {
            "client_id": client_id,
            "video": feed.video_card(client_id, video, self.presigner),
            "created": created,
            "trace": trace.steps,
        }

    def feedback(self, payload: dict[str, Any], trace: Trace) -> dict[str, Any]:
        client_id = self._client_id(payload, trace)
        video_id = self._video_id(payload, trace)
        session = self._session(client_id, trace)
        locale = session.locale
        trace.locale = locale
        verdict = payload.get("verdict")
        quiz_answer = payload.get("quiz_answer")
        if verdict is not None and verdict not in feed.VERDICTS:
            raise AppError(
                "bad_request", trace.t("verdict : understood ou unclear.", "verdict: understood or unclear.")
            )
        if quiz_answer is not None and (not isinstance(quiz_answer, int) or isinstance(quiz_answer, bool)):
            raise AppError("bad_request", trace.t("quiz_answer est un indice.", "quiz_answer is an index."))
        if verdict is None and quiz_answer is None:
            raise AppError(
                "bad_request", trace.t("verdict ou quiz_answer est requis.", "verdict or quiz_answer is required.")
            )

        def apply(index: dict[str, Any]) -> dict[str, Any]:
            video = feed.find_video(index, video_id)
            if video is None:
                raise AppError("not_found", trace.t("Vidéo introuvable.", "Video not found."))
            quiz = video.get("quiz") or {}
            outcome: dict[str, Any] = {"video": video, "quiz": None, "follow_up": None}
            correct = None
            if quiz_answer is not None and quiz:
                if not 0 <= quiz_answer < len(quiz.get("options") or []):
                    raise AppError("invalid_answer", trace.t("Option de quiz inconnue.", "Unknown quiz option."))
                correct = quiz_answer == quiz.get("answer")
                outcome["quiz"] = {
                    "correct": correct,
                    "answer": quiz.get("answer"),
                    "explanation": quiz.get("explanation"),
                }
            final = verdict or ("understood" if correct else "unclear")
            video["feedback"] = {"verdict": final, "quiz_answer": quiz_answer, "correct": correct, "at": clock.iso()}
            video["updated_at"] = clock.iso()
            gap = (index.get("gaps") or {}).get(video.get("concept_id"))
            if gap is not None:
                gap["status"] = "resolved" if final == "understood" else "unclear"
                gap["updated_at"] = clock.iso()
            if final == "unclear":
                versions = [v for v in index.get("videos") or [] if v.get("concept_id") == video.get("concept_id")]
                active = any(v.get("status") in feed.ACTIVE for v in versions)
                if not active and len(versions) < MAX_VERSIONS and feed.videos_today(index) < self.options.max_per_day:
                    concept = self.catalog.get(video.get("concept_id"))
                    level = video.get("level") or "beginner"
                    simpler_level = LEVELS[max(0, LEVELS.index(level) - 1)] if level in LEVELS else "beginner"
                    follow = feed.new_video(
                        concept_id=video["concept_id"],
                        label=video.get("label") or video["concept_id"],
                        title=concept.text("title", locale) if concept else video.get("title") or "",
                        level=simpler_level,
                        locale=locale,
                        reason="feedback",
                        evidence=[
                            *(video.get("evidence") or [])[:2],
                            {
                                "kind": "feedback",
                                "provenance": f"tldoole:{video_id}",
                                "at": clock.iso(),
                                "value": "unclear",
                            },
                        ],
                        version=len(versions) + 1,
                        simpler=True,
                    )
                    index["videos"].insert(0, follow)
                    outcome["follow_up"] = follow
            return outcome

        _, outcome = feed.update_index(self.store, client_id, apply)
        follow = outcome["follow_up"]
        if follow is not None:
            self._start_execution(client_id, [follow["video_id"]], "feedback", trace)
        return {
            "client_id": client_id,
            "video": feed.video_card(client_id, outcome["video"], self.presigner),
            "quiz": outcome["quiz"],
            "follow_up": feed.video_card(client_id, follow, self.presigner) if follow else None,
            "trace": trace.steps,
        }
