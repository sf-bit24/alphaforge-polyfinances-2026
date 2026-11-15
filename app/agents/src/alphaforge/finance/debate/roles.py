"""Rôles LLM du débat (A3 avocat, 4 lentilles) et leur repli déterministe.

- Mode ``llm`` : un ``strands.Agent`` par rôle, sortie structurée Pydantic, modèle Bedrock
  (Sonnet 5.5 pour A3, Haiku 5.5 pour les lentilles), enregistré et rejouable via ``llm.strands_replay``.
- Mode ``rules`` : mêmes contrats, produits par des règles fixes. Sert aux tests, à la démo hors
  ligne et de repli si Bedrock échoue. Le reste du pipeline (fusion, Judge) est identique.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .facts import FactBook
from .schemas import AdvocacyBrief, Amendment, LensReport, Point

if TYPE_CHECKING:
    from alphaforge.finance.contracts.policy import Limit, PolicySpec
    from alphaforge.finance.contracts.profile import InvestorProfile

SONNET = os.environ.get("ALPHAFORGE_MODEL_MAIN", "us.anthropic.claude-sonnet-5-5")
HAIKU = os.environ.get("ALPHAFORGE_MODEL_LENS", "us.anthropic.claude-haiku-5-5")
REGION = os.environ.get("AWS_REGION", "us-east-1")

COMMON = (
    "Simulation éducative AlphaForge AI : aucune transaction, aucun conseil personnalisé. "
    "Tu ne calcules ni ne devines AUCUN chiffre : tu ne cites que des fact_id fournis ou renvoyés par tes outils. "
    "Tu ne prévois aucun rendement futur. Réponds en français, brièvement."
)

LENS_PROMPTS = {
    "timeline": "Tu es la lentille HORIZON. Question : l'argent sera-t-il là quand il le faut ? "
    "Compare l'horizon le plus court des objectifs au pire rendement historique et au temps de récupération.",
    "risk": "Tu es la lentille RISQUE (tolérance ET capacité d'absorption). Question : quelle perte est possible, "
    "et est-elle supportable en dollars ? Compare les stress et la CVaR à la perte déclarée.",
    "diversity": "Tu es la lentille DIVERSITÉ ET PRÉFÉRENCES (dont l'ESG). Question : le portefeuille dépend-il "
    "d'un seul moteur, et respecte-t-il les préférences ? Examine groupes corrélés, look-through, preuves ESG.",
    "constraints": "Tu es la lentille CONTRAINTES. Question : les limites du mandat, les contraintes légales et "
    "les règles de l'investisseur sont-elles respectées, et lesquelles sont saturées ?",
}

AMEND_RULES = (
    "Tu peux proposer au plus 3 amendements, UNIQUEMENT de ces types : tighten_limit (target = rule_id d'une limite "
    "existante, value = nouveau max plus bas), cap_group (idem pour un groupe ou une exposition), exclude_asset "
    "(target = ticker, avec une preuve), require_min_group (target = rule_id d'un groupe, value = nouveau min), "
    "switch_risk_measure (target = CDAR), flag_only. Tu ne peux que RESSERRER, jamais relâcher. "
    "Chaque amendement cite au moins un fact_id existant. Tu ne proposes jamais de poids."
)


def model(model_id: str, node_id: str, versions: dict | None = None):
    """BedrockModel enregistrable/rejouable si la couche de rejeu est disponible."""
    kw = {
        "model_id": model_id,
        "region_name": REGION,
        "additional_request_fields": {"output_config": {"effort": "medium"}},
    }
    try:
        from alphaforge.finance.llm import FileStore  # type: ignore
        from alphaforge.finance.llm.strands_replay import ReplayModel  # alphaforge.finance.llm (équipe finance)

        store = FileStore(os.environ.get("ALPHAFORGE_LLM_STORE", "llm_records"))
        return ReplayModel(node_id=node_id, store=store, mode=None, versions=versions or {}, **kw)
    except ImportError:
        from strands.models import BedrockModel

        return BedrockModel(**kw)


STRAT_NOTE = (
    "limite de l'étape 0 (style), non bloquante : choix de composition dans les budgets de perte du niveau (elle peut "
    "augmenter le risque dans la bande, jamais au-delà des budgets) ; on peut baisser un plafond strat.*, jamais "
    "relever un plancher strat.*"
)


def _limits_view(policy) -> list[dict]:
    out = []
    for lim in policy.limits:
        row = {
            "rule_id": lim.rule_id,
            "kind": lim.kind,
            "min": lim.min,
            "max": lim.max,
            "selector": lim.selector.model_dump(exclude_defaults=True),
        }
        if lim.rule_id.startswith("strat."):  # seulement si l'étape 0 est active (rejeux existants inchangés)
            row.update(blocking=lim.blocking, derived_from=lim.derived_from, note=STRAT_NOTE)
        out.append(row)
    return out


def _profile_view(profile) -> dict:
    return {
        "knowledge_level": profile.knowledge_level,
        "goals": [g.model_dump(include={"label", "priority", "horizon_years"}) for g in profile.goals],
        "preferences": profile.preferences.model_dump(exclude_defaults=True),
        "biases": [b.kind_label for b in profile.biases],
        "status": profile.status,
        "max_acceptable_loss_pct": profile.max_acceptable_loss_pct,
    }


# ------------------------------------------------------------------------- mode LLM
def _candidate_weights(ctx) -> dict[str, float]:
    return {a: round(w, 4) for a, w in ctx.weights.items() if w > 1e-4}


def _structured(agent, payload: dict, output_model, round_no: int):
    """Sortie structurée d'un agent Strands ; le tour entre dans la clé de rejeu (``invocation_state``)."""
    res = agent(
        json.dumps(payload, ensure_ascii=False),
        structured_output_model=output_model,
        invocation_state={"debate_round": round_no},
    )
    return res.structured_output


def llm_lens(  # noqa: PLR0913 - signature commune avec rules_lens : pipeline.py les appelle par position
    lens: str,
    ctx,
    evidence_ids: list[str],
    round_no: int,
    brief: AdvocacyBrief | None,
    emphasis: float,
    versions: dict | None = None,
) -> LensReport:
    from strands import Agent

    from .tools import strands_tools

    payload = {
        "tour": round_no,
        "emphase_de_ta_lentille": round(emphasis, 3),
        "profil": _profile_view(ctx.profile),
        "candidat_poids": _candidate_weights(ctx),
        "preuves": ctx.book.show(evidence_ids),
        "limites_du_mandat": _limits_view(ctx.policy),
    }
    if brief is not None:  # tour 2 seulement : la lentille voit le plaidoyer après avoir jugé seule
        payload["plaidoyer_de_A3"] = brief.model_dump()
    agent = Agent(
        model=model(HAIKU, f"lens_{lens}", versions),
        name=f"lens_{lens}",
        system_prompt=f"{COMMON}\n{LENS_PROMPTS[lens]}\n{AMEND_RULES}",
        tools=strands_tools(lens, ctx),
        callback_handler=None,
    )
    with ctx.book.step(f"lens.{lens}", tool="llm", inputs={"round": round_no}, model_id=HAIKU):
        rep = _structured(agent, payload, LensReport, round_no)
    return rep.model_copy(update={"lens": lens})


def llm_advocate(
    ctx, evidence_ids: list[str], round_no: int, objections: list[LensReport] | None, versions: dict | None = None
) -> AdvocacyBrief:
    from strands import Agent

    payload = {
        "tour": round_no,
        "profil": _profile_view(ctx.profile),
        "candidat_poids": _candidate_weights(ctx),
        "preuves": ctx.book.show(evidence_ids),
    }
    if objections:
        payload["objections"] = [r.model_dump(include={"lens", "objections"}) for r in objections]
    agent = Agent(
        model=model(SONNET, "a3_advocate", versions),
        name="a3_advocate",
        system_prompt=f"{COMMON}\nTu es A3, l'AVOCAT du portefeuille candidat calculé par l'optimiseur. "
        "Défends-le en citant les preuves ; au tour 2, réponds aux objections. "
        "Tu ne peux pas changer les poids ni les limites.",
        callback_handler=None,
    )
    with ctx.book.step("a3.advocate", tool="llm", inputs={"round": round_no}, model_id=SONNET):
        return _structured(agent, payload, AdvocacyBrief, round_no)


# ------------------------------------------------------------------------- mode règles
def _val(book: FactBook, fid: str):
    f = book.facts.get(fid)
    return None if f is None else f.value


@dataclass
class _Findings:
    """Ce qu'une lentille retient : soutiens, objections et amendements proposés, dans l'ordre des règles."""

    support: list[Point] = field(default_factory=list)
    objections: list[Point] = field(default_factory=list)
    amendments: list[Amendment] = field(default_factory=list)


@dataclass(frozen=True)
class _LensInputs:
    """Ce que lisent les règles d'une lentille : le contexte du candidat, ses preuves et les limites du mandat."""

    book: FactBook
    label: str
    profile: InvestorProfile
    policy: PolicySpec
    evidence: dict[str, str]  # suffixe du fact_id (sans le libellé du candidat) -> fact_id
    limits: dict[str, Limit]  # rule_id -> limite du mandat


def rules_lens(  # noqa: PLR0913 - signature commune avec llm_lens : pipeline.py les appelle par position
    lens: str, ctx, evidence_ids: list[str], round_no: int, brief=None, emphasis: float = 0.25, versions=None
) -> LensReport:
    """Règles fixes, documentées, qui produisent le même contrat qu'une lentille LLM."""
    inputs = _LensInputs(
        book=ctx.book,
        label=ctx.label,
        profile=ctx.profile,
        policy=ctx.policy,
        evidence={fid.split(".", 1)[-1]: fid for fid in evidence_ids},
        limits={lim.rule_id: lim for lim in ctx.policy.limits},
    )
    found = _Findings()
    rules = _LENS_RULES.get(lens)
    if rules is not None:
        rules(inputs, found)
    return LensReport(lens=lens, support=found.support, objections=found.objections, amendments=found.amendments[:3])


def _risk_rules(inp: _LensInputs, found: _Findings) -> None:
    _crisis_vs_declared_loss(inp, found)
    _loss_aversion_measure(inp, found)


def _crisis_vs_declared_loss(inp: _LensInputs, found: _Findings) -> None:
    """Pire perte de crise en dollars comparée à la perte que l'investisseur déclare pouvoir absorber."""
    b, ev, lim = inp.book, inp.evidence, inp.limits
    loss = inp.profile.max_acceptable_loss_cad
    worst = max(
        (v for k, fid in ev.items() if k.startswith("stress_cad.") and (v := _val(b, fid)) is not None),
        default=None,
    )
    if loss is None or worst is None:
        return
    wid = next(fid for k, fid in ev.items() if k.startswith("stress_cad.") and _val(b, fid) == worst)
    if worst > loss and "risk.cvar_m" in lim and lim["risk.cvar_m"].max:
        found.objections.append(
            Point(
                text_fr="Une crise historique ferait perdre plus que la perte déclarée.",
                fact_ids=[wid, ev["loss_declared"]],
            )
        )
        found.amendments.append(
            Amendment(
                kind="tighten_limit",
                target="risk.cvar_m",
                value=round(lim["risk.cvar_m"].max * max(loss / worst, 0.6), 4),
                reason_fr="ramener la perte de crise sous la perte déclarée",
                evidence_fact_ids=[wid, ev["loss_declared"]],
            )
        )
    else:
        found.support.append(
            Point(
                text_fr="La pire crise couverte reste sous la perte déclarée.",
                fact_ids=[wid, ev["loss_declared"]],
            )
        )


def _loss_aversion_measure(inp: _LensInputs, found: _Findings) -> None:
    """Aversion à la perte déclarée : mesurer le risque par les baisses (CDaR)."""
    averse = any(bi.kind_label.lower() in ("aversion_perte", "aversion à la perte") for bi in inp.profile.biases)
    if averse and inp.policy.risk_measure != "CDAR":
        found.amendments.append(
            Amendment(
                kind="switch_risk_measure",
                target="CDAR",
                reason_fr="aversion à la perte : mesurer le risque par les baisses",
                evidence_fact_ids=[inp.evidence["mdd"]],
            )
        )


def _timeline_rules(inp: _LensInputs, found: _Findings) -> None:
    """Horizon court et pire cas marqué sur cet horizon : moins d'actions ; sinon, l'horizon soutient le candidat."""
    b, ev, lim = inp.book, inp.evidence, inp.limits
    h = _val(b, ev["horizon"])
    worst = _val(b, ev.get("horizon_worst", "")) if "horizon_worst" in ev else None
    if not (h is not None and h < 5 and worst is not None and worst < -0.10 and "alloc.growth" in lim):
        found.support.append(
            Point(
                text_fr="L'horizon laisse le temps de traverser les baisses observées.",
                fact_ids=[ev["horizon"], ev["recovery"]],
            )
        )
        return
    g = lim["alloc.growth"]
    if g.max is not None and g.min is not None and g.max - 0.10 >= g.min:
        found.objections.append(
            Point(
                text_fr="Horizon court et pire cas historique marqué sur cet horizon.",
                fact_ids=[ev["horizon"], ev["horizon_worst"]],
            )
        )
        found.amendments.append(
            Amendment(
                kind="cap_group",
                target="alloc.growth",
                value=round(g.max - 0.10, 4),
                reason_fr="moins d'actions quand l'argent sert bientôt",
                evidence_fact_ids=[ev["horizon"], ev["horizon_worst"]],
            )
        )


def _diversity_rules(inp: _LensInputs, found: _Findings) -> None:
    _correlated_clusters(inp, found)
    _tech_near_cap(inp, found)
    _value_filter_exclusions(inp, found)


def _correlated_clusters(inp: _LensInputs, found: _Findings) -> None:
    for k, fid in inp.evidence.items():
        if k.startswith("cluster") and (v := _val(inp.book, fid)) is not None and v > 0.5:
            found.objections.append(Point(text_fr="Plus de la moitié du portefeuille bouge d'un bloc.", fact_ids=[fid]))


def _tech_near_cap(inp: _LensInputs, found: _Findings) -> None:
    """Exposition tech consolidée à plus de 90 % de son plafond, sans préférence déclarée pour l'IA."""
    tech, lim = inp.evidence.get("lt.tech"), inp.limits
    if (
        tech
        and "exp.tech" in lim
        and (v := _val(inp.book, tech)) is not None
        and lim["exp.tech"].max
        and v > 0.9 * lim["exp.tech"].max
        and "IA" not in " ".join(inp.profile.preferences.tilts)
    ):
        found.amendments.append(
            Amendment(
                kind="cap_group",
                target="exp.tech",
                value=round(0.9 * lim["exp.tech"].max, 4),
                reason_fr="exposition tech consolidée proche du plafond",
                evidence_fact_ids=[tech],
            )
        )


def _value_filter_exclusions(inp: _LensInputs, found: _Findings) -> None:
    """Titres que les filtres de valeurs de l'investisseur excluent : le filtre devient un Fact cité."""
    b, pol = inp.book, inp.policy
    for vf in inp.profile.preferences.value_filters:
        for t, st in vf.per_ticker.items():
            if st == "exclu" and t in pol.universe and t not in pol.excluded:
                fid = b.add(
                    f"{inp.label}.vf.{t}",
                    f"Filtre de valeurs de l'investisseur : {vf.rule}",
                    "exclu",
                    "statut",
                    dataset="profile.preferences.value_filters",
                    trace_id=b.trace[-1].trace_id,
                )
                found.amendments.append(
                    Amendment(
                        kind="exclude_asset", target=t, reason_fr=f"filtre « {vf.rule} »", evidence_fact_ids=[fid]
                    )
                )


def _constraints_rules(inp: _LensInputs, found: _Findings) -> None:
    nb = inp.evidence.get("n_blocking")
    if nb and (_val(inp.book, nb) or 0) > 0:
        found.objections.append(Point(text_fr="Des limites bloquantes du mandat sont dépassées.", fact_ids=[nb]))
    elif nb:
        found.support.append(Point(text_fr="Aucune limite bloquante n'est dépassée.", fact_ids=[nb]))


_LENS_RULES = {
    "risk": _risk_rules,
    "timeline": _timeline_rules,
    "diversity": _diversity_rules,
    "constraints": _constraints_rules,
}


def rules_advocate(ctx, evidence_ids, round_no, objections=None, versions=None) -> AdvocacyBrief:
    risk = [f for f in evidence_ids if f.endswith((".cvar_m", ".mdd"))]
    return AdvocacyBrief(
        thesis_fr="Le candidat minimise le risque sous toutes les limites dérivées du profil.",
        arguments=[Point(text_fr="Mesures de risque du candidat.", fact_ids=risk[:2])],
        rebuttals=[Point(text_fr="Les amendements retenus ont été appliqués puis réoptimisés.")]
        if round_no == 2
        else [],
    )
