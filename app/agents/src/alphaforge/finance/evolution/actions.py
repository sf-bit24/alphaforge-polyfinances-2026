"""Actions du runtime pour l'évolution du portefeuille : ``evolution.tick``, ``evolution.replay`` et
``evolution.replay_summary``. Fonctions simples, qu'un routeur du runtime enregistre sous ces noms.

Appelées par la machine Step Functions ``<prefix>-evolution`` (``infrastructure/infra/evolution.tf``), qui sonde
un marqueur JSON par étape (même modèle que la collecte) :

    evolution.tick    {"action", "client_id", "month": "AAAA-MM", "run_id"}
                      -> staging/<run_id>/evolution/<AAAA-MM>/_done.json
    evolution.replay  {"action", "client_id", "run_id", "start"?: "AAAA-MM", "end"?: "AAAA-MM"}
                      -> staging/<run_id>/evolution/replay/_done.json
    evolution.replay_summary {"action", "client_id", "run_id"?}   (résumé compact, aucun marqueur)

Persona de démonstration (FICTION, ``alphaforge.finance.personas``) : ``"persona": "amira"`` à la place de
``client_id``, ou ``client_id = "demo-<persona>"`` (forme transmise par la machine) ; l'historique va sous
``clients/demo-<persona>/portefeuilles/``.

Champs facultatifs de ``tick`` et ``replay`` : ``value_cad`` (valeur initiale, sinon ``investable_wealth`` du
profil), ``monthly_flow_cad`` (flux mensuel, 0 par défaut), ``overlays`` (booléen, vrai par défaut),
``persona_label``. Toute autre clé est refusée (``bad_request``). Sans ``end``, le rejeu va jusqu'au dernier mois
des données ; sans ``start``, il part de l'origine de la trajectoire enregistrée, sinon ``DEFAULT_REPLAY_MONTHS``
mois avant ``end``. Les champs absents d'un rejeu reprennent ceux de la trajectoire enregistrée, s'il y en a une.
``monthly_flow_cad`` doit être fini ; un retrait (flux négatif) plus grand que la valeur initiale est refusé
(``bad_request``) : la v0.1 ne simule pas un retrait mensuel supérieur au portefeuille (``tick`` plafonne déjà
chaque retrait à la valeur courante ; ce contrôle écarte les trajectoires vidées dès le premier mois).

Marqueur : ``{"status": "ok" | "error", "error": null | "<code>: <message>", "run_id", "client_id", ...,
"simulation_only": true, "label": "événement de rééquilibrage illustratif", "finished_at", "release"}``. Il est
écrit en cas d'erreur aussi, dès que sa clé est connue (``run_id`` valide, et ``month`` valide pour un tick).
Un marqueur ``ok`` est définitif : écriture conditionnelle (``if_none_match`` / ``if_match`` sur l'ETag lu), et
jamais réécrit, ni par l'erreur d'une invocation en double (relance Step Functions sur ``States.Timeout``), ni
par un second succès. Cette invocation renvoie quand même son erreur à l'appelant.
La réponse suit l'enveloppe commune (app/CONTRACTS.md §2) : ``{"ok": true, "release", ...}`` ou
``{"ok": false, "release", "error": {"code", "message", "details"}}``.

Clés écrites sous ``clients/<client_id>/portefeuilles/`` (proposition, à ajouter à app/CONTRACTS.md §5) :
    <seq>-<yyyymm>.json / .md, index.json   versions chaînées (``HistoryStore``, append-only)
    trajectoire.json                        paramètres de la trajectoire (origine, valeur initiale, flux, overlays)
    rejeux/<run_id>.json                    ``ReplayResult`` complet d'un rejeu
    ticks/<yyyymm>.json                     ``TickResult`` du mois (version, performance, faits, explication)

Rejouer pour reprendre (« replay-to-resume ») : persister une ``Trajectory`` complète (overlays, niveaux de stop,
performance, décisions) serait lourd et fragile. Un tick relit donc l'historique, rejoue de façon déterministe la
fenêtre ``[origine, mois demandé]`` sans écrire, vérifie que les versions régénérées jusqu'au dernier mois stocké
ont exactement le même digest que la chaîne stockée (sinon ``conflict`` / ``history_drift`` : profil, données ou
configuration ont changé), puis n'ajoute que la version du mois demandé, calculée par le même ``tick`` que le
rejeu. Le runtime reste sans état, et chaque mois prouve à nouveau le déterminisme de toute la trajectoire.

Reprise après un arrêt (crash, délai dépassé) entre deux écritures :
- ``trajectoire.json`` est écrit (``if_none_match``) AVANT le premier ajout ; des paramètres présents sans aucune
  version sont repris s'ils sont identiques (champs fournis égaux, origine = mois demandé − 1 pour un tick),
  sinon ``conflict`` : ils restent la définition de la trajectoire, même sans version ;
- une version ``<seq>-<yyyymm>.json`` présente mais absente de ``index.json`` (arrêt entre les deux écritures de
  ``HistoryStore.append``) : si son contenu a le même hash que la version régénérée par le rejeu, l'index est
  réparé (et le ``.md`` réécrit s'il manque) ; sinon ``conflict`` / ``history_drift``. ``HistoryStore`` n'a pas
  de méthode de réparation : elle est faite ici avec l'API du ``Store`` (voir ``_repair_index``).

SIMULATION SEULEMENT : chaque mouvement est un « événement de rééquilibrage illustratif », jamais un ordre ni un
conseil personnalisé. Aucun LLM ici.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from alphaforge import clock
from alphaforge.errors import AppError, error_response, ok_response
from alphaforge.store import ConflictError, Store

from ..contracts.evolution import EVENT_LABEL, PortfolioVersion, ReplayResult, TickResult
from ..contracts.profile import InvestorProfile
from ..observability.telemetry import canonical_hash
from .config import EvolutionConfig, load_config
from .history import HistoryError, HistoryStore, MemoryStore, history_prefix
from .pit import PitReturns, month_end
from .replay import _digest, replay

logger = logging.getLogger("alphaforge.finance.evolution.actions")

ACTION_TICK = "evolution.tick"
ACTION_REPLAY = "evolution.replay"
ACTION_REPLAY_SUMMARY = "evolution.replay_summary"

RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# client_id : sûr pour une clé de stockage (aucun « / », aucun « .. ») ; un UUID v4 y entre.
CLIENT_ID = re.compile(r"^(?!.*\.\.)[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

DEFAULT_REPLAY_MONTHS = 12
MARKET_SOURCE_ENV = "ALPHAFORGE_MARKET_SOURCE"     # "parquet" (moteur) ou "csv" (export .csv.gz)
MARKET_URI_ENV = "ALPHAFORGE_MARKET_URI"           # s3://<bucket>/<clé>, clé du magasin ou fichier local

_OPTIONAL = ("value_cad", "monthly_flow_cad", "overlays", "persona_label", "persona")
TICK_KEYS = frozenset({"action", "client_id", "run_id", "month", *_OPTIONAL})
REPLAY_KEYS = frozenset({"action", "client_id", "run_id", "start", "end", *_OPTIONAL})
SUMMARY_KEYS = frozenset({"action", "client_id", "run_id", "persona"})
PERSONA_PREFIX = "demo-"      # client_id d'une persona de démonstration : demo-<persona> (FICTION)

ProfileLoader = Callable[[str], InvestorProfile]


# ----------------------------------------------------------------------------------------------- clés
def tick_marker_key(run_id: str, month: str) -> str:
    return f"staging/{run_id}/evolution/{month}/_done.json"


def replay_marker_key(run_id: str) -> str:
    return f"staging/{run_id}/evolution/replay/_done.json"


def params_key(client_id: str) -> str:
    return f"{history_prefix(client_id)}trajectoire.json"


def replay_result_key(client_id: str, run_id: str) -> str:
    return f"{history_prefix(client_id)}rejeux/{run_id}.json"


def tick_result_key(client_id: str, month: str) -> str:
    return f"{history_prefix(client_id)}ticks/{month.replace('-', '')}.json"


def version_key(v: PortfolioVersion) -> str:
    """Clé de la ``PortfolioVersion`` complète écrite par ``HistoryStore.append``."""
    return f"{history_prefix(v.client_id)}{v.seq:04d}-{v.as_of:%Y%m}.json"


# ----------------------------------------------------------------------------------------------- contexte
def _release() -> str:
    from alphaforge.config import Settings

    return Settings.from_env().release


_PIT_CACHE: dict[str, PitReturns] = {}


def _read_market_bytes(uri: str, store: Store | None) -> bytes:
    """Octets de l'export ``.csv.gz`` : ``s3://<bucket>/<clé>`` ou clé lue dans le magasin (le bucket doit être
    celui du magasin), sinon fichier local."""
    key = None
    if uri.startswith("s3://"):
        parts = uri.split("/", 3)
        if len(parts) < 4 or not parts[3]:
            raise AppError("internal", f"{MARKET_URI_ENV} doit suivre s3://<bucket>/<clé>.")
        key = parts[3]
    elif Path(uri).is_file():
        return Path(uri).read_bytes()
    if store is None:
        raise AppError("not_found", f"Données de marché introuvables : {uri}.")
    obj = store.get(key or uri)
    if obj is None:
        raise AppError("not_found", f"Données de marché introuvables : {uri}.")
    return obj.body


def load_pit(store: Store | None = None, environ: Mapping[str, str] | None = None) -> PitReturns:
    """Rendements point-in-time selon l'environnement : ``ALPHAFORGE_MARKET_SOURCE=parquet`` (défaut sans URI)
    lit les parquets du moteur ; ``csv`` (défaut avec URI) lit l'export ``.csv.gz`` de ``ALPHAFORGE_MARKET_URI``."""
    env = os.environ if environ is None else environ
    uri = (env.get(MARKET_URI_ENV) or "").strip()
    source = (env.get(MARKET_SOURCE_ENV) or "").strip().lower() or ("csv" if uri else "parquet")
    if source == "parquet":
        if "parquet" not in _PIT_CACHE:
            _PIT_CACHE["parquet"] = PitReturns.from_engine()
        return _PIT_CACHE["parquet"]
    if source in ("csv", "csv.gz"):
        if not uri:
            raise AppError("internal", f"{MARKET_URI_ENV} est requis quand {MARKET_SOURCE_ENV}={source}.")
        return PitReturns.from_csv_gz(_read_market_bytes(uri, store))
    raise AppError("internal", f"{MARKET_SOURCE_ENV} inconnu : {source!r} (attendu parquet ou csv).")


class _Ctx:
    """Dépendances résolues paresseusement : une requête invalide ne touche ni l'environnement ni les données."""

    def __init__(self, store: Store | None, pit: PitReturns | None, profile_loader: ProfileLoader | None):
        self._store, self._pit, self._loader = store, pit, profile_loader
        self._client_store = None

    @property
    def store(self) -> Store:
        if self._store is None:
            from ..debate.okf_bridge import stores_from_env

            self._client_store, _ = stores_from_env()
            self._store = self._client_store.store
        return self._store

    @property
    def pit(self) -> PitReturns:
        if self._pit is None:
            self._pit = load_pit(self.store)
        return self._pit

    def load_profile(self, client_id: str, persona: str | None = None) -> InvestorProfile:
        if persona is not None:
            # persona de démonstration : profil de test du moteur, sans magasin client (FICTION)
            from ..personas import load as load_persona

            return load_persona(persona)[0]
        if self._loader is None:
            from ..debate.okf_bridge import OkfClientStore

            self._loader = (self._client_store or OkfClientStore(self.store)).load_profile
        try:
            return self._loader(client_id)
        except KeyError as exc:
            raise AppError("not_found", f"Profil introuvable : {client_id}.", {"client_id": client_id}) from exc


# ----------------------------------------------------------------------------------------------- validation
class _Req:
    def __init__(self, payload: Mapping[str, Any]):
        self.provided = set(payload)
        self.persona: str | None = payload.get("persona")
        self.client_id: str = payload.get("client_id") or f"{PERSONA_PREFIX}{self.persona}"
        self.run_id: str = payload.get("run_id") or ""
        self.month: str = payload.get("month") or ""
        self.start: str | None = payload.get("start")
        self.end: str | None = payload.get("end")
        self.value_cad: float | None = None if payload.get("value_cad") is None else float(payload["value_cad"])
        self.monthly_flow_cad: float = float(payload.get("monthly_flow_cad", 0.0))
        self.overlays: bool = bool(payload.get("overlays", True))
        self.persona_label: str = payload.get("persona_label") or self.client_id


def _hint(payload: Any, key: str, pattern: re.Pattern[str]) -> str | None:
    """Valeur valide d'un champ, lue avant la validation complète (pour savoir où écrire le marqueur d'erreur)."""
    if not isinstance(payload, Mapping):
        return None
    v = payload.get(key)
    return v if isinstance(v, str) and pattern.match(v) else None


def _is_number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)


def _parse(payload: Any, action: str, allowed: frozenset[str], required: tuple[str, ...]) -> _Req:
    if not isinstance(payload, Mapping):
        raise AppError("bad_request", "Le corps doit être un objet JSON.")
    unknown = sorted(str(k) for k in payload if k not in allowed)
    if unknown:
        raise AppError("bad_request", f"Clés inconnues : {', '.join(unknown)}.",
                       {"unknown": unknown, "allowed": sorted(allowed)})
    if "action" in payload and payload["action"] != action:
        raise AppError("bad_request", f"action doit valoir {action}.", {"action": payload["action"]})
    persona = payload.get("persona")
    if persona is not None:
        if payload.get("client_id") is not None:
            raise AppError("bad_request", "client_id ou persona, pas les deux.", {"field": "persona"})
        known = _persona_ids()
        if not isinstance(persona, str) or persona not in known:
            raise AppError("bad_request", "persona inconnue.", {"field": "persona", "allowed": known})
        payload = {**payload, "client_id": f"{PERSONA_PREFIX}{persona}"}
    elif isinstance(payload.get("client_id"), str) and payload["client_id"].startswith(PERSONA_PREFIX):
        # « demo-<persona> » venant de la machine Step Functions (qui ne transmet qu'un client_id)
        name = payload["client_id"][len(PERSONA_PREFIX):]
        if name in _persona_ids():
            payload = {**payload, "persona": name}
    for k in required:
        if k not in payload or payload[k] is None:
            raise AppError("bad_request", f"{k} est requis.", {"field": k})
    cid = payload["client_id"]
    if not isinstance(cid, str) or not cid.strip():
        raise AppError("bad_request", "client_id doit être une chaîne non vide.", {"field": "client_id"})
    if not CLIENT_ID.match(cid):
        raise AppError("bad_request", "client_id doit suivre ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$, sans « .. ».",
                       {"field": "client_id"})
    if "run_id" in payload and (not isinstance(payload["run_id"], str) or not RUN_ID.match(payload["run_id"])):
        raise AppError("bad_request", "run_id doit suivre ^[A-Za-z0-9_-]{1,64}$.", {"run_id": payload["run_id"]})
    for k in ("month", "start", "end"):
        if k in payload and (not isinstance(payload[k], str) or not MONTH.match(payload[k])):
            raise AppError("bad_request", f"{k} doit suivre AAAA-MM.", {k: payload[k]})
    if "value_cad" in payload and not (_is_number(payload["value_cad"]) and payload["value_cad"] > 0):
        raise AppError("bad_request", "value_cad doit être un nombre strictement positif.", {"field": "value_cad"})
    if "monthly_flow_cad" in payload and not _is_number(payload["monthly_flow_cad"]):
        raise AppError("bad_request", "monthly_flow_cad doit être un nombre fini.", {"field": "monthly_flow_cad"})
    if "overlays" in payload and not isinstance(payload["overlays"], bool):
        raise AppError("bad_request", "overlays doit être un booléen.", {"field": "overlays"})
    if "persona_label" in payload:
        lab = payload["persona_label"]
        if not isinstance(lab, str) or not lab.strip() or len(lab) > 120:
            raise AppError("bad_request", "persona_label doit être une chaîne de 1 à 120 caractères.",
                           {"field": "persona_label"})
    if "monthly_flow_cad" in payload and "value_cad" in payload:     # tôt : ni profil ni données touchés
        _check_flow(float(payload["monthly_flow_cad"]), float(payload["value_cad"]))
    return _Req(payload)


def _persona_ids() -> list[str]:
    """Personas FICTION de démonstration (``alphaforge.finance.personas``, PR #47) ; liste vide si absentes."""
    try:
        from ..personas import ids
    except ImportError:
        return []
    return list(ids())


def _check_flow(flow: float, value: float) -> None:
    """v0.1 : un retrait mensuel (flux négatif) ne peut pas dépasser la valeur initiale du portefeuille. Appelé
    tôt quand les deux champs sont fournis, puis sur les paramètres effectifs de la trajectoire (valeur venant du
    profil ou de ``trajectoire.json``)."""
    if flow < 0 and -flow > value:
        raise AppError("bad_request", f"monthly_flow_cad ({flow:,.2f}) : un retrait mensuel supérieur à la valeur "
                       f"initiale ({value:,.2f} CAD) n'est pas pris en charge (v0.1).",
                       {"field": "monthly_flow_cad", "monthly_flow_cad": flow, "value_cad": value})


def _ym(d) -> str:
    return f"{month_end(d):%Y-%m}"


def _initial_value(req: _Req, profile: InvestorProfile) -> float:
    if req.value_cad is not None:
        return req.value_cad
    if profile.investable_wealth:
        return float(profile.investable_wealth)
    raise AppError("bad_request", "Valeur initiale inconnue : fournir value_cad (le profil n'a pas d'avoir "
                   "investissable).", {"field": "value_cad"})


def _params(origin: str, value_cad: float, monthly_flow_cad: float, overlays: bool) -> dict[str, Any]:
    return {"origin": origin, "value_cad": float(value_cad), "monthly_flow_cad": float(monthly_flow_cad),
            "overlays": bool(overlays)}


_PARAM_FIELDS = ("origin", "value_cad", "monthly_flow_cad", "overlays")


def _same_params(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    return all(a.get(k) == b.get(k) for k in _PARAM_FIELDS)


def _check_overrides(req: _Req, params: Mapping[str, Any]) -> None:
    """Un champ fourni à la reprise doit égaler celui de la trajectoire enregistrée (sinon le rejeu diverge)."""
    given = {"value_cad": req.value_cad, "monthly_flow_cad": req.monthly_flow_cad, "overlays": req.overlays}
    diff = [k for k, v in given.items() if k in req.provided and params.get(k) != v]
    if diff:
        raise AppError("conflict", f"Paramètres différents de la trajectoire enregistrée : {', '.join(diff)}.",
                       {"reason": "trajectory_params", "fields": diff,
                        "stored": {k: params.get(k) for k in _PARAM_FIELDS}})


def _load_params(ctx: _Ctx, client_id: str) -> dict[str, Any] | None:
    doc = ctx.store.get_json(params_key(client_id))
    return doc if isinstance(doc, dict) else None


def _trajectory_exists(stored: Mapping[str, Any], requested: Mapping[str, Any]) -> AppError:
    return AppError("conflict", "Une autre trajectoire est déjà enregistrée pour ce client (origine, valeur, flux "
                    "ou overlays différents).", {"reason": "trajectory_exists",
                                                 "stored": {k: stored.get(k) for k in _PARAM_FIELDS},
                                                 "requested": dict(requested)})


def _ensure_params(ctx: _Ctx, client_id: str, params: Mapping[str, Any], run_id: str) -> None:
    """Écrit ``trajectoire.json`` AVANT le premier ajout, de façon idempotente (``if_none_match``) : un arrêt juste
    après laisse des paramètres que la reprise accepte s'ils sont identiques. Un écrivain concurrent qui a écrit
    d'autres paramètres entre la lecture et l'écriture donne ``conflict`` / ``trajectory_exists``."""
    key = params_key(client_id)
    try:
        ctx.store.put_json(key, {**params, "created_by_run_id": run_id}, if_none_match=True)
    except ConflictError:
        cur = ctx.store.get_json(key)
        if not (isinstance(cur, dict) and _same_params(cur, params)):
            raise _trajectory_exists(cur if isinstance(cur, dict) else {}, params) from None


def _check_window(pit: PitReturns, origin: pd.Timestamp, last: pd.Timestamp) -> None:
    if origin < pit.first_month:
        raise AppError("bad_request", f"Origine {origin:%Y-%m} antérieure aux données ({pit.first_month:%Y-%m}).")
    if last > pit.last_month:
        raise AppError("bad_request", f"Mois {last:%Y-%m} postérieur aux données ({pit.last_month:%Y-%m}).")
    if last <= origin:
        raise AppError("bad_request", "La fenêtre doit compter au moins un mois après l'origine.")


# ----------------------------------------------------------------------------------------------- historique
def _stored_versions(hist: HistoryStore) -> list[PortfolioVersion]:
    ok, bad = hist.verify()
    if not ok:
        raise AppError("conflict", "Chaîne de l'historique altérée.", {"reason": "history_corrupt", "version_id": bad})
    return hist.versions()


def _drift(expected: str, got: str) -> AppError:
    return AppError("conflict", "Dérive de l'historique : le rejeu ne régénère pas les versions stockées (profil, "
                    "données ou configuration modifiés).", {"reason": "history_drift", "stored_digest": expected,
                                                           "replayed_digest": got})


def _append_refused(version: PortfolioVersion, exc: Exception) -> AppError:
    return AppError("conflict", f"Version refusée par l'historique : {exc}.",
                    {"reason": "history_append", "version_id": version.version_id})


def _append(hist: HistoryStore, version: PortfolioVersion) -> bool:
    """Ajoute ``version`` en bout de chaîne. Renvoie True si l'ajout a été une réparation de l'index (version déjà
    écrite par une invocation arrêtée avant ``index.json``), False pour un ajout normal."""
    orphan = hist.store.get_json(version_key(version))
    if orphan is not None:
        _repair_index(hist, version, orphan)
        return True
    try:
        hist.append(version)
    except (HistoryError, ConflictError) as exc:
        raise _append_refused(version, exc) from exc
    return False


def _repair_index(hist: HistoryStore, version: PortfolioVersion, orphan: Any) -> None:
    """Reprise d'un arrêt entre l'écriture de ``<seq>-<yyyymm>.json`` et celle de ``index.json``.

    Contenu différent de la version régénérée (hash canonique, celui de ``verify()``) : ``conflict`` /
    ``history_drift``, rien n'est écrit. Contenu identique : l'entrée d'index est ajoutée, le ``.md`` réécrit s'il
    manque (jamais écrasé : il porte une date de rendu).

    ``HistoryStore`` n'a pas de méthode de réparation (history.py hors du périmètre de ce module) : la réparation
    passe par l'API du ``Store``. Pour ne pas recopier sa logique, l'entrée est produite par ``HistoryStore.append``
    lui-même sur un ``MemoryStore`` jetable qui ne contient que l'index courant : mêmes contrôles (client, seq,
    parent) et même entrée chaînée (``version_hash``, ``prev_hash``, ``record_hash``) qu'un ajout normal. L'index
    réel est ensuite écrit sous condition d'ETag, comme dans ``append`` (un écrivain concurrent → ``conflict``)."""
    key = version_key(version)
    stored_hash, replayed_hash = canonical_hash(orphan), canonical_hash(version.model_dump(mode="json"))
    if stored_hash != replayed_hash:
        raise AppError("conflict", "Dérive de l'historique : une version déjà écrite, absente de l'index, diffère de "
                       "celle que régénère le rejeu.", {"reason": "history_drift", "version_key": key,
                                                         "stored_version_hash": stored_hash,
                                                         "replayed_version_hash": replayed_hash})
    store = hist.store
    idx_obj = store.get(hist.index_key)
    scratch = MemoryStore()
    if idx_obj is not None:
        scratch.put(hist.index_key, idx_obj.body)
    try:
        entry = HistoryStore(hist.client_id, scratch).append(version)
    except (HistoryError, ConflictError) as exc:
        raise _append_refused(version, exc) from exc
    md_key = key.removesuffix(".json") + ".md"
    md = scratch.get(md_key)
    if md is not None and not store.exists(md_key):
        try:
            store.put_text(md_key, md.text, if_none_match=True)
        except ConflictError:
            pass                                 # écrit entre-temps par un écrivain concurrent : on le garde
    idx = json.loads(idx_obj.text) if idx_obj is not None else []
    cond: dict[str, Any] = {"if_match": idx_obj.etag} if idx_obj is not None else {"if_none_match": True}
    try:
        store.put_json(hist.index_key, [*idx, entry], **cond)
    except ConflictError as exc:
        raise _append_refused(version, exc) from exc
    logger.warning("index réparé : %s (version déjà écrite, absente de l'index)", version.version_id)


# ----------------------------------------------------------------------------------------------- enveloppe
def _tag(d: dict[str, Any]) -> dict[str, Any]:
    d["simulation_only"] = True
    d["label"] = EVENT_LABEL
    return d


_MARKER_ATTEMPTS = 3


def _marker_status(obj: Any) -> Any:
    try:
        doc = json.loads(obj.body.decode("utf-8"))
    except ValueError:
        return None
    return doc.get("status") if isinstance(doc, dict) else None


def _write_marker(ctx: _Ctx, key: str | None, doc: dict[str, Any]) -> None:
    """Écrit le marqueur, sauf si un marqueur ``ok`` existe déjà : celui-ci est définitif (une invocation en double
    qui échoue, ou réussit en second, ne le réécrit pas). Écriture conditionnelle sur l'état lu (``if_none_match``
    s'il est absent, ``if_match`` sur son ETag sinon) : un succès concurrent écrit entre la lecture et l'écriture
    n'est pas écrasé non plus (relecture, puis abandon s'il est ``ok``)."""
    if key is None:
        return
    try:
        body = _tag({**doc, "finished_at": clock.iso(), "release": _release()})
        for _ in range(_MARKER_ATTEMPTS):
            cur = ctx.store.get(key)
            if cur is not None and _marker_status(cur) == "ok":
                if doc.get("status") != "ok":
                    logger.warning("marqueur ok conservé : %s (erreur d'une invocation en double : %s)", key,
                                   doc.get("error"))
                return
            cond: dict[str, Any] = {"if_match": cur.etag} if cur is not None else {"if_none_match": True}
            try:
                ctx.store.put_json(key, body, **cond)
                return
            except ConflictError:
                continue                         # écrit entre-temps : relire avant de réessayer
        logger.error("marqueur non écrit après %d essais (écritures concurrentes) : %s", _MARKER_ATTEMPTS, key)
    except Exception:  # noqa: BLE001 - un marqueur manquant se voit par le délai de la machine, pas par une exception
        logger.exception("marqueur non écrit : %s", key)


def _fail(ctx: _Ctx, marker: str | None, exc: AppError, ident: dict[str, Any]) -> dict[str, Any]:
    _write_marker(ctx, marker, {"status": "error", "error": f"{exc.code}: {exc.message}", **ident})
    return _tag(error_response(_release(), exc))


def write_error_marker(payload: Any, store: Store | None, code: str, message: str) -> None:
    """Marqueur d'erreur pour une tâche qui a échoué avant d'atteindre son action (ex. moteur introuvable dans le
    runtime). Ne remplace jamais un marqueur « ok » (``_write_marker`` est conditionnel)."""
    if not isinstance(payload, Mapping):
        return
    run_id, month = _hint(payload, "run_id", RUN_ID), _hint(payload, "month", MONTH)
    if not run_id:
        return
    action = payload.get("action")
    marker = tick_marker_key(run_id, month) if action == ACTION_TICK and month else replay_marker_key(run_id)
    ident = {"run_id": run_id, "client_id": _hint(payload, "client_id", CLIENT_ID)}
    _fail(_Ctx(store, None, None), marker, AppError(code if code in ("internal", "bad_request") else "internal",
                                                    message), ident)


def _run(ctx: _Ctx, marker: str | None, ident: dict[str, Any], fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        body = fn()
    except AppError as exc:
        return _fail(ctx, marker, exc, ident)
    except Exception as exc:  # noqa: BLE001 - toute erreur devient une enveloppe et un marqueur d'erreur
        logger.exception("action d'évolution en échec")
        return _fail(ctx, marker, AppError("internal", f"{type(exc).__name__}: {str(exc)[:300]}"), ident)
    return _tag(ok_response(_release(), **body))


def _done(ctx: _Ctx, marker: str) -> dict[str, Any] | None:
    """Corps d'une étape déjà réussie pour ce ``run_id`` (reprise par la machine), sinon None."""
    doc = ctx.store.get_json(marker)
    if not isinstance(doc, dict) or doc.get("status") != "ok":
        return None
    skip = {"status", "error", "finished_at", "release", "simulation_only", "label"}
    return {**{k: v for k, v in doc.items() if k not in skip}, "already_done": True}


# ----------------------------------------------------------------------------------------------- tick
def handle_tick(payload: dict, *, store: Store | None = None, pit: PitReturns | None = None,
                profile_loader: ProfileLoader | None = None, cfg: EvolutionConfig | None = None) -> dict:
    """``evolution.tick`` : un mois de plus pour la trajectoire enregistrée du client (rejouer pour reprendre).

    Sans historique, la trajectoire s'ouvre à ``month − 1`` (origine) et le mois demandé devient la version 0.
    Avec un historique, ``month`` doit être le mois suivant la dernière version (le même mois est idempotent :
    rien n'est recalculé, ``already_done`` vaut vrai) ; sinon ``bad_request``."""
    ctx = _Ctx(store, pit, profile_loader)
    run_id, month = _hint(payload, "run_id", RUN_ID), _hint(payload, "month", MONTH)
    marker = tick_marker_key(run_id, month) if run_id and month else None
    ident = {"run_id": run_id, "client_id": _hint(payload, "client_id", CLIENT_ID), "month": month}

    def go() -> dict[str, Any]:
        req = _parse(payload, ACTION_TICK, TICK_KEYS, ("client_id", "run_id", "month"))
        return _tick(req, ctx, cfg or load_config(), tick_marker_key(req.run_id, req.month))

    return _run(ctx, marker, ident, go)


def _tick(req: _Req, ctx: _Ctx, cfg: EvolutionConfig, marker: str) -> dict[str, Any]:
    done = _done(ctx, marker)
    if done is not None:
        return done
    cid, m = req.client_id, month_end(req.month)
    hist = HistoryStore(cid, ctx.store)
    stored = _stored_versions(hist)
    params = _load_params(ctx, cid)
    if stored:
        last_m = month_end(stored[-1].as_of)
        if m == last_m:
            rkey = tick_result_key(cid, req.month)
            body = _tick_body(req, stored[-1], stored, rkey if ctx.store.exists(rkey) else None, already=True)
            _write_marker(ctx, marker, {"status": "ok", "error": None, **body})
            return body
        if m != last_m + pd.offsets.MonthEnd(1):
            raise AppError("bad_request", f"month doit être {_ym(last_m + pd.offsets.MonthEnd(1))}, le mois qui suit "
                           f"la dernière version ({_ym(last_m)}).", {"month": req.month, "last": _ym(last_m)})
        if params is None:
            raise AppError("conflict", "Historique sans paramètres de trajectoire : reprise impossible.",
                           {"reason": "trajectory_params_missing"})
        _check_overrides(req, params)
        origin = month_end(params["origin"])
        if month_end(stored[0].as_of) != origin + pd.offsets.MonthEnd(1):
            raise AppError("conflict", "Dérive de l'historique : la première version ne suit pas l'origine "
                           "enregistrée.", {"reason": "history_drift", "origin": _ym(origin),
                                            "first_version": _ym(stored[0].as_of)})
    else:
        origin = m - pd.offsets.MonthEnd(1)
        if params is not None:
            # paramètres écrits par une invocation arrêtée avant le premier ajout : repris s'ils sont identiques
            if month_end(params["origin"]) != origin:
                raise AppError("conflict", "Paramètres de trajectoire déjà enregistrés (sans version) pour une autre "
                               f"origine : le premier mois attendu est "
                               f"{_ym(month_end(params['origin']) + pd.offsets.MonthEnd(1))}.",
                               {"reason": "trajectory_params", "fields": ["origin"],
                                "stored": {k: params.get(k) for k in _PARAM_FIELDS}})
            _check_overrides(req, params)

    profile = ctx.load_profile(cid, persona=req.persona)
    write_params = params is None
    if params is None:
        params = _params(_ym(origin), _initial_value(req, profile), req.monthly_flow_cad, req.overlays)
    _check_flow(params["monthly_flow_cad"], params["value_cad"])
    pit = ctx.pit
    _check_window(pit, origin, m)

    # rejeu déterministe de [origine, mois demandé], sans écrire ; le mois demandé passe par le même tick
    res, _ = replay(profile, cid, req.persona_label, origin, m, params["value_cad"], pit=pit, cfg=cfg,
                    monthly_flow=params["monthly_flow_cad"], overlays=params["overlays"], history=None,
                    run_id=req.run_id)
    n = len(stored)
    if len(res.versions) != n + 1:
        raise AppError("conflict", f"Le rejeu rend {len(res.versions)} versions, attendu {n + 1} (mois manquants "
                       "dans les données).", {"reason": "history_drift"})
    if n and _digest(res.versions[:n]) != _digest(stored):
        raise _drift(_digest(stored), _digest(res.versions[:n]))
    new = res.versions[n]
    if write_params:                             # avant le premier ajout (reprise sans trajectory_params_missing)
        _ensure_params(ctx, cid, params, req.run_id)
    _append(hist, new)

    ev = new.event
    exp = res.explanations.get(ev.event_id)
    month_prefix = f"ev.{new.as_of:%Y%m}."
    cited = set(ev.fact_ids) | {i for sec in ((exp.data_used, exp.why, exp.limits, exp.what_would_change)
                                              if exp else ()) for s in sec for i in s.fact_ids}
    result = TickResult(version=new, perf=res.perf, explanation=exp,
                        facts=[f for f in res.facts if f.fact_id.startswith(month_prefix) or f.fact_id in cited],
                        reprofile_triggers_fired=[t.code for t in ev.triggers if t.blocking])
    rkey = tick_result_key(cid, req.month)
    ctx.store.put_json(rkey, result.model_dump(mode="json"))
    body = _tick_body(req, new, [*stored, new], rkey, already=False)
    _write_marker(ctx, marker, {"status": "ok", "error": None, **body})
    return {**body, "result": result.model_dump(mode="json")}


def _tick_body(req: _Req, v: PortfolioVersion, chain: list[PortfolioVersion], result_key: str | None,
               *, already: bool) -> dict[str, Any]:
    return {
        "run_id": req.run_id, "client_id": req.client_id, "month": req.month, "version_id": v.version_id,
        "seq": v.seq, "action": v.event.action, "level": v.level, "value_cad": v.value_cad,
        "n_versions": len(chain), "digest": _digest(chain),   # digest de toute la chaîne = celui d'un rejeu complet
        "version_key": version_key(v), "result_key": result_key, "already_done": already,
    }


# ----------------------------------------------------------------------------------------------- rejeu
def handle_replay(payload: dict, *, store: Store | None = None, pit: PitReturns | None = None,
                  profile_loader: ProfileLoader | None = None, cfg: EvolutionConfig | None = None) -> dict:
    """``evolution.replay`` : rejeu point-in-time de ``[start, end]`` ; écrit les versions dans l'historique du
    client, le ``ReplayResult`` complet sous ``rejeux/<run_id>.json``, puis le marqueur.

    L'historique reste une seule chaîne : un rejeu de la même trajectoire (même origine, valeur, flux, overlays)
    est idempotent ou la prolonge ; une autre trajectoire déjà enregistrée, ou une chaîne que le rejeu ne régénère
    pas à l'identique, donne ``conflict`` (``trajectory_exists`` / ``history_drift``) sans rien écrire."""
    ctx = _Ctx(store, pit, profile_loader)
    run_id = _hint(payload, "run_id", RUN_ID)
    marker = replay_marker_key(run_id) if run_id else None
    ident = {"run_id": run_id, "client_id": _hint(payload, "client_id", CLIENT_ID)}

    def go() -> dict[str, Any]:
        req = _parse(payload, ACTION_REPLAY, REPLAY_KEYS, ("client_id", "run_id"))
        return _replay(req, ctx, cfg or load_config(), replay_marker_key(req.run_id))

    return _run(ctx, marker, ident, go)


def _replay(req: _Req, ctx: _Ctx, cfg: EvolutionConfig, marker: str) -> dict[str, Any]:
    done = _done(ctx, marker)
    if done is not None:
        return done
    cid, run_id = req.client_id, req.run_id
    hist = HistoryStore(cid, ctx.store)
    stored = _stored_versions(hist)
    params = _load_params(ctx, cid)
    if stored and params is None:
        raise AppError("conflict", "Historique sans paramètres de trajectoire.",
                       {"reason": "trajectory_params_missing"})

    profile = ctx.load_profile(cid, persona=req.persona)
    # une trajectoire enregistrée fournit les valeurs par défaut des champs absents (origine comprise) ; des
    # paramètres sans version (invocation arrêtée avant le premier ajout) la définissent tout autant
    known = params or {}
    value = req.value_cad if req.value_cad is not None else known.get("value_cad") or _initial_value(req, profile)
    flow = req.monthly_flow_cad if "monthly_flow_cad" in req.provided else known.get("monthly_flow_cad", 0.0)
    overlays = req.overlays if "overlays" in req.provided else known.get("overlays", True)
    _check_flow(flow, value)
    pit = ctx.pit
    end = month_end(req.end) if req.end else month_end(pit.last_month)
    if req.start:
        start = month_end(req.start)
    else:
        start = month_end(known["origin"]) if known else end - pd.offsets.MonthEnd(DEFAULT_REPLAY_MONTHS)
    _check_window(pit, start, end)
    new_params = _params(_ym(start), value, flow, overlays)
    if params is not None and not _same_params(params, new_params):
        raise _trajectory_exists(params, new_params)

    res, _ = replay(profile, cid, req.persona_label, start, end, value, pit=pit, cfg=cfg, monthly_flow=flow,
                    overlays=overlays, history=None, run_id=run_id)
    k = min(len(stored), len(res.versions))
    if _digest(stored[:k]) != _digest(res.versions[:k]):
        raise _drift(_digest(stored[:k]), _digest(res.versions[:k]))
    appended = res.versions[len(stored):]
    if appended and params is None:              # avant le premier ajout (params absents ⇒ historique vide)
        _ensure_params(ctx, cid, new_params, run_id)
    for v in appended:
        _append(hist, v)
    rkey = replay_result_key(cid, run_id)
    ctx.store.put_json(rkey, res.model_dump(mode="json"))
    body = _replay_body(res, rkey, n_history=len(stored) + len(appended), appended=len(appended))
    _write_marker(ctx, marker, {"status": "ok", "error": None, **body})
    return body


def _replay_body(res: ReplayResult, result_key: str, *, n_history: int, appended: int) -> dict[str, Any]:
    return {
        "run_id": res.run_id, "client_id": res.client_id, "digest": res.digest, "n_versions": len(res.versions),
        "n_events_by_action": dict(sorted(res.n_events_by_action.items())), "result_key": result_key,
        "window": [_ym(res.window[0]), _ym(res.window[1])],
        "history": {"n_versions": n_history, "appended": appended}, "already_done": False,
    }


# ----------------------------------------------------------------------------------------------- synthèse
def handle_replay_summary(payload: dict, *, store: Store | None = None) -> dict:
    """``evolution.replay_summary`` : résumé compact de l'historique (étape « Synthèse » de la machine).

    Lit l'index (``HistoryStore.index()``) et vérifie la chaîne ; aucun calcul financier, aucun marqueur."""
    ctx = _Ctx(store, None, None)

    def go() -> dict[str, Any]:
        req = _parse(payload, ACTION_REPLAY_SUMMARY, SUMMARY_KEYS, ("client_id",))
        hist = HistoryStore(req.client_id, ctx.store)
        idx = hist.index()
        chain_ok, bad = hist.verify()
        last = idx[-1] if idx else {}
        return {
            "client_id": req.client_id, "run_id": req.run_id, "n_versions": len(idx),
            "first_as_of": idx[0]["as_of"] if idx else None, "last_as_of": last.get("as_of"),
            "last_version_id": last.get("version_id"), "last_action": last.get("action"),
            "last_value_cad": last.get("value_cad"), "last_level": last.get("level"),
            "n_events_by_action": dict(sorted(Counter(e["action"] for e in idx).items())),
            "chain_ok": chain_ok, "first_bad_version": bad, "history_prefix": history_prefix(req.client_id),
        }

    return _run(ctx, None, {}, go)


__all__ = [
    "ACTION_REPLAY", "ACTION_REPLAY_SUMMARY", "ACTION_TICK", "DEFAULT_REPLAY_MONTHS", "handle_replay",
    "handle_replay_summary", "handle_tick", "load_pit", "params_key", "replay_marker_key", "replay_result_key",
    "tick_marker_key", "tick_result_key", "version_key",
]
