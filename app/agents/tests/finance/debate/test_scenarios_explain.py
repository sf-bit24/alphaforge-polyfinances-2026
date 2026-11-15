"""Explicabilité des scénarios (outil scenario_risk branché sur l'étape d'explication), sans réseau ni Bedrock.

Table FICTIVE (tests/finance/_scenario_fixture.py) ; le mode LLM utilise le modèle scripté de tests/conftest.py.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")
pytest.importorskip("strands")

from alphaforge.finance.backtest.paths import long_data_available  # noqa: E402
from alphaforge.finance.contracts import Decision, Explanation, PolicySpec, Statement  # noqa: E402
from alphaforge.finance.debate import scenarios as ds  # noqa: E402
from alphaforge.finance.debate.facts import FactBook  # noqa: E402
from alphaforge.finance.observability.verify import verify_decision  # noqa: E402
from alphaforge.finance.portfolio import scenario_risk as sr  # noqa: E402
from alphaforge.scenarios.tool import ScenarioRiskTool  # noqa: E402
from alphaforge.scenarios.tool_table import ScenarioTableLoader  # noqa: E402
from alphaforge.store.local import LocalStore  # noqa: E402
from alphaforge.store.s3 import S3Store  # noqa: E402

from ... import conftest as root  # noqa: E402
from .. import _scenario_fixture as fx  # noqa: E402

NOW = datetime(2026, 11, 15, tzinfo=UTC)
UNIVERSE = ["XIU.TO", "SPY", "XBB.TO", "ZST.TO", "GLD", "NVDA"]
H3 = fx.fid("FICTIF_a", 3, "p_loss_gt_10")


def policy(*limits) -> PolicySpec:
    return PolicySpec(
        policy_id="t", profile_id="t", profile_version=1, created_utc=NOW, universe=UNIVERSE, limits=list(limits)
    )


PROB = sr.prob_loss_limit("pl", alpha=0.10, loss_level=0.10, horizon_years=3, derived_from="test:generique")


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("ALPHAFORGE_SCENARIOS", raising=False)
    sr.set_table_provider(None)
    yield
    sr.set_table_provider(None)


@pytest.fixture
def tool(tmp_path):
    store = LocalStore(tmp_path / "kb")
    fx.publish(store)
    sr.set_table_provider(lambda run_id: ScenarioTableLoader(store, run_id=run_id).load())
    return ScenarioRiskTool(sr.SafeTableLoader())


def decision(book: FactBook, sections) -> Decision:
    expl = Explanation(**{k: [Statement(text_fr="Gabarit.", fact_ids=[])] + v for k, v in sections.items()})
    return Decision(
        decision_id="dec-s",
        profile_id="t",
        profile_version=1,
        created_utc=NOW,
        kind="proposition",
        positions=[{"asset_id": a, "weight": w} for a, w in fx.WEIGHTS.items()],
        facts=list(book.facts.values()),
        explanation=expl,
        trace=book.trace or _seed(book),
    )


def _seed(book):
    with book.step("seed"):
        pass
    return book.trace


def cited(sections) -> set[str]:
    return {i for v in sections.values() for st in v for i in st.fact_ids}


def test_rules_mode_cites_tool_facts_merged_into_the_decision(tool):
    book = FactBook("dec-s")
    sections, report = ds.explain_scenarios(book, ds.ScenarioContext(fx.WEIGHTS, policy(PROB), tool=tool))
    ids = cited(sections)
    assert H3 in ids and ids <= set(book.facts) and report == []
    step = next(t for t in book.trace if t.agent == ds.AGENT and t.tool == "scenario_risk")
    tool_trace = next(t for t in book.trace if t.agent == "scenarios")
    assert tool_trace.parent_id == step.trace_id and book.facts[H3].trace_id == tool_trace.trace_id
    d = decision(book, sections)  # Decision._integrity : chaque fact_id cité existe, chaque Fact a sa trace
    chk = verify_decision(d)  # chaque nombre écrit vient d'un Fact cité
    assert chk.ok, [r for r in chk.statements if not r["ok"]]


@pytest.mark.parametrize("case", ["absent", "denied", "disabled"])
def test_unavailable_scenarios_add_one_limitation_and_never_raise(tmp_path, monkeypatch, case):
    if case == "absent":
        sr.set_table_provider(lambda run_id: ScenarioTableLoader(LocalStore(tmp_path / "e"), run_id=run_id).load())
    elif case == "denied":
        s3 = S3Store("bucket-fictif", region="us-east-1", client=fx.DeniedS3())
        sr.set_table_provider(lambda run_id: ScenarioTableLoader(s3, run_id=run_id).load())
    else:
        monkeypatch.setenv("ALPHAFORGE_SCENARIOS", "off")

    def no_llm(*a, **k):
        raise AssertionError("aucun appel au modèle quand les scénarios sont indisponibles")

    book = FactBook("dec-s")
    context = ds.ScenarioContext(fx.WEIGHTS, policy(), mode="llm", model_factory=no_llm)
    sections, report = ds.explain_scenarios(book, context)
    assert [len(v) for v in sections.values()] == [0, 0, 1, 0]
    (st,) = sections["limits"]
    assert "scénarios indisponibles" in st.text_fr and st.fact_ids == [] and st.label == "HYPOTHESE"
    assert {"absent": "absent", "denied": "AccessDenied", "disabled": "désactivés"}[case] in st.text_fr
    assert "bucket-fictif" not in st.text_fr and not book.facts
    assert book.trace[-1].status == "refus"
    assert verify_decision(decision(book, sections)).ok


def test_unmapped_holding_is_a_limitation(tool):
    book = FactBook("dec-s")
    w = {**fx.WEIGHTS, "XBB.TO": 0.40, "NVDA": 0.05}
    sections, _ = ds.explain_scenarios(book, ds.ScenarioContext(w, policy(), tool=tool))
    (st,) = sections["limits"]
    assert "NVDA" in st.text_fr and not tool.ledger
    assert verify_decision(decision(book, sections)).ok


def test_strands_tool_is_registered_and_absorbs_facts(tool):
    book = FactBook("dec-s")
    t = ds.strands_tool(book, tool)
    assert t.tool_name == "scenario_risk"
    out = t(
        weights=dict(CA_EQ=0.15, US_MKT=0.25, BONDS=0.45, CASH=0.10, GOLD=0.05),
        horizon_years=3,
        loss_threshold_cad=0.10,
        amount_cad=1.0,
    )
    assert H3 in out and H3 in book.facts


def _llm_script(notes):
    call = {
        "weights": {"CA_EQ": 0.15, "US_MKT": 0.25, "BONDS": 0.45, "CASH": 0.10, "GOLD": 0.05},
        "horizon_years": 3,
        "loss_threshold_cad": 0.10,
        "amount_cad": 1.0,
    }
    return [[("tool", "scenario_risk", call)], [("tool", "ScenarioNotes", {"notes": notes})]]


def test_llm_explainer_has_the_tool_and_only_grounded_sentences_are_kept(tool):
    good = {
        "section": "why",
        "label": "HYPOTHESE",
        "fact_ids": [H3, H3 + ".ci_lo", H3 + ".ci_hi"],
        "text_fr": "Selon le modèle fictif A, une perte au-delà du seuil arrive dans 4 % des trajectoires "
        "(intervalle : 2 % à 6 %) ; c'est un modèle, pas une prévision.",
    }
    invented = {**good, "text_fr": "Une perte arrive dans 37 % des cas."}
    unknown = {**good, "fact_ids": ["scn.inconnu"]}
    model = root.ScriptedModel(_llm_script([good, invented, unknown]))
    book = FactBook("dec-s")
    context = ds.ScenarioContext(
        fx.WEIGHTS, policy(PROB), mode="llm", tool=tool, model_factory=lambda model_id, node_id: model
    )
    sections, report = ds.explain_scenarios(book, context)
    assert "scenario_risk" in model.calls[0]["tools"]
    assert [st.text_fr for st in sections["why"]] == [good["text_fr"]]
    assert len(report) == 2 and "37" in report[0] and "inconnu" in report[1]
    assert any(t.agent == ds.AGENT and t.tool == "scenario_risk" for t in book.trace)
    assert verify_decision(decision(book, sections)).ok


def test_llm_failure_falls_back_to_tool_template(tool):
    def broken(model_id, node_id):
        raise RuntimeError("Bedrock indisponible")

    book = FactBook("dec-s")
    context = ds.ScenarioContext(fx.WEIGHTS, policy(PROB), mode="llm", tool=tool, model_factory=broken)
    sections, report = ds.explain_scenarios(book, context)
    assert H3 in cited(sections) and "abandonnée" in report[0]


def test_attach_is_inactive_without_prob_loss_and_never_reads_the_table():
    def boom(run_id):
        raise AssertionError("table lue sans limite PROB_LOSS")

    sr.set_table_provider(boom)
    book = FactBook("dec-s")
    expl = Explanation(data_used=[], why=[], limits=[], what_would_change=[])
    context = ds.ScenarioContext(fx.WEIGHTS, policy())
    assert ds.attach_scenarios(book, expl, context) is expl and not book.trace and not book.facts
    assert ds.attach_scenarios(book, expl, ds.ScenarioContext(fx.WEIGHTS, policy(PROB)), enabled=False) is expl


def test_attach_with_prob_loss_adds_sections_under_one_step(tool):
    book = FactBook("dec-s")
    expl = Explanation(data_used=[Statement(text_fr="Gabarit.", fact_ids=[])], why=[], limits=[], what_would_change=[])
    out = ds.attach_scenarios(book, expl, ds.ScenarioContext(fx.WEIGHTS, policy(PROB), tool=tool))
    assert out.data_used[0].text_fr == "Gabarit." and H3 in cited({k: getattr(out, k) for k in ds.SECTIONS})
    parent = book.trace[0]
    assert parent.agent == ds.AGENT and parent.tool is None and parent.status == "ok"
    assert all(t.parent_id is not None for t in book.trace[1:])


def test_attach_never_raises(monkeypatch):
    def broken(book, context):
        raise RuntimeError("panne")

    monkeypatch.setattr(ds, "explain_scenarios", broken)
    book = FactBook("dec-s")
    expl = Explanation(data_used=[], why=[], limits=[], what_would_change=[])
    assert ds.attach_scenarios(book, expl, ds.ScenarioContext(fx.WEIGHTS, policy()), enabled=True) == expl
    (step,) = book.trace
    assert step.status == "erreur" and step.message == "scénarios abandonnés : RuntimeError"


def _strip_times(x):
    if isinstance(x, dict):
        return {k: None if k.endswith("_utc") else _strip_times(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_strip_times(v) for v in x]
    return x


@pytest.mark.skipif(not long_data_available(), reason="données longues du moteur absentes")
def test_pipeline_default_without_prob_loss_is_unchanged(tmp_path, monkeypatch):
    from alphaforge.finance.debate import build_portfolio

    from ..policy import _personas as P

    store = tmp_path / "kb"
    fx.publish(LocalStore(store))  # table publiée et lisible : sans PROB_LOSS, elle n'est pas lue pour autant
    monkeypatch.setenv("ALPHAFORGE_STORE", "local")
    monkeypatch.setenv("ALPHAFORGE_LOCAL_DIR", str(store))
    auto = build_portfolio(P.mateo(), P.AS_OF, decision_id="dec-auto").decision
    off = build_portfolio(P.mateo(), P.AS_OF, decision_id="dec-auto", scenarios=False).decision
    assert _strip_times(auto.model_dump(mode="json")) == _strip_times(off.model_dump(mode="json"))
    assert not any(t.agent == ds.AGENT for t in auto.trace) and not any(
        f.fact_id.startswith("scn.") for f in auto.facts
    )


@pytest.mark.skipif(not long_data_available(), reason="données longues du moteur absentes")
def test_pipeline_forced_reports_unavailable_scenarios(tmp_path, monkeypatch):
    from alphaforge.finance.debate import build_portfolio

    from ..policy import _personas as P

    monkeypatch.setenv("ALPHAFORGE_STORE", "local")
    monkeypatch.setenv("ALPHAFORGE_LOCAL_DIR", str(tmp_path / "empty"))
    d = build_portfolio(P.mateo(), P.AS_OF, scenarios=True).decision
    assert any("scénarios indisponibles" in st.text_fr for st in d.explanation.limits)
    assert verify_decision(d).ok


@pytest.mark.skipif(not long_data_available(), reason="données longues du moteur absentes")
def test_pipeline_activates_with_a_declared_prob_loss_limit(tmp_path, monkeypatch):
    from alphaforge.finance.debate import build_portfolio
    from alphaforge.finance.policy import compile_profile

    from ..policy import _personas as P

    def with_prob_loss(profile, as_of):  # mandat GÉNÉRIQUE de test : α, L et H arbitraires, limite non bloquante
        comp = compile_profile(profile, as_of)
        extra = sr.prob_loss_limit(
            "pl.test", alpha=0.10, loss_level=0.10, horizon_years=3, derived_from="test:generique", blocking=False
        )
        comp.policy = comp.policy.model_copy(update={"limits": [*comp.policy.limits, extra]})
        return comp

    monkeypatch.setenv("ALPHAFORGE_STORE", "local")
    monkeypatch.setenv("ALPHAFORGE_LOCAL_DIR", str(tmp_path / "empty"))
    res = build_portfolio(P.mateo(), P.AS_OF, compile_fn=with_prob_loss)
    d = res.decision
    check = next(c for c in d.constraints if c.rule_id == "pl.test:max")
    assert check.violated and not check.blocking  # non vérifiable (table absente) : violée, jamais validée
    assert next(f for f in d.facts if f.fact_id == check.value_fact_id).value == -1.0
    assert any("scénarios indisponibles" in st.text_fr for st in d.explanation.limits)
    assert any(t.agent == ds.AGENT for t in d.trace)
    assert verify_decision(d).ok
