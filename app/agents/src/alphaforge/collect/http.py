"""Requêtes HTTP sortantes bornées vers des sources publiques sans clé.

- Seuls les hôtes de ``ALLOWED_HOSTS`` sont joignables, en HTTPS : les adresses sont construites par le code,
  jamais par le modèle.
- Un User-Agent générique, sans aucun renseignement personnel. FRED coupe les agents inconnus et accepte celui
  du script des organisateurs (``curl/8.0``); les autres sources reçoivent ``Mozilla/5.0 (compatible; ...)``.
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
        "query1.finance.yahoo.com",
        "feeds.finance.yahoo.com",
        "news.google.com",
        "api.gdeltproject.org",
    }
)
GENERIC_USER_AGENT = "Mozilla/5.0 (compatible; AlphaForge-AI/0.1)"
HOST_USER_AGENTS = {"fred.stlouisfed.org": "curl/8.0"}
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
    request = urllib.request.Request(  # noqa: S310 - HTTPS seulement, hôtes en liste blanche (_check_url)
        url,
        headers={
            "User-Agent": HOST_USER_AGENTS.get(host, GENERIC_USER_AGENT),
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
