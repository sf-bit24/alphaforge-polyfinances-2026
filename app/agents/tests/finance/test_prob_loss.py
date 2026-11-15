"""PROB_LOSS dans le Judge (F4) : table de scénarios FICTIVE (voir _scenario_fixture.py), sans réseau ni LLM.

Fenêtre de rendements synthétique (valeurs inventées) passée au Judge : aucune donnée longue n'est nécessaire.
Mandat GÉNÉRIQUE de test : α, L et H sont arbitraires, aucun n'est tiré d'un profil ni d'une fiche persona.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")
pytest.importorskip("pydantic")

from alphaforge.finance.contracts import Decision, Explanation, Limit, PolicySpec, Statement  # noqa: E402
from alphaforge.finance.portfolio import scenario_risk as sr  # noqa: E402
from alphaforge.finance.portfolio.judge import check  # noqa: E402
from alphaforge.finance.portfolio.market import ReturnWindow  # noqa: E402
from alphaforge.scenarios.tool_table import ScenarioTableLoader  # noqa: E402
from alphaforge.store.local import LocalStore  # noqa: E402
from alphaforge.store.s3 import S3Store  # noqa: E402

from . import _scenario_fixture as fx  # noqa: E402

NOW = datetime(2026, 11, 15, tzinfo=UTC)
AS_OF = "2026-09-30"
UNIVERSE = ["XIU.TO", "SPY", "XBB.TO", "ZST.TO", "GLD", "NVDA", "QQQ"]


def window(assets=UNIVERSE) -> ReturnWindow:
    idx = pd.date_range(end="2026-09-30", periods=48, freq="ME")
    rng = np.random.default_rng(0)  # rendements FICTIFS
    df = pd.DataFrame(rng.normal(0.005, 0.03, (len(idx), len(assets))), index=idx, columns=assets)
    return ReturnWindow(df, pd.Timestamp("2026-09-30"), "CAD", "fictif-window")


def lim(rid, kind, sel, **k):
    return Limit(rule_id=rid, kind=kind, selector=sel, derived_from="test:generique", **k)


def prob_limit(alpha=0.10, loss=0.10, h=3, rid="pl"):
    return sr.prob_loss_limit(rid, alpha=alpha, loss_level=loss, horizon_years=h, derived_from="test:generique")


def policy(*limits, **over) -> PolicySpec:
    base = dict(
        policy_id="t",
        profile_id="t",
        profile_version=1,
        created_utc=NOW,
        universe=UNIVERSE,
        limits=[lim("max_titre", "asset_weight", {"classes": ["equity_single"]}, max=0.10), *limits],
    )
    base.update(over)
    return PolicySpec(**base)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("ALPHAFORGE_SCENARIOS", raising=False)
    sr.set_table_provider(None)
    yield
    sr.set_table_provider(None)


@pytest.fixture
def kb(tmp_path):
    store = LocalStore(tmp_path / "kb")
    fx.publish(store)
    return store


@pytest.fixture
def table(kb):
    sr.set_table_provider(lambda run_id: ScenarioTableLoader(kb, run_id=run_id).load())
    return kb


def run(pol, weights=fx.WEIGHTS):
    return check(weights, pol, AS_OF, window=window(), trace_id="judge-t")


def pl_check(rep, rid="pl"):
    return next(c for c in rep.checks if c.rule_id == f"{rid}:max")


def fact(rep, fid):
    return next(f for f in rep.facts if f.fact_id == fid)


# --------------------------------------------------------------------------- contrat


def test_limit_validation():
    prob_limit()
    with pytest.raises(ValueError, match="loss_level et horizon_years"):
        lim("x", "risk", {"measure": "PROB_LOSS"}, max=0.1)
    with pytest.raises(ValueError, match="0 < max < 1"):
        lim("x", "risk", {"measure": "PROB_LOSS", "loss_level": 0.1, "horizon_years": 3}, max=1.0)
    with pytest.raises(ValueError, match="réservés à PROB_LOSS"):
        lim("x", "risk", {"measure": "CVAR", "loss_level": 0.1}, max=0.1)
    with pytest.raises(ValueError, match="incohérente"):
        policy(scenario_family="USD1926")
    with pytest.raises(ValueError, match="hors univers"):
        policy(scenario_blocks={"TSLA": {"block": "US_MKT", "source": "test"}})
    assert policy().scenario_family_used == "CAD77"
    assert policy(currency="USD").scenario_family_used == "USD1926"


# --------------------------------------------------------------------------- sans PROB_LOSS : inchangé


def test_without_prob_loss_the_judge_never_reads_scenarios():
    def boom(run_id):
        raise AssertionError("table lue sans limite PROB_LOSS")

    sr.set_table_provider(boom)
    rep = run(policy())
    assert rep.child_traces == () and rep.approved
    assert rep.trace.fact_ids == [f.fact_id for f in rep.facts]
    assert all(f.trace_id == "judge-t" for f in rep.facts)


# --------------------------------------------------------------------------- évaluation


def test_pass_when_ci_hi_below_alpha(table):
    rep = run(policy(prob_limit(alpha=0.10)))
    c = pl_check(rep)
    assert not c.violated and rep.approved and c.limit == 0.10
    f = fact(rep, c.value_fact_id)
    assert f.value == 0.06 and f.status == "HYPOTHESE"  # ci_hi FICTIF de FICTIF_a, 3 ans, p_loss_gt_10
    assert "borne haute IC 90 % décisive" in f.sources[0].processing
    assert f.sources[0].dataset == f"scenarios:{fx.RUN_ID}"
    ids = {x.fact_id for x in rep.facts}
    assert {fx.fid("FICTIF_a", 3, "p_loss_gt_10"), fx.fid("FICTIF_a", 3, "p_loss_gt_10", "ci_hi")} <= ids
    (child,) = rep.child_traces
    assert child.parent_id == "judge-t" and child.tool == "scenario_risk" and child.status == "ok"
    assert all(x.trace_id in ("judge-t", child.trace_id) for x in rep.facts)
    assert c.value_fact_id in rep.trace.fact_ids and fx.fid("FICTIF_a", 3, "p_loss_gt_10") not in rep.trace.fact_ids


def test_violation_when_ci_overlaps_alpha(table):
    rep = run(policy(prob_limit(alpha=0.05)))  # valeur 0,04 <= α, mais ci_hi 0,06 > α
    c = pl_check(rep)
    assert c.violated and not rep.approved and "pl:max" in rep.blocking_violations


def test_non_blocking_limit_reports_but_does_not_refuse(table):
    lm = prob_limit(alpha=0.05).model_copy(update={"blocking": False})
    rep = run(policy(lm))
    assert pl_check(rep).violated and rep.approved


def test_active_when_ci_hi_equals_alpha(table):
    c = pl_check(run(policy(prob_limit(alpha=0.06))))
    assert c.active and not c.violated


def test_off_grid_horizon_uses_max_of_bracketing_ci_hi(table):
    rep = run(policy(prob_limit(alpha=0.07, h=4)))  # max(ci_hi 3 ans 0,06 ; 5 ans 0,08) = 0,08
    c = pl_check(rep)
    assert c.violated and fact(rep, c.value_fact_id).value == 0.08
    assert "max(3, 5)" in fact(rep, c.value_fact_id).sources[0].processing
    assert not pl_check(run(policy(prob_limit(alpha=0.09, h=4)))).violated


def test_threshold_rounded_down_to_bucket(table):
    rep = run(policy(prob_limit(alpha=0.10, loss=0.15)))  # palier p_loss_gt_10 (majorant)
    assert fact(rep, pl_check(rep).value_fact_id).value == 0.06


@pytest.mark.parametrize(
    "over, reason",
    [
        ({"loss": 0.03}, "minorant"),  # L sous le plus petit palier (5 %)
        ({"h": 30}, "hors de la grille"),  # horizon hors grille : refus de l'outil
    ],
)
def test_unverifiable_is_violated(table, over, reason):
    rep = run(policy(prob_limit(alpha=0.5, **over)))
    c = pl_check(rep)
    assert c.violated and not rep.approved
    f = fact(rep, c.value_fact_id)
    assert f.value == -1.0 and "NON VÉRIFIABLE" in f.sources[0].processing and reason in f.sources[0].processing
    assert any("non vérifiable" in w for w in rep.warnings)


def test_unmapped_holding_is_unverifiable_without_reading_the_table(table):
    def boom(run_id):
        raise AssertionError("table lue malgré un actif sans bloc")

    sr.set_table_provider(boom)
    w = {**fx.WEIGHTS, "XBB.TO": 0.40, "NVDA": 0.05}
    rep = run(policy(prob_limit(alpha=0.5)), w)
    c = pl_check(rep)
    assert c.violated
    proc = fact(rep, c.value_fact_id).sources[0].processing
    assert "NVDA" in proc and "sans bloc" in proc and rep.child_traces == ()


def test_declared_scenario_block_overrides_default_mapping(table):
    w = {**fx.WEIGHTS, "SPY": 0.20, "QQQ": 0.05}
    assert pl_check(run(policy(prob_limit(alpha=0.5)), w)).violated  # QQQ : pas de bloc par défaut
    pol = policy(prob_limit(alpha=0.5), scenario_blocks={"QQQ": {"block": "US_MKT", "source": "test : HYPOTHESE"}})
    assert not pl_check(run(pol, w)).violated


def test_default_mapping_is_conservative():
    pol = policy()
    cat = sr._catalog()
    mapped = {
        a: sr.block_of(a, pol, "CAD77", cat)[0]
        for a in ("XIU.TO", "SPY", "ESGV", "XBB.TO", "ZST.TO", "GLD", "CA_EQ", "CA_GOV_10Y", "BTC-USD")
    }
    assert mapped == {
        "XIU.TO": "CA_EQ",
        "SPY": "US_MKT",
        "ESGV": "US_MKT",
        "XBB.TO": "BONDS",
        "ZST.TO": "CASH",
        "GLD": "GOLD",
        "CA_EQ": "CA_EQ",
        "CA_GOV_10Y": "BONDS",
        "BTC-USD": "CRYPTO",
    }
    for a in ("NVDA", "QQQ", "AGG", "TLT", "ETH-USD", "US_IND_BUSEQ", "UST_TBILL", "CORP_BAA"):
        assert sr.block_of(a, pol, "CAD77", cat)[0] is None, a
    assert sr.block_of("UST_TBILL", pol, "USD1926", cat)[0] == "CASH"
    assert sr.block_of("GLD", pol, "USD1926", cat)[0] is None  # pas de GOLD dans USD1926


def test_unavailable_table_is_unverifiable_and_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHAFORGE_STORE", "local")
    monkeypatch.setenv("ALPHAFORGE_LOCAL_DIR", str(tmp_path / "empty"))
    rep = run(policy(prob_limit(alpha=0.5)))
    c = pl_check(rep)
    assert c.violated
    assert "scénarios indisponibles" in fact(rep, c.value_fact_id).sources[0].processing
    (child,) = rep.child_traces
    assert child.status == "refus" and child.parent_id == "judge-t"


def test_access_denied_store_is_unverifiable(monkeypatch):
    s3 = S3Store("bucket-fictif", region="us-east-1", client=fx.DeniedS3())
    sr.set_table_provider(lambda run_id: ScenarioTableLoader(s3, run_id=run_id).load())
    rep = run(policy(prob_limit(alpha=0.5)))
    c = pl_check(rep)
    proc = fact(rep, c.value_fact_id).sources[0].processing
    assert c.violated and "AccessDenied" in proc and "bucket-fictif" not in proc


def test_disabled_scenarios_are_unverifiable(table, monkeypatch):
    monkeypatch.setenv("ALPHAFORGE_SCENARIOS", "0")
    rep = run(policy(prob_limit(alpha=0.5)))
    assert pl_check(rep).violated
    assert "désactivés" in fact(rep, pl_check(rep).value_fact_id).sources[0].processing


def test_model_disagreement_is_a_warning(table):
    rep = run(policy(prob_limit(alpha=0.10)))  # FICTIF_b : ci_hi 0,12 > α
    assert rep.approved
    assert any("désaccord" in w and "FICTIF_b" in w for w in rep.warnings)


def test_report_absorbs_into_a_valid_decision(table):
    pytest.importorskip("scipy")
    from alphaforge.finance.debate.facts import FactBook

    rep = run(policy(prob_limit(alpha=0.10)))
    book = FactBook("dec-t")
    with book.step("judge", tool="check"):
        ids = book.absorb_report(rep)
    scn = fx.fid("FICTIF_a", 3, "p_loss_gt_10", "ci_hi")
    assert scn in ids
    d = Decision(
        decision_id="dec-t",
        profile_id="t",
        profile_version=1,
        created_utc=NOW,
        kind="proposition",
        positions=[{"asset_id": a, "weight": w} for a, w in fx.WEIGHTS.items()],
        facts=list(book.facts.values()),
        constraints=list(rep.checks),
        explanation=Explanation(
            data_used=[Statement(text_fr="Probabilité de perte (modèle fictif).", fact_ids=[scn])],
            why=[],
            limits=[],
            what_would_change=[],
        ),
        trace=book.trace,
    )
    assert {t.trace_id for t in d.trace} >= {rep.trace.trace_id, rep.child_traces[0].trace_id}
