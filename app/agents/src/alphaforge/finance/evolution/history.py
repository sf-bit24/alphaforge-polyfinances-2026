"""Historique versionné des portefeuilles simulés d'un client, chaîné par hash (append-only).

Clés écrites (proposition, à ajouter à app/CONTRACTS.md §5) sous ``clients/<client_id>/portefeuilles/`` :
    <seq:04d>-<yyyymm>.json   ``PortfolioVersion`` complète (jamais réécrite)
    <seq:04d>-<yyyymm>.md     résumé lisible (frontmatter de type « Portfolio Version », tableau des mouvements)
    index.json                liste ordonnée {version_id, seq, as_of, action, level, value_cad, drift,
                              version_hash, prev_hash, record_hash}

Chaîne : ``record_hash = canonical_hash({"prev": prev_hash, "version": canonical_hash(version)})``, avec
``GENESIS = "0" * 64`` (même schéma que ``observability/audit.py``). Modifier une version stockée ou l'index
casse ``verify()``. Supports : mémoire, répertoire local (``LocalStore``) ou tout ``alphaforge.store.Store``
(S3 en AWS). Chaque mouvement est un « événement de rééquilibrage illustratif » : SIMULATION SEULEMENT.

Point de coordination : « Portfolio Version » n'est pas (encore) dans ``okf.DOC_TYPES`` ; le résumé ``.md``
est rendu avec ``okf.render`` (qui ne valide pas) et passera ``okf.validate`` dès que le type sera déclaré.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import UTC, date, datetime
from typing import Any

from alphaforge import okf
from alphaforge.store import ConflictError, ObjectInfo, Store, StoredObject, validate_prefix

from ..contracts.evolution import EVENT_LABEL, PortfolioVersion
from ..observability.telemetry import canonical_hash

GENESIS = "0" * 64
DOC_TYPE = "Portfolio Version"


def version_id(client_id: str, seq: int, as_of: date) -> str:
    """Identifiant déterministe ``pv-<client8>-<seq:04d>-<yyyymm>``.

    ``client8`` = 8 premiers caractères hexadécimaux du sha256 de ``client_id`` : stable, sûr pour une clé
    de stockage, et ne recopie pas l'identifiant du client dans les noms d'objets."""
    client8 = hashlib.sha256(client_id.encode("utf-8")).hexdigest()[:8]
    return f"pv-{client8}-{seq:04d}-{as_of:%Y%m}"


def history_prefix(client_id: str) -> str:
    return f"clients/{client_id}/portefeuilles/"


class MemoryStore(Store):
    """``Store`` en mémoire (tests, démonstration hors ligne)."""

    name = "memory"

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _etag(body: bytes) -> str:
        return hashlib.md5(body, usedforsecurity=False).hexdigest()

    def get(self, key: str) -> StoredObject | None:
        with self._lock:
            body = self._objects.get(key)
        if body is None:
            return None
        return StoredObject(key=key, body=body, etag=self._etag(body), last_modified="")

    def put(self, key: str, body: bytes, *, content_type: str = "text/markdown; charset=utf-8",
            if_match: str | None = None, if_none_match: bool = False) -> str:
        with self._lock:
            cur = self._objects.get(key)
            if if_none_match and cur is not None:
                raise ConflictError(key)
            if if_match is not None and (cur is None or self._etag(cur) != if_match):
                raise ConflictError(key)
            self._objects[key] = bytes(body)
        return self._etag(body)

    def list(self, prefix: str, *, limit: int = 1000) -> list[ObjectInfo]:
        validate_prefix(prefix)
        with self._lock:
            keys = sorted(k for k in self._objects if k.startswith(prefix))[:limit]
            return [ObjectInfo(key=k, etag=self._etag(self._objects[k]), last_modified="",
                               size=len(self._objects[k])) for k in keys]


class HistoryError(ValueError):
    """Version refusée (séquence, parent ou client incohérents, fichier déjà présent)."""


class HistoryStore:
    """Historique append-only des ``PortfolioVersion`` d'un client.

    ``backend`` : ``None`` (mémoire), un chemin de répertoire (``LocalStore``) ou un ``Store`` existant."""

    def __init__(self, client_id: str, backend: Store | str | os.PathLike[str] | None = None):
        self.client_id = client_id
        if backend is None:
            self.store: Store = MemoryStore()
        elif isinstance(backend, Store):
            self.store = backend
        else:
            from alphaforge.store.local import LocalStore

            self.store = LocalStore(backend)
        self.prefix = history_prefix(client_id)
        validate_prefix(self.prefix)

    # ----------------------------------------------------------------- clés
    def _stem(self, v: PortfolioVersion) -> str:
        return f"{self.prefix}{v.seq:04d}-{v.as_of:%Y%m}"

    @property
    def index_key(self) -> str:
        return f"{self.prefix}index.json"

    def _index(self) -> tuple[list[dict[str, Any]], str | None]:
        obj = self.store.get(self.index_key)
        if obj is None:
            return [], None
        return json.loads(obj.text), obj.etag

    def index(self) -> list[dict[str, Any]]:
        return self._index()[0]

    # ----------------------------------------------------------------- écriture
    def append(self, version: PortfolioVersion) -> dict[str, Any]:
        """Ajoute la version en bout de chaîne et renvoie son entrée d'index.

        Refuse si ``seq`` n'est pas ``dernier.seq + 1`` (0 pour la première), si ``parent_version_id`` n'est
        pas l'identifiant de la dernière version (``None`` pour la première), si le client diffère, ou si
        un fichier de cette séquence existe déjà (jamais d'écrasement). L'index est mis à jour sous
        condition d'ETag : deux écrivains concurrents ne peuvent pas avancer la même tête."""
        if version.client_id != self.client_id:
            raise HistoryError(f"client {version.client_id!r} ≠ {self.client_id!r}")
        idx, etag = self._index()
        last = idx[-1] if idx else None
        exp_seq = last["seq"] + 1 if last else 0
        exp_parent = last["version_id"] if last else None
        if version.seq != exp_seq:
            raise HistoryError(f"seq {version.seq} refusé : attendu {exp_seq}")
        if version.parent_version_id != exp_parent:
            raise HistoryError(f"parent {version.parent_version_id!r} refusé : attendu {exp_parent!r}")
        stem = self._stem(version)
        if self.store.exists(f"{stem}.json") or self.store.exists(f"{stem}.md"):
            raise HistoryError(f"version déjà écrite : {stem}.json")

        payload = version.model_dump(mode="json")
        prev_hash = last["record_hash"] if last else GENESIS
        v_hash = canonical_hash(payload)
        entry = {
            "version_id": version.version_id, "seq": version.seq, "as_of": version.as_of.isoformat(),
            "action": version.event.action, "level": version.level, "value_cad": version.value_cad,
            "drift": version.event.drift, "version_hash": v_hash, "prev_hash": prev_hash,
            "record_hash": canonical_hash({"prev": prev_hash, "version": v_hash}),
        }
        self.store.put_json(f"{stem}.json", payload, if_none_match=True)
        self.store.put_text(f"{stem}.md", render_summary(version), if_none_match=True)
        if etag is None:
            self.store.put_json(self.index_key, [*idx, entry], if_none_match=True)
        else:
            self.store.put_json(self.index_key, [*idx, entry], if_match=etag)
        return entry

    # ----------------------------------------------------------------- lecture
    def _load(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        return self.store.get_json(f"{self.prefix}{entry['seq']:04d}-{entry['as_of'][:7].replace('-', '')}.json")

    def versions(self) -> list[PortfolioVersion]:
        out = []
        for e in self.index():
            raw = self._load(e)
            if raw is None:
                raise HistoryError(f"version manquante : {e['version_id']}")
            out.append(PortfolioVersion.model_validate(raw))
        return out

    def last(self) -> PortfolioVersion | None:
        idx = self.index()
        if not idx:
            return None
        raw = self._load(idx[-1])
        return PortfolioVersion.model_validate(raw) if raw is not None else None

    def verify(self) -> tuple[bool, str | None]:
        """Recalcule la chaîne : ``(True, None)`` si intacte, sinon ``(False, version_id du premier maillon
        altéré)`` (fichier manquant ou modifié, maillon réordonné, parent ou séquence incohérents)."""
        prev, prev_id = GENESIS, None
        for i, e in enumerate(self.index()):
            vid = e.get("version_id")
            raw = self._load(e)
            if raw is None:
                return False, vid
            v_hash = canonical_hash(raw)
            if (e.get("seq") != i or e.get("prev_hash") != prev or v_hash != e.get("version_hash")
                    or canonical_hash({"prev": prev, "version": v_hash}) != e.get("record_hash")
                    or raw.get("seq") != i or raw.get("version_id") != vid
                    or raw.get("parent_version_id") != prev_id):
                return False, vid
            prev, prev_id = e["record_hash"], vid
        return True, None


def render_summary(v: PortfolioVersion) -> str:
    """Résumé Markdown d'une version (frontmatter OKF « Portfolio Version » + tableau des mouvements)."""
    ev = v.event
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    doc = okf.OkfDoc(frontmatter={
        "type": DOC_TYPE,
        "title": f"Version de portefeuille {v.version_id}",
        "description": f"Portefeuille simulé au {v.as_of.isoformat()} ({ev.action}) ; {EVENT_LABEL}.",
        "tags": ["portefeuille", "evolution", "simulation"],
        "status": "draft",
        "owners": ["alphaforge-a3"],
        "sensitivity": "client",
        "generated": {"by": "agent:A3", "at": now},
        "sources": [{"id": "version-json", "title": "PortfolioVersion complète",
                     "resource": f"{history_prefix(v.client_id)}{v.seq:04d}-{v.as_of:%Y%m}.json"}],
        "data": {"version_id": v.version_id, "seq": v.seq, "as_of": v.as_of.isoformat(), "action": ev.action,
                 "level": v.level, "value_cad": round(v.value_cad, 2), "simulation_only": True,
                 "status": v.status},
    })
    lines = [f"**{EVENT_LABEL.capitalize()}** — simulation seulement, aucun ordre ni conseil.", "",
             f"- Action : {ev.action} ; niveau : {v.level} ; valeur simulée : {v.value_cad:,.2f} CAD",
             f"- Dérive avant opération : {ev.drift:.4f} ; rotation (aller simple) : {ev.turnover_oneway:.4f}", ""]
    if ev.trades:
        lines += ["| Actif | Poids avant | Poids après | Δ | Montant (CAD) | Motif |",
                  "|---|---:|---:|---:|---:|---|"]
        lines += [f"| {t.asset_id} | {t.w_from:.4f} | {t.w_to:.4f} | {t.dw:+.4f} | {t.amount_cad:,.2f} | {t.reason} |"
                  for t in ev.trades]
    else:
        lines.append("Aucun mouvement ce mois-ci.")
    doc.body = "\n".join(lines) + "\n"
    return okf.render(doc)
