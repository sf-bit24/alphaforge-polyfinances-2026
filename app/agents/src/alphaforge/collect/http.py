"""Requêtes HTTP sortantes bornées vers des sources publiques sans clé.

- Seuls les hôtes de ``ALLOWED_HOSTS`` sont joignables, en HTTPS : les adresses sont construites par le code,
  jamais par le modèle.
- Un User-Agent déclaré, qui nomme le robot et renvoie au dépôt, sans aucun renseignement personnel ni User-Agent
  de navigateur. FRED l'accepte (test du 2026-11-15); ``curl/8.0``, celui du script des organisateurs, ne sert qu'en
  repli, une seule fois, si FRED refuse la requête (403 ou coupure).
- Aucun contournement : un refus (403, 429, défi, coupure) remonte comme ``FetchError`` et l'agent passe à une
  autre source. Les hôtes dont le robots.txt interdit les chemins lus sont retirés de la liste, sauf
  ``query1.finance.yahoo.com``, gardé par exception assumée de l'équipe (Brain, « Collecte Web et presse »).
- Délai et taille de réponse bornés (y compris après décompression); aucun cookie, aucun identifiant.
- Une redirection n'est suivie que vers un hôte de la liste, en HTTPS.
- Les agents de recherche (``alphaforge.research``) passent leur propre liste d'hôtes (``allowed_hosts``), plus
  étroite que ou différente de ``ALLOWED_HOSTS`` : la redirection est vérifiée contre cette même liste.
- ``post_json`` ne sert qu'aux méthodes de métadonnées de Statistique Canada, appelées par le code.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections.abc import Iterable
from dataclasses import dataclass, field

ALLOWED_HOSTS = frozenset(
    {
        "www.bankofcanada.ca",
        "fred.stlouisfed.org",
        # Exception assumée : le robots.txt de cet hôte dit « Disallow: / » (vérifié le 2026-11-15).
        "query1.finance.yahoo.com",
        "api.gdeltproject.org",
        "www.newswire.ca",
        "www.prnewswire.com",
    }
)
USER_AGENT = "AlphaForgeResearchBot/0.1 (+https://github.com/sf-bit24/alphaforge-polyfinances-2026)"
FALLBACK_USER_AGENTS = {"fred.stlouisfed.org": "curl/8.0"}
# La SEC exige un courriel de contact dans le User-Agent (« fair access ») : sans ALPHAFORGE_CONTACT_EMAIL,
# ses hôtes répondent 403 et la source est déclarée bloquée. Aucun courriel n'est inventé.
SEC_HOSTS = frozenset({"www.sec.gov", "data.sec.gov", "efts.sec.gov"})
DEFAULT_TIMEOUT = 12.0
DEFAULT_MAX_BYTES = 3_000_000

# Intervalle minimal entre deux requêtes vers un même hôte (secondes), d'après les règles publiées des sources.
_MIN_INTERVAL = {
    "api.gdeltproject.org": 6.0,  # « one every 5 seconds »
    "www.sec.gov": 0.12,  # 10 requêtes par seconde au plus
    "data.sec.gov": 0.12,
    "wikimedia.org": 0.35,  # 200 requêtes par minute avec un User-Agent identifié
    "sdmx.oecd.org": 3.0,
    "www150.statcan.gc.ca": 0.05,  # 25 requêtes par seconde par IP
    "hn.algolia.com": 0.5,
    "api.bsky.app": 0.2,
    "api.kraken.com": 1.0,
}
_last_call: dict[str, float] = {}
_interval_lock = threading.Lock()


class FetchError(Exception):
    def __init__(self, message: str, *, status: int | None = None, url: str | None = None):
        super().__init__(message)
        self.status = status
        self.url = url


@dataclass(frozen=True)
class HttpResponse:
    url: str
    status: int
    body: bytes
    content_type: str
    headers: dict[str, str] = field(default_factory=dict)

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def _respect_interval(host: str) -> None:
    interval = _MIN_INTERVAL.get(host)
    if not interval:
        return
    with _interval_lock:
        wait = _last_call.get(host, 0.0) + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[host] = time.monotonic()


def _check_url(url: str, allowed: Iterable[str] | None = None) -> str:
    parsed = urllib.parse.urlsplit(url)
    hosts = ALLOWED_HOSTS if allowed is None else allowed
    if parsed.scheme != "https" or not parsed.hostname or parsed.hostname not in hosts:
        raise FetchError(f"host not allowed: {parsed.hostname}", url=url)
    if parsed.username or parsed.password or (parsed.port not in (None, 443)):
        raise FetchError("credentials or non-standard port not allowed", url=url)
    return parsed.hostname


class _AllowlistRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed: Iterable[str] | None = None):
        super().__init__()
        self.allowed = None if allowed is None else frozenset(allowed)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_url(newurl, self.allowed)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_AllowlistRedirects())


class _RobotsRedirects(urllib.request.HTTPRedirectHandler):
    """robots.txt : jusqu'à cinq redirections suivies, vers tout hôte HTTPS nommé, chemin /robots.txt seulement
    (RFC 9309, section 2.3.1.2)."""

    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or parsed.path != "/robots.txt" or not host or host.replace(".", "").isdigit():
            raise FetchError(f"robots.txt redirect not allowed: {newurl}", url=newurl)
        if ":" in host:
            raise FetchError("robots.txt redirect to an IP address", url=newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_ROBOTS_OPENER = urllib.request.build_opener(_RobotsRedirects())


def get_robots(url: str, *, timeout: float = 8.0, max_bytes: int = 500_000) -> HttpResponse:
    """Lit le robots.txt d'un hôte permis par l'appelant, en suivant ses redirections (RFC 9309)."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.path != "/robots.txt" or not parsed.hostname:
        raise FetchError("not a robots.txt URL", url=url)
    _respect_interval(parsed.hostname)
    return _send(_ROBOTS_OPENER, url, USER_AGENT, timeout, max_bytes)


def _opener(allowed: Iterable[str] | None) -> urllib.request.OpenerDirector:
    return _OPENER if allowed is None else urllib.request.build_opener(_AllowlistRedirects(allowed))


def _gunzip(body: bytes, max_bytes: int, url: str) -> bytes:
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        data = decompressor.decompress(body, max_bytes + 1)
    except zlib.error as exc:
        raise FetchError("invalid gzip body", url=url) from exc
    if len(data) > max_bytes or decompressor.unconsumed_tail:
        raise FetchError("response too large", url=url)
    return data


def user_agent_for(host: str) -> str:
    """User-Agent déclaré; la SEC reçoit en plus le courriel de contact s'il est configuré."""
    contact = (os.environ.get("ALPHAFORGE_CONTACT_EMAIL") or "").strip()
    if host in SEC_HOSTS and contact:
        return f"{USER_AGENT} {contact}"
    return USER_AGENT


def http_get(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    allowed_hosts: Iterable[str] | None = None,
) -> HttpResponse:
    host = _check_url(url, allowed_hosts)
    _respect_interval(host)
    opener = _opener(allowed_hosts)
    try:
        return _send(opener, url, user_agent_for(host), timeout, max_bytes)
    except FetchError as exc:
        fallback = FALLBACK_USER_AGENTS.get(host)
        refused = exc.status == 403 or str(exc).startswith("network error")
        if fallback is None or not refused:
            raise
        return _send(opener, url, fallback, timeout, max_bytes)


def post_json(
    url: str,
    payload: object,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    allowed_hosts: Iterable[str] | None = None,
) -> HttpResponse:
    """POST JSON, réservé aux méthodes de lecture qui l'exigent (WDS de Statistique Canada)."""
    host = _check_url(url, allowed_hosts)
    _respect_interval(host)
    data = json.dumps(payload).encode("utf-8")
    return _send(_opener(allowed_hosts), url, user_agent_for(host), timeout, max_bytes, data=data)


def _get_once(url: str, user_agent: str, timeout: float, max_bytes: int) -> HttpResponse:
    """Compatibilité : une requête GET avec la liste d'hôtes par défaut."""
    return _send(_OPENER, url, user_agent, timeout, max_bytes)


_KEPT_HEADERS = ("Last-Modified", "ETag", "Date", "Content-Type", "Retry-After", "Location")


def _send(
    opener: urllib.request.OpenerDirector,
    url: str,
    user_agent: str,
    timeout: float,
    max_bytes: int,
    *,
    data: bytes | None = None,
) -> HttpResponse:
    headers = {"User-Agent": user_agent, "Accept": "*/*", "Accept-Encoding": "gzip"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(  # noqa: S310 - HTTPS seulement, hôtes en liste blanche (_check_url)
        url, data=data, headers=headers, method="POST" if data is not None else "GET"
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise FetchError("response too large", url=url)
            if response.headers.get("Content-Encoding") == "gzip":
                body = _gunzip(body, max_bytes, url)
            kept = {name: response.headers[name] for name in _KEPT_HEADERS if response.headers.get(name)}
            final_url = response.geturl() if hasattr(response, "geturl") else url
            return HttpResponse(
                url=final_url or url,
                status=response.status,
                body=body,
                content_type=response.headers.get("Content-Type", ""),
                headers=kept,
            )
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code}", status=exc.code, url=url) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FetchError(f"network error: {type(exc).__name__}", url=url) from exc
