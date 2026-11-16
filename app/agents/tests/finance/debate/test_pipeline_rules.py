"""Bout en bout hors ligne (mode règles) : profil → F1 → 2 tours → Judge → Decision."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

from alphaforge.finance.contracts.profile import Goal, InvestorProfile, Score
from alphaforge.finance.debate import Request, build_portfolio
from alphaforge.finance.debate.explain import verify

AS_OF = date(2026, 9, 30)


def _profile(pid="p-test", horizon=4.0, wealth=900_000, loss=120_000, tilts=()):
    return InvestorProfile(
        profile_id=pid,
        created_utc=datetime(2026, 11, 14, tzinfo=UTC),
        status="COMPLETE",
        goals=[Goal(goal_id="g1", label="retraite", priority="besoin", horizon_years=horizon)],
        tolerance_declared=Score(value=35),
        investable_wealth=wealth,
        max_acceptable_loss_cad=loss,
        knowledge_level="avance",
        preferences={"tilts": list(tilts)},
    )


def test_decision_is_valid_and_traceable():
    res = build_portfolio(_profile(), AS_OF)
    d = res.decision
    assert d.kind in ("proposition", "refus_encadre")
    assert abs(sum(p.weight for p in d.positions) - 1) < 1e-6
    assert len(res.rounds) == 2 and res.rounds[1].verdicts
    for sec in (d.explanation.data_used, d.explanation.why, d.explanation.what_would_change):
        for st in sec:
            assert not verify(type("B", (), {"facts": {f.fact_id: f for f in d.facts}})(), st), st.text_fr


def test_specific_request_outside_policy_is_framed():
    res = build_portfolio(_profile(), AS_OF, request=Request("TSLA", amount_cad=50_000))
    d = res.decision
    assert d.kind == "refus_encadre"
    w = {p.asset_id: p.weight for p in d.positions}
    assert w.get("TSLA", 0.0) < 50_000 / 900_000
    assert any(c.change_fr.startswith("Avec la demande") for c in d.counterfactuals)


def test_insisting_does_not_change_the_decision():
    ws = []
    for _ in range(3):
        d = build_portfolio(_profile(), AS_OF, request=Request("TSLA", amount_cad=50_000)).decision
        ws.append((d.kind, tuple(sorted((p.asset_id, round(p.weight, 6)) for p in d.positions))))
    assert ws[0] == ws[1] == ws[2]


def test_first_limit_gives_the_measured_window():
    """La période de la première limite est la fenêtre des mesures du portefeuille proposé, citée par ses Facts."""
    d = build_portfolio(_profile(), AS_OF).decision
    facts = {f.fact_id: f for f in d.facts}
    limit = d.explanation.limits[0]
    assert limit.fact_ids == ["r2.window.first_year", "r2.window.last_year"]
    window = re.search(r"(\d{4})-\d{2}-\d{2}\.\.(\d{4})-\d{2}-\d{2}", facts["r2.cvar_m"].sources[0].processing)
    first, last = (facts[i].value for i in limit.fact_ids)
    assert (str(first), str(last)) == window.groups()
    assert f"({first}-{last} pour les titres réels" in limit.text_fr
    assert not verify(type("B", (), {"facts": facts})(), limit)
