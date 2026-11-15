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
        if "societes" in path.parts:
            assert doc.type == "Company Fundamentals", path
            data = doc.data
            assert data["ticker"].endswith(".TO") and data["reporting_currency"] and data["unit"] == "millions", path
            source_ids = {source["id"] for source in doc.frontmatter["sources"]}
            for entry in [*data["periods"], *data["balance_sheets"]]:
                assert entry["observed_at"] <= entry["published_at"], path
                assert entry["source"] in source_ids, path
