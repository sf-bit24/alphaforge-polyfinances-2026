"""Session Web d'un chercheur : hôtes permis, robots.txt, plafonds, coupe-circuit, archive et quarantaine.

Garde-fous (Brain, « Collecte Web et presse », décisions du 2026-11-15) :
- User-Agent déclaré (``collect.http``), aucun contournement : un 401, 403, 429, 451, une coupure ou un défi
  anti-robot bloque l'hôte pour le reste de la session (« bloqué, utiliser une alternative »);
- robots.txt lu avant chaque hôte (RFC 9309), sauf exception assumée de l'équipe, notée dans le constat;
- pages HTML refusées, formats binaires refusés en phase 1;
- chaque réponse est archivée (``archive/<hôte>/<AAAA-MM-JJ>/<sha256>.json``) avec l'adresse, le statut, les
  en-têtes ``Last-Modified`` et ``ETag`` et l'heure de récupération : A6 y relit chaque valeur;
- quarantaine : un hôte proposé par un chercheur n'est lu que si son robots.txt le permet et qu'il résout vers
  une adresse publique; ses constats restent hors de la base générale jusqu'à l'approbation d'un humain.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import threading
import urllib.parse
from dataclasses import dataclass
from typing import Any

from .. import clock
from ..collect import http
from ..store import Store
from . import documents
from .packs import HOSTS
from .robots import RobotsCache, request_path

BLOCKING_STATUSES = {401, 403, 407, 429, 451}
CHALLENGE_MARKERS = (b"cf-chl", b"captcha", b"challenge-platform", b"px-captcha", b"are you a robot")
MAX_QUARANTINE_HOSTS = 2
MAX_QUARANTINE_FETCHES = 3
ARCHIVE_MAX_TEXT = 3_000_000


class WebError(Exception):
    pass


@dataclass
class Archived:
    response_id: str
    url: str
    host: str
    status: int
    content_type: str
    headers: dict[str, str]
    retrieved_at: str
    sha256: str
    fmt: str
    tree: Any
    archive_key: str
    host_status: str  # allowed, exception, quarantined, derived
    robots_ok: bool | None


@dataclass
class QuarantinedHost:
    host: str
    url: str
    why: str
    robots_status: str
    robots_allows: bool
    proposed_at: str
    fetches: int = 0


@dataclass(frozen=True)
class _Capture:
    """Réponse lue et analysée (ou résultat calculé par le code), prête pour l'archive."""

    url: str
    host: str  # hôte de la réponse, après redirection
    status: int
    content_type: str
    headers: dict[str, str]
    body: bytes
    fmt: str
    tree: Any
    host_status: str
    robots_ok: bool | None
    request_body: str | None = None


def archive_key(host: str, retrieved_at: str, digest: str) -> str:
    return f"archive/{host}/{retrieved_at[:10]}/{digest}.json"


def _archive_document(capture: _Capture, retrieved_at: str, digest: str) -> dict[str, Any]:
    """Document écrit dans l'archive : adresse, statut, en-têtes, heure de récupération et corps lu."""
    return {
        "response_id": digest[:16],
        "url": capture.url,
        "host": capture.host,
        "request_body": capture.request_body,
        "status": capture.status,
        "content_type": capture.content_type,
        "headers": capture.headers,
        "retrieved_at": retrieved_at,
        "sha256": digest,
        "format": capture.fmt,
        "host_status": capture.host_status,
        "robots_ok_at_fetch": capture.robots_ok,
        "body": capture.body.decode("utf-8-sig", errors="replace")[:ARCHIVE_MAX_TEXT],
    }


def is_public_host(host: str) -> bool:
    """Vrai si l'hôte résout uniquement vers des adresses publiques (pas de réseau interne ni de métadonnées)."""
    try:
        ipaddress.ip_address(host)
        return False  # adresse littérale refusée
    except ValueError:
        pass
    if host in ("localhost",) or host.endswith((".internal", ".local", ".localhost")):
        return False
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    addresses = {info[4][0] for info in infos}
    return bool(addresses) and all(ipaddress.ip_address(address).is_global for address in addresses)


class ResearchWeb:
    def __init__(
        self,
        *,
        store: Store,
        allowed_hosts: frozenset[str],
        robots: RobotsCache | None = None,
        resolver=is_public_host,
    ):
        self.store = store
        self.allowed = set(allowed_hosts)
        self.robots = robots or RobotsCache(self._robots_text)
        self.resolver = resolver
        self.responses: dict[str, Archived] = {}
        self.blocked: dict[str, str] = {}
        self.counts: dict[str, int] = {}
        self.quarantine: dict[str, QuarantinedHost] = {}
        self.warnings: list[str] = []
        self._lock = threading.Lock()

    # --------------------------------------------------------------- utilitaires
    def _robots_text(self, url: str) -> tuple[int, str]:
        try:
            response = http.get_robots(url)
        except http.FetchError as exc:
            if exc.status is not None:
                return exc.status, ""
            raise
        return response.status, response.text()

    def _host_of(self, url: str) -> str:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise WebError("seules les adresses https sont permises")
        return parsed.hostname

    def _permitted(self, host: str) -> str:
        if host in self.blocked:
            raise WebError(f"hôte bloqué pour cette session ({self.blocked[host]}) : utiliser une alternative")
        if host in self.allowed:
            limit = HOSTS[host].max_requests if host in HOSTS else 25
            if self.counts.get(host, 0) >= limit:
                raise WebError(f"plafond de {limit} requêtes atteint pour {host} dans cette session")
            return "exception" if host in HOSTS and HOSTS[host].robots_exception else "allowed"
        entry = self.quarantine.get(host)
        if entry is not None and entry.robots_allows:
            if entry.fetches >= MAX_QUARANTINE_FETCHES:
                raise WebError(
                    f"plafond de {MAX_QUARANTINE_FETCHES} lectures atteint pour l'hôte en quarantaine {host}"
                )
            return "quarantined"
        raise WebError(f"hôte non permis pour cette mission : {host} (proposer l'hôte avec propose_host)")

    def _block(self, host: str, reason: str) -> None:
        self.blocked[host] = reason
        self.warnings.append(f"{host} bloqué : {reason}")

    # --------------------------------------------------------------- lecture
    def fetch(self, url: str) -> Archived:
        return self._archive(self._read(url, None))

    def post_json(self, url: str, payload: Any) -> Archived:
        """POST JSON, réservé aux outils typés du code (WDS de Statistique Canada)."""
        return self._archive(self._read(url, payload))

    def read_transient(self, url: str) -> Any:
        """Lit et analyse une réponse sans l'archiver (contenu personnel lu en transit, puis jeté)."""
        return self._read(url, None).tree

    def _count_request(self, host: str, host_status: str) -> None:
        with self._lock:
            self.counts[host] = self.counts.get(host, 0) + 1
            if host_status == "quarantined":
                self.quarantine[host].fetches += 1

    def _send(self, url: str, payload: Any | None, host: str, host_status: str) -> http.HttpResponse:
        """Envoie la requête; un refus (401, 403, 407, 429, 451) ou une coupure bloque l'hôte pour la session."""
        # Une redirection ne suit que les hôtes de la mission; un hôte en quarantaine ne redirige que vers lui-même.
        allowed = {host} if host_status == "quarantined" else set(self.allowed)
        try:
            if payload is None:
                return http.http_get(url, allowed_hosts=allowed, timeout=20)
            return http.post_json(url, payload, allowed_hosts=allowed, timeout=20)
        except http.FetchError as exc:
            if exc.status in BLOCKING_STATUSES:
                self._block(host, f"HTTP {exc.status}")
            elif exc.status is None and str(exc).startswith("network error"):
                self._block(host, str(exc))
            raise WebError(f"{host} : {exc}") from exc

    def _refuse_challenge(self, host: str, response: http.HttpResponse) -> None:
        body = response.body
        if any(marker in body[:20000].lower() for marker in CHALLENGE_MARKERS) and "html" in response.content_type:
            self._block(host, "défi anti-robot")
            raise WebError(f"{host} : défi anti-robot, aucun contournement")

    def _parse(self, host: str, response: http.HttpResponse) -> tuple[str, Any]:
        """Format et arbre de la réponse; une redirection vers une page de connexion bloque l'hôte."""
        try:
            fmt = documents.detect_format(response.content_type, response.body, response.url)
            tree = documents.parse_tree(response.body, fmt)
        except documents.DocumentError as exc:
            if "connexion" in str(exc) or "login" in response.url.lower():
                self._block(host, "redirection vers une page de connexion")
            raise WebError(f"{host} : {exc}") from exc
        return fmt, tree

    def _read(self, url: str, payload: Any | None) -> _Capture:
        """Contrôles (https, hôte permis et plafond, robots.txt), requête puis analyse, dans cet ordre."""
        host = self._host_of(url)
        host_status = self._permitted(host)
        robots_ok = self.robots.allowed(url)
        if not robots_ok and host_status != "exception":
            raise WebError(f"robots.txt de {host} interdit ce chemin : source exclue")
        self._count_request(host, host_status)
        response = self._send(url, payload, host, host_status)
        self._refuse_challenge(host, response)
        final_host = urllib.parse.urlsplit(response.url).hostname or host
        fmt, tree = self._parse(host, response)
        return _Capture(
            url=url,
            host=final_host,
            status=response.status,
            content_type=response.content_type,
            headers=response.headers,
            body=response.body,
            fmt=fmt,
            tree=tree,
            host_status=host_status,
            robots_ok=robots_ok,
            request_body=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
        )

    def _archive(self, capture: _Capture) -> Archived:
        retrieved_at = clock.iso()
        digest = hashlib.sha256(
            capture.url.encode("utf-8") + b"\n" + (capture.request_body or "").encode() + b"\n" + capture.body
        ).hexdigest()
        key = archive_key(capture.host, retrieved_at, digest)
        self.store.put_json(key, _archive_document(capture, retrieved_at, digest))
        archived = Archived(
            response_id=digest[:16],
            url=capture.url,
            host=capture.host,
            status=capture.status,
            content_type=capture.content_type,
            headers=dict(capture.headers),
            retrieved_at=retrieved_at,
            sha256=digest,
            fmt=capture.fmt,
            tree=capture.tree,
            archive_key=key,
            host_status=capture.host_status,
            robots_ok=capture.robots_ok,
        )
        self.responses[archived.response_id] = archived
        return archived

    def derived(self, url: str, payload: dict[str, Any], *, host_status: str = "derived") -> Archived:
        """Archive un résultat calculé par le code (un compte de mentions), sans le contenu lu en transit."""
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        host = self._host_of(url)
        return self._archive(
            _Capture(
                url=url,
                host=host,
                status=200,
                content_type="application/json",
                headers={},
                body=body,
                fmt="json",
                tree=payload,
                host_status=host_status,
                robots_ok=True,
            )
        )

    def get(self, response_id: str) -> Archived:
        archived = self.responses.get(response_id)
        if archived is None:
            raise WebError(f"réponse inconnue : {response_id} (utiliser l'identifiant rendu par fetch)")
        return archived

    # --------------------------------------------------------------- quarantaine
    def propose_host(self, url: str, why: str) -> QuarantinedHost:
        host = self._host_of(url)
        if host in self.allowed:
            raise WebError(f"{host} est déjà permis pour cette mission")
        if host in self.quarantine:
            return self.quarantine[host]
        if len(self.quarantine) >= MAX_QUARANTINE_HOSTS:
            raise WebError(f"au plus {MAX_QUARANTINE_HOSTS} hôtes proposés par chercheur")
        if not self.resolver(host):
            raise WebError(f"{host} ne résout pas vers une adresse publique : refusé")
        robots = self.robots.get(host)
        path = request_path(url)
        entry = QuarantinedHost(
            host=host,
            url=url,
            why=" ".join(str(why).split())[:300],
            robots_status=robots.status,
            robots_allows=robots.allowed(path) and robots.status != "unreachable",
            proposed_at=clock.iso(),
        )
        self.quarantine[host] = entry
        return entry
