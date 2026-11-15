"""Lecture du robots.txt selon le RFC 9309 (jokers ``*`` et ``$``, règle la plus longue, Allow gagne à égalité).

``urllib.robotparser`` ignore les jokers : il ne sert pas ici. Groupes considérés, du plus précis au plus général :
le jeton du robot (``alphaforgeresearchbot``), puis ``*``. La recherche du 2026-11-15 propose aussi d'exclure un
chemin interdit à ``Claude-User`` : ce groupe, s'il existe, est vérifié en plus (règle prudente).

Statut du fichier (RFC 9309, section 2.3.1) : 2xx lu; 4xx « indisponible », tout est permis; 5xx ou réseau
« inaccessible », tout est interdit.
"""

from __future__ import annotations

import re
import threading
import time
import urllib.parse
from dataclasses import dataclass, field

PRODUCT_TOKEN = "alphaforgeresearchbot"  # noqa: S105 - jeton de robot, pas un secret
EXTRA_TOKENS = ("claude-user",)
CACHE_SECONDS = 24 * 3600
MAX_ROBOTS_BYTES = 500_000


@dataclass
class Rule:
    allow: bool
    pattern: str
    regex: re.Pattern[str]


@dataclass
class Robots:
    groups: dict[str, list[Rule]] = field(default_factory=dict)
    status: str = "parsed"  # parsed, unavailable (4xx), unreachable (5xx, réseau)

    def _rules_for(self, token: str) -> list[Rule] | None:
        return self.groups.get(token)

    def allowed(self, path: str) -> bool:
        if self.status == "unavailable":
            return True
        if self.status == "unreachable":
            return False
        primary = self._rules_for(PRODUCT_TOKEN)
        if primary is None:
            primary = self._rules_for("*") or []
        if not _decide(primary, path):
            return False
        for token in EXTRA_TOKENS:
            rules = self._rules_for(token)
            if rules is not None and not _decide(rules, path):
                return False
        return True


def _compile(pattern: str) -> re.Pattern[str]:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = "".join(".*" if ch == "*" else re.escape(ch) for ch in body)
    return re.compile("^" + regex + ("$" if anchored else ""))


def _decide(rules: list[Rule], path: str) -> bool:
    best: Rule | None = None
    for rule in rules:
        if rule.pattern == "":
            continue  # « Disallow: » vide ne bloque rien
        if rule.regex.match(path):
            if (
                best is None
                or len(rule.pattern) > len(best.pattern)
                or (len(rule.pattern) == len(best.pattern) and rule.allow and not best.allow)
            ):
                best = rule
    return True if best is None else best.allow


def parse(text: str) -> Robots:
    robots = Robots()
    current: list[str] = []
    in_rules = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if in_rules:
                current, in_rules = [], False
            token = value.lower().split("/")[0].strip()
            current.append(token)
            robots.groups.setdefault(token, [])
        elif key in ("allow", "disallow"):
            in_rules = True
            if not current:
                continue
            path = _normalize_path(value)
            for token in current:
                robots.groups[token].append(Rule(allow=key == "allow", pattern=path, regex=_compile(path)))
    return robots


def _normalize_path(value: str) -> str:
    if not value:
        return ""
    return urllib.parse.quote(urllib.parse.unquote(value), safe="/*$?=&%:@!,;+-._~")


def request_path(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    path = parts.path or "/"
    return _normalize_path(path) + (f"?{parts.query}" if parts.query else "")


class RobotsCache:
    """Cache par hôte, pour la durée de vie de la microVM (24 h au plus)."""

    def __init__(self, fetch_text):
        # fetch_text(url) -> (status_code, text); lève une exception pour une erreur réseau.
        self._fetch_text = fetch_text
        self._cache: dict[str, tuple[float, Robots]] = {}
        self._lock = threading.Lock()

    def get(self, host: str) -> Robots:
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(host)
            if cached and now - cached[0] < CACHE_SECONDS:
                return cached[1]
        try:
            status, text = self._fetch_text(f"https://{host}/robots.txt")
        except Exception:
            robots = Robots(status="unreachable")
        else:
            if 200 <= status < 300:
                robots = parse(text)
            elif 400 <= status < 500:
                robots = Robots(status="unavailable")
            else:
                robots = Robots(status="unreachable")
        with self._lock:
            self._cache[host] = (now, robots)
        return robots

    def allowed(self, url: str) -> bool:
        host = urllib.parse.urlsplit(url).hostname or ""
        return self.get(host).allowed(request_path(url))
