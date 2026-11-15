import re
from pathlib import Path

import pytest

from alphaforge import okf
from alphaforge.tldoole.concepts import load_catalog

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
            catalog_id = doc.data.get("catalog_id")
            assert catalog_id is None or load_catalog().get(catalog_id), (path, catalog_id)
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
