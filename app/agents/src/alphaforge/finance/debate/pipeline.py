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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from alphaforge.finance.contracts.decision import Counterfactual, Decision, Explanation, Position, Statement
from alphaforge.finance.contracts.policy import Limit, PolicySpec, Selector
from alphaforge.finance.contracts.profile import InvestorProfile
from alphaforge.finance.portfolio.judge import check, framed_alternative
from alphaforge.finance.portfolio.optimizer import optimize

from . import roles
from .explain import grounding_check, rephrase, skeleton
from .facts import FactBook, fmt, sha256_json
from .merge import apply_amendments
from .schemas import LENSES, DebateRound
from .tools import LensContext, lens_evidence

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


def build_portfolio(
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
) -> BuildResult:
    if compile_fn is None:
        from alphaforge.finance.policy import compile_profile as compile_fn
    did = decision_id or f"dec-{profile.profile_id}-v{profile.version}-{uuid.uuid4().hex[:8]}"
    book = FactBook(did)
    lens_fn = roles.llm_lens if mode == "llm" else roles.rules_lens
    adv_fn = roles.llm_advocate if mode == "llm" else roles.rules_advocate

    # ---------------------------------------------------------------- S0 profil → mandat
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
        _emph_ids = [
            book.add(f"emphasis.{k}", f"Poids de la lentille {k}", v, "%", dataset="policy_compiler/emphasis.yaml")
            for k, v in comp.emphasis.items()
        ]
    if comp.decision_kind or comp.policy is None:
        kind = comp.decision_kind or "incomplet"
        expl = Explanation(
            data_used=[
                Statement(text_fr="Profil analysé selon les règles déterministes du mandat.", fact_ids=[level_fid])
            ],
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
            decision_id=did,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            created_utc=datetime.now(UTC),
            kind=kind,
            facts=list(book.facts.values()),
            explanation=expl,
            trace=book.trace,
        )
        return BuildResult(decision=d, policy=comp.policy)

    base = comp.policy
    feas_cache: dict[str, bool] = {}

    def feasible(p: PolicySpec) -> bool:
        k = sha256_json(p.model_dump(mode="json", exclude={"created_utc", "policy_id"}))
        if k not in feas_cache:
            feas_cache[k] = optimize(p, as_of).status == "optimal"
        return feas_cache[k]

    # ---------------------------------------------------------------- S0b étape 0 : style et sélection
    strat = None
    if strategy:
        from alphaforge.finance.strategy import apply_strategy

        try:
            strat = apply_strategy(
                comp,
                profile,
                as_of,
                book,
                inputs=style_inputs,
                preference=style_preference,
                protect=[request.ticker] if request else [],
            )
            base = strat.policy
        except Exception as exc:  # l'étape 0 ne fait jamais échouer la décision : repli sur le mandat de base
            strat = None
            with book.step("s0b.strategy", tool="strategy.select", inputs={"error": type(exc).__name__}) as ev:
                ev.status = "erreur"
                ev.message = f"{type(exc).__name__}: {exc}"[:300]
                book.add("strat.error", "étape 0 abandonnée : mandat de base conservé", type(exc).__name__, "texte",
                         dataset="finance/strategy", status="HYPOTHESE")

    versions = {"policy": "risk_levels@0.2.0", "profile": f"{profile.profile_id}@{profile.version}"}
    versions["strategy"] = f"strategy.yaml@{strat.version}" if strat else "off"

    # ---------------------------------------------------------------- Tour 1
    with book.step("s2.optimize", tool="optimize", inputs={"round": 1}):
        r1 = optimize(base, as_of)
        if r1.status != "optimal":
            raise RuntimeError(f"mandat infaisable : {r1.infeasible_rules}")
        book.data_version = r1.data_version
        # Lot E, OKF général : avec le magasin OKF (OkfMarketStore), la version des données couvre aussi les
        # (clé, ETag) des fondamentaux de general/societes/, lus ici une fois pour toute la décision. Jamais les
        # actualités : une nouvelle ne change ni le mandat ni la version des données.
        okf_market = getattr(evidence_fn, "__self__", evidence_fn)
        if hasattr(okf_market, "inputs"):
            book.data_version = okf_market.data_version(book.data_version)
        r1_ids, r1_active = _opt_facts(book, "r1", r1, base)
    ctx1 = LensContext(profile, base, r1.weights, as_of, book, label="r1", evidence_fn=evidence_fn)
    ev1 = {lens: lens_evidence(lens, ctx1) for lens in LENSES}
    with book.step("a3", tool="advocate", inputs={"round": 1}):
        brief1 = adv_fn(ctx1, r1_ids + ev1["risk"], 1, None, versions)

    def run_lens(lens, ctx, ev, rnd, brief):
        return lens_fn(lens, ctx, ev, rnd, brief, comp.emphasis.get(lens, 0.25), versions)

    with ThreadPoolExecutor(max_workers=4) as ex:  # tour 1 : les lentilles ne voient pas le plaidoyer
        reps1 = list(ex.map(lambda lens: run_lens(lens, ctx1, ev1[lens], 1, None), LENSES))
    with book.step("s3.merge", tool="apply_amendments", inputs={"round": 1}):
        pol2, log1 = apply_amendments(base, reps1, comp.emphasis, set(book.facts), feasible=feasible)
    round1 = DebateRound(
        round=1, candidate_fact_ids=r1_ids, advocate=brief1, lens_reports=reps1, emphasis=comp.emphasis, decisions=log1
    )

    # ---------------------------------------------------------------- Tour 2
    changed = any(a.status == "applique" and a.amendment.kind != "flag_only" for a in log1)
    with book.step("s2.optimize", tool="optimize", inputs={"round": 2, "policy_changed": changed}):
        r2 = optimize(pol2, as_of) if changed else r1
        r2_ids, r2_active = _opt_facts(book, "r2", r2, pol2)
    ctx2 = LensContext(profile, pol2, r2.weights, as_of, book, label="r2", evidence_fn=evidence_fn)
    ev2 = {lens: lens_evidence(lens, ctx2) for lens in LENSES}
    with book.step("a3", tool="advocate", inputs={"round": 2}):
        brief2 = adv_fn(ctx2, r2_ids + ev2["risk"], 2, reps1, versions)
    with ThreadPoolExecutor(max_workers=4) as ex:
        reps2 = list(ex.map(lambda lens: run_lens(lens, ctx2, ev2[lens], 2, brief2), LENSES))
    verdicts = {}
    for lens, rep in zip(LENSES, reps2, strict=True):
        applied = [a for a in log1 if a.lens == lens and a.status == "applique" and a.amendment.kind != "flag_only"]
        verdicts[lens] = (
            "objection_maintenue"
            if (rep.objections or rep.amendments)
            else "objection_satisfaite"
            if applied
            else "soutien"
        )
    round2 = DebateRound(
        round=2,
        candidate_fact_ids=r2_ids,
        advocate=brief2,
        lens_reports=reps2,
        emphasis=comp.emphasis,
        verdicts=verdicts,
    )

    # ---------------------------------------------------------------- Demande précise : avec / sans
    req_fids: list[str] = []
    final_w, final_policy = r2.weights, pol2
    strat_final = _final_strategy_facts(book, strat, final_policy) if strat is not None else None
    kind = "proposition"
    if request is not None:
        w_req = request.as_weight(profile.investable_wealth)
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
            target = {**{a: x * (1 - w_req) for a, x in r2.weights.items()}, request.ticker: w_req}
        ctxq = LensContext(profile, pol2, target, as_of, book, label="demande")
        req_fids += lens_evidence("risk", ctxq)
        with book.step("judge", tool="check", inputs={"variant": "demande"}):
            repq = check(target, pol2, as_of, trace_id=f"{book.current}:demande")
            req_fids += book.absorb_report(repq)
        if repq.approved:
            final_w = target
        else:
            kind = "refus_encadre"
            with book.step("judge", tool="framed_alternative"):
                alt, rep_alt, method = framed_alternative(target, pol2, as_of)
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
            if alt is not None:
                final_w = alt

    # ---------------------------------------------------------------- Judge final (déterministe)
    with book.step("judge", tool="check", inputs={"variant": "final"}):
        rep = check(final_w, final_policy, as_of, trace_id=f"{book.current}:final")
        book.absorb_report(rep)
    if not rep.approved:
        kind = "refus_encadre"

    # ---------------------------------------------------------------- Contrefactuels recalculés
    cf_stmts, cfs = [], []
    with book.step("counterfactuals", tool="optimize"):
        cands = []
        by_id = {lim.rule_id: lim for lim in final_policy.limits}
        for key, dual in r2.duals.items():
            rid, _, side = key.partition(":")
            lim = by_id.get(rid)
            if not r2.active.get(key) or lim is None or rid.startswith(("request.", "strat.")):
                continue
            if side == "max" and lim.max:  # un plafond à 0 (exclusion) n'est pas un levier
                cands.append((dual, rid, side, lim))
            elif side == "min" and lim.min:
                cands.append((dual, rid, side, lim))
        if cands:
            _, rid, side, lim = max(cands, key=lambda c: c[0])
            relaxed = final_policy.model_copy(deep=True)
            l2 = next(lim for lim in relaxed.limits if lim.rule_id == rid)
            if side == "max":
                old, new = l2.max, (l2.max * 1.25 if l2.kind == "risk" else min(l2.max + 0.05, 1.0))
                l2.max = new
            else:
                old, new = l2.min, max(l2.min - 0.10, 0.0)
                l2.min = new
            rr = optimize(PolicySpec.model_validate(relaxed.model_dump()), as_of)
            if rr.status == "optimal" and rr.risk_value is not None:
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
                f_r0 = r2_ids[0] if r2_ids else f_r
                cfs.append(
                    Counterfactual(
                        change_fr=f"Si la borne « {lab} » passait de {fmt(old, '%')} à {fmt(new, '%')}",
                        result_fact_ids=[f_r],
                    )
                )
                cf_stmts.append(
                    Statement(
                        text_fr=f"Si la borne « {lab} » passait de {fmt(old, '%')} à {fmt(new, '%')}, "
                        f"le risque minimisé passerait de {fmt(book.facts[f_r0].value, '%')} "
                        f"à {fmt(rr.risk_value, '%')}.",
                        fact_ids=[f_old, f_new, f_r0, f_r],
                    )
                )
        if request is not None and "demande.cvar_m" in book.facts:
            cfs.append(
                Counterfactual(
                    change_fr=f"Avec la demande sur {request.ticker} telle quelle",
                    result_fact_ids=[f for f in ("demande.cvar_m", "demande.mdd") if f in book.facts],
                )
            )
            cf_stmts.append(
                Statement(
                    text_fr=f"Avec la demande sur {request.ticker} telle quelle, la CVaR mensuelle "
                    f"serait de {fmt(book.facts['demande.cvar_m'].value, '%')}.",
                    fact_ids=["demande.cvar_m"],
                )
            )

        if strat is not None and strat.applied:
            cf_stmts += _style_counterfactuals(
                book, comp, profile, as_of, strat, style_inputs, cfs, protect=[request.ticker] if request else []
            )
            if "strat.base_risk" in book.facts:
                cfs.append(
                    Counterfactual(
                        change_fr="Sans le style ni la sélection (mandat de base)", result_fact_ids=["strat.base_risk"]
                    )
                )
                cf_stmts.append(
                    Statement(
                        text_fr="Sans le style ni la sélection (mandat de base, avant les lentilles), le risque "
                        "minimisé serait de "
                        f"{fmt(book.facts['strat.base_risk'].value, '%')}.",
                        fact_ids=["strat.base_risk"],
                        label="HYPOTHESE",
                    )
                )

    # ---------------------------------------------------------------- Explication
    expl = skeleton(
        book,
        kind=kind,
        level_fid=level_fid,
        cand="r2",
        active_fids=r2_active,
        applied=log1,
        counterfactual_stmts=cf_stmts,
        request_fids=req_fids,
        limits_extra=[
            f"Objection maintenue par la lentille « {lens} » au second tour."
            for lens, v in verdicts.items()
            if v == "objection_maintenue"
        ],
        strategy=strat_final,
    )
    # Scénarios probabilistes (outil scenario_risk) : par défaut seulement avec une limite PROB_LOSS, voir scenarios.py
    from .scenarios import ScenarioContext, attach_scenarios

    scenario_context = ScenarioContext(final_w, final_policy, profile, mode, scenario_tool)
    expl = attach_scenarios(book, expl, scenario_context, enabled=scenarios)
    report: list[str] = []
    if rephrase_explanation if rephrase_explanation is not None else mode == "llm":
        try:
            expl, report = rephrase(book, expl, profile.knowledge_level)
        except Exception as exc:  # repli : le gabarit reste
            report = [f"reformulation abandonnée : {type(exc).__name__}"]
    grounding = grounding_check(book, expl, guardrail_id, guardrail_version) if guardrail_id else None

    singles = set(strat.shortlist) | {c.ticker for c in strat.candidates} if strat else set()
    positions = [
        Position(
            asset_id=a,
            weight=w,
            role="satellite"
            if (request and a == request.ticker) or a in singles or (strat is not None and a in base.loss_bounds)
            else "coeur",
            rationale_fact_ids=[
                f
                for f in (f"r2.rc.{a}", f"strat.rank.{a}", f"strat.score.{a}", f"strat.floor.{a}")
                if f in book.facts
            ],
        )
        for a, w in sorted(final_w.items(), key=lambda kv: -kv[1])
        if w > 1e-4
    ]
    tot = sum(p.weight for p in positions)
    positions = [p.model_copy(update={"weight": p.weight / tot}) for p in positions]
    if abs(sum(p.weight for p in positions) - 1) > 1e-9:  # arrondi flottant résiduel
        positions[0] = positions[0].model_copy(
            update={"weight": positions[0].weight + 1 - sum(p.weight for p in positions)}
        )

    decision = Decision(
        decision_id=did,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        created_utc=datetime.now(UTC),
        kind=kind,
        positions=positions if kind in ("proposition", "refus_encadre") else [],
        facts=list(book.facts.values()),
        constraints=list(rep.checks),
        counterfactuals=cfs,
        explanation=expl,
        trace=book.trace,
    )
    return BuildResult(
        decision=decision,
        rounds=[round1, round2],
        policy=final_policy,
        explanation_report=report,
        grounding=grounding,
        strategy=strat,
    )


def _style_counterfactuals(book, comp, profile, as_of, strat, style_inputs, cfs, protect=()) -> list[Statement]:
    """Style un cran plus prudent, et un cran plus offensif si la gouvernance l'admet : même calcul (mêmes
    indicateurs, mêmes données), autre style ; seule la part actions visée et le risque minimisé sont rapportés."""
    from alphaforge.finance.strategy import STYLES, StyleInputs, apply_strategy

    from .explain import STYLE_FR

    stmts: list[Statement] = []
    cur = strat.decision.style
    i = STYLES.index(cur)
    base_in = style_inputs or StyleInputs()
    for label, j in (("down", i - 1), ("up", i + 1)):
        if not 0 <= j < len(STYLES):
            continue
        alt_inputs = StyleInputs(**{**base_in.__dict__, "explicit_preference": STYLES[j]})
        scratch = FactBook(f"{book.decision_id}-cf-style-{label}")
        alt = apply_strategy(comp, profile, as_of, scratch, inputs=alt_inputs, candidates=strat.candidates,
                             protect=list(protect))
        if alt.decision.style == cur:  # montée refusée par la gouvernance : pas de contrefactuel
            continue
        rr = optimize(alt.policy, as_of)
        if rr.status != "optimal" or rr.risk_value is None:
            continue
        f_style = book.add(
            f"cf.style.{label}.style", "Style testé", alt.decision.style, "texte", dataset="contrefactuel"
        )
        f_risk = book.add(
            f"cf.style.{label}.risk",
            f"Risque minimisé avec le style {alt.decision.style}",
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
            f_g = book.add(f"cf.style.{label}.band_target", "Part actions visée avec le style testé",
                           alt.plan.growth_floor, "%", dataset="contrefactuel")
            ids.append(f_g)
            text += f" et une part actions visée de {fmt(alt.plan.growth_floor, '%')}"
        change = f"Si le style était {STYLE_FR[alt.decision.style]}"
        cfs.append(Counterfactual(change_fr=change, result_fact_ids=[f_risk]))
        stmts.append(Statement(text_fr=text + ".", fact_ids=ids, label="HYPOTHESE"))
    return stmts


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
                out["band_target"] = book.add("strat.final.band_target", "part actions visée après le débat", g.min,
                                              "%", dataset="mandat final", status="HYPOTHESE",
                                              processing="plancher strat.growth_floor abaissé par la prudence")
                out["clamped"].append(out["band_target"])
        for t, f0 in strat.plan.floors.items():
            lim = lims.get(f"strat.floor.{t}")
            if lim is None or lim.min is None:
                out["clamped"].append(book.add(f"strat.final.removed.{t}", f"plancher de {t} retiré au débat", t,
                                               "texte", dataset="mandat final", status="HYPOTHESE"))
                continue
            if abs(lim.min - f0) < 1e-9:
                out["floors"][t] = f"strat.floor.{t}"
            else:
                fid = book.add(f"strat.final.floor.{t}", f"plancher du satellite {t} après le débat", lim.min, "%",
                               dataset="mandat final", status="HYPOTHESE",
                               processing="plancher abaissé par la prudence (clamp)")
                out["floors"][t] = fid
                out["clamped"].append(fid)
    return out
