"""Déclencheurs du tick mensuel (glidepath, objectifs, pertes, KYC, revue, événements, flux, overlays).

SIMULATION SEULEMENT. Chaque déclencheur est un fait calculé par le code, avec sa valeur, son seuil et la
source du seuil (chemin YAML ou champ du profil). Un déclencheur bloquant impose ``REPROFILE_REQUIRED`` :
aucune opération illustrative n'est simulée ce mois-là.

Horizon qui raccourcit : ``Goal.horizon_years`` est relatif à la création du profil et ne bouge pas tout seul
(``compiler._goal_horizon`` prend ``min(horizon_years, target_date - as_of)``). ``profile_at`` fige donc une
date cible ``origin + horizon_years`` au début du rejeu, pour que la recompilation à un ``as_of`` ultérieur
raccourcisse l'horizon de façon déterministe.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from ..contracts.evolution import PerfSnapshot, TriggerFired
from ..contracts.profile import InvestorProfile, Priority
from .config import EvolutionConfig

if TYPE_CHECKING:  # évite d'importer numpy/cvxpy pour de simples annotations
    from ..policy.models import CompileResult
    from ..portfolio.judge import JudgeReport

LEVELS = ("N0", "N1", "N2", "N3", "N4", "N5")
_NI_31_103 = "NI 31-103 art. 13.2 [non vérifié]"


@dataclass(frozen=True)
class TriggerState:
    """Photo du mois évalué : tout ce dont les déclencheurs ont besoin, déjà calculé par le code."""
    as_of: date
    origin: date
    profile: InvestorProfile
    level_prev: str | None
    level_now: str
    compile_now: CompileResult
    judge_drift: JudgeReport | None = None
    perf: PerfSnapshot | None = None
    flow_cad: float = 0.0
    value_cad: float = 0.0
    kyc_confirmed: date | None = None          # None -> origin
    last_review: date | None = None            # None -> origin
    life_event: dict[str, Any] | None = None   # {"code": str, "date": date}
    managed_account: bool = False
    overlay_signal_changes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- outils de dates


def _is_month_end(d: date) -> bool:
    return d.day == calendar.monthrange(d.year, d.month)[1]


def months_between(a: date, b: date) -> int:
    """Nombre de mois calendaires entiers de ``a`` à ``b`` (arrondi vers le bas ; négatif si ``b < a``).

    Une fin de mois vers une fin de mois compte pour un mois entier (31 janv. -> 28 févr. = 1).
    """
    if b < a:
        return -months_between(b, a)
    m = (b.year - a.year) * 12 + (b.month - a.month)
    if b.day < a.day and not _is_month_end(b):
        m -= 1
    return m


def _add_years(d: date, years: float) -> date:
    return d + timedelta(days=round(years * 365.25))


def _prev_month(d: date) -> date:
    y, m = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _fr(x: float, nd: int = 1) -> str:
    return f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")


def _pct(x: float) -> str:
    return f"{_fr(100 * x, 1)} %"


# --------------------------------------------------------------------------- profil daté


def profile_at(profile: InvestorProfile, origin: date) -> InvestorProfile:
    """Copie du profil où chaque objectif exprimé en ``horizon_years`` reçoit ``target_date = origin + horizon``.

    Calcul fait une seule fois, à l'origine du rejeu ; si l'objectif avait déjà une date, on garde la plus proche
    des deux (même horizon qu'à l'origine). ``horizon_years`` est retiré pour que seul le temps qui passe compte.
    Le profil d'entrée n'est jamais modifié.
    """
    goals = []
    for g in profile.goals:
        if g.horizon_years is None:
            goals.append(g.model_copy(deep=True))
            continue
        target = _add_years(origin, g.horizon_years)
        if g.target_date is not None:
            target = min(target, g.target_date)
        goals.append(g.model_copy(update={"target_date": target, "horizon_years": None}, deep=True))
    return profile.model_copy(update={"goals": goals}, deep=True)


def _goal_target(g, origin: date) -> date:
    if g.target_date is not None and g.horizon_years is not None:
        return min(g.target_date, _add_years(origin, g.horizon_years))
    return g.target_date if g.target_date is not None else _add_years(origin, g.horizon_years)


# --------------------------------------------------------------------------- source du niveau


def _last(trace: list[dict], rule: str, output: Any = None) -> dict | None:
    for e in reversed(trace):
        if e.get("rule") == rule and (output is None or e.get("output") == output):
            return e
    return None


def level_source(cr: CompileResult) -> str:
    """Chemin YAML de l'entrée de trace qui fixe le niveau final (plafond d'horizon en priorité si ex aequo)."""
    tr = cr.trace
    final, l0 = _last(tr, "level.final"), _last(tr, "level.L0")
    if final is None or l0 is None:
        return "risk_levels.yaml#level"
    if final.get("output") != l0.get("output"):
        return final["yaml_path"]                       # règle des dollars ou mode PROTECTION
    caps: dict = l0.get("inputs") or {}
    i0 = min(caps.values()) if caps else None
    order = (("horizon", "horizon_cap"), ("buckets", "buckets.goal"), ("status", "status.INCOMPLETE.level_cap"),
             ("R", "level.R"))
    for key, rule in order:
        if caps.get(key) == i0:
            e = _last(tr, rule, l0["output"]) if key == "buckets" else _last(tr, rule)
            if e is not None:
                return e["yaml_path"]
    return l0["yaml_path"]


# --------------------------------------------------------------------------- évaluation


def evaluate(state: TriggerState, cfg: EvolutionConfig) -> list[TriggerFired]:
    """Évalue tous les déclencheurs du mois, dans un ordre fixe (bloquants et non bloquants mêlés)."""
    s, rv = state, cfg.review
    out: list[TriggerFired] = []

    # Glidepath : changement de niveau
    if s.level_prev is not None and s.level_now != s.level_prev:
        T = s.compile_now.horizon_years
        h = f" ; horizon restant {_fr(T, 1)} ans" if T is not None else ""
        sens = "baisse" if LEVELS.index(s.level_now) < LEVELS.index(s.level_prev) else "hausse"
        out.append(TriggerFired(
            code="HORIZON_LEVEL_CHANGE", blocking=False, value=s.level_now, threshold=s.level_prev,
            threshold_source=level_source(s.compile_now),
            message_fr=f"Le niveau de risque est en {sens} : {s.level_prev} -> {s.level_now}{h}.",
        ))

    # Objectif « besoin » à moins de N mois (une seule fois : entrée dans la fenêtre ou premier mois)
    # premier tick = premier mois après l'origine (l'origine elle-même n'est jamais un tick)
    first_tick = months_between(s.origin, s.as_of) <= 1
    for g in s.profile.goals:
        if g.priority is not Priority.BESOIN:
            continue
        target = _goal_target(g, s.origin)
        left = months_between(s.as_of, target)
        if not 0 < left <= rv.need_goal_months:
            continue
        if not first_tick and months_between(_prev_month(s.as_of), target) <= rv.need_goal_months:
            continue
        out.append(TriggerFired(
            code="GOAL_NEED_12M", blocking=False, value=g.goal_id, threshold=rv.need_goal_months,
            threshold_source=cfg.src("review.need_goal_months"),
            message_fr=f"L'objectif essentiel « {g.goal_id} » arrive dans {left} mois (seuil : {rv.need_goal_months}"
                       f" mois, échéance {target.isoformat()}).",
        ))

    # Perte maximale acceptable
    p = s.profile
    if s.perf is not None:
        if p.max_acceptable_loss_pct is not None:
            if rv.drawdown_reference == "hwm":
                dd, ref = s.perf.current_drawdown, "depuis le plus haut"
            else:
                inv = s.perf.invested_cad
                dd, ref = (max(0.0, 1 - s.perf.value_cad / inv) if inv > 0 else 0.0), "par rapport aux apports nets"
            if dd >= p.max_acceptable_loss_pct:
                out.append(TriggerFired(
                    code="DRAWDOWN_LIMIT", blocking=True, value=round(dd, 6), threshold=p.max_acceptable_loss_pct,
                    threshold_source="profile.max_acceptable_loss_pct",
                    message_fr=f"La baisse {ref} atteint {_pct(dd)}, au-delà de la perte acceptable déclarée de "
                               f"{_pct(p.max_acceptable_loss_pct)} ; re-profilage requis.",
                ))
        if p.max_acceptable_loss_cad is not None:
            loss = s.perf.invested_cad - s.perf.value_cad
            if loss >= p.max_acceptable_loss_cad and loss > 0:
                out.append(TriggerFired(
                    code="DRAWDOWN_LIMIT", blocking=True, value=round(loss, 2), threshold=p.max_acceptable_loss_cad,
                    threshold_source="profile.max_acceptable_loss_cad",
                    message_fr=f"La perte par rapport aux apports nets atteint {_fr(loss, 0)} $, au-delà de la perte "
                               f"acceptable déclarée de {_fr(p.max_acceptable_loss_cad, 0)} $ ; re-profilage requis.",
                ))

    # Dérive qui viole une règle du Judge (le tick rééquilibre)
    if s.judge_drift is not None and s.judge_drift.blocking_violations:
        ids = list(s.judge_drift.blocking_violations)
        out.append(TriggerFired(
            code="JUDGE_VIOLATION_DRIFT", blocking=False, value=",".join(ids), threshold=None,
            threshold_source="portfolio.judge.check",
            message_fr=f"Les poids après dérive enfreignent {len(ids)} règle(s) du mandat : {', '.join(ids)}.",
        ))

    # Âge du KYC
    kyc = s.kyc_confirmed or s.origin
    kyc_max, kyc_key = ((rv.kyc_months_managed, "review.kyc_months_managed") if s.managed_account
                        else (rv.kyc_months_other, "review.kyc_months_other"))
    age = months_between(kyc, s.as_of)
    if age >= kyc_max:
        out.append(TriggerFired(
            code="KYC_AGE", blocking=True, value=age, threshold=kyc_max, threshold_source=cfg.src(kyc_key),
            message_fr=f"Le profil a été confirmé il y a {age} mois (limite : {kyc_max} mois, {_NI_31_103}) ; "
                       f"re-profilage requis.",
        ))

    # Revue périodique
    since = months_between(s.last_review or s.origin, s.as_of)
    if since >= rv.review_months:
        out.append(TriggerFired(
            code="REVIEW_DUE", blocking=False, value=since, threshold=rv.review_months,
            threshold_source=cfg.src("review.review_months"),
            message_fr=f"Dernière revue il y a {since} mois (périodicité : {rv.review_months} mois).",
        ))

    # Événement de vie
    ev = s.life_event
    if ev and ev.get("date") is not None and ev["date"] <= s.as_of:
        out.append(TriggerFired(
            code="LIFE_EVENT", blocking=True, value=str(ev.get("code")), threshold=ev["date"].isoformat(),
            threshold_source="state.life_event",
            message_fr=f"Événement de vie « {ev.get('code')} » daté du {ev['date'].isoformat()} ; re-profilage requis.",
        ))

    # Flux important
    lim = cfg.flows.large_flow_share * max(s.value_cad, 0.0)
    if s.flow_cad != 0 and abs(s.flow_cad) >= lim:
        kind = "Apport" if s.flow_cad > 0 else "Retrait"
        out.append(TriggerFired(
            code="LARGE_FLOW", blocking=False, value=round(s.flow_cad, 2), threshold=round(lim, 2),
            threshold_source=cfg.src("flows.large_flow_share"),
            message_fr=f"{kind} de {_fr(abs(s.flow_cad), 0)} $, soit au moins {_pct(cfg.flows.large_flow_share)} de la "
                       f"valeur ({_fr(s.value_cad, 0)} $).",
        ))

    # Changement de signal d'un overlay
    for name in s.overlay_signal_changes:
        out.append(TriggerFired(
            code="OVERLAY_SIGNAL", blocking=False, value=name, threshold=None,
            threshold_source=cfg.src(f"overlays.{name}"),
            message_fr=f"Le signal de l'overlay « {name} » a changé ce mois-ci.",
        ))
    return out
