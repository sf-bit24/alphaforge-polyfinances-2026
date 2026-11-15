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
"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass

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
DEFAULT_TIMEOUT = 12.0
DEFAULT_MAX_BYTES = 3_000_000

# GDELT demande au plus une requête toutes les cinq secondes.
_MIN_INTERVAL = {"api.gdeltproject.org": 6.0}
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


def _check_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise FetchError(f"host not allowed: {parsed.hostname}", url=url)
    return parsed.hostname


class _AllowlistRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_AllowlistRedirects)


def _gunzip(body: bytes, max_bytes: int, url: str) -> bytes:
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        data = decompressor.decompress(body, max_bytes + 1)
    except zlib.error as exc:
        raise FetchError("invalid gzip body", url=url) from exc
    if len(data) > max_bytes or decompressor.unconsumed_tail:
        raise FetchError("response too large", url=url)
    return data


def http_get(url: str, *, timeout: float = DEFAULT_TIMEOUT, max_bytes: int = DEFAULT_MAX_BYTES) -> HttpResponse:
    host = _check_url(url)
    _respect_interval(host)
    try:
        return _get_once(url, USER_AGENT, timeout, max_bytes)
    except FetchError as exc:
        fallback = FALLBACK_USER_AGENTS.get(host)
        refused = exc.status == 403 or str(exc).startswith("network error")
        if fallback is None or not refused:
            raise
        return _get_once(url, fallback, timeout, max_bytes)


def _get_once(url: str, user_agent: str, timeout: float, max_bytes: int) -> HttpResponse:
    request = urllib.request.Request(  # noqa: S310 - HTTPS seulement, hôtes en liste blanche (_check_url)
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "*/*",
            "Accept-Encoding": "gzip",
        },
    )
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise FetchError("response too large", url=url)
            if response.headers.get("Content-Encoding") == "gzip":
                body = _gunzip(body, max_bytes, url)
            return HttpResponse(
                url=url,
                status=response.status,
                body=body,
                content_type=response.headers.get("Content-Type", ""),
            )
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code}", status=exc.code, url=url) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FetchError(f"network error: {type(exc).__name__}", url=url) from exc
