"""Règles de validation d'A6 et écriture de la base générale."""

import pytest

from alphaforge import okf
from alphaforge.collect import staging, supervisor
from alphaforge.trace import Trace

from .conftest import ScriptedFactory


def news(item_id="news-1", **overrides):
    item = staging.new_item(
        item_id=item_id,
        kind="news",
        title="La Banque du Canada maintient son taux",
        url="https://example.com/boc?utm_source=x",
        source="Radio-Canada",
        published_at="2026-11-12T15:30:00Z",
        observed_at=None,
        retrieved_at="2026-11-14T10:00:00Z",
        language="fr",
        tickers=["RY.TO"],
        summary="La Banque du Canada a maintenu son taux directeur.",
        data={"provider": "gdelt"},
    )
    item.update(overrides)
    return item


def series(item_id="series-v39079-2026-11-12", **overrides):
    item = staging.new_item(
        item_id=item_id,
        kind="series",
        title="Taux cible : 2,25 % au 2026-11-12",
        url="https://www.bankofcanada.ca/valet/observations/V39079/json",
        source="Banque du Canada (API Valet)",
        published_at="2026-11-14T10:00:00Z",
        observed_at="2026-11-12",
        retrieved_at="2026-11-14T10:00:00Z",
        language="fr",
        tickers=[],
        summary="Dernière valeur : 2,25 %.",
        data={
            "series_id": "V39079",
            "observations": [{"date": "2026-11-12", "value": 2.25}],
            "unit": "percent",
            "frequency": "daily",
            "published_at_basis": "retrieved_at_upper_bound",
        },
    )
    item.update(overrides)
    return item


EMPTY = {"news_keys": set(), "data_keys": set(), "url_hashes": set(), "titles": set()}


@pytest.mark.parametrize(
    ("item", "reason"),
    [
        (None, "élément mal formé"),
        (news(kind="tweet"), "type d'élément inconnu"),
        (news(source=""), "source manquante"),
        (news(url="http://insecure.example.com"), "source manquante"),
        (news(published_at=None), "date de publication manquante"),
        (news(published_at="hier"), "date de publication manquante"),
        (news(retrieved_at=None), "date de récupération manquante"),
        (news(published_at="2026-11-15T00:00:00Z"), "publié après sa date de récupération"),
        (series(observed_at=None), "date d'observation manquante"),
        (
            series(observed_at="2026-11-15", published_at="2026-11-14T10:00:00Z"),
            "date d'observation postérieure à la publication",
        ),
    ],
)
def test_each_rule_rejects_with_its_reason(item, reason):
    accepted, rejected = supervisor.validate_items([("staging/r/press/x.json", item)], EMPTY)
    assert accepted == []
    assert rejected[0]["key"] == "staging/r/press/x.json" and rejected[0]["reason"].startswith(reason)


def test_valid_items_keep_both_dates_and_get_their_targets():
    accepted, rejected = supervisor.validate_items(
        [("staging/r/press/a.json", news()), ("staging/r/data/b.json", series())], EMPTY
    )
    assert rejected == []
    assert accepted[0].target.startswith("general/actualites/2026/11/la-banque-du-canada-maintient-son-taux-")
    assert accepted[1].target == "general/donnees/v39079/2026-11-12.md"


def test_duplicates_in_the_run_and_against_existing_documents():
    same_url = news("news-2", title="Autre titre", url="https://example.com/boc?utm_medium=y")
    same_title = news("news-3", url="https://other.example.com/a")
    accepted, rejected = supervisor.validate_items([("k1", news()), ("k2", same_url), ("k3", same_title)], EMPTY)
    assert [c.key for c in accepted] == ["k1"]
    assert [r["reason"] for r in rejected] == ["doublon dans la collecte : k1"] * 2
    target = accepted[0].target
    existing = {
        "news_keys": {target},
        "data_keys": {"general/donnees/v39079/2026-11-12.md"},
        "url_hashes": {target.rsplit("-", 1)[-1].removesuffix(".md")},
        "titles": {"la-banque-du-canada-maintient-son-taux"},
    }
    _, rejected = supervisor.validate_items([("k1", news()), ("k4", series())], existing)
    assert rejected[0]["reason"].startswith("doublon d'un document existant")
    assert rejected[1]["reason"] == "doublon d'un document existant : general/donnees/v39079/2026-11-12.md"


def test_curate_writes_okf_documents_and_honours_editorial_rejections(store):
    store.put_json("staging/run1/press/news-1.json", news())
    store.put_json(
        "staging/run1/press/news-9.json",
        news("news-9", title="Achetez cette action miracle", url="https://spam.example.com/x"),
    )
    store.put_json("staging/run1/data/series-1.json", series())
    store.put_json("staging/run1/data/_done.json", {"status": "ok"})
    factory = ScriptedFactory(
        [
            [
                (
                    "tool",
                    "review_items",
                    {
                        "decisions": [
                            {"id": "news-9", "decision": "reject", "reason": "contenu promotionnel"},
                            {"id": "news-1", "decision": "accept", "tags": ["taux"]},
                        ]
                    },
                )
            ],
            [("tool", "finish", {"note": "ok"})],
        ]
    )
    result = supervisor.curate(run_id="run1", store=store, trace=Trace(), model_factory=factory, model_id="m")
    assert len(result["written"]) == 2
    assert {"key": "staging/run1/press/news-9.json", "reason": "revue éditoriale : contenu promotionnel"} in result[
        "rejected"
    ]
    assert any("marqueur press absent" in w for w in result["warnings"])
    assert factory.requests[0]["effort"] == "medium"
    for key in result["written"]:
        doc = okf.parse(store.get(key).text)
        assert okf.validate(doc) == [] and doc.frontmatter["sensitivity"] == "public"
        source = doc.frontmatter["sources"][0]
        assert source["published_at"] and source["retrieved_at"]
    news_doc = okf.parse(store.get(next(k for k in result["written"] if "actualites" in k)).text)
    assert news_doc.type == "News" and "taux" in news_doc.frontmatter["tags"]
    data_doc = okf.parse(store.get("general/donnees/v39079/2026-11-12.md").text)
    assert data_doc.type == "Data Series" and data_doc.data["observed_at"] == "2026-11-12"
    assert "borne supérieure" in data_doc.body
    index = okf.parse(store.get("general/index.md").text)
    assert index.type == "Index" and index.data["counts"]["actualites"] == 1
    again = supervisor.curate(run_id="run1", store=store, trace=Trace(), model_factory=ScriptedFactory(), model_id="m")
    assert again["written"] == [] and all("doublon" in r["reason"] or "revue" in r["reason"] for r in again["rejected"])


def _sidecar(store, key):
    meta = store.get_json(okf.kb_metadata_key(key))
    assert meta is not None, key
    return {name: entry["value"] for name, entry in meta["metadataAttributes"].items()}


def test_curate_writes_a_knowledge_base_sidecar_next_to_each_document(store):
    store.put_json("staging/run3/press/news-1.json", news(tickers=["shop.to", "RY.TO"]))
    store.put_json("staging/run3/data/series-1.json", series())
    quote = series(
        "quote-btc-usd-2026-11-12",
        kind="quote",
        title="Clôture de BTC-USD",
        url="https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD",
        source="Yahoo Finance",
        published_at="2026-11-12T23:59:00Z",
        tickers=["BTC-USD"],
        data={"symbol": "BTC-USD", "closes": [{"date": "2026-11-12", "value": 1.0}], "currency": "USD"},
    )
    store.put_json("staging/run3/data/quote-1.json", quote)
    factory = ScriptedFactory([[("tool", "review_items", {"decisions": []})], [("tool", "finish", {})]])
    result = supervisor.curate(run_id="run3", store=store, trace=Trace(), model_factory=factory, model_id="m")
    assert len(result["written"]) == 3
    news_key = next(k for k in result["written"] if "actualites" in k)
    assert _sidecar(store, news_key) == {
        "type": {"type": "STRING", "stringValue": "News"},
        "ticker": {"type": "STRING", "stringValue": "SHOP.TO"},
        "kind": {"type": "STRING", "stringValue": "news"},
        "published_epoch": {"type": "NUMBER", "numberValue": okf.published_epoch("2026-11-12T15:30:00Z")},
    }
    series_meta = _sidecar(store, "general/donnees/v39079/2026-11-12.md")
    assert "ticker" not in series_meta and series_meta["kind"]["stringValue"] == "series"
    quote_meta = _sidecar(store, "general/donnees/btc-usd/2026-11-12.md")
    assert quote_meta["ticker"]["stringValue"] == "BTC-USD" and quote_meta["kind"]["stringValue"] == "quote"
    assert store.get_json("general/index.md.metadata.json") is None  # l'index n'a pas de compagnon
    index = okf.parse(store.get("general/index.md").text)
    assert index.data["counts"]["actualites"] == 1 and index.data["counts"]["donnees"] == 2
    assert ".metadata.json" not in index.body
    # Les compagnons ne comptent pas comme documents existants : la collecte suivante voit les mêmes doublons.
    existing = supervisor._existing_index(store)
    assert all(key.endswith(".md") for key in existing["news_keys"] | existing["data_keys"])


def test_curate_with_nothing_staged_writes_nothing(store):
    def no_model(**_):
        raise AssertionError("no model without candidates")

    result = supervisor.curate(run_id="empty", store=store, trace=Trace(), model_factory=no_model, model_id="m")
    assert result["written"] == [] and result["rejected"] == []
    assert len(result["warnings"]) == 2


def test_curate_survives_a_model_failure(store):
    """Sans revue éditoriale, les données (texte écrit par le code) passent, les actualités attendent."""
    from alphaforge import agentkit

    store.put_json("staging/run2/press/news-1.json", news())
    store.put_json("staging/run2/data/series-1.json", series())

    def failing_factory(**_):
        try:
            raise RuntimeError("bedrock down")
        except RuntimeError as exc:
            raise agentkit.model_error(exc, "fr") from exc

    result = supervisor.curate(run_id="run2", store=store, trace=Trace(), model_factory=failing_factory, model_id="m")
    assert result["written"] == ["general/donnees/v39079/2026-11-12.md"]
    assert result["rejected"] == [
        {"key": "staging/run2/press/news-1.json", "reason": "revue éditoriale indisponible : actualité non publiée"}
    ]
    assert any("revue éditoriale indisponible (model_error)" in w for w in result["warnings"])
