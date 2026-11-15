"""Tests des invariants des contrats (valeurs fictives de test, pas des données de marché)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from alphaforge.finance.contracts import Decision, InvestorProfile

NOW = datetime(2026, 11, 14, 22, 0, tzinfo=UTC)


def _profile(**over):
    base = dict(
        profile_id="p-robert", created_utc=NOW, status="COMPLETE", mode="persona", age=59,
        goals=[{"goal_id": "retraite", "label": "Financer la retraite", "priority": "besoin",
                "horizon_years": 4}],
        tolerance_declared={"value": 35, "label": "faible a moderee"},
        capacity_assessed={"value": 30, "label": "faible a moderee"},
        biases=[{"kind_label": "FOMO", "kind": "emotionnel",
                 "evidence": "veut acheter un titre tres mediatise"}],
    )
    base.update(over)
    return InvestorProfile(**base)


def _trace():
    return [{"trace_id": "t1", "agent": "quant_data", "tool": "risk_metrics", "started_utc": NOW}]


def _fact(fid="f-vol", value=0.1):
    return {"fact_id": fid, "label_fr": "Volatilité annualisée (test)", "value": value, "unit": "ratio",
            "sources": [{"dataset": "test:fixture"}], "trace_id": "t1"}


def _expl(fact_ids):
    st = [{"text_fr": "énoncé de test", "fact_ids": fact_ids}]
    return {"data_used": st, "why": st, "limits": st, "what_would_change": st}


def test_profile_ok():
    p = _profile()
    assert p.status.value == "COMPLETE"
    assert p.goals[0].priority.value == "besoin"


def test_complete_profile_cannot_have_missing_info():
    with pytest.raises(ValidationError):
        _profile(missing_info=["patrimoine"])


def test_goal_needs_horizon():
    with pytest.raises(ValidationError):
        _profile(goals=[{"goal_id": "g", "label": "x", "priority": "envie"}])


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        _profile(target_weights={"SPY": 0.5})   # aucun poids dans un profil


def test_trusted_person_requires_consent():
    with pytest.raises(ValidationError):
        _profile(trusted_person_role="fille")


def test_decision_proposal_ok():
    d = Decision(decision_id="d1", profile_id="p-robert", profile_version=1, created_utc=NOW,
                 kind="proposition",
                 positions=[{"asset_id": "A", "weight": 0.6}, {"asset_id": "B", "weight": 0.4}],
                 facts=[_fact()], explanation=_expl(["f-vol"]), trace=_trace())
    assert d.simulation_only is True


def test_explanation_cannot_cite_unknown_number():
    with pytest.raises(ValidationError, match="sans Fact"):
        Decision(decision_id="d1", profile_id="p", profile_version=1, created_utc=NOW,
                 kind="refus_encadre", facts=[_fact()], explanation=_expl(["f-inexistant"]),
                 trace=_trace())


def test_weights_must_sum_to_one():
    with pytest.raises(ValidationError, match="somment"):
        Decision(decision_id="d1", profile_id="p", profile_version=1, created_utc=NOW,
                 kind="proposition", positions=[{"asset_id": "A", "weight": 0.7}],
                 facts=[_fact()], explanation=_expl(["f-vol"]), trace=_trace())


def test_proposal_cannot_violate_blocking_constraint():
    with pytest.raises(ValidationError, match="bloquante"):
        Decision(decision_id="d1", profile_id="p", profile_version=1, created_utc=NOW,
                 kind="proposition", positions=[{"asset_id": "A", "weight": 1.0}],
                 facts=[_fact()], explanation=_expl(["f-vol"]), trace=_trace(),
                 constraints=[{"rule_id": "satellite_max", "description_fr": "test",
                               "derived_from": "profile.biases", "violated": True}])


def test_fact_must_point_to_existing_trace():
    bad = _fact() | {"trace_id": "t-absent"}
    with pytest.raises(ValidationError, match="trace_id"):
        Decision(decision_id="d1", profile_id="p", profile_version=1, created_utc=NOW,
                 kind="refus_encadre", facts=[bad], explanation=_expl(["f-vol"]), trace=_trace())


def test_simulation_flag_cannot_be_false():
    with pytest.raises(ValidationError):
        Decision(decision_id="d1", profile_id="p", profile_version=1, created_utc=NOW,
                 kind="refus_encadre", simulation_only=False, facts=[_fact()],
                 explanation=_expl(["f-vol"]), trace=_trace())
