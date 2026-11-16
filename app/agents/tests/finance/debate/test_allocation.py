"""Répartition de l'argent (``finance/debate/allocation.py``) : calcul pur, sans données longues ni numpy.

Métadonnées réelles du jeu de départ (``data/starter/assets_universe.csv``, versionné) ; parts look-through FICTIVES
injectées (aucune lecture de ``lookthrough_us_mkt.parquet``). Les tests de bout en bout avec ``build_portfolio`` sont
dans ``test_allocation_pipeline.py`` (NEEDS_ENGINE).
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from alphaforge.finance.contracts.decision import Position
from alphaforge.finance.debate import allocation as al
from alphaforge.finance.debate.explain import verify
from alphaforge.finance.debate.facts import FactBook, fmt
from alphaforge.finance.observability.verify import verify_numbers

AS_OF = date(2026, 9, 30)
# FICTION : parts par industrie d'un FNB ventilable (somme 1), pour tester le calcul seulement.
FAKE_LT = al.Lookthrough(
    {"SPY": {"US_IND_BUSEQ": 0.4, "US_IND_MONEY": 0.1, "US_IND_SHOPS": 0.3, "US_IND_OTHER": 0.2}},
    month="2026-09-30",
)


def _positions(weights: dict[str, float]) -> list[Position]:
    return [Position(asset_id=a, weight=w, role="coeur") for a, w in weights.items()]


def _build(weights, amount=100_000.0, lt=FAKE_LT):
    book = FactBook("dec-test")
    alloc = al.allocation_breakdown(book, _positions(weights), amount, AS_OF, lookthrough_fn=lambda ids, as_of: lt)
    return book, alloc


WEIGHTS = {"SPY": 0.40, "XIU.TO": 0.10, "AGG": 0.25, "GLD": 0.10, "AAPL": 0.05, "TSLA": 0.05, "BTC-USD": 0.05}


def test_no_positions_gives_none():
    book = FactBook("dec-test")
    assert al.allocation_breakdown(book, [], 100_000.0, AS_OF, lookthrough_fn=lambda *a: FAKE_LT) is None
    assert al.breakdown([], {}, FAKE_LT, 1.0) is None
    assert not book.facts


def test_weights_sum_to_one_and_amounts():
    _, alloc = _build(WEIGHTS)
    json.dumps(alloc)  # sérialisable
    assert alloc["amount_cad"] == 100_000.0
    assert alloc["currency"] == "CAD"
    for name in ("positions", "by_class", "by_currency", "by_sector"):
        assert sum(r["weight"] for r in alloc[name]) == pytest.approx(1.0, abs=1e-9)
        for r in alloc[name]:
            assert r["amount_cad"] == round(r["weight"] * 100_000.0, 2)
    for name in ("by_class", "by_currency"):
        ws = [r["weight"] for r in alloc[name]]
        assert ws == sorted(ws, reverse=True)


def test_contract_keys():
    _, alloc = _build(WEIGHTS)
    assert set(alloc) == {
        "amount_cad",
        "currency",
        "positions",
        "by_class",
        "by_currency",
        "by_sector",
        "sector_coverage",
    }
    assert set(alloc["positions"][0]) == {
        "asset_id",
        "name",
        "asset_class",
        "class_key",
        "currency",
        "sector",
        "role",
        "weight",
        "amount_cad",
        "fact_id",
    }
    for name in ("by_class", "by_currency"):
        assert all(set(r) == {"key", "label_fr", "weight", "amount_cad", "fact_id"} for r in alloc[name])
    assert all(set(r) == {"key", "label_fr", "weight", "amount_cad", "fact_id", "basis"} for r in alloc["by_sector"])


def test_classes_currencies_and_labels():
    _, alloc = _build(WEIGHTS)
    cls = {r["key"]: r for r in alloc["by_class"]}
    assert cls["fnb_actions"]["weight"] == pytest.approx(0.50)
    assert cls["fnb_actions"]["label_fr"] == "FNB d'actions"
    assert cls["obligations"]["weight"] == pytest.approx(0.25)
    assert cls["or_matieres"]["weight"] == pytest.approx(0.10)
    assert cls["actions_individuelles"]["weight"] == pytest.approx(0.10)
    assert cls["crypto"]["weight"] == pytest.approx(0.05)
    cur = {r["key"]: r["weight"] for r in alloc["by_currency"]}
    assert cur == pytest.approx({"USD": 0.90, "CAD": 0.10})


def test_sectors_direct_lookthrough_and_non_ventile():
    _, alloc = _build(WEIGHTS)
    sec = {r["key"]: r for r in alloc["by_sector"]}
    # AAPL direct 5 % + SPY 40 % × 0,4 en look-through
    assert sec["tech"]["weight"] == pytest.approx(0.05 + 0.16)
    assert sec["tech"]["basis"] == "lookthrough"
    # TSLA direct 5 % + SPY 40 % × 0,3 (commerce French -> consommation discrétionnaire)
    assert sec["consumer_discretionary"]["weight"] == pytest.approx(0.05 + 0.12)
    assert sec["obligations"]["basis"] == "direct"
    assert sec["or_matieres"]["basis"] == "direct"
    assert sec["crypto"]["basis"] == "direct"
    # XIU.TO : aucune répartition disponible, rien n'est inventé
    assert sec["non_ventile"]["weight"] == pytest.approx(0.10)
    assert sec["non_ventile"]["basis"] == "non_ventile"
    assert alloc["by_sector"][-1]["key"] == "non_ventile"
    assert alloc["sector_coverage"] == pytest.approx(0.90)


def test_without_lookthrough_equity_etfs_are_not_split():
    _, alloc = _build(WEIGHTS, lt=al.Lookthrough({}))
    sec = {r["key"]: r for r in alloc["by_sector"]}
    assert sec["non_ventile"]["weight"] == pytest.approx(0.50)  # SPY + XIU.TO
    assert sec["tech"]["weight"] == pytest.approx(0.05) and sec["tech"]["basis"] == "direct"
    assert alloc["sector_coverage"] == pytest.approx(0.50)


def test_unknown_wealth_gives_no_amounts():
    book, alloc = _build(WEIGHTS, amount=None)
    assert alloc["amount_cad"] is None
    assert all(r["amount_cad"] is None for name in ("positions", "by_class") for r in alloc[name])
    assert all(r["fact_id"] is None for r in alloc["positions"])
    assert not any(fid.startswith("mix.amount") for fid in book.facts)


def test_unknown_asset_is_other_and_not_split():
    _, alloc = _build({"SPY": 0.5, "INCONNU": 0.5})
    cls = {r["key"]: r["weight"] for r in alloc["by_class"]}
    assert cls["autres"] == pytest.approx(0.5)
    assert {r["key"]: r["weight"] for r in alloc["by_sector"]}["non_ventile"] == pytest.approx(0.5)


def test_facts_exist_and_are_sourced():
    book, alloc = _build(WEIGHTS)
    assert book.facts["mix.amount_total"].value == 100_000.0
    for r in alloc["positions"]:
        f = book.facts[r["fact_id"]]
        assert r["fact_id"] == f"mix.amount.{r['asset_id']}"
        assert f.unit == "CAD" and f.currency == "CAD"
        assert f.value == pytest.approx(r["amount_cad"])
    assert book.facts["mix.amount.SPY"].label_fr == "Montant placé dans SPY"
    for name, prefix in (("by_class", "mix.class."), ("by_currency", "mix.currency."), ("by_sector", "mix.sector.")):
        for r in alloc[name]:
            f = book.facts[r["fact_id"]]
            assert r["fact_id"] == prefix + r["key"]
            assert f.unit == "%" and f.value == pytest.approx(r["weight"])
            datasets = {s.dataset for s in f.sources}
            assert al.STARTER_DATASET in datasets and al.POSITIONS_DATASET in datasets
            assert f.trace_id.endswith(":allocation:allocation_breakdown")
    assert book.facts["mix.class.fnb_actions"].label_fr == "Part des FNB d'actions"
    tech = book.facts["mix.sector.tech"]
    assert tech.status == "HYPOTHESE"  # part look-through : approximation
    assert al.LOOKTHROUGH_DATASET in {s.dataset for s in tech.sources}
    assert book.facts["mix.sector.obligations"].status == "FAIT"
    assert any(ev.agent == "allocation" for ev in book.trace)


def test_statement_cites_class_facts_and_verifies():
    book, alloc = _build(WEIGHTS)
    st = al.allocation_statement(book, alloc)
    assert st.text_fr.startswith("Répartition de l'argent : FNB d'actions 50,0 %, obligations et quasi-liquidités")
    assert st.fact_ids == [r["fact_id"] for r in alloc["by_class"]]
    for r in alloc["by_class"]:
        assert fmt(r["weight"], "%") in st.text_fr
    assert verify(book, st) == []
    check = verify_numbers(st.text_fr, [book.facts[f] for f in st.fact_ids])
    assert check.ok, check.unmatched


def test_kf_mapping_covers_known_sector_keys():
    assert set(al.KF_SECTOR.values()) <= set(al.SECTORS)
    assert set(al.GICS_SECTOR.values()) <= set(al.SECTORS)
    assert set(al.CLASS_SECTOR.values()) <= set(al.SECTORS)


@pytest.mark.parametrize("asset", ["SPY", "AGG", "AAPL", "XIU.TO"])
def test_single_position_shares_never_exceed_one(asset):
    """Bruit flottant du solveur (poids 1.0000000000000002) : toute part publiée reste exactement dans [0, 1]."""
    # Position(weight > 1) est refusée par le contrat : model_construct simule le bruit d'une somme de poids.
    noisy = [Position.model_construct(asset_id=asset, weight=1.0000000000000002, role="coeur", rationale_fact_ids=[])]
    book = FactBook("dec-test")
    alloc = al.allocation_breakdown(book, noisy, 103_500.00009067202, AS_OF, lookthrough_fn=lambda ids, as_of: FAKE_LT)
    assert alloc["amount_cad"] == 103_500.0
    shares = [r["weight"] for name in ("positions", "by_class", "by_currency", "by_sector") for r in alloc[name]]
    assert all(0.0 <= w <= 1.0 for w in shares)
    assert alloc["positions"][0]["weight"] == 1.0
    assert 0.0 <= alloc["sector_coverage"] <= 1.0
    for name in ("positions", "by_class", "by_currency", "by_sector"):
        for r in alloc[name]:
            assert r["amount_cad"] == round(r["amount_cad"], 2)
            assert r["weight"] == round(r["weight"], 10)
            f = book.facts[r["fact_id"]]
            assert f.value == (r["amount_cad"] if name == "positions" else r["weight"])
    st = al.allocation_statement(book, alloc)
    assert verify(book, st) == []
    assert verify_numbers(st.text_fr, [book.facts[f] for f in st.fact_ids]).ok


def test_rounding_keeps_breakdowns_summing_to_one():
    _, alloc = _build({"SPY": 1 / 3, "AGG": 1 / 3, "AAPL": 1 / 3}, amount=100_000.0)
    _, tenths = _build(
        {a: 0.1 for a in ("AAPL", "MSFT", "NVDA", "JPM", "PG", "JNJ", "XOM", "RY.TO", "TD.TO", "MFC.TO")}
    )
    assert tenths["by_class"][0]["weight"] == 1.0  # 0,1 × 10 = 0,9999999999999999 avant arrondi
    assert tenths["sector_coverage"] <= 1.0
    for name in ("positions", "by_class", "by_currency", "by_sector"):
        assert sum(r["weight"] for r in alloc[name]) == pytest.approx(1.0, abs=1e-9)
        assert all(r["weight"] == round(r["weight"], 10) for r in alloc[name])
    assert alloc["sector_coverage"] <= 1.0
