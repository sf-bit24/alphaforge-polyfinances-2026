"""Runtime ``portfolio`` : portefeuille simulé d'un client (étape 0, A3, lentilles, Judge du volet finance).

Service mince autour de ``alphaforge.finance.debate`` (pipeline et ``okf_bridge``), qui reste la propriété du volet
finance. Le moteur (numpy, pandas, scipy, cvxpy) n'est importé qu'à la première action ``build`` : les autres runtimes
partagent ce code sans jamais charger le groupe de dépendances ``finance``, et ``health`` répond sans lui.

Actions (enveloppe de CONTRACTS.md, section 2) :
- ``{"action": "health"}``;
- ``{"action": "build", "client_id", "as_of"?: "AAAA-MM-JJ", "strategy"?: bool (vrai par défaut),
  "style_preference"?: "defensive" | "dynamique" | "offensive", "request"?: {"ticker", "amount_cad"?, "weight"?},
  "mode"?: "llm" | "rules", "locale"?: "fr" | "en"}`` (CONTRACTS.md, section 12).
  Le profil est lu dans ``clients/<client_id>/profil.md``; la décision est écrite sous
  ``clients/<client_id>/decisions/``. Avec ``strategy``, l'étape 0 lit ses variables dans le profil court
  (``style_inputs_from_view``), comme ``finance/debate/app.py``.
Simulation seulement : aucune transaction, aucun conseil personnalisé.

Knowledge Base du client (``profile/client_kb.py``) : le magasin est enveloppé comme dans le runtime ``profile``.
Après ``build`` (``decisions/<id>.md``) et après une tâche d'évolution (``portefeuilles/*.md``), les documents écrits
sont ingérés si la base du client est active, sinon gardés en attente. Ce runtime ne crée jamais de Knowledge Base.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import tempfile
import threading
from collections.abc import Callable
from datetime import date
from typing import Any

from .config import Settings
from .errors import AppError, error_response, ok_response, pick
from .profile.client_kb import ClientKnowledgeBases
from .store import ConflictError, Store

logger = logging.getLogger("alphaforge.portfolio")

# Évolution du portefeuille dans le temps (finance/evolution/actions.py, machine Step Functions evolution.tf)
EVOLUTION_ACTIONS = ("evolution.tick", "evolution.replay", "evolution.replay_summary")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MODES = ("llm", "rules")
LOCALES = ("fr", "en")
REQUEST_KEYS = {"ticker", "amount_cad", "weight"}
# Messages à l'investisseur : jamais de chemin, de paquet ni de champ technique (gardés dans ``details``).
BAD_REQUEST_FR = "Votre demande n'a pas pu être lue. Rechargez la page, puis réessayez."
BAD_REQUEST_EN = "Your request could not be read. Reload the page, then try again."
UNAVAILABLE_FR = "Le service ne répond pas pour l'instant : réessayez dans un instant."
UNAVAILABLE_EN = "The service is not answering right now: try again in a moment."
ENGINE_DOWN_FR = "Le simulateur ne répond pas pour l'instant : réessayez dans un instant."
ENGINE_DOWN_EN = "The simulator is not answering right now: try again in a moment."


class FinanceEngine:
    """Accès paresseux au moteur du volet finance (importé au premier ``build``, une seule fois)."""

    def __init__(self, store: Store | None = None) -> None:
        self._lock = threading.Lock()
        self._loaded: dict[str, Any] | None = None
        self._store = store

    def load(self) -> dict[str, Any]:
        with self._lock:
            if self._loaded is None:
                try:
                    # Dépendances du groupe finance d'abord : sans elles (zip commun), l'erreur doit le dire, même si
                    # les données longues manquent aussi. Ces imports ne lisent pas encore ALPHAFORGE_BT_DATA.
                    import cvxpy  # noqa: F401
                    import numpy  # noqa: F401
                    import pandas  # noqa: F401
                except ImportError as exc:
                    raise self._missing_engine(exc) from exc
                if self._store is not None:
                    # Données longues (parquets non versionnés, absents du zip) : déposées sous runtime/data/long/
                    # par scripts/finance/upload_long_data.py. ALPHAFORGE_BT_DATA doit être posé AVANT le premier
                    # import du moteur (backtest.data lit ce chemin une seule fois).
                    from .finance.debate.longdata import LongDataError, ensure_long_data

                    try:
                        ensure_long_data(self._store)
                    except LongDataError as exc:
                        logger.error("long data unavailable: %s", exc)
                        raise AppError(
                            "internal", ENGINE_DOWN_FR, {"detail": str(exc), "path": "runtime/data/long/"}
                        ) from exc
                try:
                    from .finance.debate import okf_bridge, pipeline
                    from .finance.observability import telemetry
                    from .finance.policy.from_profile_view import style_inputs_from_view
                    from .finance.strategy import STYLES
                except ImportError as exc:
                    raise self._missing_engine(exc) from exc

                try:
                    # Traces OpenTelemetry : X-Ray si ALPHAFORGE_OTLP_XRAY=1 (posée par Terraform). Idempotent.
                    telemetry.setup()
                except Exception:  # la télémétrie ne doit jamais empêcher une simulation
                    logger.exception("telemetry setup failed")
                self._loaded = {
                    "pipeline": pipeline,
                    "okf_bridge": okf_bridge,
                    "telemetry": telemetry,
                    "style_inputs_from_view": style_inputs_from_view,
                    "styles": tuple(STYLES),
                }
            return self._loaded

    @staticmethod
    def _missing_engine(exc: ImportError) -> AppError:
        # Zip commun (sans le groupe finance) : Terraform s'y replie si agents-portfolio.zip manque.
        logger.error("finance engine unavailable: %s", exc)
        return AppError(
            "internal", ENGINE_DOWN_FR, {"missing_module": exc.name, "expected_package": "agents-portfolio.zip"}
        )


class PortfolioService:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        app: Any | None = None,
        *,
        engine: Callable[[], dict[str, Any]] | None = None,
        client_kb: ClientKnowledgeBases | None = None,
    ):
        self.settings = settings
        # Ingestion dans la Knowledge Base du client, jamais de création : magasin enveloppé si elle est configurée.
        self.client_kb = client_kb or ClientKnowledgeBases.from_settings(settings, store, can_create=False)
        self.store = self.client_kb.wrap(store)
        self.app = app
        self._engine = engine or FinanceEngine(store).load
        self._questionnaire: Any | None = None
        self._evolution_threads: dict[str, threading.Thread] = {}

    def handle(self, payload: Any) -> dict[str, Any]:
        release = self.settings.release
        locale = payload.get("locale") if isinstance(payload, dict) and payload.get("locale") in LOCALES else "fr"
        try:
            if not isinstance(payload, dict):
                raise AppError("bad_request", BAD_REQUEST_FR)
            action = payload.get("action")
            if not isinstance(action, str) or not action:
                raise AppError("bad_request", pick(locale, BAD_REQUEST_FR, BAD_REQUEST_EN))
            if action == "health":
                return ok_response(release, role=self.settings.role, env=self.settings.env)
            if action in EVOLUTION_ACTIONS:
                return self._evolution(action, payload, release)
            if action != "build":
                raise AppError(
                    "unknown_action",
                    pick(locale, BAD_REQUEST_FR, BAD_REQUEST_EN),
                    {"action": action, "expected": ["build", "health", *EVOLUTION_ACTIONS]},
                )
            return ok_response(release, **self.build(payload, locale))
        except AppError as exc:
            return error_response(release, exc)
        except ConflictError:
            return error_response(
                release,
                AppError(
                    "conflict",
                    pick(
                        locale,
                        "Une autre simulation a été enregistrée au même moment. Réessayez.",
                        "Another simulation was saved at the same moment. Try again.",
                    ),
                ),
            )
        except Exception as exc:
            logger.exception("portfolio build failed")
            if type(exc).__module__.split(".")[0] in ("botocore", "boto3", "strands"):
                return error_response(
                    release,
                    AppError(
                        "model_error",
                        pick(locale, UNAVAILABLE_FR, UNAVAILABLE_EN),
                        {"type": type(exc).__name__},
                    ),
                )
            return error_response(release, AppError("internal", pick(locale, UNAVAILABLE_FR, UNAVAILABLE_EN)))

    # ------------------------------------------------------------------ évolution dans le temps
    def _evolution(self, action: str, payload: dict[str, Any], release: str) -> dict[str, Any]:
        """Actions ``evolution.*`` (``finance/evolution/actions.py``), appelées par la machine ``<prefix>-evolution``.

        ``replay_summary`` répond tout de suite. ``tick`` et ``replay`` (plusieurs minutes) sont acceptés aussitôt,
        puis exécutés en tâche asynchrone de ``BedrockAgentCoreApp`` (``/ping`` à ``HealthyBusy``) ; leur résultat
        est le marqueur ``staging/<run_id>/evolution/.../_done.json`` que la machine sonde (même modèle que la
        collecte). Le moteur et les données longues sont chargés avant, dans la tâche.
        """
        if action == "evolution.replay_summary":
            from .finance.evolution import actions

            return {"release": release, **actions.handle_replay_summary(payload, store=self.store)}
        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise AppError("bad_request", "run_id est requis.", {"field": "run_id"})
        task_id = self.app.add_async_task(f"portfolio:{action}:{run_id}", {"run_id": run_id}) if self.app else None
        thread = threading.Thread(target=self._evolution_job, args=(action, dict(payload), task_id),
                                  name=f"evolution-{run_id}", daemon=True)
        thread.start()
        self._evolution_threads[run_id] = thread
        return ok_response(release, accepted=True, action=action, run_id=run_id, simulation_only=True)

    def _evolution_job(self, action: str, payload: dict[str, Any], task_id: int | None) -> None:
        try:
            self._engine()      # dépendances finance et données longues (ALPHAFORGE_BT_DATA) avant le moteur
            from .finance.evolution import actions

            handler = actions.handle_tick if action == "evolution.tick" else actions.handle_replay
            out = handler(payload, store=self.store)
            if not out.get("ok"):
                logger.warning("evolution %s %s : %s", action, payload.get("run_id"), out.get("error"))
            self.client_kb.sync_noted()  # portefeuilles/*.md écrits par la tâche : ingérés si la base est active
        except Exception:  # noqa: BLE001 - la tâche de fond ne doit jamais tuer le runtime ; le marqueur dit l'échec
            logger.exception("evolution %s failed", action)
            try:
                from .finance.evolution import actions

                actions.write_error_marker(payload, self.store, "internal", "échec de la tâche d'évolution")
            except Exception:  # noqa: BLE001
                logger.exception("evolution error marker failed")
        finally:
            if task_id is not None and self.app is not None:
                self.app.complete_async_task(task_id)

    def wait_evolution(self, run_id: str, timeout: float | None = None) -> None:
        """Attend la fin d'une tâche d'évolution (tests)."""
        thread = self._evolution_threads.get(run_id)
        if thread is not None:
            thread.join(timeout)

    # ------------------------------------------------------------------ build
    def _parse(self, payload: dict[str, Any], locale: str) -> dict[str, Any]:
        from .profile.state import is_client_id

        def bad(fr: str, en: str, **details: Any) -> AppError:
            # Demande mal formée par l'interface, jamais par l'investisseur : le motif reste dans ``details``.
            return AppError("bad_request", pick(locale, BAD_REQUEST_FR, BAD_REQUEST_EN), {"reason": en, **details})

        client_id = payload.get("client_id")
        persona = payload.get("persona")
        if persona is not None:
            from .finance.personas import ids as persona_ids

            if client_id is not None:
                raise bad("client_id ou persona, pas les deux.", "client_id or persona, not both.")
            if persona not in persona_ids():
                raise bad("persona inconnu.", "Unknown persona.", allowed=persona_ids())
        elif not is_client_id(client_id):
            raise bad("client_id doit être un UUID v4.", "client_id must be a UUID v4.")
        as_of = payload.get("as_of")
        if as_of is not None:
            try:
                if not isinstance(as_of, str) or not DATE.match(as_of):
                    raise ValueError(as_of)
                as_of = date.fromisoformat(as_of)
            except ValueError as exc:
                raise bad("as_of doit être une date AAAA-MM-JJ.", "as_of must be a YYYY-MM-DD date.") from exc
        mode = payload.get("mode", "llm")
        if mode not in MODES:
            raise bad("mode vaut llm ou rules.", "mode must be llm or rules.", allowed=list(MODES))
        strategy = payload.get("strategy", True)
        if not isinstance(strategy, bool):
            raise bad("strategy est un booléen.", "strategy must be a boolean.")
        style = payload.get("style_preference")
        if style is not None and not isinstance(style, str):
            raise bad("style_preference est une chaîne.", "style_preference must be a string.")
        request = payload.get("request")
        if request is not None:
            if (
                not isinstance(request, dict)
                or set(request) - REQUEST_KEYS
                or not isinstance(request.get("ticker"), str)
                or not request["ticker"].strip()
                or any(
                    request.get(k) is not None
                    and (isinstance(request[k], bool) or not isinstance(request[k], int | float))
                    for k in ("amount_cad", "weight")
                )
            ):
                raise bad(
                    "request vaut {ticker, amount_cad?, weight?}.",
                    "request must be {ticker, amount_cad?, weight?}.",
                    allowed=sorted(REQUEST_KEYS),
                )
        return {
            "client_id": client_id,
            "persona": persona,
            "as_of": as_of,
            "mode": mode,
            "strategy": strategy,
            "style": style,
            "request": request,
        }

    def build(self, payload: dict[str, Any], locale: str) -> dict[str, Any]:
        args = self._parse(payload, locale)
        try:
            engine = self._engine()
        except AppError as exc:
            # Le moteur écrit son message en français : il suit ici la langue de la demande.
            raise AppError(exc.code, pick(locale, ENGINE_DOWN_FR, ENGINE_DOWN_EN), exc.details) from exc
        pipeline, bridge = engine["pipeline"], engine["okf_bridge"]
        styles = engine["styles"]
        if args["style"] is not None and args["style"] not in styles:
            raise AppError(
                "bad_request",
                pick(locale, BAD_REQUEST_FR, BAD_REQUEST_EN),
                {"reason": "Unknown style_preference.", "allowed": list(styles)},
            )
        if self._questionnaire is None:
            from .profile.questionnaire import Questionnaire

            self._questionnaire = Questionnaire.load()
        client_store = bridge.OkfClientStore(self.store, self._questionnaire, locale=locale)
        market_store = bridge.OkfMarketStore(self.store)
        persona_label = None
        if args["persona"]:
            # Persona FICTION de démonstration : profil de test du moteur, variables de style de demo.yaml.
            from .finance.personas import load as load_persona

            profile, style_inputs, demo_request, persona_label = load_persona(args["persona"])
            if args["request"] is None and demo_request:
                args["request"] = demo_request
            if not args["strategy"]:
                style_inputs = None
            args["client_id"] = profile.profile_id
        else:
            try:
                profile = client_store.load_profile(args["client_id"])
            except KeyError as exc:
                raise AppError(
                    "not_found",
                    pick(
                        locale,
                        "Nous ne trouvons pas votre profil. Rechargez la page, puis réessayez.",
                        "We cannot find your profile. Reload the page, then try again.",
                    ),
                ) from exc
            # Portefeuille existant lu avec le profil : sa clé et son ETag entrent dans la version des données.
            market_store.note_client_inputs(client_store.inputs)
            # Étape 0 : variables de style du profil court, lues comme dans finance/debate/app.py.
            style_inputs = None
            if args["strategy"]:
                style_inputs = engine["style_inputs_from_view"](client_store.view(args["client_id"])[0])
        as_of = args["as_of"] or pipeline.DEFAULT_AS_OF
        telemetry = engine.get("telemetry")
        try:
            # Span racine : les outils du moteur (optimize, judge.check, strategy.select…) et l'audit
            # partagent une seule trace X-Ray, que la décision enregistrée cite (audit.otel_trace_id).
            with self._root_span(telemetry, profile_id=args["client_id"], persona=args["persona"], mode=args["mode"]):
                trace_id = self._trace_id(telemetry)
                result = pipeline.build_portfolio(
                    profile,
                    as_of,
                    request=pipeline.Request(**args["request"]) if args["request"] else None,
                    mode=args["mode"],
                    evidence_fn=market_store.evidence,
                    guardrail_id=self.settings.guardrail_id,
                    guardrail_version=self.settings.guardrail_version,
                    strategy=args["strategy"],
                    style_preference=args["style"],
                    style_inputs=style_inputs,
                    # Source de l'ancrage Guardrails de l'explication (lue seulement si un guardrail est posé).
                    grounding_docs=market_store.methodology() if self.settings.guardrail_id else (),
                )
                decision_key = client_store.save_decision(result.decision, result.policy)
                audit = self._audit(result.decision)
            # decisions/<id>.md dans la Knowledge Base du client : jamais une erreur pour l'investisseur.
            client_kb = None if args["persona"] else self.client_kb.sync(args["client_id"], None)
        finally:
            if telemetry is not None:
                try:
                    telemetry.flush()  # après la fermeture du span racine, pour qu'il soit exporté
                except Exception:
                    logger.exception("telemetry flush failed")
        return {
            "client_id": args["client_id"],
            "persona": args["persona"],
            "persona_label": persona_label,
            "fiction": bool(args["persona"]),
            "audit": audit,
            "xray_trace_id": xray_trace_id(trace_id),
            "as_of": as_of.isoformat(),
            "mode": args["mode"],
            "simulation_only": True,
            "decision_key": decision_key,
            "decision": result.decision.model_dump(mode="json"),
            "rounds": [
                {
                    "round": r.round,
                    "verdicts": r.verdicts,
                    "amendments": [a.model_dump(mode="json") for a in r.decisions],
                }
                for r in result.rounds
            ],
            "explanation_report": result.explanation_report,
            "grounding": result.grounding,
            "client_kb": client_kb,
            "strategy": result.strategy.summary() if result.strategy is not None else None,
            "allocation": result.allocation,
        }

    @staticmethod
    def _root_span(telemetry: Any, **attrs: Any) -> contextlib.AbstractContextManager[Any]:
        span = getattr(telemetry, "span", None)
        if span is None:
            return contextlib.nullcontext()
        try:
            return span("portfolio.build", **attrs)
        except Exception:  # la télémétrie ne doit jamais empêcher une simulation
            logger.exception("root span failed")
            return contextlib.nullcontext()

    @staticmethod
    def _trace_id(telemetry: Any) -> str | None:
        current_ids = getattr(telemetry, "current_ids", None)
        return current_ids()[0] if current_ids is not None else None

    def _audit(self, decision: Any) -> dict[str, Any] | None:
        """Chaîne d'audit (finance/observability/audit.py) : tête dans DynamoDB, décision dans le bucket de traces.
        Seulement si Terraform a posé la table et le bucket ; un échec est rapporté sans annuler la simulation."""
        table, bucket = os.environ.get("ALPHAFORGE_DECISIONS_TABLE"), os.environ.get("ALPHAFORGE_TRACE_BUCKET")
        if not (table and bucket):
            return None
        try:
            from .finance.observability import audit

            root = os.path.join(tempfile.gettempdir(), "alphaforge-audit")
            os.makedirs(root, exist_ok=True)
            entry = audit.record_decision(
                decision,
                root,
                aws={"region": self.settings.region, "bucket": bucket, "decisions_table": table},
            )
            kept = {k: entry.get(k) for k in ("seq", "record_hash", "prev_hash", "s3_key", "otel_trace_id")}
            return {**kept, "xray_trace_id": xray_trace_id(kept["otel_trace_id"])}
        except Exception as exc:
            logger.exception("audit record failed")
            return {"error": type(exc).__name__}


def xray_trace_id(otel_trace_id: str | None) -> str | None:
    """Identifiant OpenTelemetry (32 hex) vers le format X-Ray ``1-<8 hex>-<24 hex>`` (console, get-trace-summaries)."""
    if not otel_trace_id or not re.fullmatch(r"[0-9a-f]{32}", otel_trace_id):
        return None
    return f"1-{otel_trace_id[:8]}-{otel_trace_id[8:]}"
