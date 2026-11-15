"""Rejeu point-in-time sur les données longues de l'engine (sauté sans elles, voir conftest).

Profils de test ``tests/finance/policy/_personas.py`` (entrées HYPOTHESE, fiction) ; fenêtres courtes (8 mois) pour
rester rapide. Aucun seuil n'est tiré d'une fiche persona : les bornes vérifiées sont celles de la ``PolicySpec``
compilée par le moteur. SIMULATION SEULEMENT.
"""
from __future__ import annotations

from datetime import date
from typing import get_args

import pytest

from alphaforge.finance.backtest import data as bt_data
from alphaforge.finance.contracts.evolution import Action
from alphaforge.finance.evolution import replay as R
from alphaforge.finance.evolution import tick as T
from alphaforge.finance.evolution.overlays.base import equity_share
from alphaforge.finance.evolution.pit import PitReturns
from alphaforge.finance.policy import compile_profile
from alphaforge.finance.portfolio.judge import TOL as JUDGE_TOL

from ..policy._personas import amira, robert

WINDOW = ("2021-10", "2022-06")          # origine fin 2021-10, 8 mois rejoués (dont le début de la baisse de 2022)
VALUE = 100_000.0
FLOW_AMIRA = 500.0
FORBIDDEN = ("achète", "achetez", "vends", "vendez", "recommand", "garanti")
STRESS_KEYS = {"name", "window", "max_drawdown", "twr_cum", "value_end", "events", "status", "note", "policy_date",
               "sans_historique", "borne_perte_sans_historique"}


@pytest.fixture(scope="module")
def pit() -> PitReturns:
    return PitReturns.from_engine()


def _replay(name: str, pit: PitReturns, **kw):
    prof, flow = (amira(), FLOW_AMIRA) if name == "amira" else (robert(), 0.0)
    kw.setdefault("monthly_flow", flow)
    kw.setdefault("overlays", False)
    return R.replay(prof, f"client-{name}", name, *WINDOW, VALUE, pit=pit, **kw)


@pytest.fixture(scope="module")
def runs(pit):
    """robert (N0, sans flux), amira (avec apports mensuels) et robert avec un événement de vie (bloquant)."""
    return {
        "robert": _replay("robert", pit),
        "amira": _replay("amira", pit),
        "robert_event": _replay("robert", pit, life_event={"code": "deces_conjoint", "date": date(2022, 2, 1)}),
    }


RUNS = ["robert", "amira", "robert_event"]


# ---------------------------------------------------------------- (a) déterminisme
def test_replay_digest_deterministic(pit, runs):
    first, _ = runs["amira"]
    again, _ = _replay("amira", pit)
    fresh, _ = _replay("amira", PitReturns.from_engine())          # même données relues : même digest
    assert first.digest == again.digest == fresh.digest
    assert first.model_dump(mode="json") == again.model_dump(mode="json")
    assert first.digest != runs["robert"][0].digest
    assert len(first.versions) == 8 and first.window == (date(2021, 10, 31), date(2022, 6, 30))


# ---------------------------------------------------------------- (b) pas de refus silencieux
@pytest.mark.parametrize("name", RUNS)
def test_judge_after_approved_or_violations_listed(runs, name):
    res, _ = runs[name]
    for v in res.versions:
        ev = v.event
        assert ev.judge_after == "approuve" or ev.judge_violations_after, (v.as_of, ev.judge_after)
        if ev.judge_after == "refuse":
            assert ev.judge_violations_after, f"refus silencieux au {v.as_of}"
        if ev.judge_after == "approuve":
            assert ev.judge_violations_after == []


# ---------------------------------------------------------------- (c) aucune opération en HOLD
@pytest.mark.parametrize("name", RUNS)
def test_no_trade_on_hold(runs, name):
    res, _ = runs[name]
    holds = [v for v in res.versions if v.event.action == "HOLD"]
    for v in holds:
        assert v.event.trades == [] and v.event.turnover_oneway == 0.0 and v.event.cost_cad == 0.0
    assert sum(res.n_events_by_action.values()) == len(res.versions)
    assert res.n_events_by_action.get("HOLD", 0) == len(holds)


def test_life_event_requires_reprofile_once(runs):
    res, _ = runs["robert_event"]
    by_month = {v.as_of: v.event for v in res.versions}
    ev = by_month[date(2022, 2, 28)]
    assert ev.action == "REPROFILE_REQUIRED" and ev.trades == []
    assert any(t.code == "LIFE_EVENT" and t.blocking for t in ev.triggers)
    assert [m for m, e in by_month.items() if e.action == "REPROFILE_REQUIRED"] == [date(2022, 2, 28)]
    recon = {f.fact_id: f for f in res.facts}["ev.202202.reconfirmation"]
    assert recon.status == "FICTION"                                  # hypothèse du rejeu, étiquetée


# ---------------------------------------------------------------- (d) explications
@pytest.mark.parametrize("name", RUNS)
def test_explanations_lexicon_and_citations(runs, name):
    res, _ = runs[name]
    facts = {f.fact_id: f for f in res.facts}
    assert len(facts) == len(res.facts)                               # identifiants uniques
    for v in res.versions:
        ev = v.event
        assert set(ev.fact_ids) <= set(facts), set(ev.fact_ids) - set(facts)
        if ev.action == "HOLD":
            assert ev.event_id not in res.explanations
            continue
        exp = res.explanations[ev.event_id]
        sections = (exp.data_used, exp.why, exp.limits, exp.what_would_change)
        assert all(sections), f"question sans réponse au {v.as_of}"
        for st in (s for sec in sections for s in sec):
            low = st.text_fr.lower()
            assert not any(w in low for w in FORBIDDEN), st.text_fr
            missing = set(st.fact_ids) - set(facts)
            assert not missing, (v.as_of, st.text_fr, missing)
            for fid in st.fact_ids:                                    # un fait daté du mois cite bien ce mois
                if fid.startswith("ev.") and facts[fid].as_of is not None:
                    assert facts[fid].as_of == v.as_of, fid
    non_hold = [v for v in res.versions if v.event.action != "HOLD"]
    assert len(res.explanations) == len(non_hold)


def test_some_events_are_explained(runs):
    assert runs["amira"][0].explanations and runs["robert_event"][0].explanations


# ---------------------------------------------------------------- (e) rejeu de stress
def test_stress_replay_summary_and_no_side_effect(runs, pit):
    _, traj = runs["amira"]
    before = (dict(traj.weights), traj.seq, traj.last_version_id, traj.perf.months, traj.value_cad,
              dict(traj.target), traj.level, len(traj.decisions))
    out = R.stress_replay(traj, "covid-2020")
    assert set(out) == STRESS_KEYS
    assert out["status"] == "HYPOTHESE" and out["name"] == "covid-2020"
    s, e = R.STRESS_WINDOWS["covid-2020"]
    assert out["window"] == [str(s), str(e)]
    assert sum(out["events"].values()) == len(pit.months(s, e)) == 12
    assert set(out["events"]) <= set(get_args(Action))
    assert 0.0 <= out["max_drawdown"] < 1.0 and out["value_end"] > 0
    after = (dict(traj.weights), traj.seq, traj.last_version_id, traj.perf.months, traj.value_cad,
             dict(traj.target), traj.level, len(traj.decisions))
    assert after == before                                            # copie : la trajectoire n'est pas touchée
    with pytest.raises(KeyError):
        R.stress_replay(traj, "crise-inconnue")


# ---------------------------------------------------------------- (f) overlays bornés (robert, 2021-10 -> 2022-06)
@pytest.fixture(scope="module")
def overlay_run(pit):
    """Rejeu avec overlays : porte de validation (9 overlays) puis projection chaque mois.
    Lent : ~30 s ici, prévoir jusqu'à ~2 min (timeout généreux en CI)."""
    policies = []
    real_tick = R.tick

    def recording_tick(traj, m, **kw):
        out = real_tick(traj, m, **kw)
        policies.append(traj.policy)                                  # politique réellement utilisée ce mois
        return out

    mp = pytest.MonkeyPatch()
    mp.setattr(R, "tick", recording_tick)
    try:
        res, traj = _replay("robert", pit, overlays=True)
    finally:
        mp.undo()
    assert len(policies) == len(res.versions)
    return res, traj, policies


def _equity_assets(policy, classes: dict[str, str]) -> tuple[set[str], float, float]:
    g = next(lim for lim in policy.limits if lim.rule_id == "alloc.growth")
    sel = g.selector
    tags: dict[str, list[str]] = {}
    if sel.tags_any:
        cat = bt_data.load_assets()
        tags = {a: list(cat.at[a, "tag_list"]) for a in policy.investable if a in cat.index}
    eq = {a for a in policy.investable
          if a in sel.assets or classes.get(a) in sel.classes or set(tags.get(a, ())) & set(sel.tags_any)}
    return eq, (g.min if g.min is not None else 0.0), (g.max if g.max is not None else 1.0)


def _band_gaps(overlay_run, attr: str) -> list[tuple[date, float, float, float]]:
    res, _, policies = overlay_run
    classes = R.asset_classes()
    out = []
    for v, pol in zip(res.versions, policies, strict=True):
        assert v.policy_hash == T._hash(pol.model_dump(mode="json"))
        eq, lo, hi = _equity_assets(pol, classes)
        out.append((v.as_of, equity_share(getattr(v, attr), eq), lo, hi))
    return out


def test_overlay_target_inside_equity_band(overlay_run):
    for as_of, share, lo, hi in _band_gaps(overlay_run, "target"):
        assert lo - 1e-6 <= share <= hi + 1e-6, (as_of, share, lo, hi)


def test_overlay_weights_inside_equity_band_judge_tolerance(overlay_run):
    for as_of, share, lo, hi in _band_gaps(overlay_run, "weights"):
        assert lo - JUDGE_TOL <= share <= hi + JUDGE_TOL, (as_of, share, lo, hi)


def test_overlay_weights_inside_equity_band_strict(overlay_run):
    for as_of, share, lo, hi in _band_gaps(overlay_run, "weights"):
        assert lo - 1e-6 <= share <= hi + 1e-6, (as_of, share, lo, hi)


def test_overlay_not_passed_never_moves(overlay_run):
    res, _, _ = overlay_run
    assert res.overlays_gate and all(s.active == (s.gate == "passe") for s in res.overlays_gate)
    gates = {s.name: s.gate for s in res.overlays_gate}
    for v in res.versions:
        assert {o.name for o in v.event.overlays} == set(gates)
        for o in v.event.overlays:
            assert o.gate == gates[o.name]                            # porte évaluée une fois, avant la fenêtre
            if o.gate != "passe":
                assert not o.active and not o.delta, (v.as_of, o.name, o.delta)
    for c in res.comparators:
        assert c.n_trials >= 1


def test_overlay_explanations_cite_existing_facts(overlay_run):
    res, _, _ = overlay_run
    ids = {f.fact_id for f in res.facts}
    for v in res.versions:
        if v.event.action == "HOLD":
            continue
        exp = res.explanations[v.event.event_id]
        for st in (*exp.data_used, *exp.why, *exp.limits, *exp.what_would_change):
            assert not any(w in st.text_fr.lower() for w in FORBIDDEN), st.text_fr
            assert set(st.fact_ids) <= ids, set(st.fact_ids) - ids


def test_overlay_fact_ids_resolve_to_same_month(overlay_run):
    res, _, _ = overlay_run
    facts = {f.fact_id: f for f in res.facts}
    for v in res.versions:
        for o in v.event.overlays:
            for fid in o.fact_ids:
                assert facts[fid].as_of == v.as_of, (fid, facts[fid].as_of, v.as_of)


# ---------------------------------------------------------------- cache des fenêtres du Judge
def test_judge_window_cache_not_shared_across_policies():
    d = date(2022, 3, 31)
    base = compile_profile(robert(), d).policy
    keep = []
    for _ in range(200):                     # copies superficielles : l'adresse libérée est reprise au plus vite
        p1 = base.model_copy(update={"policy_id": "client-1"})
        T._window(p1, d)
        addr = id(p1)
        del p1
        p2 = base.model_copy(update={"currency": "USD", "policy_id": "client-2"})
        if id(p2) == addr:
            break
        keep.append(p2)
    else:
        pytest.skip("adresse non réutilisée par l'interpréteur : cas non reproduit")
    assert T._window(p2, d).currency == "USD"
