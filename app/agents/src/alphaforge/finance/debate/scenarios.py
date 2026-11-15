"""Explicabilité des scénarios probabilistes : l'outil ``scenario_risk`` branché sur l'étape d'explication.

Simulation seulement, jamais un conseil. « Le code calcule, le modèle explique, chaque nombre cite sa source » :
- l'outil (``alphaforge.scenarios.tool``) lit la table précalculée et produit des ``Fact`` et un ``TraceEvent`` ;
  ``run_scenario`` les **absorbe dans le FactBook** de la décision (donc dans ``Decision.facts`` et
  ``Decision.trace``), avec deux Facts de requête (horizon lu, palier de perte) : une phrase qui cite un ``fact_id``
  de scénario est validée par ``Decision._integrity`` et par ``observability.verify_decision`` ;
- mode ``rules`` : un appel déterministe sur le portefeuille final et des gabarits dont chaque nombre est la valeur
  formatée d'un Fact cité (fidèles par construction) ;
- mode ``llm`` : l'agent ``explainer_scenarios`` reçoit l'outil Strands ``scenario_risk`` (il choisit ses appels)
  et écrit au plus quatre phrases ; une phrase est gardée seulement si elle cite des ``fact_id`` de scénario
  présents dans le FactBook et si chacun de ses nombres vient de ces Facts (``verify_numbers``). Sans phrase valide,
  ou en cas d'erreur (rejeu absent, Bedrock), repli sur les gabarits ;
- **inactif sans erreur** si les scénarios sont désactivés (``ALPHAFORGE_SCENARIOS=0``), si la table est absente
  ou illisible, ou si le magasin refuse la lecture (AccessDenied / 403) : aucun appel au modèle, une seule limite
  « scénarios indisponibles » (HYPOTHESE, sans chiffre), une étape ``refus`` dans la trace (raison détaillée dans
  ``TraceEvent.message``). Le pipeline continue.

Activation dans le pipeline (``attach_scenarios``, appelé par ``build_portfolio(..., scenarios=None)``) : par
défaut, seulement si le mandat final déclare une limite PROB_LOSS ; sans elle, l'explication, les Facts et la trace
restent ceux d'avant les scénarios. ``scenarios=True`` force l'étape, ``scenarios=False`` l'interdit. Le rapport de
l'étape (phrases rejetées, repli sur les gabarits, erreur) est écrit dans le ``TraceEvent.message`` de l'étape.

Paramètres d'appel : poids du portefeuille final rattachés aux blocs (``portfolio/scenario_risk.map_to_blocks``,
prudent : un actif sans bloc empêche l'appel, dit dans les limites) ; si le mandat porte une limite PROB_LOSS, ses
L et H ; sinon H = horizon le plus court des objectifs (années entières, au moins 1) et L = perte maximale déclarée
par l'investisseur (``max_acceptable_loss_pct``) si elle existe. Aucun seuil n'est inventé ici.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from alphaforge.finance.contracts.decision import Explanation, Fact, Statement, TraceEvent
from alphaforge.finance.contracts.policy import PolicySpec
from alphaforge.finance.portfolio.scenario_risk import (
    UNAVAILABLE_FR,
    SafeTableLoader,
    describe_error,
    map_to_blocks,
    scenarios_enabled,
)

from .facts import FactBook, fmt

AGENT = "explainer.scenarios"
NODE_ID = "explainer_scenarios"
SECTIONS = ("data_used", "why", "limits", "what_would_change")
MAX_NOTES = 4
DATASET = "scenario_risk (requête)"

SYSTEM_PROMPT = (
    "Simulation éducative AlphaForge AI : aucune transaction, aucun conseil personnalisé. Tu es l'agent "
    "d'EXPLICABILITÉ des scénarios probabilistes. Appelle l'outil scenario_risk avec les poids par bloc et l'horizon "
    "fournis (tu peux comparer un autre horizon de la grille), puis écris au plus 4 phrases en français simple. "
    "Chaque phrase cite les fact_id renvoyés par l'outil (champs fact_id et request_fact_ids), n'écrit AUCUN nombre "
    "absent de ces Facts, montre l'intervalle, nomme le modèle et rappelle que c'est un modèle, pas une prévision. "
    "Si l'outil refuse, explique le refus sans chiffre."
)

Sections = dict[str, list[Statement]]


class ScenarioNote(BaseModel):
    section: Literal["data_used", "why", "limits", "what_would_change"]
    text_fr: str
    fact_ids: list[str] = Field(default_factory=list)
    label: Literal["FAIT", "HYPOTHESE"] = "HYPOTHESE"


class ScenarioNotes(BaseModel):
    notes: list[ScenarioNote] = Field(default_factory=list)


@dataclass(frozen=True)
class ScenarioContext:
    """Ce que l'étape lit du pipeline : portefeuille final, mandat, profil et mode, plus les doublures de test."""

    weights: dict[str, float]
    policy: PolicySpec
    profile: Any = None
    mode: str = "rules"
    tool: Any = None  # ScenarioRiskTool injecté (tests, rejeu) ; None = magasin du projet
    model_factory: Callable | None = None  # fabrique du modèle Strands (tests) ; None = roles.model


def empty_sections() -> Sections:
    return {k: [] for k in SECTIONS}


def _limit(text: str) -> Statement:
    return Statement(text_fr=text, fact_ids=[], label="HYPOTHESE")


def _why_unavailable(reason: str) -> str:
    """Catégorie sans chiffre (la raison détaillée reste dans la trace)."""
    if "désactivés" in reason:
        return "désactivés dans cet environnement"
    if "AccessDenied" in reason or "refusée" in reason:
        return "lecture du magasin refusée (AccessDenied)"
    if "absent" in reason or "introuvable" in reason:
        return "table absente ou non publiée"
    return "table illisible ou non vérifiée"


# --------------------------------------------------------------------------- activation dans le pipeline


def has_prob_loss(policy: PolicySpec) -> bool:
    return any(limit.kind == "risk" and limit.selector.measure == "PROB_LOSS" for limit in policy.limits)


def scenarios_requested(policy: PolicySpec, *, enabled: bool | None) -> bool:
    """``None`` (défaut du pipeline) : seulement si le mandat déclare une limite PROB_LOSS ; sinon ``enabled``."""
    return has_prob_loss(policy) if enabled is None else enabled


def attach_scenarios(
    book: FactBook, explanation: Explanation, context: ScenarioContext, *, enabled: bool | None = None
) -> Explanation:
    """L'explication complétée par les scénarios ; inchangée (et rien dans le FactBook) si l'étape n'est pas
    demandée. Jamais bloquant : une erreur laisse l'explication sans scénarios et s'écrit dans la trace."""
    if not scenarios_requested(context.policy, enabled=enabled):
        return explanation
    with book.step(AGENT, inputs={"mode": context.mode}) as ev:
        try:
            sections, report = explain_scenarios(book, context)
        except Exception as exc:  # jamais bloquant : l'explication sans scénarios reste valide
            sections, report = empty_sections(), [f"scénarios abandonnés : {type(exc).__name__}"]
            ev.status = "erreur"
        if report:
            ev.message = " ; ".join(report)[:500]
    return explanation.model_copy(
        update={section: [*getattr(explanation, section), *sections[section]] for section in SECTIONS}
    )


# --------------------------------------------------------------------------- outil et absorption


def scenario_tool(run_id: str | None = None):
    """``ScenarioRiskTool`` sur le magasin du projet, ou None si les scénarios sont désactivés."""
    if not scenarios_enabled():
        return None
    from alphaforge.scenarios.tool import ScenarioRiskTool

    return ScenarioRiskTool(SafeTableLoader(run_id))


def absorb_result(book: FactBook, res: dict) -> dict[str, str]:
    """Facts et TraceEvent d'un résultat de l'outil dans le FactBook (parent = étape courante), plus les Facts de
    requête (horizon lu, palier de perte). Renvoie les fact_id de requête."""
    parent = book._stack[-1] if book._stack else None
    raw = res["trace_event"]
    ev = TraceEvent.model_validate({**raw, "parent_id": raw.get("parent_id") or parent})
    book.absorb([Fact.model_validate(f) for f in res["facts"]], ev)
    if res["status"] != "ok":
        return {}
    tid, req = ev.trace_id, {}
    hz = res["horizon"]
    req["horizon"] = book.add(
        f"scn.req.{tid}.horizon",
        "horizon lu dans la grille de scénarios",
        hz["used"],
        "ans",
        dataset=DATASET,
        processing="horizon exact" if hz["exact"] else "horizon de la grille immédiatement inférieur",
        trace_id=tid,
    )
    if hz.get("upper") is not None:
        req["horizon_upper"] = book.add(
            f"scn.req.{tid}.horizon_upper",
            "horizon supérieur de la grille (comparaison)",
            hz["upper"],
            "ans",
            dataset=DATASET,
            trace_id=tid,
        )
    if res.get("threshold"):
        req["loss_level"] = book.add(
            f"scn.req.{tid}.loss_level",
            "palier de perte lu (arrondi vers le bas)",
            res["threshold"]["bucket_pct"],
            "%",
            dataset=DATASET,
            processing=res["threshold"]["rule"],
            trace_id=tid,
        )
    res["request_fact_ids"] = req
    return req


def run_scenario(book: FactBook, sr, agent: str = AGENT, **kwargs) -> dict:
    """Un appel tracé de l'outil ; ses Facts entrent dans la décision. Ne lève pas (un refus est un résultat)."""
    with book.step(agent, tool="scenario_risk", inputs=kwargs) as ev:
        res = sr.run(**kwargs)
        absorb_result(book, res)
        if res["status"] != "ok":
            ev.status = "refus"
            ev.message = res["error"]["message"][:300]
    return res


def strands_tool(book: FactBook, sr, agent: str = AGENT):
    """Outil Strands ``scenario_risk`` (même nom, description et schéma que l'outil du volet E) dont chaque appel
    est tracé dans le FactBook et y verse ses Facts : l'agent ne peut citer que des fact_id réellement produits."""
    from strands import tool

    from alphaforge.scenarios.tool import INPUT_SCHEMA, TOOL_DESCRIPTION, compact_for_model

    @tool(name="scenario_risk", description=TOOL_DESCRIPTION, inputSchema=INPUT_SCHEMA)
    def scenario_risk(  # noqa: PLR0913 - signature imposée par @tool (paramètres de l'outil, noms figés)
        *,
        weights: dict,
        horizon_years: int,
        loss_threshold_cad: float | None = None,
        amount_cad: float | None = None,
        family: str = "CAD77",
        model_id: str | None = None,
        basis: str = "nominal",
        include_sensitivity: bool = False,
    ) -> str:
        res = run_scenario(
            book,
            sr,
            agent,
            weights=weights,
            horizon_years=horizon_years,
            loss_threshold_cad=loss_threshold_cad,
            amount_cad=amount_cad,
            family=family,
            model_id=model_id,
            basis=basis,
            include_sensitivity=include_sensitivity,
        )
        out = compact_for_model(res)
        if res.get("request_fact_ids"):
            out["request_fact_ids"] = res["request_fact_ids"]
        return json.dumps(out, ensure_ascii=False, default=str)

    return scenario_risk


# --------------------------------------------------------------------------- paramètres


def _horizon_and_loss(policy: PolicySpec, profile) -> tuple[int, float | None]:
    """L et H de la limite PROB_LOSS du mandat ; sans elle, horizon le plus court et perte déclarée du profil."""
    prob = [lim for lim in policy.limits if lim.kind == "risk" and lim.selector.measure == "PROB_LOSS"]
    if prob:
        return prob[0].selector.horizon_years, prob[0].selector.loss_level
    from .tools import shortest_horizon

    horizon = max(int(shortest_horizon(profile)), 1) if profile is not None else 1
    return horizon, getattr(profile, "max_acceptable_loss_pct", None) or None


def call_params(weights: dict[str, float], policy: PolicySpec, profile) -> tuple[dict | None, str | None]:
    """(arguments de l'outil, None) ou (None, raison) ; voir la docstring du module."""
    family = policy.scenario_family_used
    mapping = map_to_blocks(weights, policy, family)
    if mapping.unmapped:
        return None, (
            "scénarios probabilistes non calculés pour ce portefeuille : "
            + ", ".join(sorted(mapping.unmapped))
            + " sans bloc de scénarios (rattachement prudent : un "
            "titre, un secteur ou un FNB spécialisé n'est pas l'indice d'un bloc)"
        )
    if not mapping.weights:
        return None, "scénarios probabilistes non calculés : aucun actif détenu"
    horizon, loss = _horizon_and_loss(policy, profile)
    params = {
        "weights": {b: round(x, 6) for b, x in sorted(mapping.weights.items())},
        "horizon_years": horizon,
        "family": family,
        "model_id": policy.scenario_model_id,
    }
    if loss:
        params |= {"loss_threshold_cad": float(loss), "amount_cad": 1.0}
    return params, None


# --------------------------------------------------------------------------- vérification des phrases du LLM


def check_note(book: FactBook, st: Statement) -> list[str]:
    """Problèmes d'une phrase du LLM (vide = acceptée) : fact_id de scénario connus, nombres sourcés."""
    from alphaforge.finance.observability.verify import verify_numbers

    if not st.fact_ids:
        return ["aucun fact_id cité"]
    problems = [f"fact_id inconnu : {fid}" for fid in st.fact_ids if fid not in book.facts]
    problems += [f"fact_id hors scénarios : {fid}" for fid in st.fact_ids if not fid.startswith("scn.")]
    chk = verify_numbers(st.text_fr, [book.facts[i] for i in st.fact_ids if i in book.facts])
    if not chk.ok:
        problems.append(f"nombres non sourcés : {chk.unmatched}")
    return problems


# --------------------------------------------------------------------------- gabarits (mode rules et repli)


def _v(book: FactBook, fid: str, unit: str = "%") -> str:
    return fmt(book.facts[fid].value, unit)


def _ci_sentence(book: FactBook, view: dict, what: str, req: dict) -> Statement | None:
    ids = [view["fact_id"], view["fact_id"] + ".ci_lo", view["fact_id"] + ".ci_hi"]
    if not all(i in book.facts for i in ids):
        return None
    h = req.get("horizon")
    at = f" à {_v(book, h, 'ans')}" if h else ""
    text = (
        f"{what}{at}, selon ce modèle : {_v(book, ids[0])} (intervalle de confiance du modèle : "
        f"{_v(book, ids[1])} à {_v(book, ids[2])})."
    )
    return Statement(text_fr=text, fact_ids=ids + ([h] if h else []), label="HYPOTHESE")


def _data_used_sentence(book: FactBook, res: dict) -> Statement:
    l1 = res["grid"].get("l1_fact_id")
    return Statement(
        text_fr=f"Scénarios probabilistes : table précalculée, modèle « {res['model_name']} », famille "
        f"{res['family']}, données jusqu'à {res['fitted_through']} ; mélange de la grille le plus proche à une "
        f"distance L1 de {_v(book, l1, 'ratio')}. C'est un modèle statistique de l'histoire, "
        "pas une prévision.",
        fact_ids=[l1] if l1 in book.facts else [],
        label="HYPOTHESE",
    )


def _why_sentences(book: FactBook, res: dict, metric: str | None) -> list[Statement]:
    """Probabilité de perte au palier lu, puis perte maximale et rendement médian, chacun avec son intervalle."""
    req, out = res.get("request_fact_ids") or {}, []
    if metric and metric in res["primary"] and "loss_level" in req:
        what = f"Probabilité d'une perte cumulée de plus de {_v(book, req['loss_level'])}"
        st = _ci_sentence(book, res["primary"][metric], what, req)
        if st is not None:
            st.fact_ids.append(req["loss_level"])
            out.append(st)
    for key, what in (
        ("mdd_p90", "Perte maximale en cours de route, centile défavorable"),
        ("ret_ann_p50", "Rendement annualisé médian simulé"),
    ):
        if key in res["primary"] and (st := _ci_sentence(book, res["primary"][key], what, req)) is not None:
            out.append(st)
    return out


def _model_spread_limits(book: FactBook, res: dict, metric: str | None) -> list[Statement]:
    """Une limite par autre modèle de la table qui donne la même mesure : l'écart fait partie de l'incertitude."""
    focus = metric if metric else next((k for k in ("mdd_p90", "ret_ann_p50") if k in res["primary"]), None)
    out = []
    for entry in res.get("all_models") or []:
        view = entry["metrics"].get(focus) if focus else None
        if entry["model_id"] == res["model_id"] or not view or view.get("fact_id") not in book.facts:
            continue
        out.append(
            Statement(
                text_fr=f"Un autre modèle (« {entry['name']} ») donne {_v(book, view['fact_id'])} pour la même "
                "mesure : l'écart entre modèles fait partie de l'incertitude.",
                fact_ids=[view["fact_id"]],
                label="HYPOTHESE",
            )
        )
    return out


def template_sections(book: FactBook, res: dict) -> Sections:
    out = empty_sections()
    if res["status"] != "ok":
        out["limits"].append(
            _limit(
                f"Scénarios probabilistes : l'outil a refusé ce cas ({res['error']['code']}) ; "
                "aucun chiffre n'est extrapolé hors de la grille précalculée."
            )
        )
        return out
    metric = (res.get("threshold") or {}).get("bucket_metric")
    out["data_used"].append(_data_used_sentence(book, res))
    out["why"] += _why_sentences(book, res, metric)
    out["limits"] += _model_spread_limits(book, res, metric)
    if not res.get("validated", False):
        out["limits"].append(
            _limit(
                "Ces chiffres sortent du domaine validé hors échantillon (horizon, base ou blocs "
                "non testés) : à lire comme une hypothèse."
            )
        )
    out["limits"].append(
        _limit(
            "Les modèles de scénarios sous-estiment les pertes des obligations quand les taux "
            "montent (validation hors échantillon) ; ils ne couvrent ni frais ni impôts."
        )
    )
    out["what_would_change"].append(
        _limit(
            "Un autre horizon, un autre seuil de perte ou un autre mélange changerait "
            "ces probabilités ; l'outil n'extrapole jamais hors de sa grille."
        )
    )
    return out


# --------------------------------------------------------------------------- étape d'explication


def _llm_sections(book: FactBook, sr, params: dict, model_factory=None) -> tuple[Sections, list]:
    from strands import Agent

    from .roles import SONNET, model

    agent = Agent(
        model=(model_factory or model)(SONNET, NODE_ID),
        name=NODE_ID,
        system_prompt=SYSTEM_PROMPT,
        tools=[strands_tool(book, sr)],
        callback_handler=None,
    )
    with book.step(AGENT, tool="llm", inputs={"params": params}, model_id=SONNET):
        res = agent(json.dumps({"appel_suggere": params}, ensure_ascii=False), structured_output_model=ScenarioNotes)
    notes: ScenarioNotes = res.structured_output
    out, report = empty_sections(), []
    for i, note in enumerate(notes.notes[:MAX_NOTES]):
        st = Statement(text_fr=note.text_fr, fact_ids=note.fact_ids, label=note.label)
        problems = check_note(book, st)
        if problems:
            report.append(f"scénarios[{i}] phrase rejetée : {problems}")
            continue
        out[note.section].append(st)
    return out, report


def _llm_attempt(book: FactBook, sr, params: dict, model_factory=None) -> tuple[Sections | None, list[str]]:
    """Sections écrites par l'agent, ou None (aucune phrase valide, erreur) : repli sur les gabarits."""
    try:
        sections, report = _llm_sections(book, sr, params, model_factory)
    except Exception as exc:  # rejeu absent, Bedrock, sortie invalide : repli déterministe
        return None, [f"scénarios : explication LLM abandonnée ({type(exc).__name__}), gabarits"]
    if any(sections.values()):
        return sections, report
    return None, [*report, "scénarios : aucune phrase valide du LLM, gabarits"]


def _unavailable_reason(sr) -> str | None:
    """Raison pour laquelle la table ne peut pas être lue, ou None si elle l'est."""
    if sr is None:
        return f"{UNAVAILABLE_FR} : désactivés (ALPHAFORGE_SCENARIOS)"
    try:
        sr.loader.load()
    except Exception as exc:  # ScenarioTableError (SafeTableLoader) ou erreur d'un chargeur injecté
        return getattr(sr.loader, "reason", None) or f"{UNAVAILABLE_FR} : {describe_error(exc)}"
    return None


def _skipped(book: FactBook, inputs: dict, reason: str, limitation: str) -> tuple[Sections, list[str]]:
    """Étape non faite : une étape ``refus`` dans la trace et une seule limite, sans chiffre."""
    with book.step(AGENT, tool="scenario_risk", inputs=inputs) as ev:
        ev.status, ev.message = "refus", reason[:300]
    out = empty_sections()
    out["limits"].append(_limit(limitation))
    return out, [reason]


def explain_scenarios(book: FactBook, context: ScenarioContext) -> tuple[Sections, list[str]]:
    """Sections à ajouter à l'explication, et rapport. Ne lève pas pour une table indisponible."""
    sr = context.tool if context.tool is not None else scenario_tool(context.policy.scenario_run_id)
    reason = _unavailable_reason(sr)
    if reason is not None:
        limitation = (
            f"Scénarios probabilistes non utilisés ({UNAVAILABLE_FR} : {_why_unavailable(reason)}) : les mesures "
            "de risque reposent sur l'historique seulement."
        )
        return _skipped(book, {"available": False}, reason, limitation)
    params, why_not = call_params(context.weights, context.policy, context.profile)
    if params is None:
        return _skipped(book, {"mapped": False}, why_not, why_not[0].upper() + why_not[1:] + ".")
    report: list[str] = []
    if context.mode == "llm":
        sections, report = _llm_attempt(book, sr, params, context.model_factory)
        if sections is not None:
            return sections, report
    res = run_scenario(book, sr, **params)
    return template_sections(book, res), report
