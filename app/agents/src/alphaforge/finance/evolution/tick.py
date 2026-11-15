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

    kw: dict[str, Any] = {
        "mode": "rules",
        "rephrase_explanation": False,
        "decision_id": f"dec-{profile.profile_id[:16]}-{as_of:%Y%m}",
    }  # déterministe (digest)
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
    profile: InvestorProfile  # profil ANCRÉ (profile_at) : les horizons raccourcissent avec le temps
    origin: date
    cfg: EvolutionConfig
    pit: PitReturns
    weights: dict[str, float]
    value_cad: float
    base_target: dict[str, float]  # cible stratégique de F1 → F4 (avant overlays)
    target: dict[str, float]  # cible effective (après overlays bornés)
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
    glide_pending: bool = False  # changement de cible étalé : la suite du glissement reste plafonnée
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
    proxied: dict[str, str]  # actif -> proxy utilisé ce mois (HYPOTHESE)


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
    except (KeyError, ValueError):  # actif hors catalogue (tests synthétiques) : pas de coussin
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
    except Exception:  # solveur en échec : pas de coussin
        return dict(target)
    if x.value is None:
        return dict(target)
    out = _clean({a: float(v) for a, v in zip(comp.assets, np.clip(x.value, 0, None), strict=True)})
    rep = _judge(out, policy, as_of)
    return out if rep is not None and rep.approved else dict(target)


def start(  # noqa: PLR0913 - signature publique : replay.py et les tests passent les options par mot-clé
    client_id: str,
    profile: InvestorProfile,
    origin: date,
    value_cad: float,
    pit: PitReturns,
    cfg: EvolutionConfig,
    *,
    initial_weights: dict[str, float] | None = None,
    build_fn: Callable[[InvestorProfile, date], BuildOutcome] = default_build,
    overlay_fn=None,
    history: HistoryStore | None = None,
    asset_class: dict[str, str] | None = None,
    cash_assets: tuple[str, ...] = ("ZST.TO",),
) -> Trajectory:
    """Construit la cible stratégique à l'origine (F1 → F4) et ouvre la trajectoire."""
    origin = month_end(origin).date()
    anchored = profile_at(profile, origin)
    out = build_fn(anchored, origin)
    out = BuildOutcome(
        target=cushioned(out.policy, _clean(out.target), origin, cfg.bands.cap_cushion),
        policy=out.policy,
        level=out.level,
        decision=out.decision,
    )
    w0 = _norm(initial_weights) if initial_weights else dict(out.target)
    return Trajectory(
        client_id=client_id,
        profile=anchored,
        origin=origin,
        cfg=cfg,
        pit=pit,
        weights=w0,
        value_cad=float(value_cad),
        base_target=dict(out.target),
        target=dict(out.target),
        policy=out.policy,
        level=out.level,
        perf=PerfTracker(float(value_cad), cash_assets=cash_assets),
        history=history,
        decision_id=out.decision.decision_id if out.decision else None,
        decisions=[out.decision] if out.decision else [],
        build_fn=build_fn,
        overlay_fn=overlay_fn,
        asset_class=dict(asset_class or {}),
        kyc_confirmed=origin,
        last_review=origin,
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

    key = (_hash(policy.model_dump(mode="json")), as_of)  # contenu, pas id() : une adresse peut être réutilisée
    if key not in _WINDOWS:
        if len(_WINDOWS) > 64:
            _WINDOWS.clear()
        _WINDOWS[key] = returns_window(policy, as_of, compile_policy(policy, as_of).assets)
    return _WINDOWS[key]


def _judge(weights: dict[str, float], policy: PolicySpec, as_of: date):
    from ..portfolio.judge import check

    try:
        return check(weights, policy, as_of, window=_window(policy, as_of))
    except Exception:  # un historique insuffisant au début d'une fenêtre ne doit pas arrêter le rejeu
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
        if (
            o is None
            or (lim.max is not None and (o.max is None or lim.max < o.max - 1e-9))
            or (lim.min is not None and (o.min is None or lim.min > o.min + 1e-9))
        ):
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
    m = month_end(month)
    mt = _MonthTick(traj, m, policy_date or m.date(), flow_cad)
    mt.mark_value()
    mt.apply_month_flow()
    mt.recompile_policy()
    mt.apply_overlays()
    mt.evaluate_triggers()
    mt.choose_action()
    mt.execute_trades()
    return mt.record_version()


class _MonthTick:
    """Un mois en cours de calcul : le contexte (trajectoire, dates, vue point-in-time), les faits datés du mois et
    le résultat de chaque étape, posé dans l'ordre fixe du docstring du module. Chaque méthode publique est une
    étape ; ``tick`` les enchaîne."""

    def __init__(self, traj: Trajectory, m: pd.Timestamp, policy_date: date, flow_cad: float) -> None:
        self.traj, self.cfg, self.m, self.d, self.pd_ = traj, traj.cfg, m, m.date(), policy_date
        self.pit_t = traj.pit.with_horizon(m)  # point-in-time : toute lecture après t lève LookaheadError
        self.flow_cad = flow_cad
        self.facts: list[Fact] = []
        self.src_pit = Source(
            dataset=f"pit:monthly_returns@{traj.pit.data_version}", processing="rendements mensuels CAD"
        )
        self.states: list[OverlayState] = []
        self.alpha = 1.0
        self.reason: str | None = None
        self.trades: list[Trade] = []
        self.rebuilt_for_risk = False

    def fact(  # noqa: PLR0913 - un paramètre par champ du Fact (contrat decision.py), statut et source par mot-clé
        self,
        key: str,
        label: str,
        value,
        unit: str,
        *,
        status: str = "FAIT",
        source: Source | None = None,
    ) -> str:
        fid = f"ev.{self.d:%Y%m}.{key}"
        self.facts.append(
            Fact(
                fact_id=fid,
                label_fr=label,
                value=value if not isinstance(value, float) else round(value, 6),
                unit=unit,
                as_of=self.d,
                status=status,
                sources=[source or self.src_pit],
                trace_id=f"evolution:{self.traj.client_id[:8]}:{self.d:%Y%m}",
            )
        )
        return fid

    # ------------------------------------------------------------------ 1 à 5 : état du mois avant décision
    def mark_value(self) -> None:
        """1. Mise à la valeur de marché avec les rendements du mois (proxy long déclaré si pas d'historique)."""
        r, self.proxied = _month_returns(self.traj, self.pit_t, self.m)
        self.w_drift, self.gross, _missing = mark_to_market(self.traj.weights, r)
        self.value = self.traj.value_cad * (1.0 + self.gross)
        self.fid_r = self.fact("r_portefeuille", "Rendement du portefeuille sur le mois", self.gross, "%")
        for a, p in self.proxied.items():
            self.fact(f"proxy.{a}", f"Historique de {a} remplacé par {p}", p, "texte", status="HYPOTHESE")

    def apply_month_flow(self) -> None:
        """2. Flux du mois ; ``flow_cad`` devient le flux effectif (un retrait est plafonné à la valeur)."""
        if not self.flow_cad:
            return
        v_before = self.value
        self.w_drift, self.value = apply_flow(
            self.w_drift, self.value, self.flow_cad, self.traj.target, self.cfg.flows.contribution_first
        )
        self.flow_cad = self.value - v_before

    def recompile_policy(self) -> None:
        """3. Glidepath : re-compilation de F1 à la date sur le profil ancré."""
        from ..policy import compile_profile

        traj = self.traj
        comp = compile_profile(traj.profile, self.pd_)
        self.comp, self.level_prev, self.level_now = comp, traj.level, comp.level
        # F1 resserre les limites avec le temps même à niveau égal (règle des dollars, horizon) : un resserrement
        # impose de recalculer la cible ; un simple relâchement est adopté sans mouvement.
        self.tightened = _limits_tightened(traj.policy, comp.policy) if comp.policy is not None else []
        self.target_changed = comp.policy is not None and (self.level_now != self.level_prev or bool(self.tightened))
        if comp.policy is not None and not self.target_changed:
            traj.policy = comp.policy
        self.policy_now = comp.policy or traj.policy  # la politique À LA DATE : Judge et conformité s'y mesurent

    def apply_overlays(self) -> None:
        """4. Overlays bornés sur la cible stratégique ; note les signaux qui ont changé."""
        traj = self.traj
        self.target = dict(traj.base_target)
        if traj.overlay_fn is not None and traj.overlay_active is not None:
            self._overlay_target()
        self.changed_signals = [s.name for s in self.states if s.active and traj.last_signals.get(s.name) != s.signal]
        for s in self.states:
            traj.last_signals[s.name] = s.signal

    def _overlay_target(self) -> None:
        self.target, self.states, ofacts, self.alpha = _overlays_judged(
            self.traj, self.pit_t, self.m, self.w_drift, self.value, self.pd_
        )
        self.facts.extend(ofacts)

    def evaluate_triggers(self) -> None:
        """5. Judge sur les poids dérivés, puis déclencheurs."""
        traj = self.traj
        self.judge_before = _judge(self.w_drift, self.policy_now, self.pd_)
        # baisse estimée à la fin de ce mois, avant opération (indice TWR ; la référence « cost » est gérée
        # par les déclencheurs à partir de value_cad et invested_cad)
        perf_now = traj.perf.snapshot().model_copy(
            update={
                "value_cad": self.value,
                "invested_cad": traj.perf.initial_value_cad + sum(traj.perf.flows) + self.flow_cad,
                "current_drawdown": _dd_twr(traj.perf, self.gross),
            }
        )
        self.trig = evaluate(
            TriggerState(
                as_of=self.pd_,
                origin=traj.origin,
                profile=traj.profile,
                level_prev=self.level_prev,
                level_now=self.level_now,
                compile_now=self.comp,
                judge_drift=self.judge_before,
                perf=perf_now,
                flow_cad=self.flow_cad,
                value_cad=self.value,
                kyc_confirmed=traj.kyc_confirmed,
                last_review=traj.last_review,
                life_event=traj.life_event,
                managed_account=traj.managed_account,
                overlay_signal_changes=self.changed_signals,
            ),
            self.cfg,
        )

    # ------------------------------------------------------------------ 6 : échelle d'actions et mouvements
    def choose_action(self) -> None:
        """6. Échelle d'actions : REPROFILE_REQUIRED > REOPTIMIZE > OVERLAY_SHIFT > REBALANCE_TO_BANDS > HOLD."""
        traj, max_turnover = self.traj, self.cfg.trading.max_turnover_tick
        self.br = breaches(self.w_drift, self.target, self.cfg.bands)
        self.w_to = self.w_drift
        drift_refused = self.judge_before is not None and not self.judge_before.approved
        if any(t.blocking for t in self.trig):
            # aucune décision stratégique en attendant le profil ; une limite bloquante franchie par la dérive est
            # tout de même rétablie (conformité minimale) : attendre ne doit jamais laisser une violation en place
            self.action = "REPROFILE_REQUIRED"
            traj.reprofile_pending = True
            if drift_refused:
                self.reason = "compliance"
        elif self.target_changed:
            self._reoptimize()
        elif traj.glide_pending:
            # suite d'un changement de cible à la hausse : même plafond de rotation chaque mois jusqu'à la cible
            self.action, self.reason = "REOPTIMIZE", "glidepath"
            self.w_to = _step_to(self.w_drift, self.target, max_turnover)
            traj.glide_pending = turnover(self.w_to, self.target)[1] > 1e-6
        elif self.changed_signals and drift_metric(self.w_drift, self.target) > EPS:
            self.action, self.reason = "OVERLAY_SHIFT", "overlay"
            self.w_to = _step_to(self.w_drift, self.target, max_turnover)
        elif self.br:
            self.action, self.reason = "REBALANCE_TO_BANDS", "band"
            self.w_to = rebalance_to_bands(self.w_drift, self.target, self.cfg.bands)
        elif drift_refused:
            # la dérive seule fait franchir une limite bloquante (ex. une ligne au plafond qui monte) : opération de
            # conformité minimale, sans rééquilibrage complet
            self.action, self.reason = "REBALANCE_TO_BANDS", "compliance"
        else:
            self.action = "HOLD"

    def _reoptimize(self) -> None:
        """Niveau changé ou limites resserrées : nouvelle cible F1 → F4 à la date, overlays compris."""
        traj = self.traj
        self.action = "REOPTIMIZE"
        base, out = self._rebuild_target()
        traj.base_target, traj.policy, traj.level = base, out.policy, out.level
        self.target = dict(base)
        if traj.overlay_fn is not None:
            self._overlay_target()
        # niveau en baisse ou limites resserrées : on y va d'un coup ; une hausse se fait par glissement
        stricter = _rank(self.level_now) < _rank(self.level_prev) or bool(self.tightened)
        self.w_to = (
            dict(self.target) if stricter else _step_to(self.w_drift, self.target, self.cfg.trading.max_turnover_tick)
        )
        self.reason = "glidepath"
        traj.glide_pending = turnover(self.w_to, self.target)[1] > 1e-6

    def _rebuild_target(self) -> tuple[dict[str, float], BuildOutcome]:
        """F1 → F4 à la date de la politique (décision gardée avec les déclencheurs du mois) ; cible coussinée."""
        traj = self.traj
        out = traj.build_fn(traj.profile, self.pd_)
        if out.decision is not None:
            dec = out.decision.model_copy(update={"reprofile_triggers_fired": [t.code for t in self.trig]})
            traj.decisions.append(dec)
            traj.decision_id = dec.decision_id
        return cushioned(out.policy, _clean(out.target), self.pd_, self.cfg.bands.cap_cushion), out

    def execute_trades(self) -> None:
        """Mouvements vers ``w_to``, puis rétablissement des limites ; coût et Judge après l'opération."""
        self.w_eff = dict(self.w_drift)
        if self.reason is not None:
            if self.reason != "compliance":
                self.trades, self.w_eff = plan_trades(
                    self.w_drift, self.w_to, self.value, self.reason, self.cfg.trading.min_trade_cad
                )
            self._restore_linear_limits()
            self._restore_risk_limits()
            if self.reason == "compliance":
                self.reason = "liquidation"
        self.ow, self.tw = turnover(self.w_drift, self.w_eff)
        self.cost = cost_cad(self.ow, self.value, self.cfg.trading.cost_bps)
        self.value_after = self.value - self.cost
        self.judge_after = _judge(self.w_eff, self.policy_now, self.pd_) if self.trades else self.judge_before

    def _restore_linear_limits(self) -> None:
        """Conformité : projection minimale sur les limites linéaires de la politique, depuis les poids obtenus.

        Ces opérations passent même sous le montant minimal : une limite bloquante n'est pas négociable. Contrôle
        strict (1e-6) en plus du Judge (tolérance 1e-4) : un reliquat d'arrondi ne doit pas dépasser une limite.
        """
        rep_mid = _judge(self.w_eff, self.policy_now, self.pd_)
        if not (
            (rep_mid is not None and not rep_mid.approved) or _strict_breaches(self.w_eff, self.traj, self.policy_now)
        ):
            return
        w_fix = _project(self.policy_now, self.w_eff, self.pd_, allowed_target=self.target)
        if w_fix is None:
            return
        kind = "liquidation" if self.reason == "compliance" else self.reason
        extra, self.w_eff = plan_trades(dict(self.w_eff), w_fix, self.value, kind, 0.0)
        self.trades = _merge_trades(self.trades, extra, self.w_drift, self.w_eff, self.value)

    def _restore_risk_limits(self) -> None:
        """Une limite de RISQUE (non linéaire) encore violée : retour à la cible.

        Si la cible elle-même n'est plus approuvée à cette date (mesure de risque sur un historique glissant), le
        moteur la recalcule : F1 → F4 à la date, puis mouvement vers la nouvelle cible.
        """
        rep_fix = _judge(self.w_eff, self.policy_now, self.pd_)
        if rep_fix is None or rep_fix.approved:
            return
        self._move_to_target("band")
        rep_t = _judge(self.w_eff, self.policy_now, self.pd_)
        if rep_t is None or rep_t.approved or self.action == "REOPTIMIZE":
            return
        traj = self.traj
        base, out = self._rebuild_target()
        traj.base_target, traj.policy, self.policy_now = base, out.policy, out.policy
        self.target = dict(base)
        self._move_to_target("reoptimize")
        if self.action != "REPROFILE_REQUIRED":
            self.action = "REOPTIMIZE"
        self.rebuilt_for_risk = True

    def _move_to_target(self, reason: str) -> None:
        extra, self.w_eff = plan_trades(dict(self.w_eff), dict(self.target), self.value, reason, 0.0)
        self.trades = _merge_trades(self.trades, extra, self.w_drift, self.w_eff, self.value)

    # ------------------------------------------------------------------ 7 : performance, faits, version
    def record_version(self) -> TickOutput:
        """7. Performance, faits pour l'explication, nouvelle version chaînée ; la trajectoire avance d'un mois."""
        traj = self.traj
        r_net = (self.value_after - self.flow_cad) / traj.value_cad - 1.0 if traj.value_cad > 0 else 0.0
        cash = traj.perf.cash_assets[0] if traj.perf.cash_assets else None
        traj.perf.update(
            self.d,
            r_net,
            self.value_after,
            self.flow_cad,
            self.ow,
            self.cost,
            self.w_eff,
            r_cash=self.pit_t.month(self.m).get(cash) if cash and cash in self.pit_t.assets else None,
        )
        version = self._new_version(self._event_facts())
        if traj.history is not None:
            traj.history.append(version)
        traj.weights, traj.value_cad, traj.target = version.weights, self.value_after, dict(self.target)
        if self.action not in ("REPROFILE_REQUIRED", "REOPTIMIZE"):
            traj.level = self.level_now  # un re-profilage en attente ne doit pas « consommer » un changement de niveau
        traj.seq, traj.last_version_id, traj.overlay_states = version.seq, version.version_id, self.states
        if any(t.code == "REVIEW_DUE" for t in self.trig):
            traj.last_review = self.d
        return TickOutput(version=version, facts=self.facts, triggers=self.trig, proxied=self.proxied)

    def _event_facts(self) -> list[str]:
        """Faits de fin de mois ; rend les identifiants cités par l'événement."""
        cfg, w_drift, target = self.cfg, self.w_drift, self.target
        self._decision_facts()
        ids = [
            self.fid_r,
            self.fact(
                "baisse", "Baisse depuis le plus haut (indice TWR)", self.traj.perf.snapshot().current_drawdown, "%"
            ),
            self.fact("derive", "Dérive Σ|w−w*|/2 avant opération", drift_metric(w_drift, target), "%"),
            self.fact("rotation", "Rotation aller simple du mois", self.ow, "%"),
            self.fact(
                "cout",
                "Coût estimé des mouvements",
                self.cost,
                "CAD",
                source=Source(dataset=cfg.src("trading.cost_bps"), processing=f"{cfg.trading.cost_bps} pb × rotation"),
            ),
            self.fact(
                "niveau",
                "Niveau de risque F1 à la date",
                self.level_now,
                "niveau",
                source=Source(dataset="policy/risk_levels.yaml", processing="compile_profile(profil ancré, t)"),
            ),
        ]
        if self.alpha < 1.0:
            self.fact(
                "overlay_alpha", "Part du déplacement des overlays conservée après contrôle du Judge", self.alpha, "%"
            )
        ids += [
            self.fact(f"bande.{a}", f"Écart de {a} à sa cible", w_drift.get(a, 0.0) - target.get(a, 0.0), "%")
            for a in self.br
        ]
        self._trigger_facts()
        return ids

    def _decision_facts(self) -> None:
        """Valeur après coûts, et ce qui a fait bouger la cible ce mois-ci (recalcul pour le risque, limites F1)."""
        self.fact("valeur", "Valeur du portefeuille en fin de mois, après coûts", self.value_after, "CAD")
        if self.rebuilt_for_risk:
            self.fact(
                "cible_recalculee",
                "Cible recalculée : l'ancienne n'était plus approuvée par le Judge à cette date",
                "recalculée",
                "texte",
                source=Source(dataset="portfolio/judge.py", processing="check(cible, politique, t)"),
            )
        if self.tightened:
            self.fact(
                "limites_resserrees",
                "Limites resserrées par F1 à cette date",
                ", ".join(self.tightened),
                "texte",
                source=Source(dataset="policy/risk_levels.yaml", processing="compile_profile(profil ancré, t)"),
            )

    def _trigger_facts(self) -> None:
        """Un fait par déclencheur ; un code répété reçoit un suffixe (.2, .3...) pour garder des ids uniques."""
        seen_codes: Counter[str] = Counter()
        for t in self.trig:
            seen_codes[t.code] += 1
            key = t.code if seen_codes[t.code] == 1 else f"{t.code}.{seen_codes[t.code]}"
            val = t.value if isinstance(t.value, int | float | str) else str(t.value)
            self.fact(
                f"declencheur.{key}",
                t.message_fr,
                val,
                _trigger_unit(t) if isinstance(val, int | float) else "texte",
                source=Source(dataset=t.threshold_source, processing="seuil du déclencheur"),
            )

    def _new_version(self, fact_ids: list[str]) -> PortfolioVersion:
        traj, w_drift, target = self.traj, self.w_drift, self.target
        seq = traj.seq + 1
        vid = version_id(traj.client_id, seq, self.d)
        judge_after = self.judge_after
        event = RebalanceEvent(
            event_id=f"ev-{vid}",
            month=self.d,
            action=self.action,
            drift=round(drift_metric(w_drift, target), 9),
            breaches=self.br,
            triggers=self.trig,
            overlays=self.states,
            trades=self.trades,
            flow_cad=self.flow_cad,
            turnover_oneway=self.ow,
            turnover_twoway=self.tw,
            cost_cad=round(self.cost, 2),
            judge_before=_verdict(self.judge_before),
            judge_after=_verdict(judge_after),
            judge_violations_after=list(judge_after.blocking_violations) if judge_after is not None else [],
            fact_ids=fact_ids,
        )
        return PortfolioVersion(
            version_id=vid,
            parent_version_id=traj.last_version_id,
            seq=seq,
            client_id=traj.client_id,
            profile_version=traj.profile.version,
            decision_id=traj.decision_id,
            as_of=self.d,
            weights=_norm(self.w_eff),
            value_cad=round(self.value_after, 2),
            target=_norm(target),
            level=self.level_now,
            policy_hash=_hash(self.policy_now.model_dump(mode="json")),
            data_version=traj.pit.data_version,
            config_hash=self.cfg.sha256,
            event=event,
        )


def _strict_breaches(w: dict[str, float], traj: Trajectory, policy: PolicySpec | None = None) -> list[str]:
    from .overlays.base import linear_breaches

    try:
        return linear_breaches(w, policy or traj.policy, traj.asset_class, tol=1e-6) if traj.asset_class else []
    except Exception:  # contrôle strict indisponible : le Judge reste la référence
        return []


def _overlays_judged(  # noqa: PLR0913 - signature gardée : test_tick_review l'appelle telle quelle
    traj: Trajectory,
    pit_t: PitReturns,
    m: pd.Timestamp,
    w_drift: dict[str, float],
    value: float,
    pd_: date,
) -> tuple[dict[str, float], list[OverlayState], list[Fact], float]:
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
    if rep is None:  # Judge indisponible : aucune garantie sur les limites de risque -> pas de déplacement
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
    scaled = [
        s.model_copy(update={"clipped": True, "delta": {a: v * alpha for a, v in s.delta.items()}}) for s in states
    ]
    return _mix(base, target, alpha), scaled, ofacts, alpha


def _mix(a: dict[str, float], b: dict[str, float], k: float) -> dict[str, float]:
    keys = sorted(set(a) | set(b))
    return _norm({x: a.get(x, 0.0) + k * (b.get(x, 0.0) - a.get(x, 0.0)) for x in keys})


def _turnover2(a: dict[str, float], b: dict[str, float]) -> float:
    return turnover(a, b)[1]


def _project(
    policy: PolicySpec, w: dict[str, float], as_of: date, allowed_target: dict[str, float] | None = None
) -> dict[str, float] | None:
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


def _merge_trades(
    a: list[Trade], b: list[Trade], w0: dict[str, float], w1: dict[str, float], value: float
) -> list[Trade]:
    """Fusionne deux séries de mouvements en une seule par actif (de ``w0`` à ``w1``)."""
    reason = {t.asset_id: t.reason for t in a}
    reason.update({t.asset_id: t.reason for t in b if t.asset_id not in reason})
    out = []
    for asset in sorted(reason):
        f, t = w0.get(asset, 0.0), w1.get(asset, 0.0)
        if abs(t - f) > EPS:
            out.append(
                Trade(
                    asset_id=asset,
                    w_from=f,
                    w_to=t,
                    dw=t - f,
                    amount_cad=round((t - f) * value, 2),
                    reason=reason[asset],
                )
            )
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
