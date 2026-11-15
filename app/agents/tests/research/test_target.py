"""Clés de la base générale : arborescence fermée (CONTRACTS.md, section 5)."""

from alphaforge.research import checks

GENERAL_FOLDERS = ("actualites", "donnees", "faits", "signaux", "depots", "recherches")


def item(kind, label, host="www.bankofcanada.ca", **extra):
    return {
        "id": f"{kind}-0123456789",
        "kind": kind,
        "title": label,
        "url": f"https://{host}/x",
        "source": "Banque du Canada",
        "published_at": "2026-11-14T21:00:00Z",
        "observed_at": "2026-11-13",
        "tickers": [],
        "data": {"label": label, "provenance": {"host": host}, "values": {"accession": "0000950170-26-000001"}},
        **extra,
    }


def test_fact_and_signal_folders_come_from_the_host_not_the_label():
    a = checks.target(item("fact", "USD/CAD au premier jour ouvrable de novembre"))
    b = checks.target(item("fact", "Taux de change américain, 13 novembre"))
    assert a == b == "general/faits/bankofcanada-ca/2026-11-13-" + a.rsplit("-", 1)[-1]
    signal = checks.target(item("signal", "Hausse de 25 pb", host="external-api.kalshi.com"))
    assert signal.startswith("general/signaux/external-api-kalshi-com/2026-11-13-")


def test_every_kind_lands_in_a_contract_folder():
    for kind in ("news", "series", "quote", "fact", "signal", "filing", "brief"):
        key = checks.target(item(kind, "Un libellé quelconque", tickers=["ENB.TO"]))
        assert key.startswith("general/") and key.split("/")[1] in GENERAL_FOLDERS, key
