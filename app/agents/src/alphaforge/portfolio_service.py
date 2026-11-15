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
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from datetime import date
from typing import Any

from .config import Settings
from .errors import AppError, error_response, ok_response, pick
from .store import ConflictError, Store

logger = logging.getLogger("alphaforge.portfolio")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MODES = ("llm", "rules")
LOCALES = ("fr", "en")
REQUEST_KEYS = {"ticker", "amount_cad", "weight"}


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
                            "internal",
                            "Les données de marché du moteur sont indisponibles (runtime/data/long/).",
                            {"detail": str(exc)},
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
            "internal",
            "Le moteur du volet finance n'est pas dans ce paquet (agents-portfolio.zip attendu).",
            {"missing_module": exc.name},
        )


class PortfolioService:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        app: Any | None = None,
        *,
        engine: Callable[[], dict[str, Any]] | None = None,
    ):
        self.settings = settings
        self.store = store
        self.app = app
        self._engine = engine or FinanceEngine(store).load
        self._questionnaire: Any | None = None

    def handle(self, payload: Any) -> dict[str, Any]:
        release = self.settings.release
        locale = payload.get("locale") if isinstance(payload, dict) and payload.get("locale") in LOCALES else "fr"
        try:
            if not isinstance(payload, dict):
                raise AppError("bad_request", "Le corps doit être un objet JSON.")
            action = payload.get("action")
            if not isinstance(action, str) or not action:
                raise AppError("bad_request", pick(locale, "action est requise.", "action is required."))
            if action == "health":
                return ok_response(release, role=self.settings.role, env=self.settings.env)
            if action != "build":
                raise AppError(
                    "unknown_action",
                    pick(locale, f"Action inconnue : {action}.", f"Unknown action: {action}."),
                    {"action": action, "expected": ["build", "health"]},
                )
            return ok_response(release, **self.build(payload, locale))
        except AppError as exc:
            return error_response(release, exc)
        except ConflictError:
            return error_response(
                release,
                AppError(
                    "conflict",
                    pick(locale, "La décision existe déjà. Réessayez.", "The decision already exists. Try again."),
                ),
            )
        except Exception as exc:
            logger.exception("portfolio build failed")
            if type(exc).__module__.split(".")[0] in ("botocore", "boto3", "strands"):
                return error_response(
                    release,
                    AppError(
                        "model_error",
                        pick(
                            locale,
                            "Le modèle n'a pas pu répondre. Réessayez dans un instant.",
                            "The model could not answer. Please try again in a moment.",
                        ),
                        {"type": type(exc).__name__},
                    ),
                )
            return error_response(release, AppError("internal", pick(locale, "Erreur interne.", "Internal error.")))

    # ------------------------------------------------------------------ build
    def _parse(self, payload: dict[str, Any], locale: str) -> dict[str, Any]:
        from .profile.state import is_client_id

        def bad(fr: str, en: str, **details: Any) -> AppError:
            return AppError("bad_request", pick(locale, fr, en), details)

        client_id = payload.get("client_id")
        if not is_client_id(client_id):
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
            "as_of": as_of,
            "mode": mode,
            "strategy": strategy,
            "style": style,
            "request": request,
        }

    def build(self, payload: dict[str, Any], locale: str) -> dict[str, Any]:
        args = self._parse(payload, locale)
        engine = self._engine()
        pipeline, bridge = engine["pipeline"], engine["okf_bridge"]
        styles = engine["styles"]
        if args["style"] is not None and args["style"] not in styles:
            raise AppError(
                "bad_request",
                pick(locale, "style_preference inconnu.", "Unknown style_preference."),
                {"allowed": list(styles)},
            )
        if self._questionnaire is None:
            from .profile.questionnaire import Questionnaire

            self._questionnaire = Questionnaire.load()
        client_store = bridge.OkfClientStore(self.store, self._questionnaire, locale=locale)
        market_store = bridge.OkfMarketStore(self.store)
        try:
            profile = client_store.load_profile(args["client_id"])
        except KeyError as exc:
            raise AppError("not_found", pick(locale, "Profil introuvable.", "Profile not found.")) from exc
        # Étape 0 : variables de style du profil court, lues comme dans finance/debate/app.py.
        style_inputs = None
        if args["strategy"]:
            style_inputs = engine["style_inputs_from_view"](client_store.view(args["client_id"])[0])
        as_of = args["as_of"] or pipeline.DEFAULT_AS_OF
        try:
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
            )
        finally:
            telemetry = engine.get("telemetry")
            if telemetry is not None:
                try:
                    telemetry.flush()
                except Exception:
                    logger.exception("telemetry flush failed")
        decision_key = client_store.save_decision(result.decision, result.policy)
        return {
            "client_id": args["client_id"],
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
            "strategy": result.strategy.summary() if result.strategy is not None else None,
        }
