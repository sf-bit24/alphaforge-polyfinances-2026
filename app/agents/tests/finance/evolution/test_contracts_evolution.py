"""Invariants des contrats de l'évolution (pydantic seulement : tourne toujours en CI, sans numpy).

Valeurs fictives de test (poids, montants) : aucune n'est tirée d'une fiche persona ni des données de marché.
"""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from alphaforge.finance.contracts.evolution import (
    EVENT_LABEL,
    ComparatorRow,
    PortfolioVersion,
    RebalanceEvent,
    Trade,
)

D = date(2022, 3, 31)


def _trade(**over) -> Trade:
    base = dict(asset_id="A", w_from=0.40, w_to=0.45, dw=0.05, amount_cad=500.0, reason="band")
    base.update(over)
    return Trade(**base)


def _event(**over) -> RebalanceEvent:
    base = dict(event_id="ev-1", month=D, action="HOLD", drift=0.0)
    base.update(over)
    return RebalanceEvent(**base)


def _version(**over) -> PortfolioVersion:
    base = dict(version_id="pv-1", parent_version_id=None, seq=0, client_id="c", profile_version=1, as_of=D,
                weights={"A": 0.6, "B": 0.4}, value_cad=100_000.0, target={"A": 0.6, "B": 0.4}, level="N3",
                policy_hash="h", data_version="test", config_hash="cfg", event=_event())
    base.update(over)
    return PortfolioVersion(**base)


def _row(**over) -> ComparatorRow:
    base = dict(name="trend_tilt", applied=False, n_trials=5, sharpe=0.4, dsr=0.6, cagr=0.05, max_drawdown=0.2,
                turnover_ann=0.3, verdict_fr="testé, non retenu")
    base.update(over)
    return ComparatorRow(**base)


# ---------------------------------------------------------------- Trade
def test_trade_dw_consistent_accepted():
    t = _trade()
    assert t.dw == pytest.approx(t.w_to - t.w_from)


@pytest.mark.parametrize("dw", [0.0, 0.06, -0.05, 0.05 + 1e-6])
def test_trade_dw_inconsistent_rejected(dw):
    with pytest.raises(ValidationError, match="dw incohérent"):
        _trade(dw=dw)


def test_trade_dw_float_noise_tolerated():
    # erreur d'arrondi flottant sous 1e-9 : acceptée
    _trade(w_from=0.1, w_to=0.3, dw=0.2)
    _trade(dw=0.05 + 5e-10)


def test_trade_reason_literal():
    with pytest.raises(ValidationError):
        _trade(reason="achat")


# ---------------------------------------------------------------- PortfolioVersion
def test_version_valid_defaults():
    v = _version()
    assert v.status == "FICTION"
    assert v.schema_version == "0.1.0"
    assert v.event.label == EVENT_LABEL == "événement de rééquilibrage illustratif"


@pytest.mark.parametrize("weights", [{"A": 0.6, "B": 0.3}, {"A": 0.7, "B": 0.4}, {"A": 1.0 + 1e-5}])
def test_version_weights_must_sum_to_one(weights):
    with pytest.raises(ValidationError, match="somme"):
        _version(weights=weights)


def test_version_weights_sum_tolerance():
    _version(weights={"A": 0.6, "B": 0.4 + 5e-7})


def test_version_negative_weight_rejected():
    with pytest.raises(ValidationError, match="négatif"):
        _version(weights={"A": 1.1, "B": -0.1})


def test_version_status_is_fiction_only():
    with pytest.raises(ValidationError):
        _version(status="FAIT")
    with pytest.raises(ValidationError):
        _version(status="HYPOTHESE")


def test_version_seq_and_value_bounds():
    with pytest.raises(ValidationError):
        _version(seq=-1)
    with pytest.raises(ValidationError):
        _version(value_cad=-1.0)
    with pytest.raises(ValidationError):
        _version(profile_version=0)


def test_version_extra_field_forbidden():
    with pytest.raises(ValidationError):
        _version(advice="acheter")


def test_version_json_round_trip():
    v = _version(event=_event(action="REBALANCE_TO_BANDS", trades=[_trade()], breaches=["A"]))
    assert PortfolioVersion.model_validate_json(v.model_dump_json()) == v


# ---------------------------------------------------------------- RebalanceEvent
def test_event_label_fixed():
    assert _event().label == "événement de rééquilibrage illustratif"
    assert _event(label="événement de rééquilibrage illustratif").label == EVENT_LABEL
    for bad in ("ordre d'achat", "recommandation", "Événement de rééquilibrage illustratif", ""):
        with pytest.raises(ValidationError):
            _event(label=bad)


@pytest.mark.parametrize("action", ["HOLD", "REBALANCE_TO_BANDS", "OVERLAY_SHIFT", "REOPTIMIZE",
                                    "REPROFILE_REQUIRED"])
def test_event_known_actions(action):
    assert _event(action=action).action == action


@pytest.mark.parametrize("action", ["BUY", "SELL", "hold", "JUDGE_RESIDUAL", "LIQUIDATE", ""])
def test_event_unknown_action_rejected(action):
    with pytest.raises(ValidationError):
        _event(action=action)


@pytest.mark.parametrize("field", ["judge_before", "judge_after"])
def test_event_judge_verdict_literal(field):
    assert getattr(_event(), field) == "non_evalue"
    with pytest.raises(ValidationError):
        _event(**{field: "ok"})


# ---------------------------------------------------------------- ComparatorRow
def test_comparator_requires_trials_and_dsr_fields():
    assert _row().n_trials == 5
    with pytest.raises(ValidationError):
        _row(n_trials=0)
    with pytest.raises(ValidationError):
        _row(n_trials=-3)
    for missing in ("n_trials", "dsr", "sharpe"):
        kw = _row().model_dump()
        kw.pop(missing)
        with pytest.raises(ValidationError):
            ComparatorRow(**kw)


def test_comparator_dsr_may_be_none_but_explicit():
    assert _row(dsr=None).dsr is None
