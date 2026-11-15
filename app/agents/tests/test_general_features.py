"""Écriture des documents Stock Features (CONTRACTS.md, section 5) et de leur fichier compagnon (5.1)."""

import copy

import pytest

from alphaforge import okf
from alphaforge.collect import general
from alphaforge.store import ConflictError

SHA = "a" * 64


def feature(**overrides):
    value = {
        "value": 0.41,
        "unit": "ratio",
        "currency": None,
        "status": "ok",
        "observed_at": "2026-11-12",
        "published_at": "2026-11-12T21:00:00Z",
        "formula": "écart type annualisé des rendements quotidiens (adj_close), 252 séances",
        "source_key": "starter:prices_daily.csv",
        "source_sha256": SHA,
    }
    value.update(overrides)
    return value


def payload(**overrides):
    value = {
        "ticker": "shop.to",
        "as_of": "2026-11-12",
        "feature_set": "core-v1",
        "features": {
            "vol_252d": feature(),
            "last_close": feature(value=150.25, unit="price", currency="CAD", published_at="2026-11-12T20:00:00Z"),
        },
        "missing": ["beta_252d"],
        "inputs": [{"key": "starter:prices_daily.csv", "etag": '"abc"'}],
    }
    value.update(overrides)
    return value


def test_write_stock_features_writes_the_document_then_its_sidecar(store):
    key = general.write_stock_features(store, payload(), now="2026-11-14T10:00:00Z")
    assert key == "general/donnees/features/shop-to/2026-11-12.md"
    doc = okf.parse(store.get(key).text)
    assert okf.validate(doc) == [] and doc.type == "Stock Features"
    assert doc.frontmatter["sensitivity"] == "public" and doc.frontmatter["generated"]["by"] == "code:finance-features"
    assert doc.data["ticker"] == "SHOP.TO"
    assert doc.data["features"]["vol_252d"]["value"] == 0.41  # valeur reçue, jamais recalculée ni arrondie
    assert doc.data["missing"] == ["beta_252d"]
    assert doc.frontmatter["stale_after"] == "2026-12-17T00:00:00Z"
    [source] = doc.frontmatter["sources"]
    assert source["resource"] == "starter:prices_daily.csv" and source["sha256"] == SHA and source["etag"] == '"abc"'
    assert source["published_at"] == "2026-11-12T21:00:00Z"
    assert "| vol_252d | 0.41 | ratio |" in doc.body and "- beta_252d" in doc.body
    meta = store.get_json(key + ".metadata.json")
    attrs = {name: entry["value"] for name, entry in meta["metadataAttributes"].items()}
    assert attrs == {
        "type": {"type": "STRING", "stringValue": "Stock Features"},
        "ticker": {"type": "STRING", "stringValue": "SHOP.TO"},
        "kind": {"type": "STRING", "stringValue": "features"},
        "published_epoch": {"type": "NUMBER", "numberValue": okf.published_epoch("2026-11-12T21:00:00Z")},
    }


def test_stock_features_are_append_only(store):
    general.write_stock_features(store, payload())
    before = store.get("general/donnees/features/shop-to/2026-11-12.md.metadata.json").body
    changed = payload(features={"vol_252d": feature(value=0.5, published_at="2026-11-12T10:00:00Z")}, missing=[])
    with pytest.raises(ConflictError):
        general.write_stock_features(store, changed)
    assert store.get("general/donnees/features/shop-to/2026-11-12.md.metadata.json").body == before
    assert general.write_stock_features(store, payload(as_of="2026-11-13")).endswith("/2026-11-13.md")


def test_a_feature_without_value_is_allowed_when_its_status_says_so(store):
    data = payload(features={"vol_252d": feature(value=None, status="insufficient_history")})
    key = general.write_stock_features(store, data)
    assert "| vol_252d | — |" in store.get(key).text


@pytest.mark.parametrize(
    ("mutate", "problem"),
    [
        (lambda p: p.update(ticker="pas un symbole"), "ticker is missing"),
        (lambda p: p.update(as_of="12/11/2026"), "as_of must be"),
        (lambda p: p.update(as_of="2026-02-30"), "as_of must be"),
        (lambda p: p.update(feature_set="Core V1"), "feature_set must match"),
        (lambda p: p.update(extra=1), "unknown keys ['extra']"),
        (lambda p: p["features"].update({"Vol": feature()}), "feature name 'Vol'"),
        (lambda p: p["features"]["vol_252d"].pop("formula"), "misses ['formula']"),
        (lambda p: p["features"]["vol_252d"].update(note="x"), "unknown keys ['note']"),
        (lambda p: p["features"]["vol_252d"].update(value="0.41"), "finite number or null"),
        (lambda p: p["features"]["vol_252d"].update(value=float("nan")), "finite number or null"),
        (lambda p: p["features"]["vol_252d"].update(value=True), "finite number or null"),
        (lambda p: p["features"]["vol_252d"].update(value=None), "status ok needs a value"),
        (lambda p: p["features"]["vol_252d"].update(currency="cad"), "three-letter code"),
        (lambda p: p["features"]["vol_252d"].update(observed_at="2026-11-13"), "observed_at is after published_at"),
        (lambda p: p["features"]["vol_252d"].update(published_at="2026-11-13T00:00:00Z"), "look-ahead"),
        (lambda p: p["features"]["vol_252d"].update(published_at="hier"), "published_at is missing"),
        (lambda p: p["features"]["vol_252d"].update(source_sha256="ABC"), "64 lowercase hexadecimal"),
        (lambda p: p["features"]["vol_252d"].update(source_key="s3:autre.csv"), "not listed in inputs"),
        (lambda p: p["features"]["last_close"].update(source_sha256="b" * 64), "several sha256"),
        (lambda p: p.update(missing=["vol_252d"]), "never repeat a computed feature"),
        (lambda p: p.update(features={}, missing=[]), "both empty"),
        (lambda p: p.update(inputs=[{"key": "starter:prices_daily.csv"}]), "inputs[0] must be {key, etag}"),
    ],
)
def test_invalid_stock_features_are_refused_with_their_reason(store, mutate, problem):
    data = copy.deepcopy(payload())
    mutate(data)
    with pytest.raises(general.FeaturesError) as excinfo:
        general.write_stock_features(store, data)
    assert any(problem in p for p in excinfo.value.problems), excinfo.value.problems
    assert store.list("general/", limit=10) == []


def test_write_document_refuses_an_invalid_okf_document(store):
    doc = okf.new_doc(
        type="Rumour",
        title="T",
        description="D",
        tags=[],
        owners=["x"],
        sensitivity="public",
        generated_by="agent:A6",
        at="2026-11-14T10:00:00Z",
    )
    with pytest.raises(okf.OkfError):
        general.write_document(store, "general/donnees/x/2026-11-12.md", doc)
    assert store.list("general/", limit=10) == []
