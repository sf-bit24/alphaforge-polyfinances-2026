"""Construire le portefeuille : profil → mandat → débat en deux tours → Judge → explication.

``build_portfolio`` renvoie une ``contracts.Decision`` complète (positions, Facts, contrôles,
contrefactuels recalculés, explication vérifiée, trace) et l'enregistrement du débat.

Garanties :
- aucun poids ni chiffre ne vient d'un LLM : poids = optimiseur F2, contrôles = Judge F4 ;
- les lentilles ne voient PAS le plaidoyer au tour 1 (jugement indépendant), puis le voient au tour 2 ;
- le tour 2 est tranché par le code : un amendement appliqué est « satisfait », une objection du tour 2
  est « maintenue » et reste visible, mais ne change pas le mandat (pas de 3e optimisation) ;
- la ``Decision`` ne dépend que de (profil, version des données, mandat, demande) : insister ne la change pas.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from alphaforge.finance.contracts.decision import Counterfactual, Decision, Explanation, Position, Statement
from alphaforge.finance.contracts.policy import Limit, PolicySpec, Selector
from alphaforge.finance.contracts.profile import InvestorProfile
from alphaforge.finance.portfolio.judge import check, framed_alternative
from alphaforge.finance.portfolio.optimizer import optimize

from . import roles
from .esg import esg_exclusions, esg_preference
from .explain import grounding_check, grounding_context, keep_grounded, merge_grounding, rephrase, skeleton
from .facts import FactBook, fmt, sha256_json
from .merge import apply_amendments
from .schemas import LENS_FR, LENSES, AdvocacyBrief, AppliedAmendment, DebateRound, LensReport
from .tools import LensContext, lens_evidence

if TYPE_CHECKING:
    from alphaforge.finance.policy.models import CompileResult
    from alphaforge.finance.portfolio.judge import JudgeReport
    from alphaforge.finance.portfolio.optimizer import OptimizationResult
    from alphaforge.finance.strategy.select import StrategyResult

DEFAULT_AS_OF = date(2026, 9, 30)


@dataclass
class Request:
    """Demande précise de l'investisseur, ex. « 50 000 $ dans TSLA »."""

    ticker: str
    amount_cad: float | None = None
    weight: float | None = None

    def as_weight(self, wealth: float | None) -> float:
        if self.weight is not None:
            return self.weight
        if self.amount_cad is not None and wealth:
            return min(self.amount_cad / wealth, 1.0)
        raise ValueError("demande : montant et patrimoine, ou poids, requis")


@dataclass
class BuildResult:
    decision: Decision
    rounds: list[DebateRound] = field(default_factory=list)
    policy: PolicySpec | None = None
    explanation_report: list[str] = field(default_factory=list)
    grounding: dict | None = None
    strategy: object | None = None  # finance.strategy.select.StrategyResult quand l'étape 0 est active


def _opt_facts(book: FactBook, label: str, res, policy: PolicySpec) -> tuple[list[str], list[str]]:
    """Facts d'une optimisation : mesure de risque et limites actives (avec leur prix dual)."""
    ids, active = [], []
    src = f"optimizer:F2 ({res.solver}, fenêtre {res.window[0]}..{res.window[1]})" if res.window else "optimizer:F2"
    if res.risk_value is not None:
        ids.append(
            book.add(
                f"{label}.opt_risk",
                f"Risque minimisé ({res.risk_measure}, mensuel)",
                res.risk_value,
                "%",
                dataset=src,
                processing=f"objectif {res.objective}",
            )
        )
    by_id = {lim.rule_id: lim for lim in policy.limits}
    for key, is_active in sorted(res.active.items(), key=lambda kv: -res.duals.get(kv[0], 0.0)):
        rid, _, side = key.partition(":")
        parent = rid.split("[")[0]  # compile.py nomme « rule_id[actif] » ; seul strat.* est rapporté ainsi
        lim = by_id.get(rid) or (by_id.get(parent) if parent.startswith("strat.") else None)
        if not is_active or lim is None:
            continue
        bound = lim.max if side == "max" else lim.min
        if not bound:  # plafond à 0 = exclusion ; plancher à 0 = sans effet
            continue
        what = "plafond" if side == "max" else "plancher"
        lab = lim.description_fr or rid
        fid = book.add(
            f"{label}.active.{key}",
            f"{what.capitalize()} atteint : {lab}",
            bound,
            "%",
            dataset=src,
            processing=f"prix dual {res.duals.get(key, 0.0):.4g}",
        )
        active.append(fid)
    return ids, active


def _with_request(policy: PolicySpec, req: Request, w: float) -> PolicySpec:
    p = policy.model_copy(deep=True)
    p.limits.append(
        Limit(
            rule_id=f"request.min.{req.ticker}",
            kind="asset_weight",
            selector=Selector(assets=[req.ticker]),
            min=round(w, 6),
            blocking=True,
            derived_from="demande précise de l'investisseur",
            source="request",
            description_fr=f"poids demandé dans {req.ticker}",
        )
    )
    return PolicySpec.model_validate(p.model_dump())


def build_portfolio(  # noqa: PLR0913 - signature publique : les appelants passent ces options par mot-clé
    profile: InvestorProfile,
    as_of: date = DEFAULT_AS_OF,
    *,
    request: Request | None = None,
    mode: str = "rules",
    evidence_fn=None,
    compile_fn=None,
    rephrase_explanation: bool | None = None,
    guardrail_id: str | None = None,
    guardrail_version: str | None = None,
    decision_id: str | None = None,
    strategy: bool = True,
    style_preference: str | None = None,
    style_inputs=None,
    scenarios: bool | None = None,
    scenario_tool=None,
    grounding_docs: Sequence[tuple[str, str]] = (),
) -> BuildResult:
    """S0 mandat (F1) → S0c preuves ESG → S0b étape 0 → tours 1 et 2 du débat → demande précise avec / sans →
    Judge final (F4) → contrefactuels recalculés → explication (reformulation, ancrage Guardrails) → Decision."""
    if compile_fn is None:
        from alphaforge.finance.policy import compile_profile as compile_fn
    options = _Options(
        mode=mode,
        evidence_fn=evidence_fn,
        rephrase_explanation=rephrase_explanation,
        guardrail_id=guardrail_id,
        guardrail_version=guardrail_version,
        strategy=strategy,
        style_preference=style_preference,
        style_inputs=style_inputs,
        scenarios=scenarios,
        scenario_tool=scenario_tool,
        grounding_docs=grounding_docs,
    )
    did = decision_id or f"dec-{profile.profile_id}-v{profile.version}-{uuid.uuid4().hex[:8]}"
    build = _Build(profile, as_of, request, options, FactBook(did))
    mandate = _compile_mandate(build, compile_fn)
    if mandate.comp.policy is None:  # filet : mandat impossible à compiler
        return _without_policy(build, mandate)
    debate = _open_debate(build, mandate)
    debated = _second_round(debate, _first_round(debate))
    outcome = _final_portfolio(debate, debated)
    cfs, cf_stmts = _counterfactuals(debate, debated)
    expl, report, grounding = _explanation(debate, debated, outcome, cf_stmts)
    positions = _positions(debate, outcome.weights)
    decision = Decision(
        decision_id=did,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        created_utc=datetime.now(UTC),
        # Le statut du profil prime sur l'issue de la demande ; le portefeuille est toujours rendu.
        kind=mandate.comp.decision_kind or outcome.kind,
        positions=positions,
        facts=list(build.book.facts.values()),
        constraints=list(outcome.judge.checks),
        counterfactuals=cfs,
        explanation=expl,
        trace=build.book.trace,
    )
    return BuildResult(
        decision=decision,
        rounds=debated.rounds,
        policy=debated.policy,
        explanation_report=report,
        grounding=grounding,
        strategy=debate.strat,
    )


# ------------------------------------------------------------------------- état partagé par les étapes
@dataclass(frozen=True)
class _Options:
    """Options de ``build_portfolio`` lues par les étapes (mêmes noms que ses paramètres)."""

    mode: str
    evidence_fn: Callable | None
    rephrase_explanation: bool | None
    guardrail_id: str | None
    guardrail_version: str | None
    strategy: bool
    style_preference: str | None
    style_inputs: Any
    scenarios: bool | None
    scenario_tool: Any
    grounding_docs: Sequence[tuple[str, str]]

    @property
    def rephrases(self) -> bool | None:
        """Reformulation LLM de l'explication : comme demandé, sinon seulement en mode llm."""
        return self.rephrase_explanation if self.rephrase_explanation is not None else self.mode == "llm"


@dataclass
class _Build:
    """Une construction : profil, date, demande, options, registre des faits, et rôles du débat selon le mode."""

    profile: InvestorProfile
    as_of: date
    request: Request | None
    options: _Options
    book: FactBook
    lens_fn: Callable = field(init=False)
    advocate_fn: Callable = field(init=False)

    def __post_init__(self) -> None:
        llm = self.options.mode == "llm"
        self.lens_fn = roles.llm_lens if llm else roles.rules_lens
        self.advocate_fn = roles.llm_advocate if llm else roles.rules_advocate

    @property
    def protect(self) -> list[str]:
        """Titre de la demande précise, que les exclusions ESG et l'étape 0 ne retirent pas (liste neuve)."""
        return [self.request.ticker] if self.request else []


@dataclass(frozen=True)
class _Mandate:
    """S0 : mandat compilé (F1), fait du niveau, faits du portefeuille existant et raison chiffrée du statut."""

    comp: CompileResult
    level_fid: str
    holding_fids: list[str]
    status_stmts: dict[str, list[Statement]] | None


@dataclass(frozen=True)
class _Debate:
    """Ce que les deux tours partagent : mandat de départ (après les preuves ESG et l'étape 0), versions figées,
    magasin OKF et test de faisabilité des amendements."""

    build: _Build
    mandate: _Mandate
    base: PolicySpec
    strat: StrategyResult | None
    versions: dict[str, str]
    market: Any  # magasin OKF derrière evidence_fn (OkfMarketStore), sinon evidence_fn lui-même
    feasible: Callable[[PolicySpec], bool]


@dataclass(frozen=True)
class _FirstRound:
    result: OptimizationResult
    reports: list[LensReport]
    policy: PolicySpec  # mandat après les amendements du tour 1
    log: list[AppliedAmendment]
    round: DebateRound


@dataclass(frozen=True)
class _DebateResult:
    """Issue du débat : candidat et mandat du tour 2, amendements du tour 1, verdicts du tour 2."""

    rounds: list[DebateRound]
    applied: list[AppliedAmendment]
    policy: PolicySpec
    result: OptimizationResult
    fact_ids: list[str]
    active: list[str]
    verdicts: dict[str, str]


@dataclass(frozen=True)
class _Outcome:
    """Portefeuille final (avec ou sans la demande précise) et rapport du Judge final."""

    weights: dict[str, float]
    kind: str
    request_fids: list[str]
    judge: JudgeReport
    strategy_final: dict | None


@dataclass(frozen=True)
class _Draft:
    """Explication en cours : texte (reformulé ou non), son gabarit et le rapport de vérification."""

    explanation: Explanation
    template: Explanation
    report: list[str]


# ------------------------------------------------------------------------- S0 profil → mandat
def _compile_mandate(build: _Build, compile_fn) -> _Mandate:
    """Profil → mandat (F1), puis la raison chiffrée du statut du profil s'il en a un."""
    book, profile, as_of = build.book, build.profile, build.as_of
    with book.step("s0.policy_compiler", tool="compile_profile", inputs={"as_of": str(as_of)}):
        comp = compile_fn(profile, as_of)
        level_fid = book.add(
            "level",
            "Niveau de risque effectif",
            comp.level,
            "niveau",
            dataset="alphaforge/finance/policy/risk_levels.yaml@0.2.0",
            processing=f"R = {comp.R:.1f}",
        )
        for k, v in comp.emphasis.items():
            book.add(
                f"emphasis.{k}",
                f"Poids de la lentille {LENS_FR.get(k, k)}",
                v,
                "%",
                dataset="policy_compiler/emphasis.yaml",
            )
        holding_fids = _holding_facts(book, profile)
    # Statut du profil (protection, incomplet, position d'attente) : il resserre le mandat, il n'empêche plus le
    # portefeuille. Sa raison réelle devient des faits tirés de la trace du compilateur.
    status_stmts = None
    if comp.decision_kind and comp.policy is not None:
        with book.step("s0.status", tool="compile_profile", inputs={"decision_kind": comp.decision_kind}):
            status_stmts = _status_statements(book, comp, profile)
    return _Mandate(comp, level_fid, holding_fids, status_stmts)


def _without_policy(build: _Build, mandate: _Mandate) -> BuildResult:
    """Filet : mandat impossible à compiler, aucune allocation ; la décision dit ce qui manque."""
    book, profile, comp, level_fid = build.book, build.profile, mandate.comp, mandate.level_fid
    expl = Explanation(
        data_used=[Statement(text_fr="Profil analysé selon les règles déterministes du mandat.", fact_ids=[level_fid])],
        why=[
            Statement(
                text_fr="Le profil ne permet pas encore une proposition : informations manquantes ou "
                "signaux de vulnérabilité ; une position d'attente prudente s'applique.",
                fact_ids=[level_fid],
            )
        ],
        limits=[
            Statement(
                text_fr="Aucune allocation n'est calculée tant que le profil n'est pas complété.", label="HYPOTHESE"
            )
        ],
        what_would_change=[
            Statement(
                text_fr="Compléter : " + ", ".join(profile.missing_info or ["le profil"]) + ".", label="HYPOTHESE"
            )
        ],
    )
    d = Decision(
        decision_id=book.decision_id,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        created_utc=datetime.now(UTC),
        kind=comp.decision_kind or "incomplet",
        facts=list(book.facts.values()),
        explanation=expl,
        trace=book.trace,
    )
    return BuildResult(decision=d, policy=comp.policy)


# ------------------------------------------------------------------------- S0c preuves ESG, S0b étape 0
def _open_debate(build: _Build, mandate: _Mandate) -> _Debate:
    """Mandat de départ du débat : preuves ESG de la base générale, puis étape 0 (style et sélection)."""
    comp = mandate.comp
    # Preuves ESG avant l'étape 0, pour qu'elle ne retienne jamais un titre exclu ; la preuve devient la raison de
    # l'exclusion.
    market = getattr(build.options.evidence_fn, "__self__", build.options.evidence_fn)
    comp.policy = esg_exclusions(build.profile, comp.policy, market, build.as_of, build.book, protect=build.protect)
    strat, base = _select_strategy(build, comp)
    versions = {"policy": "risk_levels@0.2.0", "profile": f"{build.profile.profile_id}@{build.profile.version}"}
    versions["strategy"] = f"strategy.yaml@{strat.version}" if strat else "off"
    return _Debate(build, mandate, base, strat, versions, market, _feasibility(build.as_of))


def _select_strategy(build: _Build, comp: CompileResult) -> tuple[StrategyResult | None, PolicySpec]:
    """Étape 0 : (résultat, mandat retenu). Désactivée ou en erreur : (None, mandat de base)."""
    base = comp.policy
    if not build.options.strategy:
        return None, base
    from alphaforge.finance.strategy import apply_strategy

    try:
        strat = apply_strategy(
            comp,
            build.profile,
            build.as_of,
            build.book,
            inputs=build.options.style_inputs,
            preference=build.options.style_preference,
            protect=build.protect,
        )
    except Exception as exc:  # l'étape 0 ne fait jamais échouer la décision : repli sur le mandat de base
        _strategy_failed(build.book, exc)
        return None, base
    return strat, strat.policy


def _strategy_failed(book: FactBook, exc: Exception) -> None:
    with book.step("s0b.strategy", tool="strategy.select", inputs={"error": type(exc).__name__}) as ev:
        ev.status = "erreur"
        ev.message = f"{type(exc).__name__}: {exc}"[:300]
        book.add(
            "strat.error",
            "étape 0 abandonnée : mandat de base conservé",
            type(exc).__name__,
            "texte",
            dataset="finance/strategy",
            status="HYPOTHESE",
        )


def _feasibility(as_of: date) -> Callable[[PolicySpec], bool]:
    """Faisabilité d'un mandat amendé (garde de la fusion), en cache par empreinte du mandat."""
    cache: dict[str, bool] = {}

    def feasible(p: PolicySpec) -> bool:
        k = sha256_json(p.model_dump(mode="json", exclude={"created_utc", "policy_id"}))
        if k not in cache:
            cache[k] = optimize(p, as_of).status == "optimal"
        return cache[k]

    return feasible


# ------------------------------------------------------------------------- Tours 1 et 2
def _first_round(debate: _Debate) -> _FirstRound:
    """Tour 1 : candidat optimisé, plaidoyer, lentilles sans le plaidoyer, puis fusion de leurs amendements."""
    build, base = debate.build, debate.base
    book = build.book
    with book.step("s2.optimize", tool="optimize", inputs={"round": 1}):
        r1 = optimize(base, build.as_of)
        if r1.status != "optimal":
            raise RuntimeError(f"mandat infaisable : {r1.infeasible_rules}")
        _stamp_data_version(debate, r1)
        r1_ids, _ = _opt_facts(book, "r1", r1, base)
    ctx = LensContext(
        build.profile, base, r1.weights, build.as_of, book, label="r1", evidence_fn=build.options.evidence_fn
    )
    brief, reports = _hearing(debate, ctx, r1_ids, 1, None)
    emphasis = debate.mandate.comp.emphasis
    with book.step("s3.merge", tool="apply_amendments", inputs={"round": 1}):
        policy, log = apply_amendments(
            base,
            reports,
            emphasis,
            set(book.facts),
            feasible=debate.feasible,
            esg_preference=esg_preference(build.profile),
        )
    round1 = DebateRound(
        round=1, candidate_fact_ids=r1_ids, advocate=brief, lens_reports=reports, emphasis=emphasis, decisions=log
    )
    return _FirstRound(r1, reports, policy, log, round1)


def _stamp_data_version(debate: _Debate, r1: OptimizationResult) -> None:
    """Version des données de la décision : celle de l'optimiseur, étendue des entrées lues hors du jeu figé."""
    book = debate.build.book
    book.data_version = r1.data_version
    # Données de marché quotidiennes (alphaforge.market) lues par l'étape 0 : leur version entre dans celle de
    # la décision. En repli sur le jeu de départ (figé), rien ne change.
    if debate.strat is not None:
        from alphaforge import market

        mv = market.data_version()
        if mv.get("source") == "market" and mv.get("version"):
            book.data_version = f"{book.data_version}+market:{mv['version']}"
    # Lot E, OKF général : avec le magasin OKF (OkfMarketStore), la version des données couvre aussi les
    # (clé, ETag) des fondamentaux de general/societes/ et des faits ESG de general/faits/, lus une fois pour
    # toute la décision. Jamais les actualités : une nouvelle ne change ni le mandat ni la version des données.
    if hasattr(debate.market, "inputs"):
        book.data_version = debate.market.data_version(book.data_version)


def _hearing(
    debate: _Debate, ctx: LensContext, candidate_ids: list[str], round_no: int, objections: list[LensReport] | None
) -> tuple[AdvocacyBrief, list[LensReport]]:
    """Un tour du débat sur un candidat : preuves par lentille, plaidoyer de A3, puis les quatre lentilles."""
    build, versions, emphasis = debate.build, debate.versions, debate.mandate.comp.emphasis
    evidence = {lens: lens_evidence(lens, ctx) for lens in LENSES}
    with build.book.step("a3", tool="advocate", inputs={"round": round_no}):
        brief = build.advocate_fn(ctx, candidate_ids + evidence["risk"], round_no, objections, versions)
    shown = None if round_no == 1 else brief  # tour 1 : les lentilles ne voient pas le plaidoyer

    def run_lens(lens):
        return build.lens_fn(lens, ctx, evidence[lens], round_no, shown, emphasis.get(lens, 0.25), versions)

    with ThreadPoolExecutor(max_workers=4) as ex:
        reports = list(ex.map(run_lens, LENSES))
    return brief, reports


def _second_round(debate: _Debate, first: _FirstRound) -> _DebateResult:
    """Tour 2 : réoptimisation si le mandat a changé, puis les lentilles voient le plaidoyer ; le code tranche."""
    build = debate.build
    book = build.book
    changed = any(a.status == "applique" and a.amendment.kind != "flag_only" for a in first.log)
    with book.step("s2.optimize", tool="optimize", inputs={"round": 2, "policy_changed": changed}):
        r2 = optimize(first.policy, build.as_of) if changed else first.result
        r2_ids, r2_active = _opt_facts(book, "r2", r2, first.policy)
    ctx = LensContext(
        build.profile, first.policy, r2.weights, build.as_of, book, label="r2", evidence_fn=build.options.evidence_fn
    )
    brief, reports = _hearing(debate, ctx, r2_ids, 2, first.reports)
    verdicts = _verdicts(first.log, reports)
    round2 = DebateRound(
        round=2,
        candidate_fact_ids=r2_ids,
        advocate=brief,
        lens_reports=reports,
        emphasis=debate.mandate.comp.emphasis,
        verdicts=verdicts,
    )
    return _DebateResult([first.round, round2], first.log, first.policy, r2, r2_ids, r2_active, verdicts)


def _verdicts(log: list[AppliedAmendment], reports: list[LensReport]) -> dict[str, str]:
    """Verdict de chaque lentille au tour 2 : une objection ou un amendement la maintient ; sinon, un amendement
    appliqué au tour 1 est satisfait ; sinon, soutien."""
    verdicts = {}
    for lens, rep in zip(LENSES, reports, strict=True):
        applied = [a for a in log if a.lens == lens and a.status == "applique" and a.amendment.kind != "flag_only"]
        if rep.objections or rep.amendments:
            verdicts[lens] = "objection_maintenue"
        elif applied:
            verdicts[lens] = "objection_satisfaite"
        else:
            verdicts[lens] = "soutien"
    return verdicts


# ------------------------------------------------------------------------- Demande précise et Judge final
def _final_portfolio(debate: _Debate, debated: _DebateResult) -> _Outcome:
    """Candidat du tour 2, ou variante avec la demande précise si le Judge l'approuve, puis Judge final."""
    build = debate.build
    book = build.book
    strat_final = _final_strategy_facts(book, debate.strat, debated.policy) if debate.strat is not None else None
    weights, kind, req_fids = debated.result.weights, "proposition", []
    if build.request is not None:
        weights, kind, req_fids = _request_variant(build, debated)
    with book.step("judge", tool="check", inputs={"variant": "final"}):
        rep = check(weights, debated.policy, build.as_of, trace_id=f"{book.current}:final")
        book.absorb_report(rep)
    if not rep.approved:
        kind = "refus_encadre"
    return _Outcome(weights, kind, req_fids, rep, strat_final)


def _request_variant(build: _Build, debated: _DebateResult) -> tuple[dict[str, float], str, list[str]]:
    """Demande avec / sans : (poids, issue, faits cités). Refusée par le Judge, une proposition encadrée la
    remplace quand elle existe ; sinon le candidat du tour 2 reste."""
    request, book, policy = build.request, build.book, debated.policy
    req_fids: list[str] = []
    w_req = request.as_weight(build.profile.investable_wealth)
    with book.step("request", tool="optimize_with_request", inputs={"ticker": request.ticker, "weight": w_req}):
        req_fids.append(
            book.add(
                "request.weight",
                f"Poids demandé dans {request.ticker}",
                w_req,
                "%",
                dataset="interaction investisseur",
            )
        )
        target = {**{a: x * (1 - w_req) for a, x in debated.result.weights.items()}, request.ticker: w_req}
    ctxq = LensContext(build.profile, policy, target, build.as_of, book, label="demande")
    req_fids += lens_evidence("risk", ctxq)
    with book.step("judge", tool="check", inputs={"variant": "demande"}):
        repq = check(target, policy, build.as_of, trace_id=f"{book.current}:demande")
        req_fids += book.absorb_report(repq)
    if repq.approved:
        return target, "proposition", req_fids
    with book.step("judge", tool="framed_alternative"):
        alt, rep_alt, method = framed_alternative(target, policy, build.as_of)
        book.absorb_report(rep_alt)
        req_fids.append(
            book.add(
                "request.framed_method",
                "Méthode de la proposition encadrée",
                method,
                "texte",
                dataset="judge:F4",
            )
        )
    return (alt if alt is not None else debated.result.weights), "refus_encadre", req_fids


# ------------------------------------------------------------------------- Contrefactuels recalculés
def _counterfactuals(debate: _Debate, debated: _DebateResult) -> tuple[list[Counterfactual], list[Statement]]:
    """Contrefactuels et leurs énoncés, dans cet ordre : borne la plus chère desserrée, demande telle quelle,
    styles voisins, mandat de base sans l'étape 0."""
    build = debate.build
    book = build.book
    pairs: list[tuple[Counterfactual, Statement]] = []
    with book.step("counterfactuals", tool="optimize"):
        relaxed = _relaxed_bound(book, debated, build.as_of)
        if relaxed is not None:
            pairs.append(relaxed)
        if build.request is not None and "demande.cvar_m" in book.facts:
            pairs.append(_request_counterfactual(book, build.request.ticker))
        if debate.strat is not None and debate.strat.applied:
            pairs += _strategy_counterfactuals(debate)
    return [cf for cf, _ in pairs], [st for _, st in pairs]


def _relaxed_bound(book: FactBook, debated: _DebateResult, as_of: date) -> tuple[Counterfactual, Statement] | None:
    """La limite active au prix dual le plus élevé, desserrée d'un cran, puis réoptimisée sur les mêmes données."""
    lever = _costliest_bound(debated.result, debated.policy)
    if lever is None:
        return None
    rid, side, lim = lever
    relaxed = debated.policy.model_copy(deep=True)
    old, new = _relax(next(lim for lim in relaxed.limits if lim.rule_id == rid), side)
    rr = optimize(PolicySpec.model_validate(relaxed.model_dump()), as_of)
    if rr.status != "optimal" or rr.risk_value is None:
        return None
    lab = lim.description_fr or rid
    f_old = book.add("cf.bound_old", f"Borne actuelle « {lab} » ({side})", old, "%", dataset="mandat")
    f_new = book.add("cf.bound_new", f"Borne testée « {lab} » ({side})", new, "%", dataset="contrefactuel")
    f_r = book.add(
        "cf.relax_risk",
        "Risque minimisé avec la borne testée",
        rr.risk_value,
        "%",
        dataset="optimizer:F2",
        processing="réoptimisation, mêmes données",
    )
    f_r0 = debated.fact_ids[0] if debated.fact_ids else f_r
    change = f"Si la borne « {lab} » passait de {fmt(old, '%')} à {fmt(new, '%')}"
    statement = Statement(
        text_fr=f"{change}, le risque minimisé passerait de {fmt(book.facts[f_r0].value, '%')} "
        f"à {fmt(rr.risk_value, '%')}.",
        fact_ids=[f_old, f_new, f_r0, f_r],
    )
    return Counterfactual(change_fr=change, result_fact_ids=[f_r]), statement


def _costliest_bound(r2: OptimizationResult, policy: PolicySpec) -> tuple[str, str, Limit] | None:
    """(rule_id, côté, limite) de la borne active au prix dual le plus élevé ; ni la demande ni l'étape 0, et jamais
    un plafond ou un plancher à 0."""
    by_id = {lim.rule_id: lim for lim in policy.limits}
    cands = []
    for key, dual in r2.duals.items():
        rid, _, side = key.partition(":")
        lim = by_id.get(rid)
        if not r2.active.get(key) or lim is None or rid.startswith(("request.", "strat.")):
            continue
        if (side == "max" and lim.max) or (side == "min" and lim.min):  # un plafond à 0 (exclusion) n'est pas un levier
            cands.append((dual, rid, side, lim))
    if not cands:
        return None
    _, rid, side, lim = max(cands, key=lambda c: c[0])
    return rid, side, lim


def _relax(lim: Limit, side: str) -> tuple[float, float]:
    """Desserre la borne en place : plafond de risque × 1,25, autre plafond + 5 points (≤ 100 %), plancher − 10
    points (≥ 0). Renvoie (ancienne, nouvelle)."""
    if side == "max":
        old, new = lim.max, (lim.max * 1.25 if lim.kind == "risk" else min(lim.max + 0.05, 1.0))
        lim.max = new
    else:
        old, new = lim.min, max(lim.min - 0.10, 0.0)
        lim.min = new
    return old, new


def _request_counterfactual(book: FactBook, ticker: str) -> tuple[Counterfactual, Statement]:
    cf = Counterfactual(
        change_fr=f"Avec la demande sur {ticker} telle quelle",
        result_fact_ids=[f for f in ("demande.cvar_m", "demande.mdd") if f in book.facts],
    )
    statement = Statement(
        text_fr=f"Avec la demande sur {ticker} telle quelle, la CVaR mensuelle "
        f"serait de {fmt(book.facts['demande.cvar_m'].value, '%')}.",
        fact_ids=["demande.cvar_m"],
    )
    return cf, statement


def _strategy_counterfactuals(debate: _Debate) -> list[tuple[Counterfactual, Statement]]:
    """Styles voisins, puis le mandat de base sans le style ni la sélection."""
    book = debate.build.book
    pairs = _style_counterfactuals(debate)
    if "strat.base_risk" in book.facts:
        cf = Counterfactual(
            change_fr="Sans le style ni la sélection (mandat de base)", result_fact_ids=["strat.base_risk"]
        )
        statement = Statement(
            text_fr="Sans le style ni la sélection (mandat de base, avant les lentilles), le risque "
            "minimisé serait de "
            f"{fmt(book.facts['strat.base_risk'].value, '%')}.",
            fact_ids=["strat.base_risk"],
            label="HYPOTHESE",
        )
        pairs.append((cf, statement))
    return pairs


# ------------------------------------------------------------------------- Explication
def _explanation(
    debate: _Debate, debated: _DebateResult, outcome: _Outcome, cf_stmts: list[Statement]
) -> tuple[Explanation, list[str], dict | None]:
    """Gabarit vérifié, reformulation éventuelle, puis ancrage Guardrails : (explication, rapport, ancrage)."""
    build = debate.build
    template = _template(debate, debated, outcome, cf_stmts)
    expl, report = _rephrased(build, template)
    if not build.options.guardrail_id:
        return expl, report, None
    expl, grounding, report = _grounded(build, _Draft(expl, template, report), outcome.judge.checks, debated.verdicts)
    return expl, report, grounding


def _template(debate: _Debate, debated: _DebateResult, outcome: _Outcome, cf_stmts: list[Statement]) -> Explanation:
    """Gabarit de l'explication : squelette, portefeuille existant, scénarios, puis raison du statut."""
    build, mandate = debate.build, debate.mandate
    book = build.book
    expl = skeleton(
        book,
        kind=outcome.kind,
        level_fid=mandate.level_fid,
        cand="r2",
        active_fids=debated.active,
        applied=debated.applied,
        counterfactual_stmts=cf_stmts,
        request_fids=outcome.request_fids,
        limits_extra=[
            f"Objection maintenue par la lentille « {LENS_FR.get(lens, lens)} » au second tour."
            for lens, v in debated.verdicts.items()
            if v == "objection_maintenue"
        ],
        strategy=outcome.strategy_final,
    )
    if mandate.holding_fids:
        expl.data_used.insert(1, _holding_statement(book, mandate.holding_fids))
    # Scénarios probabilistes (outil scenario_risk) : par défaut seulement avec une limite PROB_LOSS, voir scenarios.py
    from .scenarios import ScenarioContext, attach_scenarios

    options = build.options
    scenario_context = ScenarioContext(
        outcome.weights, debated.policy, build.profile, options.mode, options.scenario_tool
    )
    expl = attach_scenarios(book, expl, scenario_context, enabled=options.scenarios)
    if mandate.status_stmts:
        expl = _with_status(expl, mandate.status_stmts)
    return expl


def _rephrased(build: _Build, template: Explanation) -> tuple[Explanation, list[str]]:
    """Reformulation LLM phrase par phrase si demandée ; en cas d'échec, le gabarit reste."""
    if not build.options.rephrases:
        return template, []
    try:
        expl, report = rephrase(build.book, template, build.profile.knowledge_level)
    except Exception:  # repli : le gabarit reste ; l'étape « explainer » de la trace garde l'erreur
        return template, ["Reformulation abandonnée : les gabarits sont conservés."]
    return expl, report


def _positions(debate: _Debate, weights: dict[str, float]) -> list[Position]:
    """Positions de poids non négligeable, du plus gros au plus petit, normalisées à 100 %. Satellite : le titre
    demandé, un titre de l'étape 0 ou un actif à budget de perte propre ; cœur sinon."""
    build, strat, base = debate.build, debate.strat, debate.base
    request, book = build.request, build.book
    singles = set(strat.shortlist) | {c.ticker for c in strat.candidates} if strat else set()
    positions = [
        Position(
            asset_id=a,
            weight=w,
            role="satellite"
            if (request and a == request.ticker) or a in singles or (strat is not None and a in base.loss_bounds)
            else "coeur",
            rationale_fact_ids=[
                f for f in (f"r2.rc.{a}", f"strat.rank.{a}", f"strat.score.{a}", f"strat.floor.{a}") if f in book.facts
            ],
        )
        for a, w in sorted(weights.items(), key=lambda kv: -kv[1])
        if w > 1e-4
    ]
    tot = sum(p.weight for p in positions)
    positions = [p.model_copy(update={"weight": p.weight / tot}) for p in positions]
    if abs(sum(p.weight for p in positions) - 1) > 1e-9:  # arrondi flottant résiduel
        positions[0] = positions[0].model_copy(
            update={"weight": positions[0].weight + 1 - sum(p.weight for p in positions)}
        )
    return positions


HOLDINGS_DATASET = "client:portefeuille-existant.md (positions évaluées par profile/portfolio.py)"


def _holding_facts(book: FactBook, profile: InvestorProfile) -> list[str]:
    """Portefeuille existant (``profile.holdings``, valeurs en CAD calculées par le code d'A2) : nombre de positions,
    valeur totale et plus grande position, avec sa part du patrimoine investissable s'il est connu."""
    if not profile.holdings:
        return []
    total = sum(h.market_value for h in profile.holdings)
    top = max(profile.holdings, key=lambda h: (h.market_value, h.ticker))
    ids = [
        book.add(
            "holdings.n", "Positions existantes évaluées", len(profile.holdings), "positions", dataset=HOLDINGS_DATASET
        ),
        book.add(
            "holdings.total", "Valeur du portefeuille existant", total, "CAD", dataset=HOLDINGS_DATASET, currency="CAD"
        ),
        book.add(
            "holdings.top",
            f"Plus grande position existante ({top.ticker})",
            top.market_value,
            "CAD",
            dataset=HOLDINGS_DATASET,
            currency="CAD",
        ),
    ]
    if profile.investable_wealth:
        ids.append(
            book.add(
                "holdings.top_share",
                f"Part de {top.ticker} dans le patrimoine investissable",
                top.market_value / profile.investable_wealth,
                "%",
                dataset=HOLDINGS_DATASET,
                processing="valeur de la position / investable_wealth",
            )
        )
    return ids


def _holding_statement(book: FactBook, fids: list[str]) -> Statement:
    f = book.facts
    ticker = f["holdings.top"].label_fr.rsplit("(", 1)[-1].rstrip(")")
    text = (
        f"Portefeuille existant pris en compte : {fmt(f['holdings.n'].value, 'positions')} positions évaluées, "
        f"{fmt(f['holdings.total'].value, 'CAD')} au total ; la plus grande, {ticker}, vaut "
        f"{fmt(f['holdings.top'].value, 'CAD')}"
    )
    if "holdings.top_share" in f:
        text += f", soit {fmt(f['holdings.top_share'].value, '%')} du patrimoine investissable"
    return Statement(text_fr=text + ".", fact_ids=fids)


STATUS_DATASET = "alphaforge/finance/policy/risk_levels.yaml@0.2.0#status"
DOLLAR_DATASET = "alphaforge/finance/policy/risk_levels.yaml@0.2.0#dollar_rule"


def _trace_rule(comp, rule: str) -> dict | None:
    """Dernière règle ``rule`` inscrite par le compilateur (entrées, sortie, chemin YAML), ou None."""
    for record in reversed(comp.trace or []):
        if isinstance(record, dict) and record.get("rule") == rule:
            return record
    return None


def _shown(book: FactBook, fid: str) -> str:
    """Valeur affichée (et vérifiée) d'un fait, dans son unité."""
    return fmt(book.facts[fid].value, book.facts[fid].unit)


def _status_statements(book: FactBook, comp, profile: InvestorProfile) -> dict[str, list[Statement]]:
    """Pourquoi le profil a un statut, en faits tirés de la trace du compilateur.

    Protection par la règle des dollars : l* et la plus petite perte de planification de la grille. Protection
    demandée par le profil : son statut. Profil incomplet : les champs obligatoires manquants et le plafond de
    niveau. Le portefeuille est construit dans ce mandat resserré ; ces énoncés disent pourquoi il est si prudent.
    """
    out: dict[str, list[Statement]] = {"data_used": [], "why": [], "limits": [], "what_would_change": []}
    if comp.decision_kind == "protection":
        _protection_statements(book, comp, profile, out)
    cap = _trace_rule(comp, "status.INCOMPLETE.level_cap")
    if comp.decision_kind in ("incomplet", "position_attente") and cap is not None:
        _incomplete_statements(book, comp, profile, cap, out)
    return out


def _protection_statements(book: FactBook, comp, profile: InvestorProfile, out: dict[str, list[Statement]]) -> None:
    """Statut protection : règle des dollars, statut demandé par le profil, revue humaine."""
    by_profile = str(getattr(profile.status, "value", profile.status)) == "PROTECTION"
    dollar = _trace_rule(comp, "dollar_rule.protection")
    if dollar is not None:
        _dollar_rule_statements(book, comp, dollar, out, by_profile=by_profile)
    if by_profile:
        book.add("status.profile", "Statut demandé par le profil", "PROTECTION", "texte", dataset="profil client")
        out["why"].append(
            Statement(
                text_fr="Le profil signale une situation à protéger (statut PROTECTION) : le portefeuille "
                "construit est le plus prudent du mandat, sans titre individuel ni cryptoactif.",
                fact_ids=["status.profile"],
            )
        )
    referral = _trace_rule(comp, "status.PROTECTION.human_referral")
    if referral is not None and referral.get("output"):
        fid = book.add("status.human_referral", "Revue humaine demandée", "oui", "texte", dataset=STATUS_DATASET)
        out["limits"].append(
            Statement(
                text_fr="Statut protection : une revue par une personne (conseiller ou personne de confiance) est "
                "recommandée avant toute suite.",
                fact_ids=[fid],
                label="HYPOTHESE",
            )
        )


def _dollar_rule_statements(
    book: FactBook, comp, dollar: dict, out: dict[str, list[Statement]], *, by_profile: bool
) -> None:
    """Protection par la règle des dollars : même sans actions, la plus petite perte de planification dépasse l*."""
    book.add(
        "status.l_star",
        "Perte acceptable retenue (l*)",
        dollar["inputs"]["l_star"],
        "%",
        dataset=DOLLAR_DATASET,
        processing="la plus basse de la perte de planification au plafond d'actions, de la perte déclarée "
        "et de la perte absorbable",
    )
    book.add(
        "status.min_l_plan",
        "Plus petite perte de planification de la grille d'actions",
        dollar["inputs"]["min_L_plan"],
        "%",
        dataset=DOLLAR_DATASET,
    )
    detail, ids = _admitted_losses(book, comp)
    out["data_used"].append(
        Statement(
            text_fr=f"Perte acceptable retenue : {_shown(book, 'status.l_star')}, la plus basse des pertes admises"
            f"{detail}.",
            fact_ids=ids,
        )
    )
    out["why"].append(
        Statement(
            text_fr="Statut protection : même sans actions, la plus petite perte de planification "
            f"({_shown(book, 'status.min_l_plan')}) dépasse la perte acceptable retenue "
            f"({_shown(book, 'status.l_star')}). Le "
            "portefeuille construit est le plus prudent du mandat : sans actions, sans titre individuel ni "
            "cryptoactif.",
            fact_ids=["status.min_l_plan", "status.l_star"],
        )
    )
    if not by_profile:
        out["what_would_change"].append(
            Statement(
                text_fr=f"Si la perte acceptable retenue atteignait {_shown(book, 'status.min_l_plan')}, le statut "
                "protection serait levé (règle des dollars).",
                fact_ids=["status.min_l_plan"],
                label="HYPOTHESE",
            )
        )


def _admitted_losses(book: FactBook, comp) -> tuple[str, list[str]]:
    """Pertes déclarée et absorbable entrées dans l* : (détail entre parenthèses, faits cités avec l*)."""
    star = _trace_rule(comp, "dollar_rule.l_star") or {"inputs": {}}
    parts, ids = [], ["status.l_star"]
    for key, fid, label, text in (
        ("l_declared", "status.l_declared", "Perte maximale déclarée (part du patrimoine)", "perte déclarée"),
        ("l_cap", "status.l_cap", "Perte absorbable (capacité)", "perte absorbable"),
    ):
        if star["inputs"].get(key) is not None:
            book.add(fid, label, star["inputs"][key], "%", dataset=DOLLAR_DATASET)
            parts.append(f"{text} {_shown(book, fid)}")
            ids.append(fid)
    return (f" ({', '.join(parts)})" if parts else ""), ids


def _incomplete_statements(
    book: FactBook, comp, profile: InvestorProfile, cap: dict, out: dict[str, list[Statement]]
) -> None:
    """Profil incomplet ou en position d'attente : informations obligatoires manquantes et plafond de niveau."""
    book.add(
        "status.level_cap", "Niveau plafond d'un profil incomplet", cap["output"], "niveau", dataset=STATUS_DATASET
    )
    missing = (_trace_rule(comp, "decision_kind") or {"inputs": {}})["inputs"].get("must_have_missing") or []
    if missing:
        book.add(
            "status.missing",
            "Informations obligatoires manquantes",
            ", ".join(missing),
            "texte",
            dataset=STATUS_DATASET,
        )
        out["why"].append(
            Statement(
                text_fr=f"Informations obligatoires manquantes ({_shown(book, 'status.missing')}) : le portefeuille "
                "est construit avec des valeurs prudentes par défaut, à revoir dès que le profil est complété.",
                fact_ids=["status.missing"],
            )
        )
    out["why"].append(
        Statement(
            text_fr=f"Profil à compléter : le niveau est plafonné à {_shown(book, 'status.level_cap')}, sans titre "
            "individuel ni cryptoactif, tant que le profil n'est pas complété.",
            fact_ids=["status.level_cap"],
        )
    )
    todo = list(profile.missing_info or []) or list(missing) or ["le profil"]
    book.add("status.todo", "Informations à compléter", ", ".join(todo), "texte", dataset="profil client")
    out["what_would_change"].append(
        Statement(text_fr=f"Compléter : {_shown(book, 'status.todo')}.", fact_ids=["status.todo"], label="HYPOTHESE")
    )


def _with_status(expl: Explanation, status: dict[str, list[Statement]]) -> Explanation:
    """Raison du statut : en tête de « pourquoi », juste après le niveau dans « données », en fin ailleurs."""
    return Explanation(
        data_used=expl.data_used[:1] + status["data_used"] + expl.data_used[1:],
        why=status["why"] + expl.why,
        limits=expl.limits + status["limits"],
        what_would_change=expl.what_would_change + status["what_would_change"],
    )


def _grounded(
    build: _Build, draft: _Draft, checks, verdicts: dict[str, str]
) -> tuple[Explanation, dict | None, list[str]]:
    """Ancrage Guardrails énoncé par énoncé, contre les faits cités, la décision et les fiches de méthode.

    Un énoncé reformulé non ancré reprend son gabarit, revérifié ; un gabarit non ancré est signalé dans le rapport.
    """
    book, options = build.book, build.options
    guardrail_id, guardrail_version, docs = options.guardrail_id, options.guardrail_version, options.grounding_docs
    with book.step(
        "explainability",
        tool="bedrock.apply_guardrail",
        inputs={"guardrail_id": guardrail_id, "guardrail_version": guardrail_version, "docs": [k for k, _ in docs]},
    ) as ev:
        context = grounding_context(book, checks, verdicts)
        grounding = grounding_check(
            book, draft.explanation, guardrail_id, guardrail_version, context=context, docs=docs
        )
        expl, reverted = keep_grounded(draft.explanation, draft.template, grounding)
        report = draft.report
        if reverted:
            again = grounding_check(
                book, expl, guardrail_id, guardrail_version, context=context, docs=docs, only=set(reverted)
            )
            grounding = merge_grounding(grounding, again)
            report = report + [f"{sec}[{i}] reformulation non ancrée : gabarit conservé" for sec, i in reverted]
        report = report + [
            f"{r['section']}[{r['index']}] sous le seuil d'ancrage (score {r.get('score')})"
            for r in grounding["statements"]
            if r.get("action") == "GUARDRAIL_INTERVENED"
        ]
        ev.output_summary = (
            f"{grounding['checked']} énoncés vérifiés, {grounding['below']} sous le seuil, "
            f"{grounding['errors']} en erreur, {len(reverted)} gabarits remis"
        )
    return expl, grounding, report


def _style_counterfactuals(debate: _Debate) -> list[tuple[Counterfactual, Statement]]:
    """Style un cran plus prudent, et un cran plus offensif si la gouvernance l'admet : même calcul (mêmes
    indicateurs, mêmes données), autre style ; seule la part actions visée et le risque minimisé sont rapportés."""
    from alphaforge.finance.strategy import STYLES, StyleInputs, apply_strategy

    build, strat = debate.build, debate.strat
    book = build.book
    pairs: list[tuple[Counterfactual, Statement]] = []
    cur = strat.decision.style
    i = STYLES.index(cur)
    base_in = build.options.style_inputs or StyleInputs()
    for label, j in (("down", i - 1), ("up", i + 1)):
        if not 0 <= j < len(STYLES):
            continue
        alt_inputs = StyleInputs(**{**base_in.__dict__, "explicit_preference": STYLES[j]})
        scratch = FactBook(f"{book.decision_id}-cf-style-{label}")
        alt = apply_strategy(
            debate.mandate.comp,
            build.profile,
            build.as_of,
            scratch,
            inputs=alt_inputs,
            candidates=strat.candidates,
            protect=build.protect,
        )
        if alt.decision.style == cur:  # montée refusée par la gouvernance : pas de contrefactuel
            continue
        rr = optimize(alt.policy, build.as_of)
        if rr.status != "optimal" or rr.risk_value is None:
            continue
        pairs.append(_style_counterfactual(book, label, alt, rr))
    return pairs


def _style_counterfactual(
    book: FactBook, label: str, alt: StrategyResult, rr: OptimizationResult
) -> tuple[Counterfactual, Statement]:
    """Faits et énoncé d'un style testé : style, risque minimisé, titres retenus et part actions visée."""
    from .explain import STYLE_FR

    f_style = book.add(
        f"cf.style.{label}.style",
        "Style testé",
        STYLE_FR[alt.decision.style],
        "texte",
        dataset="contrefactuel",
        processing=alt.decision.style,
    )
    f_risk = book.add(
        f"cf.style.{label}.risk",
        f"Risque minimisé avec le style {STYLE_FR[alt.decision.style]}",
        rr.risk_value,
        "%",
        dataset="optimizer:F2",
        processing="même calcul de l'étape 0, autre style ; réoptimisation, mêmes données",
    )
    f_n = book.add(
        f"cf.style.{label}.n_titres",
        "Titres retenus avec le style testé",
        len(alt.shortlist),
        "titres",
        dataset="contrefactuel",
    )
    ids = [f_style, f_risk, f_n]
    text = (
        f"Avec un style {STYLE_FR[alt.decision.style]}, le risque minimisé serait de {fmt(rr.risk_value, '%')} "
        f"avec {len(alt.shortlist)} titres retenus"
    )
    if alt.plan.growth_floor is not None:
        f_g = book.add(
            f"cf.style.{label}.band_target",
            "Part actions visée avec le style testé",
            alt.plan.growth_floor,
            "%",
            dataset="contrefactuel",
        )
        ids.append(f_g)
        text += f" et une part actions visée de {fmt(alt.plan.growth_floor, '%')}"
    change = f"Si le style était {STYLE_FR[alt.decision.style]}"
    return Counterfactual(change_fr=change, result_fact_ids=[f_risk]), Statement(
        text_fr=text + ".", fact_ids=ids, label="HYPOTHESE"
    )


def _final_strategy_facts(book: FactBook, strat, final_policy: PolicySpec) -> dict:
    """Valeurs de l'étape 0 dans le mandat FINAL (après les amendements des lentilles et le clamp) : l'explication
    cite ces Facts-là, jamais les valeurs d'avant le débat."""
    lims = {lim.rule_id: lim for lim in final_policy.limits if lim.rule_id.startswith("strat.")}
    out: dict = {"band_target": None, "floors": {}, "clamped": []}
    with book.step("s0b.final", tool="strategy.final", inputs={"n_strat_limits": len(lims)}):
        g = lims.get("strat.growth_floor")
        if g is not None and g.min is not None:
            if strat.plan.growth_floor is not None and abs(g.min - strat.plan.growth_floor) < 1e-9:
                out["band_target"] = "strat.band_target"
            else:
                out["band_target"] = book.add(
                    "strat.final.band_target",
                    "part actions visée après le débat",
                    g.min,
                    "%",
                    dataset="mandat final",
                    status="HYPOTHESE",
                    processing="plancher strat.growth_floor abaissé par la prudence",
                )
                out["clamped"].append(out["band_target"])
        for t, f0 in strat.plan.floors.items():
            lim = lims.get(f"strat.floor.{t}")
            if lim is None or lim.min is None:
                out["clamped"].append(
                    book.add(
                        f"strat.final.removed.{t}",
                        f"plancher de {t} retiré au débat",
                        t,
                        "texte",
                        dataset="mandat final",
                        status="HYPOTHESE",
                    )
                )
                continue
            if abs(lim.min - f0) < 1e-9:
                out["floors"][t] = f"strat.floor.{t}"
            else:
                fid = book.add(
                    f"strat.final.floor.{t}",
                    f"plancher du satellite {t} après le débat",
                    lim.min,
                    "%",
                    dataset="mandat final",
                    status="HYPOTHESE",
                    processing="plancher abaissé par la prudence (clamp)",
                )
                out["floors"][t] = fid
                out["clamped"].append(fid)
    return out
