"""Fusion déterministe des amendements des lentilles.

Règles :
1. Un amendement hors schéma, hors univers, sans preuve existante ou qui RELÂCHE une borne est rejeté.
2. Les conflits se tranchent par priorité : contraintes > risque > horizon > diversité. À priorité
   égale, la lentille au poids d'emphase le plus élevé passe d'abord.
3. Garde anti-cliquet : on n'applique pas un amendement qui rend le mandat infaisable ; on n'abaisse
   pas une limite de risque sous ``floor_ratio`` fois sa valeur d'origine (défaut 0,6), pour ne pas
   pousser vers le quasi-encaisse à force de resserrements successifs.
4. Garde des actualités : un amendement autre que ``flag_only`` qui cite une actualité (``okf.news.*``) est
   rejeté. Une nouvelle peut être signalée, jamais changer le mandat (rumeur ≠ fait).
"""

from __future__ import annotations

from collections.abc import Callable

from alphaforge.finance.contracts.policy import Limit, PolicySpec, Selector
from alphaforge.finance.strategy.okf_facts import NEWS_FACT_PREFIX
from alphaforge.finance.strategy.rules import clamp_strategy_floors

from .schemas import PRIORITY, AppliedAmendment, LensReport

FLOOR_RATIO = 0.6
NEWS_REJECT_FR = "une actualité ne justifie jamais un changement du mandat (rumeur ≠ fait)"
_MEASURE_ORDER = {"VARIANCE": 0, "CVAR": 1, "CDAR": 2}  # CDaR = plus prudente (drawdown)


def _limit(policy: PolicySpec, rule_id: str) -> Limit | None:
    return next((lim for lim in policy.limits if lim.rule_id == rule_id), None)


def apply_amendments(
    policy: PolicySpec,
    reports: list[LensReport],
    emphasis: dict[str, float],
    known_fact_ids: set[str],
    original: PolicySpec | None = None,
    feasible: Callable[[PolicySpec], bool] | None = None,
    floor_ratio: float = FLOOR_RATIO,
) -> tuple[PolicySpec, list[AppliedAmendment]]:
    original = original or policy
    items = [(r.lens, a) for r in reports for a in r.amendments]
    items.sort(key=lambda la: (PRIORITY[la[0]], -emphasis.get(la[0], 0.0)))
    cur = policy.model_copy(deep=True)
    log: list[AppliedAmendment] = []

    def reject(lens, a, why):
        log.append(AppliedAmendment(lens=lens, amendment=a, status="rejete", why_fr=why))

    for lens, a in items:
        if a.kind != "flag_only" and any(f.startswith(NEWS_FACT_PREFIX) for f in a.evidence_fact_ids):
            reject(lens, a, NEWS_REJECT_FR)
            continue
        missing = [f for f in a.evidence_fact_ids if f not in known_fact_ids]
        if missing:
            reject(lens, a, f"preuve inconnue : {missing}")
            continue
        if a.kind == "flag_only":
            log.append(
                AppliedAmendment(lens=lens, amendment=a, status="applique", why_fr="signalement, sans changement")
            )
            continue
        new = cur.model_copy(deep=True)
        before = after = None
        if a.kind in ("tighten_limit", "cap_group"):
            lim = _limit(new, a.target)
            if lim is None:
                reject(lens, a, f"limite inconnue : {a.target}")
                continue
            if a.value is None or lim.max is None or not a.value < lim.max - 1e-12:
                reject(lens, a, "ne resserre pas la limite (le max doit baisser)")
                continue
            if a.kind == "cap_group" and lim.kind not in ("group_weight", "exposure", "asset_weight"):
                reject(lens, a, "cap_group vise une limite de poids ou d'exposition")
                continue
            orig = _limit(original, a.target)
            floor = (
                (orig.max * floor_ratio) if orig is not None and orig.max is not None and lim.kind == "risk" else 0.0
            )
            if a.value < floor or a.value < 0 or (lim.min is not None and a.value < lim.min):
                reject(lens, a, f"sous le plancher anti-cliquet ({floor:.4f}) ou sous le min")
                continue
            before, after = lim.max, a.value
            lim.max = a.value
        elif a.kind == "require_min_group":
            lim = _limit(new, a.target)
            if a.target.startswith("strat."):
                reject(lens, a, "un plancher de style (strat.*) ne peut que baisser : le relever ajouterait du risque")
                continue
            if lim is None or lim.kind != "group_weight":
                reject(lens, a, f"limite de groupe inconnue : {a.target}")
                continue
            cur_min = lim.min or 0.0
            if a.value is None or not a.value > cur_min + 1e-12 or (lim.max is not None and a.value > lim.max):
                reject(lens, a, "doit relever le min sans dépasser le max")
                continue
            before, after = lim.min, a.value
            lim.min = a.value
        elif a.kind == "exclude_asset":
            if a.target not in new.universe:
                reject(lens, a, f"actif hors univers : {a.target}")
                continue
            if a.target in new.excluded:
                reject(lens, a, "déjà exclu")
                continue
            new.excluded[a.target] = a.evidence_fact_ids[0]
            new.limits.append(
                Limit(
                    rule_id=f"amend.exclude.{a.target}",
                    kind="asset_weight",
                    selector=Selector(assets=[a.target]),
                    max=0.0,
                    blocking=True,
                    derived_from=f"lentille {lens}",
                    source=f"fact:{a.evidence_fact_ids[0]}",
                    description_fr=a.reason_fr[:200],
                )
            )
            before, after = "admis", "exclu"
        elif a.kind == "switch_risk_measure":
            tgt = a.target.upper()
            if tgt not in _MEASURE_ORDER or _MEASURE_ORDER[tgt] <= _MEASURE_ORDER.get(new.risk_measure, 0):
                reject(lens, a, "seul un passage vers une mesure plus prudente est admis")
                continue
            before, after = new.risk_measure, tgt
            new.risk_measure = tgt
        try:
            new = PolicySpec.model_validate(new.model_dump())
            if any(lim.rule_id.startswith("strat.") for lim in new.limits):
                # la prudence l'emporte sur le style : un plafond abaissé abaisse les planchers strat.* liés
                new, _ = clamp_strategy_floors(new)
        except Exception as exc:  # contrat invalide
            reject(lens, a, f"mandat invalide après amendement : {exc}"[:300])
            continue
        why_ok = "appliqué"
        if feasible is not None and not feasible(new):
            relaxed = _relax_strategy_floors(new, feasible)
            if relaxed is None:
                reject(lens, a, "rendrait le mandat infaisable")
                continue
            # la prudence l'emporte sur le style : les planchers strat.* cèdent avant le resserrement
            new, why_ok = relaxed, "appliqué ; planchers du style retirés pour rester faisable"
        cur = new
        log.append(
            AppliedAmendment(lens=lens, amendment=a, status="applique", why_fr=why_ok, before=before, after=after)
        )
    return cur, log


def _relax_strategy_floors(policy: PolicySpec, feasible: Callable[[PolicySpec], bool]) -> PolicySpec | None:
    """Retire les planchers strat.* (titres, puis part actions visée) jusqu'à ce que le mandat soit faisable."""
    for drop in (("strat.floor.",), ("strat.floor.", "strat.growth_floor")):
        lims = [lim for lim in policy.limits if not lim.rule_id.startswith(drop)]
        if len(lims) == len(policy.limits):
            continue
        data = policy.model_dump()
        data["limits"] = [lim.model_dump() for lim in lims]
        cand = PolicySpec.model_validate(data)
        if feasible(cand):
            return cand
    return None
