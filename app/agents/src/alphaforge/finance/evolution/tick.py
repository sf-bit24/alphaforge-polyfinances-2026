"""Tick mensuel : un mois de la vie simulée d'un portefeuille (déterministe, point-in-time).

Ordre fixe, documenté dans la fiche Brain ``references/calibration/evolution-portefeuille.md`` :

1. mise à la valeur de marché avec les rendements du mois t (``PitReturns.with_horizon(t)`` : rien après t) ;
2. flux du mois (un apport va d'abord aux lignes sous-pondérées) ;
3. re-compilation de F1 à la date t sur le profil ancré (``profile_at``) : c'est le glidepath ;
4. overlays dynamiques bornés (seulement ceux qui ont passé la porte de validation) ;
5. Judge F4 sur les poids dérivés, puis déclencheurs ;
6. échelle d'actions : REPROFILE_REQUIRED > REOPTIMIZE > OVERLAY_SHIFT > REBALANCE_TO_BANDS > HOLD ;
7. Judge F4 après l'opération ; nouvelle version chaînée ; faits pour l'explication.

Aucun LLM ici. SIMULATION SEULEMENT : chaque mouvement est un « événement de rééquilibrage illustratif ».
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from ..contracts.decision import Decision, Fact, Source
from ..contracts.evolution import OverlayState, PortfolioVersion, RebalanceEvent, Trade, TriggerFired
from ..contracts.policy import PolicySpec
from ..contracts.profile import InvestorProfile
from .bands import breaches, rebalance_to_bands
from .config import EvolutionConfig
from .drift import drift_metric, mark_to_market
from .history import HistoryStore, version_id
from .performance import PerfTracker
from .pit import PitReturns, month_end
from .rebalance import apply_flow, cost_cad, plan_trades, turnover
from .triggers import TriggerState, evaluate, profile_at

EPS = 1e-9


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def _norm(w: dict[str, float]) -> dict[str, float]:
    w = {a: max(0.0, float(x)) for a, x in w.items() if x > EPS}
    s = sum(w.values())
    return {a: x / s for a, x in sorted(w.items())} if s > 0 else {}


def _clean(w: dict[str, float], floor: float = 1e-4) -> dict[str, float]:
    """Retire le bruit des solveurs (poids < 0,01 %) et renormalise."""
    return _norm({a: x for a, x in w.items() if x >= floor})


def _level(dec: Decision) -> str:
    for f in dec.facts:
        if f.fact_id == "level":
            return str(f.value)
    return "?"


@dataclass
class BuildOutcome:
    """Ce que le moteur F1 → F4 rend pour fixer (ou refixer) la cible stratégique."""
    target: dict[str, float]
    policy: PolicySpec
    level: str
    decision: Decision | None


def default_build(profile: InvestorProfile, as_of: date) -> BuildOutcome:
    """Cible stratégique par le pipeline existant en mode « rules » (aucun LLM), importé sans modification."""
    import inspect

    from ..debate.pipeline import build_portfolio

    kw: dict[str, Any] = {"mode": "rules", "rephrase_explanation": False,
                          "decision_id": f"dec-{profile.profile_id[:16]}-{as_of:%Y%m}"}   # déterministe (digest)
    # étape 0 (style et sélection, PR #43) : comportement par défaut du produit, gardé tel quel ; le rejeu reste
    # reproductible (la stratégie est déterministe). EVOLUTION_STRATEGY=0 la désactive pour comparer.
    import os

    if "strategy" in inspect.signature(build_portfolio).parameters and os.environ.get("EVOLUTION_STRATEGY") == "0":
        kw["strategy"] = False
    res = build_portfolio(profile, as_of, **kw)
    dec = res.decision
    target = _norm({p.asset_id: p.weight for p in dec.positions})
    if res.policy is None or not target:
        raise ValueError(f"aucune allocation au {as_of} : décision « {dec.kind} »")
    return BuildOutcome(target=target, policy=res.policy, level=_level(dec), decision=dec)


@dataclass
class Trajectory:
    """État mutable d'une trajectoire simulée (un client, une fenêtre)."""
    client_id: str
    profile: InvestorProfile               # profil ANCRÉ (profile_at) : les horizons raccourcissent avec le temps
    origin: date
    cfg: EvolutionConfig
    pit: PitReturns
    weights: dict[str, float]
    value_cad: float
    base_target: dict[str, float]          # cible stratégique de F1 → F4 (avant overlays)
    target: dict[str, float]               # cible effective (après overlays bornés)
    policy: PolicySpec
    level: str
    perf: PerfTracker
    history: HistoryStore | None = None
    decision_id: str | None = None
    seq: int = -1
    last_version_id: str | None = None
    overlay_active: set[str] = field(default_factory=set)
    overlay_states: list[OverlayState] = field(default_factory=list)
    last_signals: dict[str, float | None] = field(default_factory=dict)
    entry_prices: dict[str, float] = field(default_factory=dict)
    peaks: dict[str, float] = field(default_factory=dict)
    need_floor_cad: float | None = None
    kyc_confirmed: date | None = None
    last_review: date | None = None
    life_event: dict | None = None
    managed_account: bool = False
    reprofile_pending: bool = False
    glide_pending: bool = False            # changement de cible étalé : la suite du glissement reste plafonnée
    decisions: list[Decision] = field(default_factory=list)
    build_fn: Callable[[InvestorProfile, date], BuildOutcome] = default_build
    overlay_fn: Callable[..., tuple[dict, list[OverlayState], list[Fact]]] | None = None
    asset_class: dict[str, str] = field(default_factory=dict)
    gate_note: str = ""


@dataclass
class TickOutput:
    version: PortfolioVersion
    facts: list[Fact]
    triggers: list[TriggerFired]
    proxied: dict[str, str]                # actif -> proxy utilisé ce mois (HYPOTHESE)


def cushioned(policy: PolicySpec, target: dict[str, float], as_of: date, cushion: float) -> dict[str, float]:
    """Cible posée ``cushion`` à l'intérieur de chaque limite linéaire (plus stricte que le profil).

    Changement minimal (L1, HiGHS) parmi les seules lignes de la cible ; une limite trop étroite pour le coussin
    garde ses bornes d'origine. Si le programme est infaisable, ou si le Judge refuse la cible coussinée (limite de
    risque), la cible d'origine est rendue telle quelle.
    """
    if cushion <= 0:
        return dict(target)
    import cvxpy as cp
    import numpy as np

    from ..portfolio.compile import compile_policy

    try:
        comp = compile_policy(policy, as_of)
    except (KeyError, ValueError):   # actif hors catalogue (tests synthétiques) : pas de coussin
        return dict(target)
    t0 = np.array([float(target.get(a, 0.0)) for a in comp.assets])
    x = cp.Variable(len(comp.assets))
    cons = [cp.sum(x) == 1, x >= 0] + [x[i] == 0 for i, a in enumerate(comp.assets) if target.get(a, 0.0) <= 0]
    for row in comp.rows:
        lo, hi = row.lo, row.hi
        room = (hi - lo) if (lo is not None and hi is not None) else None
        c = cushion if room is None or room >= 4 * cushion else 0.0
        if hi is not None:
            cons.append(row.vector @ x <= (hi - c if hi - c > 0 else hi))
        if lo is not None:
            cons.append(row.vector @ x >= lo + c if lo > 0 else row.vector @ x >= lo)
    prob = cp.Problem(cp.Minimize(cp.norm1(x - t0)), cons)
    try:
        prob.solve(solver="HIGHS") if "HIGHS" in cp.installed_solvers() else prob.solve()
    except Exception:  # noqa: BLE001
        return dict(target)
    if x.value is None:
        return dict(target)
    out = _clean({a: float(v) for a, v in zip(comp.assets, np.clip(x.value, 0, None), strict=True)})
    rep = _judge(out, policy, as_of)
    return out if rep is not None and rep.approved else dict(target)


def start(client_id: str, profile: InvestorProfile, origin: date, value_cad: float, pit: PitReturns,
          cfg: EvolutionConfig, *, initial_weights: dict[str, float] | None = None,
          build_fn: Callable[[InvestorProfile, date], BuildOutcome] = default_build,
          overlay_fn=None, history: HistoryStore | None = None, asset_class: dict[str, str] | None = None,
          cash_assets: tuple[str, ...] = ("ZST.TO",)) -> Trajectory:
    """Construit la cible stratégique à l'origine (F1 → F4) et ouvre la trajectoire."""
    origin = month_end(origin).date()
    anchored = profile_at(profile, origin)
    out = build_fn(anchored, origin)
    out = BuildOutcome(target=cushioned(out.policy, _clean(out.target), origin, cfg.bands.cap_cushion),
                       policy=out.policy, level=out.level, decision=out.decision)
    w0 = _norm(initial_weights) if initial_weights else dict(out.target)
    return Trajectory(
        client_id=client_id, profile=anchored, origin=origin, cfg=cfg, pit=pit, weights=w0, value_cad=float(value_cad),
        base_target=dict(out.target), target=dict(out.target), policy=out.policy, level=out.level,
        perf=PerfTracker(float(value_cad), cash_assets=cash_assets), history=history,
        decision_id=out.decision.decision_id if out.decision else None,
        decisions=[out.decision] if out.decision else [], build_fn=build_fn, overlay_fn=overlay_fn,
        asset_class=dict(asset_class or {}), kyc_confirmed=origin, last_review=origin,
    )


def _month_returns(traj: Trajectory, pit_t: PitReturns, month: pd.Timestamp) -> tuple[dict[str, float], dict[str, str]]:
    """Rendements du mois ; un actif sans historique prend celui de son proxy long déclaré (HYPOTHESE)."""
    row = pit_t.month(month)
    out: dict[str, float] = {}
    proxied: dict[str, str] = {}
    for a in traj.weights:
        r = row.get(a)
        if r is None or (isinstance(r, float) and math.isnan(r)):
            hp = traj.policy.history_proxies.get(a)
            pr = row.get(hp.proxy) if hp else None
            if pr is not None and not (isinstance(pr, float) and math.isnan(pr)):
                out[a], proxied[a] = float(pr), hp.proxy
                continue
            out[a] = 0.0
            proxied[a] = "aucun (rendement nul)"
        else:
            out[a] = float(r)
    return out, proxied


_WINDOWS: dict[tuple[str, date], Any] = {}


def _window(policy: PolicySpec, as_of: date):
    """Fenêtre de rendements du Judge, calculée une fois par (politique, mois) : même résultat, sans relire les
    parquets à chaque contrôle."""
    from ..portfolio.compile import compile_policy
    from ..portfolio.market import returns_window

    key = (_hash(policy.model_dump(mode="json")), as_of)   # contenu, pas id() : une adresse peut être réutilisée
    if key not in _WINDOWS:
        if len(_WINDOWS) > 64:
            _WINDOWS.clear()
        _WINDOWS[key] = returns_window(policy, as_of, compile_policy(policy, as_of).assets)
    return _WINDOWS[key]


def _judge(weights: dict[str, float], policy: PolicySpec, as_of: date):
    from ..portfolio.judge import check

    try:
        return check(weights, policy, as_of, window=_window(policy, as_of))
    except Exception:  # noqa: BLE001 - un historique insuffisant au début d'une fenêtre ne doit pas arrêter le rejeu
        return None


def _trigger_unit(t: TriggerFired) -> str:
    """Unité d'affichage de la valeur d'un déclencheur (le formateur multiplie « % » par 100)."""
    if t.code in ("KYC_AGE", "REVIEW_DUE"):
        return "mois"
    if t.code == "LARGE_FLOW" or t.threshold_source.endswith("_cad"):
        return "CAD"
    return "%"


def _limits_tightened(old: PolicySpec, new: PolicySpec) -> list[str]:
    """Limites de ``new`` plus strictes que dans ``old`` (max abaissé, min relevé, ou limite nouvelle)."""
    prev = {lim.rule_id: lim for lim in old.limits}
    out = []
    for lim in new.limits:
        o = prev.get(lim.rule_id)
        if o is None:
            out.append(lim.rule_id)
        elif (lim.max is not None and (o.max is None or lim.max < o.max - 1e-9)) or (
                lim.min is not None and (o.min is None or lim.min > o.min + 1e-9)):
            out.append(lim.rule_id)
    return sorted(out)


def _step_to(w_from: dict[str, float], w_to: dict[str, float], max_twoway: float) -> dict[str, float]:
    """Avance de ``w_from`` vers ``w_to`` d'au plus ``max_twoway`` de rotation aller-retour (glissement)."""
    _, tw = turnover(w_from, w_to)
    if tw <= max_twoway + EPS:
        return dict(w_to)
    k = max_twoway / tw
    keys = sorted(set(w_from) | set(w_to))
    return _norm({a: w_from.get(a, 0.0) + k * (w_to.get(a, 0.0) - w_from.get(a, 0.0)) for a in keys})


def tick(traj: Trajectory, month, flow_cad: float = 0.0, *, policy_date: date | None = None) -> TickOutput:
    """Un mois. ``policy_date`` fige la date de la politique (F1, Judge, déclencheurs d'horizon) : utilisé pour
    les rejeux de stress, où l'on applique les rendements d'un mois ancien au portefeuille d'aujourd'hui."""
    cfg = traj.cfg
    m = month_end(month)
    d = m.date()
    pd_ = policy_date or d
    pit_t = traj.pit.with_horizon(m)                       # point-in-time : toute lecture après t lève LookaheadError
    facts: list[Fact] = []
    src_pit = Source(dataset=f"pit:monthly_returns@{traj.pit.data_version}", processing="rendements mensuels CAD")

    def fact(key: str, label: str, value, unit: str, status: str = "FAIT", source: Source | None = None) -> str:
        fid = f"ev.{d:%Y%m}.{key}"
        facts.append(Fact(fact_id=fid, label_fr=label, value=value if not isinstance(value, float) else round(value, 6),
                          unit=unit, as_of=d, status=status, sources=[source or src_pit],
                          trace_id=f"evolution:{traj.client_id[:8]}:{d:%Y%m}"))
        return fid

    # 1. mise à la valeur de marché
    r, proxied = _month_returns(traj, pit_t, m)
    w_drift, gross, _missing = mark_to_market(traj.weights, r)
    value = traj.value_cad * (1.0 + gross)
    fid_r = fact("r_portefeuille", "Rendement du portefeuille sur le mois", gross, "%")
    for a, p in proxied.items():
        fact(f"proxy.{a}", f"Historique de {a} remplacé par {p}", p, "texte", status="HYPOTHESE")

    # 2. flux du mois
    if flow_cad:
        v_before = value
        w_drift, value = apply_flow(w_drift, value, flow_cad, traj.target, cfg.flows.contribution_first)
        flow_cad = value - v_before          # flux effectif (un retrait est plafonné à la valeur)

    # 3. glidepath : re-compilation de F1 à la date
    from ..policy import compile_profile

    comp = compile_profile(traj.profile, pd_)
    level_prev, level_now = traj.level, comp.level
    # F1 resserre les limites avec le temps même à niveau égal (règle des dollars, horizon) : un resserrement
    # impose de recalculer la cible ; un simple relâchement est adopté sans mouvement.
    tightened = _limits_tightened(traj.policy, comp.policy) if comp.policy is not None else []
    target_changed = comp.policy is not None and (level_now != level_prev or bool(tightened))
    if comp.policy is not None and not target_changed:
        traj.policy = comp.policy
    policy_now = comp.policy or traj.policy      # la politique À LA DATE : Judge et conformité s'y mesurent

    # 4. overlays bornés
    states: list[OverlayState] = []
    target = dict(traj.base_target)
    alpha = 1.0
    if traj.overlay_fn is not None and traj.overlay_active is not None:
        target, states, ofacts, alpha = _overlays_judged(traj, pit_t, m, w_drift, value, pd_)
        facts.extend(ofacts)
    changed_signals = [s.name for s in states if s.active and traj.last_signals.get(s.name) != s.signal]
    for s in states:
        traj.last_signals[s.name] = s.signal

    # 5. Judge sur les poids dérivés, puis déclencheurs
    judge_before = _judge(w_drift, policy_now, pd_)
    # baisse estimée à la fin de ce mois, avant opération (indice TWR ; la référence « cost » est gérée
    # par les déclencheurs à partir de value_cad et invested_cad)
    perf_now = traj.perf.snapshot().model_copy(update={
        "value_cad": value, "invested_cad": traj.perf.initial_value_cad + sum(traj.perf.flows) + flow_cad,
        "current_drawdown": _dd_twr(traj.perf, gross)})
    trig = evaluate(TriggerState(
        as_of=pd_, origin=traj.origin, profile=traj.profile, level_prev=level_prev, level_now=level_now,
        compile_now=comp, judge_drift=judge_before, perf=perf_now, flow_cad=flow_cad, value_cad=value,
        kyc_confirmed=traj.kyc_confirmed, last_review=traj.last_review, life_event=traj.life_event,
        managed_account=traj.managed_account, overlay_signal_changes=changed_signals,
    ), cfg)
    blocking = [t for t in trig if t.blocking]

    # 6. échelle d'actions
    br = breaches(w_drift, target, cfg.bands)
    w_to, reason = w_drift, None
    if blocking:
        # aucune décision stratégique en attendant le profil ; une limite bloquante franchie par la dérive est
        # tout de même rétablie (conformité minimale) : attendre ne doit jamais laisser une violation en place
        action = "REPROFILE_REQUIRED"
        traj.reprofile_pending = True
        if judge_before is not None and not judge_before.approved:
            reason, w_to = "compliance", w_drift
    elif target_changed:
        action = "REOPTIMIZE"
        out = traj.build_fn(traj.profile, pd_)
        if out.decision is not None:
            dec = out.decision.model_copy(update={"reprofile_triggers_fired": [t.code for t in trig]})
            traj.decisions.append(dec)
            traj.decision_id = dec.decision_id
        base = cushioned(out.policy, _clean(out.target), pd_, cfg.bands.cap_cushion)
        traj.base_target, traj.policy, traj.level = base, out.policy, out.level
        target = dict(base)
        if traj.overlay_fn is not None:
            target, states, ofacts, alpha = _overlays_judged(traj, pit_t, m, w_drift, value, pd_)
            facts.extend(ofacts)
        # niveau en baisse ou limites resserrées : on y va d'un coup ; une hausse se fait par glissement
        stricter = _rank(level_now) < _rank(level_prev) or bool(tightened)
        w_to = dict(target) if stricter else _step_to(w_drift, target, cfg.trading.max_turnover_tick)
        reason = "glidepath"
        traj.glide_pending = turnover(w_to, target)[1] > 1e-6
    elif traj.glide_pending:
        # suite d'un changement de cible à la hausse : même plafond de rotation chaque mois jusqu'à la cible
        action, reason = "REOPTIMIZE", "glidepath"
        w_to = _step_to(w_drift, target, cfg.trading.max_turnover_tick)
        traj.glide_pending = turnover(w_to, target)[1] > 1e-6
    elif changed_signals and drift_metric(w_drift, target) > EPS:
        action = "OVERLAY_SHIFT"
        w_to, reason = _step_to(w_drift, target, cfg.trading.max_turnover_tick), "overlay"
    elif br:
        action = "REBALANCE_TO_BANDS"
        w_to, reason = rebalance_to_bands(w_drift, target, cfg.bands), "band"
    elif judge_before is not None and not judge_before.approved:
        # la dérive seule fait franchir une limite bloquante (ex. une ligne au plafond qui monte) : opération de
        # conformité minimale, sans rééquilibrage complet
        action, reason = "REBALANCE_TO_BANDS", "compliance"
        w_to = w_drift
    else:
        action = "HOLD"

    trades: list[Trade] = []
    w_eff = dict(w_drift)
    rebuilt_for_risk = False
    if reason is not None:
        if reason != "compliance":
            trades, w_eff = plan_trades(w_drift, w_to, value, reason, cfg.trading.min_trade_cad)
        # conformité : projection minimale sur les limites linéaires de la politique, depuis les poids obtenus.
        # Ces opérations passent même sous le montant minimal : une limite bloquante n'est pas négociable. Contrôle
        # strict (1e-6) en plus du Judge (tolérance 1e-4) : un reliquat d'arrondi ne doit pas dépasser une limite.
        rep_mid = _judge(w_eff, policy_now, pd_)
        if (rep_mid is not None and not rep_mid.approved) or _strict_breaches(w_eff, traj, policy_now):
            w_fix = _project(policy_now, w_eff, pd_, allowed_target=target)
            if w_fix is not None:
                extra, w_eff = plan_trades(dict(w_eff), w_fix, value, "liquidation" if reason == "compliance"
                                           else reason, 0.0)
                trades = _merge_trades(trades, extra, w_drift, w_eff, value)
        # une limite de RISQUE (non linéaire) encore violée : retour à la cible...
        rep_fix = _judge(w_eff, policy_now, pd_)
        if rep_fix is not None and not rep_fix.approved:
            extra, w_eff = plan_trades(dict(w_eff), dict(target), value, "band", 0.0)
            trades = _merge_trades(trades, extra, w_drift, w_eff, value)
            # ... et si la cible elle-même n'est plus approuvée à cette date (mesure de risque sur un historique
            # glissant), le moteur la recalcule : F1 → F4 à la date, puis mouvement vers la nouvelle cible
            rep_t = _judge(w_eff, policy_now, pd_)
            if rep_t is not None and not rep_t.approved and action != "REOPTIMIZE":
                out = traj.build_fn(traj.profile, pd_)
                if out.decision is not None:
                    dec = out.decision.model_copy(update={"reprofile_triggers_fired": [t.code for t in trig]})
                    traj.decisions.append(dec)
                    traj.decision_id = dec.decision_id
                base = cushioned(out.policy, _clean(out.target), pd_, cfg.bands.cap_cushion)
                traj.base_target, traj.policy, policy_now = base, out.policy, out.policy
                target = dict(base)
                extra, w_eff = plan_trades(dict(w_eff), dict(target), value, "reoptimize", 0.0)
                trades = _merge_trades(trades, extra, w_drift, w_eff, value)
                if action != "REPROFILE_REQUIRED":
                    action = "REOPTIMIZE"
                rebuilt_for_risk = True
        if reason == "compliance":
            reason = "liquidation"
    ow, tw = turnover(w_drift, w_eff)
    cost = cost_cad(ow, value, cfg.trading.cost_bps)
    value_after = value - cost
    judge_after = _judge(w_eff, policy_now, pd_) if trades else judge_before

    # 7. performance, version, faits
    r_net = (value_after - flow_cad) / traj.value_cad - 1.0 if traj.value_cad > 0 else 0.0
    cash = traj.perf.cash_assets[0] if traj.perf.cash_assets else None
    traj.perf.update(d, r_net, value_after, flow_cad, ow, cost, w_eff,
                     r_cash=pit_t.month(m).get(cash) if cash and cash in pit_t.assets else None)
    snap = traj.perf.snapshot()
    fact("valeur", "Valeur du portefeuille en fin de mois, après coûts", value_after, "CAD")
    if rebuilt_for_risk:
        fact("cible_recalculee", "Cible recalculée : l'ancienne n'était plus approuvée par le Judge à cette date",
             "recalculée", "texte",
             source=Source(dataset="portfolio/judge.py", processing="check(cible, politique, t)"))
    if tightened:
        fact("limites_resserrees", "Limites resserrées par F1 à cette date", ", ".join(tightened), "texte",
             source=Source(dataset="policy/risk_levels.yaml", processing="compile_profile(profil ancré, t)"))
    fid_dd = fact("baisse", "Baisse depuis le plus haut (indice TWR)", snap.current_drawdown, "%")
    fid_drift = fact("derive", "Dérive Σ|w−w*|/2 avant opération", drift_metric(w_drift, target), "%")
    fid_to = fact("rotation", "Rotation aller simple du mois", ow, "%")
    fid_cost = fact("cout", "Coût estimé des mouvements", cost, "CAD",
                    source=Source(dataset=cfg.src("trading.cost_bps"),
                                  processing=f"{cfg.trading.cost_bps} pb × rotation"))
    fid_lvl = fact("niveau", "Niveau de risque F1 à la date", level_now, "niveau",
                   source=Source(dataset="policy/risk_levels.yaml", processing="compile_profile(profil ancré, t)"))
    if alpha < 1.0:
        fact("overlay_alpha", "Part du déplacement des overlays conservée après contrôle du Judge", alpha, "%")
    band_ids = [fact(f"bande.{a}", f"Écart de {a} à sa cible", w_drift.get(a, 0.0) - target.get(a, 0.0), "%")
                for a in br]
    seen_codes: Counter[str] = Counter()
    for t in trig:
        seen_codes[t.code] += 1
        key = t.code if seen_codes[t.code] == 1 else f"{t.code}.{seen_codes[t.code]}"
        val = t.value if isinstance(t.value, (int, float, str)) else str(t.value)
        fact(f"declencheur.{key}", t.message_fr, val, _trigger_unit(t) if isinstance(val, (int, float)) else "texte",
             source=Source(dataset=t.threshold_source, processing="seuil du déclencheur"))

    seq = traj.seq + 1
    vid = version_id(traj.client_id, seq, d)
    event = RebalanceEvent(
        event_id=f"ev-{vid}", month=d, action=action, drift=round(drift_metric(w_drift, target), 9), breaches=br,
        triggers=trig, overlays=states, trades=trades, flow_cad=flow_cad, turnover_oneway=ow, turnover_twoway=tw,
        cost_cad=round(cost, 2),
        judge_before=_verdict(judge_before), judge_after=_verdict(judge_after),
        judge_violations_after=list(judge_after.blocking_violations) if judge_after is not None else [],
        fact_ids=[fid_r, fid_dd, fid_drift, fid_to, fid_cost, fid_lvl, *band_ids],
    )
    version = PortfolioVersion(
        version_id=vid, parent_version_id=traj.last_version_id, seq=seq, client_id=traj.client_id,
        profile_version=traj.profile.version, decision_id=traj.decision_id, as_of=d, weights=_norm(w_eff),
        value_cad=round(value_after, 2), target=_norm(target), level=level_now,
        policy_hash=_hash(policy_now.model_dump(mode="json")), data_version=traj.pit.data_version,
        config_hash=cfg.sha256, event=event,
    )
    if traj.history is not None:
        traj.history.append(version)

    traj.weights, traj.value_cad, traj.target = version.weights, value_after, dict(target)
    if action not in ("REPROFILE_REQUIRED", "REOPTIMIZE"):
        traj.level = level_now   # un re-profilage en attente ne doit pas « consommer » un changement de niveau
    traj.seq, traj.last_version_id, traj.overlay_states = seq, vid, states
    if any(t.code == "REVIEW_DUE" for t in trig):
        traj.last_review = d
    return TickOutput(version=version, facts=facts, triggers=trig, proxied=proxied)


def _strict_breaches(w: dict[str, float], traj: Trajectory, policy: PolicySpec | None = None) -> list[str]:
    from .overlays.base import linear_breaches

    try:
        return linear_breaches(w, policy or traj.policy, traj.asset_class, tol=1e-6) if traj.asset_class else []
    except Exception:  # noqa: BLE001
        return []


def _overlays_judged(traj: Trajectory, pit_t: PitReturns, m: pd.Timestamp, w_drift: dict[str, float], value: float,
                     pd_: date) -> tuple[dict[str, float], list[OverlayState], list[Fact], float]:
    """Cible après overlays, puis contrôle du Judge sur la CIBLE elle-même (limites de risque comprises).

    Les bornes des overlays ne couvrent que les limites linéaires ; si la cible déplacée viole une limite de risque
    (CVaR, CDaR, MDD...), le déplacement est réduit d'un facteur α ∈ [0, 1] (bissection, 6 pas) jusqu'à
    l'approbation. α = 0 rend la cible de base. Un overlay ne relâche donc jamais une limite du profil.
    """
    target, states, ofacts = traj.overlay_fn(traj, pit_t, m, w_drift, value)
    # faits datés : un identifiant ``ov.*`` est le même chaque mois, on le préfixe par le mois
    ren = {f.fact_id: f"ev.{m:%Y%m}.{f.fact_id}" for f in ofacts}
    ofacts = [f.model_copy(update={"fact_id": ren[f.fact_id]}) for f in ofacts]
    states = [s.model_copy(update={"fact_ids": [ren.get(i, i) for i in s.fact_ids]}) for s in states]
    target = _clean(target)
    base = traj.base_target
    if _turnover2(base, target) <= EPS:
        return target, states, ofacts, 1.0
    rep = _judge(target, traj.policy, pd_)
    if rep is None:    # Judge indisponible : aucune garantie sur les limites de risque -> pas de déplacement
        return dict(base), [s.model_copy(update={"clipped": True, "delta": {}}) for s in states], ofacts, 0.0
    if rep.approved:
        return target, states, ofacts, 1.0
    lo, hi = 0.0, 1.0
    for _ in range(6):
        mid = (lo + hi) / 2
        cand = _mix(base, target, mid)
        r = _judge(cand, traj.policy, pd_)
        if r is not None and r.approved:
            lo = mid
        else:
            hi = mid
    alpha = lo
    scaled = [s.model_copy(update={"clipped": True, "delta": {a: v * alpha for a, v in s.delta.items()}})
              for s in states]
    return _mix(base, target, alpha), scaled, ofacts, alpha


def _mix(a: dict[str, float], b: dict[str, float], k: float) -> dict[str, float]:
    keys = sorted(set(a) | set(b))
    return _norm({x: a.get(x, 0.0) + k * (b.get(x, 0.0) - a.get(x, 0.0)) for x in keys})


def _turnover2(a: dict[str, float], b: dict[str, float]) -> float:
    return turnover(a, b)[1]


def _project(policy: PolicySpec, w: dict[str, float], as_of: date,
             allowed_target: dict[str, float] | None = None) -> dict[str, float] | None:
    """Changement minimal (norme L1) qui remet ``w`` dans les limites linéaires de la politique.

    Contrairement à ``optimizer.project`` (moindres carrés, qui étale de petits poids sur tout l'univers),
    seuls les actifs déjà détenus ou dans ``allowed_target`` (la cible) peuvent recevoir du poids.
    """
    import cvxpy as cp
    import numpy as np

    from ..portfolio.compile import compile_policy
    from ..portfolio.optimizer import _solve

    comp = compile_policy(policy, as_of)
    keep = set(w) | set(allowed_target or ())
    w0 = np.array([float(w.get(a, 0.0)) for a in comp.assets])
    x = cp.Variable(len(comp.assets))
    cons = [cp.sum(x) == 1, x >= 0]
    cons += [x[i] == 0 for i, a in enumerate(comp.assets) if a not in keep]
    for row in comp.rows:
        if row.hi is not None:
            cons.append(row.vector @ x <= row.hi)
        if row.lo is not None:
            cons.append(row.vector @ x >= row.lo)
    # objectif : changement minimal ; départage léger vers la cible (les ventes forcées vont d'abord aux lignes
    # sous-pondérées). Programme linéaire résolu par simplexe (HiGHS) : solution de sommet, donc peu de lignes.
    t0 = np.array([float((allowed_target or {}).get(a, 0.0)) for a in comp.assets])
    prob = cp.Problem(cp.Minimize(cp.norm1(x - w0) + 0.01 * cp.norm1(x - t0)), cons)
    try:
        if "HIGHS" in cp.installed_solvers():
            prob.solve(solver="HIGHS")
    except cp.error.SolverError:
        pass
    if x.value is None:
        _solve(prob)
    if x.value is None:
        return None
    out = {a: float(v) for a, v in zip(comp.assets, np.clip(x.value, 0, None), strict=True)}
    return _norm({a: v for a, v in out.items() if v >= 1e-7})


def _merge_trades(a: list[Trade], b: list[Trade], w0: dict[str, float], w1: dict[str, float],
                  value: float) -> list[Trade]:
    """Fusionne deux séries de mouvements en une seule par actif (de ``w0`` à ``w1``)."""
    reason = {t.asset_id: t.reason for t in a}
    reason.update({t.asset_id: t.reason for t in b if t.asset_id not in reason})
    out = []
    for asset in sorted(reason):
        f, t = w0.get(asset, 0.0), w1.get(asset, 0.0)
        if abs(t - f) > EPS:
            out.append(Trade(asset_id=asset, w_from=f, w_to=t, dw=t - f, amount_cad=round((t - f) * value, 2),
                             reason=reason[asset]))
    return out


def _dd_twr(perf: PerfTracker, r_month: float) -> float:
    """Baisse depuis le plus haut de l'indice TWR, en incluant le rendement brut du mois en cours."""
    idx = 1.0
    peak = 1.0
    for r in [*perf.returns, r_month]:
        idx *= 1.0 + r
        peak = max(peak, idx)
    return max(0.0, 1.0 - idx / peak)


def _rank(level: str) -> int:
    try:
        return int(level.lstrip("N"))
    except ValueError:
        return -1


def _verdict(rep) -> str:
    if rep is None:
        return "non_evalue"
    return "approuve" if rep.approved else "refuse"
