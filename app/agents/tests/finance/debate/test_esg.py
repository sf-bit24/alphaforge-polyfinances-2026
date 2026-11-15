"""Preuves ESG dans le portefeuille (pur, en CI) : lecture point dans le temps de general/faits/, garde ESG de la
fusion, et exclusion avant l'étape 0 d'un titre qu'un fait relie à une catégorie exclue, preuve citée."""

from __future__ import annotations

from datetime import UTC, date, datetime

from alphaforge import okf
from alphaforge.finance.contracts.profile import Goal, InvestorProfile, Preferences, Score, ValueFilter
from alphaforge.finance.debate.esg import esg_exclusions, esg_preference
from alphaforge.finance.debate.facts import FactBook
from alphaforge.finance.debate.merge import ESG_NO_PREFERENCE_FR, ESG_OTHER_ASSET_FR, apply_amendments
from alphaforge.finance.debate.okf_bridge import OkfMarketStore
from alphaforge.finance.debate.schemas import Amendment, LensReport
from alphaforge.store.local import LocalStore

from ..strategy._helpers import make_comp

AS_OF = date(2026, 9, 30)
ENB_KEY = "general/faits/data-donnees-ec-gc-ca/2026-06-30-aaaa1111.md"


def fact_doc(tickers, *, esg=None, published="2026-07-15T12:00:00Z", value="1"):
    data = {
        "kind": "fact",
        "item_id": "fact-x",
        "value": value,
        "unit": "t éq. CO2",
        "url": "https://data-donnees.ec.gc.ca/x.json",
        "tickers": list(tickers),
        "published_at": published,
        "observed_at": "2026-06-30",
        "retrieved_at": published,
        "provenance": {"licence": "Licence du gouvernement ouvert – Canada"},
    }
    if esg is not None:
        data["esg"] = esg
    doc = okf.new_doc(
        type="Fact",
        title="Activité dans les combustibles fossiles",
        description="Fait ESG de test.",
        tags=["faits", "esg"],
        owners=["alphaforge-a6"],
        sensitivity="public",
        generated_by="agent:A6",
        at=published,
        status="stable",
        sources=[{"id": "fact-x", "title": "Test", "resource": data["url"]}],
        data=data,
    )
    return okf.render(doc)


FOSSIL = {"kind": "sector_activity", "metric": "fossil_fuels", "period": "2026"}


def seeded(tmp_path, *docs):
    store = LocalStore(tmp_path)
    for key, text in docs:
        store.put_text(key, text)
    return OkfMarketStore(store)


def profile(*, exclusions=(), esg=False):
    return InvestorProfile(
        profile_id="p-esg",
        created_utc=datetime(2026, 11, 14, tzinfo=UTC),
        status="COMPLETE",
        goals=[Goal(goal_id="g1", label="retraite", priority="besoin", horizon_years=10)],
        tolerance_declared=Score(value=50),
        investable_wealth=100_000,
        preferences=Preferences(
            value_filters=[ValueFilter(rule=f"exclure : {c}", per_ticker={}) for c in exclusions],
            esg_required=esg,
        ),
    )


def test_reader_is_point_in_time_and_ignores_facts_without_esg(tmp_path):
    later = "general/faits/data-donnees-ec-gc-ca/2026-10-30-bbbb2222.md"
    plain = "general/faits/bankofcanada-ca/2026-09-01-cccc3333.md"
    bad = "general/faits/data-donnees-ec-gc-ca/2026-06-30-dddd4444.md"
    market = seeded(
        tmp_path,
        (ENB_KEY, fact_doc(["ENB.TO"], esg=FOSSIL)),
        (later, fact_doc(["enb.to"], esg=FOSSIL, published="2026-10-31T12:00:00Z")),
        (plain, fact_doc(["ENB.TO"])),
        (bad, fact_doc(["ENB.TO"], esg={"kind": "greenwashing", "metric": "x", "period": "2026"})),
    )
    facts = market.evidence("ENB.TO", "esg", AS_OF)
    assert [(f.fact_id, f.status, f.sources[0].dataset) for f in facts] == [
        ("okf.esg.ENB.TO.1", "FAIT", f"okf-esg:{ENB_KEY}")
    ]  # publié après as_of : ignoré
    assert [f.sources[0].dataset for f in market.evidence("ENB.TO", "esg", date(2026, 11, 30))] == [
        f"okf-esg:{later}",
        f"okf-esg:{ENB_KEY}",
    ]
    assert plain not in market.inputs and ENB_KEY in market.inputs and later in market.inputs
    assert "hors de la liste" in market.rejected[bad]
    assert market.evidence("RY.TO", "esg", AS_OF) == []


def test_esg_facts_enter_the_data_version(tmp_path):
    empty = OkfMarketStore(LocalStore(tmp_path / "a")).data_version("base")
    with_esg = seeded(tmp_path / "b", (ENB_KEY, fact_doc(["ENB.TO"], esg=FOSSIL))).data_version("base")
    assert empty != with_esg


def _merge(amendment, *, preference):
    policy = make_comp().policy
    rep = LensReport(lens="diversity", amendments=[amendment])
    known = {"okf.esg.CNQ.TO.1", "okf.esg.RY.TO.1", "r1.cvar_m"}
    return apply_amendments(policy, [rep], {"diversity": 1.0}, known, esg_preference=preference)


def _exclude(target, evidence):
    return Amendment(kind="exclude_asset", target=target, reason_fr="test", evidence_fact_ids=evidence)


def test_merge_applies_esg_evidence_only_with_a_preference_and_for_its_own_asset():
    _, log = _merge(_exclude("CNQ.TO", ["okf.esg.CNQ.TO.1"]), preference=False)
    assert [(x.status, x.why_fr) for x in log] == [("rejete", ESG_NO_PREFERENCE_FR)]
    _, log = _merge(_exclude("CNQ.TO", ["okf.esg.RY.TO.1"]), preference=True)  # preuve d'un autre titre
    assert [(x.status, x.why_fr) for x in log] == [("rejete", ESG_OTHER_ASSET_FR)]
    _, log = _merge(_exclude("CNQ.TO", ["okf.esg.CNQ.TO.9"]), preference=True)  # fait inexistant
    assert log[0].status == "rejete" and "preuve inconnue" in log[0].why_fr
    after, log = _merge(_exclude("CNQ.TO", ["okf.esg.CNQ.TO.1"]), preference=True)
    assert [x.status for x in log] == ["applique"] and after.excluded["CNQ.TO"] == "okf.esg.CNQ.TO.1"
    flag = Amendment(kind="flag_only", target="CNQ.TO", reason_fr="test", evidence_fact_ids=["okf.esg.CNQ.TO.1"])
    _, log = _merge(flag, preference=False)  # un signalement reste permis
    assert [x.status for x in log] == ["applique"]


def test_esg_preference_follows_the_profile():
    assert not esg_preference(profile())
    assert esg_preference(profile(esg=True)) and esg_preference(profile(exclusions=["fossil_fuels"]))


def _policy_with(*extra):
    pol = make_comp().policy
    return pol.model_copy(update={"universe": [*pol.universe, *extra]})


def test_fossil_fuels_profile_excludes_enb_with_the_fact_cited(tmp_path):
    market = seeded(tmp_path, (ENB_KEY, fact_doc(["ENB.TO"], esg=FOSSIL)))
    pol = _policy_with("ENB.TO")
    book = FactBook("dec-test")
    new = esg_exclusions(profile(exclusions=["fossil_fuels"]), pol, market, AS_OF, book)
    assert new.excluded["ENB.TO"] == "okf.esg.ENB.TO.1"
    cited = book.facts["okf.esg.ENB.TO.1"]
    assert cited.sources[0].dataset == f"okf-esg:{ENB_KEY}" and cited.trace_id.endswith("s0c.esg_exclusions:esg_items")
    assert "ENB.TO" not in new.investable

    # Sans exclusion dans le profil, ou pour la demande précise de l'investisseur : rien ne change.
    assert esg_exclusions(profile(esg=True), pol, market, AS_OF, FactBook("d2")) is pol
    kept = esg_exclusions(profile(exclusions=["fossil_fuels"]), pol, market, AS_OF, FactBook("d3"), protect=["ENB.TO"])
    assert "ENB.TO" not in kept.excluded
    # Une autre catégorie que celle du fait ne l'exclut pas.
    assert "ENB.TO" not in esg_exclusions(profile(exclusions=["tobacco"]), pol, market, AS_OF, FactBook("d4")).excluded
