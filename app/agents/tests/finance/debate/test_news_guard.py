"""Garde des actualités dans la fusion des amendements (pur, en CI) : une nouvelle se signale, ne change jamais le
mandat."""

from __future__ import annotations

from alphaforge.finance.debate.merge import NEWS_REJECT_FR, apply_amendments
from alphaforge.finance.debate.schemas import Amendment, LensReport

from ..strategy._helpers import make_comp

NEWS = "okf.news.NVDA.1"
FUND = "okf.fund.ATD.TO.revenue"
RISK = "r1.cvar_m"
KNOWN = {NEWS, FUND, RISK, f"{NEWS}#42"}


def _merge(*amendments, lens="diversity"):
    policy = make_comp().policy
    rep = LensReport(lens=lens, amendments=list(amendments))
    return policy, *apply_amendments(policy, [rep], {lens: 1.0}, KNOWN)


def _am(kind, target, evidence, value=None):
    return Amendment(kind=kind, target=target, value=value, reason_fr="test", evidence_fact_ids=evidence)


def test_any_mandate_change_citing_news_is_rejected():
    cases = [
        _am("tighten_limit", "risk.cvar_m", [NEWS], 0.05),
        _am("cap_group", "exp.tech", [RISK, NEWS], 0.30),
        _am("exclude_asset", "NVDA", [NEWS]),
        _am("switch_risk_measure", "CDAR", [NEWS]),
        _am("require_min_group", "alloc.growth", [f"{NEWS}#42"], 0.65),  # suffixe d'unicité du FactBook
    ]
    for a in cases:
        before, after, log = _merge(a, lens="constraints")
        assert [x.status for x in log] == ["rejete"], a
        assert log[0].why_fr == NEWS_REJECT_FR
        assert after.model_dump() == before.model_dump()


def test_flag_only_citing_news_stays_allowed():
    before, after, log = _merge(_am("flag_only", "NVDA", [NEWS]))
    assert [x.status for x in log] == ["applique"] and log[0].why_fr == "signalement, sans changement"
    assert after.model_dump() == before.model_dump()


def test_same_change_without_news_is_applied():
    _, after, log = _merge(_am("tighten_limit", "risk.cvar_m", [RISK, FUND], 0.05), lens="risk")
    assert [x.status for x in log] == ["applique"]
    assert next(lim for lim in after.limits if lim.rule_id == "risk.cvar_m").max == 0.05
