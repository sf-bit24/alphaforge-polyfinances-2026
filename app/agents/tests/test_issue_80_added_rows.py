"""Issue #80, suite : une ligne ajoutée par l'investisseur sans texte d'origine n'invente pas de ``raw``.

Le contrat permet ``raw: null`` pour une position (une ligne ajoutée n'a pas de ligne écrite) et demande une
chaîne pour une ligne non résolue. Avant, ``raw_from_dict`` remplaçait un texte absent par « ? ».
"""

import pytest

from alphaforge.profile.portfolio import build_view, positions_to_raws, raw_from_dict

# Ligne ajoutée dans l'écran de vérification : une valeur déclarée, rien d'autre (vérification e2e, p8).
VALUE_ONLY = {"id": "p8", "raw": None, "ticker": None, "name": None, "market_value": 1000, "currency": None}
# Ligne ajoutée puis laissée vide : les valeurs par défaut de l'interface (blankPosition).
BLANK = {"id": "p9", "raw": None, "ticker": None, "name": None, "currency": "CAD", "account_type": "unknown"}


def test_an_added_line_without_text_keeps_no_raw_and_its_other_values():
    view = build_view(positions_to_raws([VALUE_ONLY]), status="confirmed")
    position = view["positions"][0]
    assert position["raw"] is None
    assert {key: position[key] for key in ("ticker", "name", "market_value", "currency", "value_cad", "resolved")} == {
        "ticker": None,
        "name": None,
        "market_value": 1000,
        "currency": "CAD",
        "value_cad": 1000,
        "resolved": True,
    }
    assert position["notes"] == (
        "devise supposée CAD (non précisée); titre non identifié; valeur fournie par l'investisseur"
    )
    assert view["unresolved"] == []


@pytest.mark.parametrize(
    ("item", "raw"),
    [
        ({"raw": "100 RY.TO CELI", "ticker": "RY.TO"}, "100 RY.TO CELI"),
        ({"ticker": "RY.TO", "name": "Banque Royale"}, "RY.TO Banque Royale"),
        ({"raw": "   ", "name": "fonds maison XYZ"}, "fonds maison XYZ"),
        ({"market_value": 1000}, None),
    ],
)
def test_raw_is_the_written_line_then_ticker_and_name_else_none(item, raw):
    assert raw_from_dict(item).raw == raw


def test_a_blank_added_line_does_not_become_a_position():
    raws = positions_to_raws([VALUE_ONLY, BLANK, {"id": "p10", "quantity": 5}])
    assert [raw.market_value for raw in raws] == [1000]


def test_an_unresolved_line_without_text_is_named_by_its_position_id():
    """Une ligne non résolue garde un ``raw`` texte (le contrat l'exige), comme le mock : l'id de la position."""
    euro = {"id": "p8", "raw": None, "ticker": None, "name": None, "market_value": 1000, "currency": "EUR"}
    view = build_view(positions_to_raws([euro]), status="confirmed")
    assert view["positions"][0]["raw"] is None
    assert view["unresolved"] == [{"raw": "p1", "reason": "devise non prise en charge (EUR)", "position_id": "p1"}]
