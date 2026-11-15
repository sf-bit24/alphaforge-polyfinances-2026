"""Fixtures de la recherche par experts : un faux réseau (aucune requête réelle) et des réponses types."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

import pytest

from alphaforge.collect import http


class FakeHttp:
    """Remplace ``http_get`` et ``post_json`` : routes par préfixe d'adresse, robots.txt absents (404) par défaut."""

    def __init__(self):
        self.routes: dict[str, tuple[int, str, bytes]] = {}
        self.robots: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []

    def add(self, prefix: str, body: Any, *, status: int = 200, content_type: str = "application/json") -> None:
        raw = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode()
        self.routes[prefix] = (status, content_type, raw)

    def _answer(self, url: str, method: str, allowed_hosts: Any) -> http.HttpResponse:
        self.calls.append((method, url))
        host = urllib.parse.urlsplit(url).hostname
        if allowed_hosts is not None and host not in allowed_hosts:
            raise http.FetchError(f"host not allowed: {host}", url=url)
        if url.endswith("/robots.txt"):
            if host in self.robots:
                return http.HttpResponse(
                    url=url, status=200, body=self.robots[host].encode(), content_type="text/plain"
                )
            raise http.FetchError("HTTP 404", status=404, url=url)
        for prefix in sorted(self.routes, key=len, reverse=True):
            if url.startswith(prefix):
                status, content_type, body = self.routes[prefix]
                if status >= 400:
                    raise http.FetchError(f"HTTP {status}", status=status, url=url)
                return http.HttpResponse(
                    url=url, status=status, body=body, content_type=content_type, headers={"ETag": '"x"'}
                )
        raise http.FetchError("HTTP 404", status=404, url=url)

    def get(self, url: str, *, allowed_hosts=None, **_: Any) -> http.HttpResponse:
        return self._answer(url, "GET", allowed_hosts)

    def post(self, url: str, payload: Any, *, allowed_hosts=None, **_: Any) -> http.HttpResponse:
        return self._answer(url, "POST", allowed_hosts)


@pytest.fixture
def fake_http(monkeypatch):
    fake = FakeHttp()
    monkeypatch.setattr(http, "http_get", fake.get)
    monkeypatch.setattr(http, "post_json", fake.post)
    return fake


VALET_FX = {
    "seriesDetail": {
        "FXUSDCAD": {"label": "USD/CAD", "description": "US dollar to Canadian dollar daily exchange rate"}
    },
    "observations": [
        {"d": "2026-11-11", "FXUSDCAD": {"v": "1.4012"}},
        {"d": "2026-11-12", "FXUSDCAD": {"v": "1.4031"}},
        {"d": "2026-11-13", "FXUSDCAD": {"v": "1.4257"}},
    ],
}

KALSHI_MARKET = {
    "market": {
        "ticker": "KXCBDECISIONCANADA-26DEC-H25",
        "yes_bid": 51,
        "yes_ask": 52,
        "volume": 2500000,
        "open_interest": 35661,
        "rules_primary": "If the Bank of Canada raises its target rate by 25 bps on December 9, 2026, resolves Yes.",
        "close_time": "2026-12-09T15:00:00Z",
    }
}

RSS_FEED = """<?xml version="1.0"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><title>Économie</title>
<item><title>Enbridge annonce un dividende trimestriel</title>
<link>https://ici.radio-canada.ca/nouvelle/123</link><guid>rc-123</guid>
<pubDate>Thu, 13 Nov 2026 14:00:00 GMT</pubDate><description>Résumé court.</description></item>
</channel></rss>"""
