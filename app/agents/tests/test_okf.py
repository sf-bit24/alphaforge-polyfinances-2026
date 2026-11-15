import re
from pathlib import Path

import pytest

from alphaforge import okf

KNOWLEDGE = Path(__file__).resolve().parents[2] / "knowledge" / "general"


def sample_doc():
    return okf.new_doc(
        type="Investor Profile",
        title="Profil investisseur",
        description="Profil en cinq dimensions.",
        tags=["profil-investisseur"],
        owners=["alphaforge-a1"],
        sensitivity="client",
        generated_by="agent:A1",
        at="2026-11-14T23:10:00Z",
        status="draft",
        stale_after="2027-02-14T00:00:00Z",
        sources=[
            {
                "id": "base-q_horizon",
                "title": "Réponse à q_horizon",
                "resource": "base:q_horizon",
                "retrieved_at": "2026-11-14T23:10:00Z",
            }
        ],
        data={
            "facts": {"horizon.horizon_band": {"value": "gt10", "at": "2026-11-14T23:10:00Z"}},
            "flags": [True, False],
            "note": "yes",
            "date": "2026-11-12",
            "n": 1.5,
        },
        body="# Profil\n\nCorps « accentué » : é à ç.\n",
    )


def test_round_trip_is_lossless():
    doc = sample_doc()
    text = okf.render(doc)
    assert text.startswith("---\ntype: Investor Profile\n")
    parsed = okf.parse(text)
    assert parsed.frontmatter == doc.frontmatter
    assert parsed.body == doc.body
    assert okf.render(parsed) == text
    assert okf.validate(parsed) == []


def test_strings_that_look_like_dates_or_booleans_stay_strings():
    parsed = okf.parse(okf.render(sample_doc()))
    assert parsed.data["date"] == "2026-11-12"
    assert parsed.data["note"] == "yes"
    assert parsed.frontmatter["generated"]["at"] == "2026-11-14T23:10:00Z"


def test_unquoted_yaml_dates_are_read_as_iso_strings():
    text = (
        "---\ntype: Methodology\ntitle: T\ndescription: D\ntags: []\nstatus: stable\nowners: [x]\n"
        "sensitivity: public\ngenerated: { by: human, at: 2026-11-14T22:00:00Z }\nsources: []\n"
        "stale_after: 2027-02-14\n---\n\nCorps\n"
    )
    doc = okf.parse(text)
    assert doc.frontmatter["generated"]["at"] == "2026-11-14T22:00:00Z"
    assert doc.frontmatter["stale_after"] == "2027-02-14"
    assert doc.body == "Corps\n"


def test_validation_reports_problems():
    doc = okf.parse("---\ntype: Unknown\ntitle: T\n---\nbody\n")
    problems = okf.validate(doc)
    assert any("unknown type" in p for p in problems)
    assert any("missing key sources" in p for p in problems)


@pytest.mark.parametrize("text", ["no frontmatter", "---\ntitle: x\nno end", "---\n- a\n- b\n---\n"])
def test_parse_rejects_invalid_documents(text):
    with pytest.raises(okf.OkfError):
        okf.parse(text)


REPO = KNOWLEDGE.parents[2]
REPO_PATH = re.compile(r"((?:app|infrastructure|research)/[\w./-]+\.(?:py|yaml|md|csv|tf))")


def test_notions_cite_existing_files_under_one_id():
    """Un fichier du dépôt cité par une notion existe, et toutes les notions le citent sous le même id."""
    ids_by_path: dict[str, set[str]] = {}
    for path in sorted((KNOWLEDGE / "notions").glob("*.md")):
        for source in okf.parse(path.read_text(encoding="utf-8")).frontmatter["sources"]:
            cited = REPO_PATH.findall(source.get("resource", ""))
            for file in cited:
                assert (REPO / file).exists(), (path.name, file)
            if cited:  # le premier fichier cité identifie la source
                ids_by_path.setdefault(cited[0], set()).add(source["id"])
    assert all(len(ids) == 1 for ids in ids_by_path.values()), ids_by_path
    assert ids_by_path, "aucune notion ne cite un fichier du dépôt"


def test_seed_knowledge_documents_are_valid_public_okf():
    paths = sorted(KNOWLEDGE.rglob("*.md"))
    assert len(paths) >= 5 and not (KNOWLEDGE / "index.md").exists()  # general/index.md appartient à A6
    for path in paths:
        doc = okf.parse(path.read_text(encoding="utf-8"))
        assert okf.validate(doc) == [], path
        assert doc.frontmatter["sensitivity"] == "public", path
        if "methodologie" in path.parts:
            assert doc.type == "Methodology"
            titles = " ".join(source["title"] for source in doc.frontmatter["sources"])
            assert "BNCD" in titles or "énoncé" in titles.lower() or "jeu de départ" in titles.lower(), path
        if "notions" in path.parts:
            assert doc.type == "Financial Concept", path
            for slug in doc.data.get("related", []):
                assert (path.parent / f"{slug}.md").exists(), (path, slug)
            for link in re.findall(r"\]\(([^)#]+\.md)\)", doc.body):
                assert (path.parent / link).resolve().exists(), (path, link)
        if "societes" in path.parts:
            assert doc.type == "Company Fundamentals", path
            data = doc.data
            assert data["ticker"].endswith(".TO") and data["reporting_currency"] and data["unit"] == "millions", path
            source_ids = {source["id"] for source in doc.frontmatter["sources"]}
            for entry in [*data["periods"], *data["balance_sheets"]]:
                assert entry["observed_at"] <= entry["published_at"], path
                assert entry["source"] in source_ids, path


# --------------------------------------------------------------------------- types du volet finance et métadonnées


def _general_doc(type_, data):
    return okf.new_doc(
        type=type_,
        title="T",
        description="D",
        tags=[],
        owners=["alphaforge-a6"],
        sensitivity="public",
        generated_by="agent:A6",
        at="2026-11-14T10:00:00Z",
        data=data,
    )


def test_finance_document_types_are_declared():
    for type_ in ("Stock Features", "Portfolio Decision"):
        assert type_ in okf.DOC_TYPES
        assert okf.validate(_general_doc(type_, {})) == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SHOP.TO", "SHOP.TO"),
        ("shop.to", "SHOP.TO"),
        ("shop-to", "SHOP.TO"),
        (" ry.to ", "RY.TO"),
        ("rci-b-to", "RCI-B.TO"),
        ("btc-usd", "BTC-USD"),
        ("BRK-B", "BRK-B"),
        ("aapl", "AAPL"),
        ("^gspc", "^GSPC"),
        ("", None),
        ("pas un symbole", None),
        (None, None),
        (42, None),
    ],
)
def test_canonical_ticker(raw, expected):
    assert okf.canonical_ticker(raw) == expected


def test_published_epoch_is_utc_seconds():
    assert okf.published_epoch("2026-11-12T15:30:00Z") == 1794497400
    assert okf.published_epoch("2026-11-12T10:30:00-05:00") == 1794497400
    assert okf.published_epoch("2026-11-12") == 1794441600  # minuit UTC
    assert okf.published_epoch("hier") is None and okf.published_epoch(None) is None


def _attrs(meta):
    return {name: entry["value"] for name, entry in meta["metadataAttributes"].items()}


def test_kb_metadata_for_news_uses_the_first_ticker_and_the_publication_date():
    doc = _general_doc(
        "News", {"kind": "news", "tickers": ["shop.to", "RY.TO"], "published_at": "2026-11-12T15:30:00Z"}
    )
    key = "general/actualites/2026/11/titre-abcd1234.md"
    meta = okf.kb_metadata(key, doc.frontmatter)
    assert okf.kb_metadata_key(key) == key + ".metadata.json"
    assert _attrs(meta) == {
        "type": {"type": "STRING", "stringValue": "News"},
        "ticker": {"type": "STRING", "stringValue": "SHOP.TO"},
        "kind": {"type": "STRING", "stringValue": "news"},
        "published_epoch": {"type": "NUMBER", "numberValue": 1794497400},
    }
    assert all(entry["includeForEmbedding"] is False for entry in meta["metadataAttributes"].values())


def test_kb_metadata_for_a_macro_series_has_no_ticker():
    doc = _general_doc("Data Series", {"kind": "series", "series_id": "V39079", "published_at": "2026-11-14T10:00:00Z"})
    attrs = _attrs(okf.kb_metadata("general/donnees/v39079/2026-11-12.md", doc.frontmatter))
    assert set(attrs) == {"type", "kind", "published_epoch"}


def test_kb_metadata_for_a_quote_reads_the_symbol():
    doc = _general_doc("Data Series", {"kind": "quote", "symbol": "BTC-USD", "published_at": "2026-11-12"})
    attrs = _attrs(okf.kb_metadata("general/donnees/btc-usd/2026-11-12.md", doc.frontmatter))
    assert attrs["ticker"]["stringValue"] == "BTC-USD" and attrs["kind"]["stringValue"] == "quote"


def test_kb_metadata_for_stock_features_uses_the_latest_input_publication():
    data = {
        "ticker": "shop-to",
        "as_of": "2026-11-12",
        "features": {
            "a": {"published_at": "2026-11-10T21:00:00Z"},
            "b": {"published_at": "2026-11-12T15:30:00Z"},
            "c": {"published_at": None},
        },
    }
    attrs = _attrs(
        okf.kb_metadata(
            "general/donnees/features/shop-to/2026-11-12.md", _general_doc("Stock Features", data).frontmatter
        )
    )
    assert attrs["ticker"]["stringValue"] == "SHOP.TO"
    assert attrs["kind"]["stringValue"] == "features"
    assert attrs["published_epoch"]["numberValue"] == 1794497400


def test_kb_metadata_without_a_publication_date_omits_the_epoch():
    attrs = _attrs(okf.kb_metadata("general/methodologie/x.md", _general_doc("Methodology", {}).frontmatter))
    assert attrs == {"type": {"type": "STRING", "stringValue": "Methodology"}}


@pytest.mark.parametrize(
    "key", ["clients/abc/profil.md", "general/donnees/x/2026-11-12.json", "general/x.md.metadata.json"]
)
def test_kb_metadata_only_for_general_markdown(key):
    with pytest.raises(okf.OkfError):
        okf.kb_metadata(key, _general_doc("News", {}).frontmatter)


def test_kb_metadata_rejects_an_unknown_type():
    with pytest.raises(okf.OkfError):
        okf.kb_metadata("general/x.md", {"type": "Rumour"})
