"""Variables du profil court → StyleInputs (adaptateur pur, sûr en CI)."""

from __future__ import annotations

from alphaforge.finance.policy.from_profile_view import style_inputs_from_view
from alphaforge.finance.strategy import StyleInputs, derive_style

from ._helpers import amira


def _view(fields: dict, knowledge="intermediate"):
    return {"knowledge_level": knowledge, "dimensions": {"d": {"fields": fields}}, "facts": []}


def test_reads_short_profile_codes_without_inventing_values():
    v = _view({
        "objective.goal": "income",
        "preferences.approach": "individual_securities",
        "preferences.interests": ["dividends", "canadian_companies", "none"],
        "preferences.exclusions": ["fossil_fuels"],
        "preferences.exclusion_strictness": "absolute",
        "risk_capacity.employment_sector": "technology",
        "constraints.currency_preference": "cad_only",
        "context.amount_cad": 50000,
        "knowledge.quiz_bond_rates": "rises",
        "knowledge.self_assessment": "advanced",
        "behavior.hype_reaction": "buy_a_lot",
        "risk_tolerance.drop_reaction": "hold",
    })
    s = style_inputs_from_view(v)
    assert s.goal == "income" and s.approach == "individual_securities"
    assert s.interests == ("dividends", "canadian_companies") and s.exclusions == ("fossil_fuels",)
    assert s.employment_sector == "technology" and s.currency_preference == "cad_only" and s.amount_cad == 50000.0
    assert s.quiz == {"quiz_bond_rates": "rises"} and s.hype_reaction == "buy_a_lot"
    assert s.sell_threshold_pct is None  # absente : rien n'est inventé


def test_empty_view_gives_neutral_inputs():
    assert style_inputs_from_view(_view({})) == StyleInputs(knowledge_level="intermediate")


def test_concentrated_sector_from_existing_portfolio():
    port = {"exposures": {"flags": ["concentration_sector"], "by_sector": {"Energy": 0.55, "Financials": 0.2}}}
    s = style_inputs_from_view(_view({}), port)
    assert s.concentrated_sectors == ("Energy",)


def test_view_inputs_drive_guardrails():
    s = style_inputs_from_view(_view({"behavior.hype_reaction": "buy_a_lot", "objective.goal": "growth"}))
    d = derive_style(amira(), s)
    assert d.flags.fomo and d.shift == 0 and any("FOMO" in r for r in d.refused)
