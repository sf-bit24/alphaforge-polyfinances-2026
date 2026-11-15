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
5. Garde ESG : un amendement autre que ``flag_only`` qui cite une preuve ESG (``okf.esg.*``) n'est appliqué que si
   l'investisseur a des exclusions ou une préférence ESG (``esg_preference``). Un ``exclude_asset`` qui cite une
   preuve ESG doit en citer une du titre visé.
6. Garde des dépôts : même règle que pour les actualités pour un dépôt réglementaire (``okf.filing.*``). Son
   existence est un fait, mais son contenu n'est pas lu : il peut être signalé, jamais justifier un changement du
   mandat.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from alphaforge.finance.contracts.policy import Limit, PolicySpec, Selector
from alphaforge.finance.strategy.okf_facts import ESG_FACT_PREFIX, FILING_FACT_PREFIX, NEWS_FACT_PREFIX
from alphaforge.finance.strategy.rules import clamp_strategy_floors

from .facts import fmt
from .schemas import LENS_FR, PRIORITY, Amendment, AppliedAmendment, LensReport

FLOOR_RATIO = 0.6
NEWS_REJECT_FR = "une actualité ne justifie jamais un changement du mandat (rumeur ≠ fait)"
ESG_NO_PREFERENCE_FR = "une preuve ESG ne change le mandat que si l'investisseur a des exclusions ou une préférence ESG"
ESG_OTHER_ASSET_FR = "la preuve ESG citée concerne un autre titre que celui à exclure"
FILING_REJECT_FR = "un dépôt réglementaire est signalé, jamais une preuve de changement du mandat (contenu non lu)"
_MEASURE_ORDER = {"VARIANCE": 0, "CVAR": 1, "CDAR": 2}  # CDaR = plus prudente (drawdown)


def _missing_evidence_fr(n_missing: int) -> str:
    """Rejet pour preuve absente, sans l'identifiant : il reste dans ``amendment.evidence_fact_ids`` (audit)."""
    if n_missing == 1:
        return "preuve inconnue : le fait cité est introuvable dans la décision"
    return f"preuve inconnue : {n_missing} faits cités sont introuvables dans la décision"


def _limit(policy: PolicySpec, rule_id: str) -> Limit | None:
    return next((lim for lim in policy.limits if lim.rule_id == rule_id), None)


class _RejectedError(Exception):
    """Amendement refusé ; ``why`` est la raison montrée dans le journal de la fusion."""

    def __init__(self, why: str):
        super().__init__(why)
        self.why = why


@dataclass(frozen=True)
class _Guards:
    known_fact_ids: set[str]
    original: PolicySpec
    feasible: Callable[[PolicySpec], bool] | None
    floor_ratio: float
    esg_preference: bool


def apply_amendments(  # noqa: PLR0913 - les quatre entrées de la fusion, puis ses gardes passées par mot-clé
    policy: PolicySpec,
    reports: list[LensReport],
    emphasis: dict[str, float],
    known_fact_ids: set[str],
    *,
    original: PolicySpec | None = None,
    feasible: Callable[[PolicySpec], bool] | None = None,
    floor_ratio: float = FLOOR_RATIO,
    esg_preference: bool = False,
) -> tuple[PolicySpec, list[AppliedAmendment]]:
    guards = _Guards(known_fact_ids, original or policy, feasible, floor_ratio, esg_preference)
    items = [(r.lens, a) for r in reports for a in r.amendments]
    items.sort(key=lambda la: (PRIORITY[la[0]], -emphasis.get(la[0], 0.0)))
    cur = policy.model_copy(deep=True)
    log: list[AppliedAmendment] = []
    for lens, a in items:
        try:
            cur, entry = _apply_one(cur, lens, a, guards)
        except _RejectedError as rejected:
            entry = AppliedAmendment(lens=lens, amendment=a, status="rejete", why_fr=rejected.why)
        log.append(entry)
    return cur, log


def _apply_one(cur: PolicySpec, lens: str, a: Amendment, guards: _Guards) -> tuple[PolicySpec, AppliedAmendment]:
    """Mandat après l'amendement ``a`` et son entrée du journal ; lève ``_RejectedError`` s'il est refusé."""
    _check_evidence(a, guards)
    if a.kind == "flag_only":
        return cur, AppliedAmendment(lens=lens, amendment=a, status="applique", why_fr="signalement, sans changement")
    new = cur.model_copy(deep=True)
    before, after = _change(new, lens, a, guards)
    new = _revalidated(new)
    new, why_ok = _kept_feasible(new, guards.feasible)
    return new, AppliedAmendment(lens=lens, amendment=a, status="applique", why_fr=why_ok, before=before, after=after)


def _check_evidence(a: Amendment, guards: _Guards) -> None:
    """Gardes 4 à 6 (actualités, ESG, dépôts), puis preuves inconnues."""
    changes_policy = a.kind != "flag_only"
    if changes_policy and any(f.startswith(NEWS_FACT_PREFIX) for f in a.evidence_fact_ids):
        raise _RejectedError(NEWS_REJECT_FR)
    esg_ids = [f for f in a.evidence_fact_ids if f.startswith(ESG_FACT_PREFIX)]
    if changes_policy and esg_ids and not guards.esg_preference:
        raise _RejectedError(ESG_NO_PREFERENCE_FR)
    if (
        a.kind == "exclude_asset"
        and esg_ids
        and not any(f.startswith(f"{ESG_FACT_PREFIX}{a.target}.") for f in esg_ids)
    ):
        raise _RejectedError(ESG_OTHER_ASSET_FR)
    if changes_policy and any(f.startswith(FILING_FACT_PREFIX) for f in a.evidence_fact_ids):
        raise _RejectedError(FILING_REJECT_FR)
    missing = [f for f in a.evidence_fact_ids if f not in guards.known_fact_ids]
    if missing:
        raise _RejectedError(_missing_evidence_fr(len(missing)))


def _change(new: PolicySpec, lens: str, a: Amendment, guards: _Guards) -> tuple:
    """Applique l'amendement à ``new`` (copie du mandat courant) ; renvoie la borne (avant, après)."""
    if a.kind in ("tighten_limit", "cap_group"):
        return _lower_max(new, a, guards)
    if a.kind == "require_min_group":
        return _raise_group_min(new, a)
    if a.kind == "exclude_asset":
        return _exclude_asset(new, lens, a)
    if a.kind == "switch_risk_measure":
        return _switch_risk_measure(new, a)
    return None, None


def _lower_max(new: PolicySpec, a: Amendment, guards: _Guards) -> tuple:
    lim = _limit(new, a.target)
    if lim is None:
        raise _RejectedError("limite inconnue : la limite visée n'est pas dans le mandat")
    if a.value is None or lim.max is None or not a.value < lim.max - 1e-12:
        raise _RejectedError("ne resserre pas la limite (le max doit baisser)")
    if a.kind == "cap_group" and lim.kind not in ("group_weight", "exposure", "asset_weight"):
        raise _RejectedError("un plafond de groupe ne vise qu'une limite de poids ou d'exposition")
    floor = _ratchet_floor(_limit(guards.original, a.target), lim, guards.floor_ratio)
    if a.value < floor or a.value < 0 or (lim.min is not None and a.value < lim.min):
        raise _RejectedError(f"sous le plancher anti-cliquet ({fmt(floor, '%')}) ou sous le minimum")
    before, after = lim.max, a.value
    lim.max = a.value
    return before, after


def _ratchet_floor(orig: Limit | None, lim: Limit, floor_ratio: float) -> float:
    """Garde anti-cliquet : une limite de risque ne descend pas sous ``floor_ratio`` fois son max d'origine."""
    return (orig.max * floor_ratio) if orig is not None and orig.max is not None and lim.kind == "risk" else 0.0


def _raise_group_min(new: PolicySpec, a: Amendment) -> tuple:
    lim = _limit(new, a.target)
    if a.target.startswith("strat."):
        raise _RejectedError("un plancher de style (strat.*) ne peut que baisser : le relever ajouterait du risque")
    if lim is None or lim.kind != "group_weight":
        raise _RejectedError("limite de groupe inconnue : la limite visée n'est pas une limite de groupe du mandat")
    cur_min = lim.min or 0.0
    if a.value is None or not a.value > cur_min + 1e-12 or (lim.max is not None and a.value > lim.max):
        raise _RejectedError("doit relever le min sans dépasser le max")
    before, after = lim.min, a.value
    lim.min = a.value
    return before, after


def _exclude_asset(new: PolicySpec, lens: str, a: Amendment) -> tuple:
    if a.target not in new.universe:
        raise _RejectedError(f"actif hors univers : {a.target}")
    if a.target in new.excluded:
        raise _RejectedError("déjà exclu")
    new.excluded[a.target] = a.evidence_fact_ids[0]
    new.limits.append(
        Limit(
            rule_id=f"amend.exclude.{a.target}",
            kind="asset_weight",
            selector=Selector(assets=[a.target]),
            max=0.0,
            blocking=True,
            derived_from=f"lentille {LENS_FR.get(lens, lens)}",
            source=f"fact:{a.evidence_fact_ids[0]}",
            description_fr=a.reason_fr[:200],
        )
    )
    return "admis", "exclu"


def _switch_risk_measure(new: PolicySpec, a: Amendment) -> tuple:
    tgt = a.target.upper()
    if tgt not in _MEASURE_ORDER or _MEASURE_ORDER[tgt] <= _MEASURE_ORDER.get(new.risk_measure, 0):
        raise _RejectedError("seul un passage vers une mesure plus prudente est admis")
    before, after = new.risk_measure, tgt
    new.risk_measure = tgt
    return before, after


def _revalidated(new: PolicySpec) -> PolicySpec:
    """Mandat revalidé par le contrat ; les planchers strat.* suivent un plafond abaissé."""
    try:
        new = PolicySpec.model_validate(new.model_dump())
        if any(lim.rule_id.startswith("strat.") for lim in new.limits):
            # la prudence l'emporte sur le style : un plafond abaissé abaisse les planchers strat.* liés
            new, _ = clamp_strategy_floors(new)
    except Exception as exc:  # contrat invalide
        raise _RejectedError(f"mandat invalide après amendement : {exc}"[:300]) from exc
    return new


def _kept_feasible(new: PolicySpec, feasible: Callable[[PolicySpec], bool] | None) -> tuple[PolicySpec, str]:
    """Garde de faisabilité : les planchers strat.* cèdent avant le resserrement, sinon l'amendement est refusé."""
    if feasible is None or feasible(new):
        return new, "appliqué"
    relaxed = _relax_strategy_floors(new, feasible)
    if relaxed is None:
        raise _RejectedError("rendrait le mandat infaisable")
    # la prudence l'emporte sur le style : les planchers strat.* cèdent avant le resserrement
    return relaxed, "appliqué ; planchers du style retirés pour rester faisable"


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
