"""Rejeu point-in-time d'une trajectoire : mois par mois, avec bandes, glidepath, overlays validés et déclencheurs.

- La porte de validation des overlays est évaluée **avant** la fenêtre rejouée (``train_end = start``) : aucun
  mois rejoué ne sert à décider qu'un overlay est actif.
- Chaque mois passe par ``tick.tick`` (lecture des rendements jusqu'à t seulement).
- Le ``digest`` (sha256 canonique des versions) permet de vérifier que deux rejeux sont identiques.
- ``stress_replay`` applique au portefeuille du début les rendements d'une crise ancienne (indices longs de
  remplacement, HYPOTHESE), politique figée à la date d'origine.

SIMULATION SEULEMENT.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from datetime import date

import pandas as pd

from ..contracts.decision import Explanation, Fact, Source
from ..contracts.evolution import ComparatorRow, OverlayState, ReplayResult
from ..contracts.profile import InvestorProfile
from .config import EvolutionConfig, load_config
from .explain_change import explain_event
from .history import HistoryStore
from .pit import PitReturns, month_end
from .tick import Trajectory, start, tick

STRESS_WINDOWS = {
    "crise-2008": (date(2007, 10, 31), date(2009, 12, 31)),
    "covid-2020": (date(2020, 1, 31), date(2020, 12, 31)),
    "inflation-2022": (date(2021, 12, 31), date(2022, 12, 31)),
}


def asset_classes() -> dict[str, str]:
    from ..backtest import data as bt_data

    cat = bt_data.load_assets()
    return {a: str(c) for a, c in cat["asset_class"].items()}


def proxied_returns(pit: PitReturns, traj: Trajectory, end) -> pd.DataFrame:
    """Rendements ≤ ``end`` des actifs de la politique ; avant le lancement d'un actif, son proxy long (HYPOTHESE)."""
    r = pit.with_horizon(end).upto(end)
    cols = {}
    for a in traj.policy.investable:
        s = r[a] if a in r.columns else pd.Series(index=r.index, dtype=float)
        hp = traj.policy.history_proxies.get(a)
        if hp is not None and hp.proxy in r.columns:
            s = s.fillna(r[hp.proxy])
        cols[a] = s
    return pd.DataFrame(cols, index=r.index)


def _overlay_fn(asset_class: dict[str, str], gate_states: dict[str, OverlayState], cfg: EvolutionConfig):
    from .overlays.base import apply_overlays, context_from
    from .overlays.registry import build_overlays

    overlays = build_overlays(cfg)

    def fn(traj: Trajectory, pit_t: PitReturns, m: pd.Timestamp, w_drift: dict, value: float):
        returns_upto = proxied_returns(pit_t, traj, m)
        ctx = context_from(traj.policy, m, returns_upto, traj.base_target, w_drift, asset_class, cfg=cfg,
                           entry_prices=traj.entry_prices, peaks=traj.peaks, need_floor_cad=traj.need_floor_cad,
                           value_cad=value)
        return apply_overlays(ctx, overlays, traj.overlay_active, gate_states=gate_states)

    return fn


def evaluate_gates(traj: Trajectory, train_end, asset_class: dict[str, str], cfg: EvolutionConfig
                   ) -> tuple[dict[str, OverlayState], list[ComparatorRow]]:
    """Porte de validation de chaque overlay, sur l'historique strictement antérieur à la fenêtre rejouée."""
    from .overlays.gate import default_grid, evaluate_gate

    train_end = month_end(train_end)
    r = proxied_returns(traj.pit, traj, train_end)
    # entraînement sur les lignes de la cible qui ont assez d'historique (proxys compris) ; le poids des lignes trop
    # récentes (ex. crypto) est versé en quasi-liquidités POUR L'ENTRAÎNEMENT SEULEMENT (HYPOTHESE, affichée)
    held = {a: w for a, w in traj.base_target.items() if w > 0}
    long_enough = {a for a in held if a in r.columns and r[a].notna().sum() >= cfg.gate.min_train_months}
    short = sorted(set(held) - long_enough)
    gate_target = {a: held[a] for a in long_enough}
    cash = next((a for a in ("ZST.TO", "UST_TBILL") if a in long_enough or a in r.columns), None)
    if short and cash:
        gate_target[cash] = gate_target.get(cash, 0.0) + sum(held[a] for a in short)
        if cash not in r.columns:
            r[cash] = traj.pit.with_horizon(train_end).upto(train_end)[cash]
    tot = sum(gate_target.values())
    if tot <= 0:
        raise ValueError("porte : aucune ligne avec assez d'historique")
    gate_target = {a: w / tot for a, w in gate_target.items()}   # somme 1 même sans quasi-liquidités
    cols = sorted(gate_target)
    complete = r[cols].dropna(how="any")
    months = list(complete.index)
    traj.gate_note = (f"entraînement sur {len(months)} mois ; lignes sans historique long remplacées par "
                      f"{cash} : {', '.join(short)}" if short else f"entraînement sur {len(months)} mois")
    # DSR « déflaté » par le nombre TOTAL d'essais faits pour ce profil (toutes stratégies confondues)
    enabled = [n for n in cfg.overlays.order if cfg.overlay(n).get("enabled", True)]
    n_total = sum(len(default_grid(cfg, n)) for n in enabled)
    states, rows = {}, []
    for name in cfg.overlays.order:
        st, row = evaluate_gate(name, complete, train_end, gate_target, traj.policy, asset_class, cfg,
                                months=months, need_floor_cad=traj.need_floor_cad, value_cad=traj.value_cad,
                                n_trials_total=n_total)
        states[name], rows = st, [*rows, row]
    return states, rows


def _digest(versions) -> str:
    payload = [v.model_dump(mode="json") for v in versions]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def replay(profile: InvestorProfile, client_id: str, persona_label: str, start_month, end_month, value_cad: float,
           *, pit: PitReturns | None = None, cfg: EvolutionConfig | None = None, monthly_flow: float = 0.0,
           overlays: bool = True, history: HistoryStore | None = None, run_id: str | None = None,
           flows: Callable[[date], float] | None = None, life_event: dict | None = None,
           on_month: Callable | None = None) -> tuple[ReplayResult, Trajectory]:
    cfg = cfg or load_config()
    pit = pit or PitReturns.from_engine()
    classes = asset_classes()
    traj = start(client_id, profile, month_end(start_month).date(), value_cad, pit, cfg, history=history,
                 asset_class=classes)
    traj.life_event = life_event
    # plancher CPPI d'un objectif « besoin » : réserve de 3 ans de retraits (risk_levels.yaml#buckets.
    # withdrawal_reserve_years), sinon le montant de l'objectif ; HYPOTHESE de construction
    need = [g for g in traj.profile.goals if g.priority.value == "besoin"]
    if need:
        traj.need_floor_cad = float(sum((3 * g.recurring_withdrawal) if g.recurring_withdrawal else (g.amount or 0.0)
                                        for g in need)) or None
    sats = {a for a in traj.policy.investable if classes.get(a) in ("equity_single", "crypto")}
    gate_states, comparators = ({}, [])
    if overlays:
        gate_states, comparators = evaluate_gates(traj, start_month, classes, cfg)
        traj.overlay_active = {n for n, s in gate_states.items() if s.active}
        traj.overlay_fn = _overlay_fn(classes, gate_states, cfg)
    versions, facts = [], []
    explanations: dict[str, Explanation] = {}
    months = pit.months(month_end(start_month) + pd.offsets.MonthEnd(1), month_end(end_month))
    for m in months:
        flow = flows(m.date()) if flows else monthly_flow
        prev = dict(traj.weights)
        out = tick(traj, m, flow_cad=flow)
        if overlays:
            from .overlays.base import update_stop_levels

            traj.entry_prices, traj.peaks = update_stop_levels(proxied_returns(pit, traj, m), prev,
                                                               out.version.weights, sats, traj.entry_prices, traj.peaks)
        versions.append(out.version)
        if out.version.event.action == "REPROFILE_REQUIRED":
            # hypothèse du rejeu (FICTION) : l'investisseur fictif reconfirme son profil sans changement ce mois-ci
            traj.kyc_confirmed, traj.last_review, traj.life_event = m.date(), m.date(), None
            out.facts.append(Fact(fact_id=f"ev.{m:%Y%m}.reconfirmation", label_fr="Profil reconfirmé sans changement "
                                  "(hypothèse du rejeu)", value="reconfirmé", unit="texte", status="FICTION",
                                  sources=[Source(dataset="evolution:replay", processing="hypothèse du rejeu")],
                                  trace_id=f"evolution:{client_id[:8]}:{m:%Y%m}"))
        facts.extend(out.facts)
        if out.version.event.action != "HOLD":
            exp, extra = explain_event(out.version, out.facts, cfg)
            explanations[out.version.event.event_id] = exp
            facts.extend(f for f in extra if f.fact_id.startswith("ev."))
        if on_month:
            on_month(out)
    facts.extend(_cfg_facts_once(cfg, versions))
    snap = traj.perf.snapshot()
    res = ReplayResult(
        run_id=run_id or f"rejeu-{client_id[:16]}-{month_end(start_month):%Y%m}-{month_end(end_month):%Y%m}",
        client_id=client_id, persona_label=persona_label,
        window=(month_end(start_month).date(), month_end(end_month).date()), versions=versions, perf=snap,
        comparators=comparators, overlays_gate=list(gate_states.values()),
        n_events_by_action=dict(Counter(v.event.action for v in versions)), facts=_dedup(facts),
        explanations=explanations, config_hash=cfg.sha256, data_version=pit.data_version, digest=_digest(versions),
    )
    return res, traj


def stress_replay(traj: Trajectory, name: str, *, cfg: EvolutionConfig | None = None) -> dict:
    """Rejoue une crise ancienne sur une COPIE du portefeuille courant de ``traj`` (politique figée à la dernière date).

    Les rendements anciens des lignes sans historique viennent de leurs proxys longs (HYPOTHESE). Rend un résumé
    (pire baisse, valeur finale, mouvements) ; rien n'est écrit dans l'historique.
    """
    import copy

    cfg = cfg or traj.cfg
    s, e = STRESS_WINDOWS[name]
    t = copy.copy(traj)
    t.history, t.weights, t.target = None, dict(traj.weights), dict(traj.target)
    from .performance import PerfTracker

    t.perf = PerfTracker(traj.value_cad, cash_assets=traj.perf.cash_assets)
    t.seq, t.last_version_id, t.last_signals = -1, None, dict(traj.last_signals)
    t.decisions = list(traj.decisions)
    # politique figée à la DERNIÈRE date du rejeu, celle du portefeuille stressé (même niveau, pas de REOPTIMIZE)
    frozen = traj.perf.months_seen[-1] if traj.perf.months_seen else traj.origin
    events = Counter()
    no_hist: dict[str, float] = {}
    for m in traj.pit.months(month_end(s), month_end(e)):
        out = tick(t, m, policy_date=frozen)
        events[out.version.event.action] += 1
        for a, p in out.proxied.items():
            if p.startswith("aucun"):
                no_hist[a] = max(no_hist.get(a, 0.0), traj.weights.get(a, 0.0))
    snap = t.perf.snapshot()
    bound = sum(w * traj.policy.loss_bounds.get(a, 0.0) for a, w in no_hist.items())
    return {"name": name, "window": [str(s), str(e)], "max_drawdown": snap.max_drawdown, "twr_cum": snap.twr_cum,
            "value_end": snap.value_cad, "events": dict(events), "status": "HYPOTHESE", "policy_date": str(frozen),
            "sans_historique": no_hist, "borne_perte_sans_historique": bound,
            "note": ("rendements anciens (proxys longs) appliqués au portefeuille de fin de rejeu, politique figée "
                     "à la dernière date du rejeu ; les lignes sans historique (ex. crypto) ont un rendement nul, ce "
                     "qui sous-estime la baisse : borne de perte supplémentaire Σ w·δ indiquée à part")}


def _cfg_facts_once(cfg: EvolutionConfig, versions) -> list[Fact]:
    from .explain_change import _cfg_facts

    return _cfg_facts(cfg, f"{versions[0].as_of:%Y%m}") if versions else []


def _dedup(facts: list[Fact]) -> list[Fact]:
    seen, out = set(), []
    for f in facts:
        if f.fact_id not in seen:
            seen.add(f.fact_id)
            out.append(f)
    return out
