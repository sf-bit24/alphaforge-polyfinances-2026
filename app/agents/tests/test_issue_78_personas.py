"""Issue #78 : les décisions des trois profils FICTION (mêmes scénarios que les fixtures du mode ``mock``) n'ont aucun
code interne dans leurs textes français. Sauté sans numpy/pandas ni données longues (ALPHAFORGE_BT_DATA)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from alphaforge.finance.backtest.paths import long_data_available

pytestmark = pytest.mark.skipif(not long_data_available(), reason="données longues du moteur absentes")

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "finance" / "export_web_fixtures.py"
RAW = re.compile(r"(?<![\w.])(offensive|defensive|technology|energy|refuse|timeline|low_composure)(?![\w])")
NBSP = "\u00a0"


def _export_script():
    spec = importlib.util.spec_from_file_location("export_web_fixtures_78", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def responses():
    script = _export_script()
    return {persona: script.response_for(persona) for persona in script.SCENARIOS}


def french_texts(decision: dict) -> list[str]:
    """Ce que l'investisseur lit d'une Decision : libellés, valeurs texte, contrôles, contrefactuels, énoncés, trace."""
    out = [decision.get("disclaimer_fr") or ""]
    for fact in decision["facts"]:
        out.append(fact["label_fr"])
        if isinstance(fact["value"], str):
            out.append(fact["value"])
    for check in decision["constraints"]:
        out += [check["description_fr"], check["derived_from"]]
    out += [cf["change_fr"] for cf in decision["counterfactuals"]]
    out += [st["text_fr"] for section in decision["explanation"].values() for st in section]
    out += [ev["output_summary"] for ev in decision["trace"] if ev.get("output_summary")]
    return out


def test_no_raw_code_in_the_french_texts_of_a_persona_decision(responses):
    for persona, response in responses.items():
        bad = [t for t in french_texts(response["decision"]) if RAW.search(t) or re.search(r"\d%", t)]
        assert not bad, (persona, bad)


def test_amira_shows_french_values_and_lens_names(responses):
    d = responses["amira"]["decision"]
    facts = {f["fact_id"]: f for f in d["facts"]}
    assert facts["strat.style"]["value"] == "offensif"
    assert facts["strat.preference"]["value"] == "offensif"
    assert facts["emphasis.timeline"]["label_fr"] == "Poids de la lentille horizon"
    assert facts["strat.ineligible.AMZN"]["value"].startswith(f"baisse maximale longue 93{NBSP}% > 80{NBSP}%")
    assert "secteur d'emploi (technologie)" in facts["strat.ineligible.MSFT"]["value"]
    assert facts["strat.sector_cap.energy"]["label_fr"] == "plafond d'exposition au secteur de l'énergie (look-through)"
    limits = [st["text_fr"] for st in d["explanation"]["limits"]]
    assert "Objection maintenue par la lentille « diversité et préférences » au second tour." in limits


def test_robert_signal_and_refused_request_are_readable(responses):
    d = responses["robert"]["decision"]
    facts = {f["fact_id"]: f for f in d["facts"]}
    flag = facts["strat.flag.low_composure"]
    assert flag["label_fr"] == (
        "signal de comportement : faible sang-froid face aux baisses (garde-fou, jamais une allocation)"
    )
    assert "risk.cdar_m" not in flag["value"] and "risk.cdar_m" in flag["sources"][0]["processing"]
    request = [ev for ev in d["trace"] if ev["agent"] == "judge" and ev["trace_id"].endswith(":demande")]
    assert request and re.fullmatch(r"refusée ; \d+ violations? bloquantes?", request[0]["output_summary"])


def test_every_number_of_the_explanations_is_still_a_cited_fact(responses):
    from alphaforge.finance.contracts import Decision
    from alphaforge.finance.observability.verify import verify_decision

    for persona, response in responses.items():
        check = verify_decision(Decision.model_validate(response["decision"]))
        assert check.ok, (persona, [s for s in check.statements if not s["ok"]])
