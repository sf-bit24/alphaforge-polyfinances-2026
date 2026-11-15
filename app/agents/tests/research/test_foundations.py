"""robots.txt (RFC 9309), lecture des réponses, localisateurs, nombres et registre des sources."""

import pytest

from alphaforge.research import documents, robots
from alphaforge.research.packs import HOSTS, PACKS, SUBJECTS, check_registry, describe_packs, pack_hosts

from .conftest import RSS_FEED, VALET_FX


# ----------------------------------------------------------------------------- robots.txt
def test_robots_wildcards_longest_match_and_allow_ties():
    parsed = robots.parse(
        """
        User-agent: *
        Disallow: /private
        Allow: /private/public$
        Disallow: /*.pdf$
        Disallow: /rss
        Allow: /rss/ok
        """
    )
    assert parsed.allowed("/index.html")
    assert not parsed.allowed("/private/x")
    assert parsed.allowed("/private/public")
    assert not parsed.allowed("/private/public/more")
    assert not parsed.allowed("/docs/report.pdf")
    assert parsed.allowed("/docs/report.pdf?x=1")
    assert not parsed.allowed("/rss/feed")
    assert parsed.allowed("/rss/ok/feed")


def test_robots_own_group_wins_and_claude_user_is_checked():
    text = """
    User-agent: *
    Disallow: /

    User-agent: AlphaForgeResearchBot
    Allow: /

    User-agent: Claude-User
    Disallow: /news/
    """
    parsed = robots.parse(text)
    assert parsed.allowed("/data")
    assert not parsed.allowed("/news/1")


def test_robots_status_rules():
    assert robots.Robots(status="unavailable").allowed("/anything")
    assert not robots.Robots(status="unreachable").allowed("/anything")
    assert robots.parse("User-agent: *\nDisallow:\n").allowed("/x")


def test_robots_cache_maps_statuses():
    cache = robots.RobotsCache(lambda url: (404, ""))
    assert cache.allowed("https://a.example/x")
    cache = robots.RobotsCache(lambda url: (503, ""))
    assert not cache.allowed("https://b.example/x")

    def boom(url):
        raise OSError("network")

    assert not robots.RobotsCache(boom).allowed("https://c.example/x")


# ----------------------------------------------------------------------------- documents
def test_detect_format_refuses_html_and_binaries():
    with pytest.raises(documents.DocumentError, match="HTML"):
        documents.detect_format("text/html; charset=utf-8", b"<html></html>")
    with pytest.raises(documents.DocumentError, match="HTML"):
        documents.detect_format("application/octet", b"<!DOCTYPE html><html>")
    with pytest.raises(documents.DocumentError, match="binaire"):
        documents.detect_format("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK\x03\x04")
    assert documents.detect_format("application/json", b"{}") == "json"
    assert documents.detect_format("text/csv", b"a,b\n1,2") == "csv"
    assert documents.detect_format("application/rss+xml", RSS_FEED.encode()) == "feed"
    assert documents.detect_format("text/xml", b"<root><a>1</a></root>") == "xml"


def test_xml_with_dtd_is_refused():
    with pytest.raises(documents.DocumentError, match="DTD"):
        documents.parse_tree(b'<!DOCTYPE x [<!ENTITY e "boom">]><x>&e;</x>', "xml")


def test_locators_on_json_csv_feed_and_xml():
    tree = documents.parse_tree(__import__("json").dumps(VALET_FX).encode(), "json")
    assert documents.scalar(documents.resolve(tree, "observations[2].FXUSDCAD.v")) == "1.4257"
    csv_tree = documents.parse_tree(b"Date Range,Value\n2026-09,101.7\n2026-10,101.8\n", "csv")
    assert documents.scalar(documents.resolve(csv_tree, 'rows[1]["Date Range"]')) == "2026-10"
    feed = documents.parse_tree(RSS_FEED.encode(), "feed")
    assert documents.scalar(documents.resolve(feed, "items[0].title")).startswith("Enbridge annonce")
    xml = documents.parse_tree(
        b'<feed xmlns:m="m"><entry><content><m:properties><m:BC_10YEAR m:type="Edm.Double">4.12</m:BC_10YEAR>'
        b"</m:properties></content></entry><entry><content><m:properties><m:BC_10YEAR>4.15</m:BC_10YEAR>"
        b"</m:properties></content></entry></feed>",
        "xml",
    )
    assert documents.scalar(documents.resolve(xml, "feed.entry[0].content.properties.BC_10YEAR")) == "4.12"
    assert documents.scalar(documents.resolve(xml, "feed.entry[1].content.properties.BC_10YEAR")) == "4.15"
    with pytest.raises(documents.DocumentError):
        documents.resolve(tree, "observations[9].d")
    with pytest.raises(documents.DocumentError):
        documents.scalar(documents.resolve(tree, "observations"))


def test_extract_rows_and_preview_paging():
    tree = documents.parse_tree(__import__("json").dumps(VALET_FX).encode(), "json")
    rows = documents.extract_rows(tree, "observations", "d", "FXUSDCAD.v")
    assert [r["value"] for r in rows] == ["1.4012", "1.4031", "1.4257"]
    first = documents.preview(tree, 0, lines=3)
    assert first["total_lines"] > 3 and first["next_offset"] == 3
    assert any("observations[0].FXUSDCAD.v = 1.4012" in line for line in documents.preview(tree, 0)["lines"])


def test_number_grounding_with_rounding_spaces_and_percentages():
    assert documents.grounded("Le taux vaut 4,2 % en 2026.", ["4.20"], ["2026/11/13"]) == []
    assert documents.grounded("Hausse de 12 % en 2026.", ["4.20"], ["2026/11/12"]) == ["12"]
    assert documents.grounded("Loyer de 1 820 $ au T2.", ["1820", "2"]) == []
    assert documents.grounded("Les marchés cotent 51 %.", ["0.51"]) == []
    assert documents.grounded("USD/CAD à 1,43.", ["1.4257"]) == []
    assert documents.grounded("USD/CAD à 1,40.", ["1.4257"]) == ["1.4"]
    assert documents.grounded("Hausse de 7 %.", ["1.4257"]) == ["7"]


# ----------------------------------------------------------------------------- registre
def test_registry_is_consistent():
    assert check_registry() == []
    assert len(SUBJECTS) == 7
    for pack in PACKS.values():
        assert all(h in HOSTS for h in pack.hosts)
    assert HOSTS["query1.finance.yahoo.com"].robots_exception is True
    assert sum(1 for h in HOSTS.values() if h.robots_exception) == 1


def test_excluded_sources_are_not_reachable():
    every_host = pack_hosts(list(PACKS))
    for banned in (
        "www.sedarplus.ca",
        "www.msci.com",
        "news.google.com",
        "feeds.finance.yahoo.com",
        "www.cboe.com",
        "cdn.cboe.com",
        "api.binance.com",
        "www.reddit.com",
        "www.wsj.com",
    ):
        assert banned not in every_host


def test_describe_packs_lists_hosts_endpoints_and_traps():
    text = describe_packs(["market-implied"])
    assert "external-api.kalshi.com" in text and "resolution rules" in text and "endpoint:" in text


def test_robots_redirects_are_followed_only_to_robots_paths():
    from alphaforge.collect import http
    from alphaforge.collect.http import FetchError

    handler = http._RobotsRedirects()
    request = __import__("urllib.request").request.Request("https://data-api.ecb.europa.eu/robots.txt")
    assert handler.redirect_request(request, None, 301, "Moved", {}, "https://data.ecb.europa.eu/robots.txt")
    for bad in (
        "https://data.ecb.europa.eu/admin",
        "http://data.ecb.europa.eu/robots.txt",
        "https://169.254.169.254/robots.txt",
    ):
        with pytest.raises(FetchError):
            handler.redirect_request(request, None, 301, "Moved", {}, bad)
    with pytest.raises(FetchError):
        http.get_robots("https://data.ecb.europa.eu/service/data")
