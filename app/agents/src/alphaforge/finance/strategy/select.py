"""Étape 0, orchestration : style → candidats → classement → sélection → limites ``strat.*`` → faisabilité.

``apply_strategy`` part du mandat de base de F1 (``comp.policy``) et rend un mandat enrichi de limites
``strat.*`` non bloquantes et d'exclusions de sélection. La faisabilité se vérifie avec l'optimiseur PUIS le
Judge : la stratégie ne doit introduire aucune violation bloquante que le mandat de base n'avait pas. En cas
d'échec, le repli (``rules.degrade_steps``) s'arrête au premier palier acceptable ; chaque palier est un Fact.
Chaque nombre est un Fact ``strat.*`` qui cite ``strategy.yaml@<version>`` ; aucun ne vient d'un LLM.
SIMULATION ÉDUCATIVE SEULEMENT.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from alphaforge.finance.contracts import PolicySpec
from alphaforge.finance.observability.telemetry import traced_tool
from alphaforge.finance.policy.models import CompileResult
from alphaforge.finance.portfolio.judge import check
from alphaforge.finance.portfolio.optimizer import optimize

from .config import StrategyConfig, load_strategy
from .rules import (
    Candidate,
    Plan,
    Ranked,
    apply_to_policy,
    degrade_steps,
    interest_asset_floors,
    rank_scores,
    sector_caps,
    shortlist,
)
from .rules import stock_floors as _stock_floors
from .scoring import compute_candidates
from .style import StyleDecision, StyleInputs, band_target, derive_style, limit

FEATURE_UNITS = {
    "vol": "%",
    "beta": "ratio",
    "corr_core": "ratio",
    "mdd_long": "%",
    "dividend_yield": "%",
    "liquidity_cad": "CAD",
    "momentum": "%",
}
FEATURE_LABELS = {
    "vol": "volatilité hebdomadaire annualisée sur 5 ans",
    "beta": "bêta quotidien sur 2 ans contre l'indice local",
    "corr_core": "corrélation hebdomadaire au cœur XIU.TO + SPY, en CAD",
    "mdd_long": "baisse maximale sur l'historique long raccordé",
    "dividend_yield": "rendement du dividende sur 12 mois",
    "liquidity_cad": "valeur médiane échangée par séance sur 63 séances",
    "momentum": "momentum sur douze mois hors dernier mois (sensibilité seulement)",
}


@dataclass
class StrategyResult:
    policy: PolicySpec  # mandat retenu (avec stratégie, ou de base si repli complet)
    base_policy: PolicySpec
    decision: StyleDecision
    candidates: list[Candidate]
    ranking: list[Ranked]
    shortlist: list[str]
    plan: Plan  # plan final, après repli éventuel
    fallback: list[str]
    applied: bool
    risk_cost: float | None  # CVaR (stratégie) − CVaR (base), mesure de l'objectif ; jamais un rendement
    version: str
    sha256: str
    notes: list[str] = field(default_factory=list)
    fact_ids: dict[str, list[str]] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "style": self.decision.style,
            "from_level": self.decision.from_level,
            "applied": self.applied,
            "shortlist": self.shortlist,
            "growth_floor": self.plan.growth_floor,
            "floors": self.plan.floors,
            "sector_caps": {k: v[0] for k, v in self.plan.sector_caps.items()},
            "fallback": self.fallback,
            "version": self.version,
        }


def _employer_tickers(profile: Any) -> set[str]:
    out: set[str] = set()
    if profile is None:
        return out
    inc = getattr(profile, "income", None)
    if inc is not None and getattr(inc, "employer_ticker", None):
        out.add(inc.employer_ticker)
    for e in getattr(profile, "employer_equity", None) or []:
        t = getattr(e, "ticker", None)
        if t:
            out.add(t)
    return out


class _Feasibility:
    """optimize puis Judge ; mémorise les résultats par empreinte du mandat."""

    def __init__(self, base: PolicySpec, as_of):
        self.as_of = as_of
        self.cache: dict[str, tuple[bool, Any, set[str]]] = {}
        ok, r, viol = self._run(base)
        self.base_result, self.base_viol = r, viol

    def _run(self, p: PolicySpec):
        r = optimize(p, self.as_of)
        if r.status != "optimal":
            return False, r, {"optimiseur:" + r.status}
        rep = check(r.weights, p, self.as_of, trace_id="strat-feasibility")
        return True, r, set(rep.blocking_violations)

    def __call__(self, p: PolicySpec) -> tuple[bool, Any, set[str]]:
        k = p.model_dump_json(exclude={"created_utc", "policy_id"})
        if k not in self.cache:
            ok, r, viol = self._run(p)
            self.cache[k] = (ok and viol <= self.base_viol, r, viol - self.base_viol)
        return self.cache[k]


def _pct(x: float | None) -> float | None:
    return None if x is None else round(float(x), 6)


@dataclass(frozen=True)
class _Fact:
    """Un Fact ``strat.*`` à écrire : sa source est ``strategy.yaml@<version>#<path>``."""

    key: str
    label: str
    value: Any
    unit: str
    path: str
    status: str = "HYPOTHESE"
    processing: str | None = None
    currency: str | None = None


@dataclass
class _Run:
    """Une exécution de l'étape 0 : le mandat compilé, les entrées, la config, et le FactBook où chaque nombre
    devient un Fact rangé dans son groupe (``StrategyResult.fact_ids``)."""

    comp: CompileResult
    inputs: StyleInputs
    cfg: StrategyConfig
    as_of: date
    book: Any
    ids: dict[str, list[str]] = field(default_factory=lambda: {"rule": [], "band": [], "ranking": [], "result": []})

    @property
    def base(self) -> PolicySpec:
        return self.comp.policy

    def add(self, group: str, fact: _Fact) -> str:
        fid = self.book.add(
            fact.key,
            fact.label,
            fact.value,
            fact.unit,
            dataset=f"{self.cfg.ref}#{fact.path}",
            status=fact.status,
            processing=fact.processing,
            as_of=self.as_of,
            currency=fact.currency,
        )
        self.ids[group].append(fid)
        return fid


@dataclass(frozen=True)
class _Outcome:
    """Mandat retenu après la vérification de faisabilité et le repli éventuel."""

    policy: PolicySpec
    plan: Plan
    fallback: list[str]
    applied: bool
    base_risk: float | None  # risque minimisé du mandat de base
    risk_cost: float | None


@traced_tool(
    "strategy.select",
    lambda r: {
        "style": r.decision.style,
        "applied": r.applied,
        "n_shortlist": len(r.shortlist),
        "n_fallback": len(r.fallback),
    },
)
def apply_strategy(  # noqa: PLR0913 - signature publique : debate/pipeline.py et les tests passent ces options par mot-clé
    comp: CompileResult,
    profile: Any,
    as_of: date,
    book,
    *,
    inputs: StyleInputs | None = None,
    preference: str | None = None,
    protect: Sequence[str] = (),
    cfg: StrategyConfig | None = None,
    candidates: list[Candidate] | None = None,
) -> StrategyResult:
    cfg = cfg or load_strategy()
    inputs = _with_preference(inputs or StyleInputs(), preference)
    base = comp.policy
    if base is None:
        raise ValueError("apply_strategy : aucun mandat (statut incomplet ou protection)")
    run = _Run(comp, inputs, cfg, as_of, book)

    with book.step(
        "s0b.strategy", tool="strategy.derive_style", inputs={"level": comp.level, "preference": preference}
    ):
        d = derive_style(comp, inputs, profile=profile, cfg=cfg)
        _record_style(run, d)
        _record_guardrails(run, d)
        _record_band(run, d)

    with book.step("s0b.scoring", tool="strategy.score_stocks", inputs={"n_universe": len(base.universe)}):
        cands = candidates if candidates is not None else compute_candidates(base, as_of, cfg)
        ranked = rank_scores(cands, d.style, inputs, base.excluded, cfg, employer_tickers=_employer_tickers(profile))
        _record_ranking(run, cands, ranked, d.style)

    with book.step("s0b.select", tool="strategy.select", inputs={"style": d.style, "k": d.k}):
        plan, notes = _build_plan(run, d, ranked, cands, protect)

    n_limits = len(plan.floors) + len(plan.sector_caps)
    with book.step("s0b.feasibility", tool="optimize+check", inputs={"n_limits": n_limits}):
        outcome = _settle(run, plan)
        _record_outcome(run, outcome)

    return StrategyResult(
        policy=outcome.policy,
        base_policy=base,
        decision=d,
        candidates=cands,
        ranking=ranked,
        shortlist=[t for t in outcome.plan.floors if t not in outcome.plan.interest_floors],
        plan=outcome.plan,
        fallback=outcome.fallback,
        applied=outcome.applied,
        risk_cost=outcome.risk_cost,
        version=cfg.version,
        sha256=cfg.sha256,
        notes=notes,
        fact_ids=run.ids,
    )


def _with_preference(inputs: StyleInputs, preference: str | None) -> StyleInputs:
    """Le paramètre ``preference`` ne s'applique que si les entrées n'en portent pas déjà une."""
    if preference and not inputs.explicit_preference:
        return StyleInputs(**{**inputs.__dict__, "explicit_preference": preference})
    return inputs


# --------------------------------------------------------------------------- s0b.strategy : style et bande


def _record_style(run: _Run, d: StyleDecision) -> None:
    """Facts du style retenu, du style tiré du niveau et de la préférence."""
    shift = f"niveau {run.comp.level} → {d.from_level}, décalage {d.shift:+d}"
    run.add(
        "rule",
        _Fact(
            "strat.style",
            "style de composition retenu (étape 0)",
            d.style,
            "texte",
            path="level_to_style",
            processing=shift,
        ),
    )
    run.add(
        "rule",
        _Fact(
            "strat.style_from_level",
            "style tiré du niveau (convention d'équipe)",
            d.from_level,
            "texte",
            path="level_to_style",
        ),
    )
    run.add(
        "rule",
        _Fact(
            "strat.preference",
            "préférence de style",
            d.preference or "aucune",
            "texte",
            path="preference",
            processing=d.preference_source,
        ),
    )


def _record_guardrails(run: _Run, d: StyleDecision) -> None:
    """Facts des montées refusées, des contradictions et des signaux de comportement (garde-fous)."""
    for i, r in enumerate(d.refused):
        run.add(
            "rule",
            _Fact(f"strat.preference_refused.{i}", "préférence refusée ou plafonnée", r, "texte", path="preference"),
        )
    for i, c in enumerate(d.contradictions):
        run.add(
            "rule",
            _Fact(
                f"strat.contradiction.{i}",
                "contradiction réglée par la réponse la plus prudente",
                c,
                "texte",
                path="preference",
            ),
        )
    for f in d.flags.active():
        label = f"signal de comportement : {f} (garde-fou, jamais une allocation)"
        run.add(
            "rule",
            _Fact(f"strat.flag.{f}", label, " ; ".join(d.flags.evidence.get(f, [])), "texte", path="profile_codes"),
        )


def _record_band(run: _Run, d: StyleDecision) -> None:
    """Facts de la bande d'actions (e_min, e_cap, π) et du nombre de titres visé."""
    comp = run.comp
    g_lim = limit(comp, "alloc.growth")
    run.add(
        "band",
        _Fact(
            "strat.e_min",
            "part actions minimale du niveau",
            _pct(g_lim.min if g_lim else None),
            "%",
            path="band",
            status="FAIT",
            processing="risk_levels.yaml#levels.<niveau>.equity",
        ),
    )
    run.add(
        "band",
        _Fact(
            "strat.e_cap",
            "part actions maximale (règle des dollars)",
            _pct(comp.e_cap),
            "%",
            path="band",
            status="FAIT",
            processing="risk_levels.yaml#dollar_rule.e_cap",
        ),
    )
    run.add(
        "band",
        _Fact(
            "strat.pi",
            "position visée dans la bande d'actions (0 = plancher, 1 = plafond)",
            round(d.pi, 4),
            "ratio",
            path="band",
            processing=d.pi_reason,
        ),
    )
    run.add(
        "band", _Fact("strat.K", "nombre de titres individuels visé", d.k, "titres", path="k", processing=d.k_reason)
    )


# --------------------------------------------------------------------------- s0b.scoring : indicateurs et classement


def _record_ranking(run: _Run, cands: list[Candidate], ranked: list[Ranked], style: str) -> None:
    """Facts du classement : indicateurs par titre, rangs au seul momentum, score, rang et inéligibilité."""
    run.add(
        "ranking",
        _Fact("strat.n_candidates", "titres individuels classés", len(cands), "titres", path="weights", status="FAIT"),
    )
    _record_features(run, cands)
    _record_momentum_ranks(run, cands)
    for r in ranked:
        run.add(
            "ranking",
            _Fact(
                f"strat.score.{r.ticker}",
                f"score du style {style} ({r.ticker})",
                round(r.score, 6),
                "ratio",
                path=f"weights.{style}",
                processing="rangs en percentile pondérés + bonus",
            ),
        )
        run.add(
            "ranking",
            _Fact(
                f"strat.rank.{r.ticker}",
                f"rang de {r.ticker} sur {len(ranked)}",
                r.rank,
                "rang",
                path=f"weights.{style}",
            ),
        )
        if not r.eligible:
            run.add(
                "ranking",
                _Fact(
                    f"strat.ineligible.{r.ticker}",
                    f"{r.ticker} écarté",
                    " ; ".join(r.reasons),
                    "texte",
                    path="eligibility",
                ),
            )


def _feature_processing(c: Candidate, feature: str) -> str | None:
    """Provenance affichée d'un indicateur : source de la baisse longue, indice du bêta."""
    if feature == "mdd_long":
        return c.details.get("mdd_long_source")
    if feature == "beta":
        return c.details.get("beta_index")
    return None


def _record_features(run: _Run, cands: list[Candidate]) -> None:
    for c in cands:
        for f, v in c.features.items():
            if f not in FEATURE_UNITS or v is None:
                continue
            run.add(
                "ranking",
                _Fact(
                    f"strat.feat.{c.ticker}.{f}",
                    f"{FEATURE_LABELS[f]} ({c.ticker})",
                    round(float(v), 6),
                    FEATURE_UNITS[f],
                    path="features",
                    status=c.status.get(f, "HYPOTHESE"),
                    processing=_feature_processing(c, f),
                    currency="CAD" if f == "liquidity_cad" else None,
                ),
            )


def _record_momentum_ranks(run: _Run, cands: list[Candidate]) -> None:
    """Rang au seul momentum : sensibilité affichée, jamais dans le score."""
    mom = sorted(
        [c for c in cands if c.features.get("momentum") is not None],
        key=lambda c: (-c.features["momentum"], c.ticker),
    )
    for i, c in enumerate(mom):
        run.add(
            "ranking",
            _Fact(
                f"strat.sens.mom.rank.{c.ticker}",
                f"rang de {c.ticker} au seul momentum (sensibilité)",
                i + 1,
                "rang",
                path="features.momentum_months",
            ),
        )


# --------------------------------------------------------------------------- s0b.select : plan de l'étape 0


def _build_plan(
    run: _Run, d: StyleDecision, ranked: list[Ranked], cands: list[Candidate], protect: Sequence[str]
) -> tuple[Plan, list[str]]:
    """Titres retenus et leurs planchers, planchers des intérêts servis par un FNB, plafonds sectoriels, part
    actions visée, exclusions des non retenus."""
    comp, inputs, cfg = run.comp, run.inputs, run.cfg
    by_t = {c.ticker: c for c in cands}
    chosen = shortlist(ranked, d.k, cfg)
    floors, notes = _stock_floors(chosen, comp, d, inputs, cfg)
    sel_tags = {t for tk in floors for t in by_t[tk].tags if t in cfg.sectors.tags}  # titres réellement gardés
    for i, n in enumerate(notes):
        run.add(
            "result",
            _Fact(f"strat.note.{i}", "titre retenu puis retiré (plancher trop petit)", n, "texte", path="floors"),
        )
    # Intérêts servis par un FNB (or → GLD) : ajoutés après les titres, donc retirés en premier par le repli.
    i_floors, i_owner, i_notes = interest_asset_floors(run.base, comp, d, inputs, cfg)
    floors = {**floors, **{t: f for t, f in i_floors.items() if t not in floors}}
    for i, n in enumerate(i_notes):
        run.add(
            "result",
            _Fact(f"strat.interest_note.{i}", "intérêt sans plancher", n, "texte", path="bonus.interest_assets"),
        )
    caps = sector_caps(comp, d.style, inputs, sel_tags, cfg)
    g = band_target(comp, d.pi, cfg)
    excl = _selection_exclusions(run, cands, set(floors) | set(protect))
    plan = Plan(growth_floor=g, floors=floors, sector_caps=caps, exclusions=excl, interest_floors=i_owner)
    return plan, [*notes, *i_notes]


def _selection_exclusions(run: _Run, cands: list[Candidate], keep: set[str]) -> dict[str, str]:
    """``non_shortlisted: exclude`` : les titres non retenus (ni protégés) sortent de l'univers investissable."""
    if run.cfg.non_shortlisted != "exclude":
        return {}
    excluded = run.base.excluded
    return {
        c.ticker: f"strat.shortlist (fact strat.rank.{c.ticker})"
        for c in cands
        if c.ticker not in keep and c.ticker not in excluded
    }


# --------------------------------------------------------------------------- s0b.feasibility : optimiseur, Judge, repli


def _without_small_lines(run: _Run, plan: Plan) -> Plan:
    """Le repli ne crée jamais de ligne sous le minimum en dollars (si le montant est connu)."""
    amount = run.inputs.amount_cad
    if not amount:
        return plan
    lmin = run.cfg.eligibility.min_line_cad
    return replace(plan, floors={t: f for t, f in plan.floors.items() if f * amount >= lmin})


def _settle(run: _Run, plan: Plan) -> _Outcome:
    """Premier palier faisable : le plan, puis les paliers de ``degrade_steps`` ; à défaut, le mandat de base."""
    base, cfg = run.base, run.cfg
    feas = _Feasibility(base, run.as_of)
    fallback: list[str] = []
    policy = apply_to_policy(base, plan, cfg)
    ok, res, new_viol = feas(policy)
    if not ok:
        g_lim = limit(run.comp, "alloc.growth")
        e_min = float(g_lim.min or 0.0) if g_lim else 0.0
        for label, step in degrade_steps(plan, e_min, cfg.band.rounding):
            fallback.append(f"{label} (violations : {sorted(new_viol) or 'optimiseur'})")
            plan = _without_small_lines(run, step)
            policy = apply_to_policy(base, plan, cfg)
            ok, res, new_viol = feas(policy)
            if ok:
                break
    applied = ok and not plan.empty()
    if not ok:
        policy, plan = base, Plan(None, {}, {}, {})
        fallback.append("mandat de base conservé")
    b_res = feas.base_result
    rc = (
        (res.risk_value - b_res.risk_value)
        if (applied and res is not None and res.risk_value is not None and b_res.risk_value is not None)
        else None
    )
    return _Outcome(policy, plan, fallback, applied, b_res.risk_value, rc)


def _record_outcome(run: _Run, out: _Outcome) -> None:
    """Facts du résultat : paliers de repli, plan final, risque minimisé et son écart, application."""
    for i, f in enumerate(out.fallback):
        run.add("result", _Fact(f"strat.fallback.{i}", "palier de repli de l'étape 0", f, "texte", path="floors"))
    _record_plan(run, out.plan)
    if out.base_risk is not None:
        run.add(
            "result",
            _Fact(
                "strat.base_risk",
                "risque minimisé du mandat sans l'étape 0",
                round(out.base_risk, 6),
                "%",
                path="band",
                status="FAIT",
                processing="optimiseur F2 sur le mandat de base (CVaR mensuelle)",
            ),
        )
    if out.risk_cost is not None:
        run.add(
            "result",
            _Fact(
                "strat.risk_cost",
                "écart de risque (CVaR mensuelle) dû au style, sans rendement",
                round(out.risk_cost, 6),
                "%",
                path="band",
                processing="CVaR95 optimisée avec stratégie − sans stratégie",
            ),
        )
    run.add(
        "result",
        _Fact(
            "strat.applied",
            "étape 0 appliquée au mandat",
            "oui" if out.applied else "non",
            "texte",
            path="non_shortlisted",
        ),
    )


def _floor_fact(ticker: str, floor: float, interest: str | None) -> _Fact:
    """Plancher d'un satellite retenu par le classement, ou d'un FNB servant un intérêt de l'investisseur."""
    if interest:
        return _Fact(
            f"strat.floor.{ticker}",
            f"plancher de {ticker} (intérêt {interest})",
            floor,
            "%",
            path="bonus.interest_assets",
            processing="min(φ·plafond de la limite liée, f_abs)",
        )
    return _Fact(
        f"strat.floor.{ticker}",
        f"plancher du satellite {ticker}",
        floor,
        "%",
        path="floors",
        processing="min(φ·min(w_each, w_total/K), f_abs)",
    )


def _record_plan(run: _Run, plan: Plan) -> None:
    """Facts du plan final : part actions visée, planchers des satellites (en dollars si le montant est connu),
    plafonds sectoriels."""
    if plan.growth_floor is not None:
        run.add(
            "result",
            _Fact(
                "strat.band_target",
                "part actions visée, placée par la tolérance et plafonnée par la capacité (hors crypto)",
                plan.growth_floor,
                "%",
                path="band",
                processing="e_min + π·(e_cap − e_min), arrondi au 5 % inférieur",
            ),
        )
    for t, f in plan.floors.items():
        run.add("result", _floor_fact(t, f, plan.interest_floors.get(t)))
    amount = run.inputs.amount_cad
    if amount:
        for t, f in plan.floors.items():
            run.add(
                "result",
                _Fact(
                    f"strat.floor_cad.{t}",
                    f"plancher du satellite {t} en dollars",
                    round(f * amount, 2),
                    "CAD",
                    path="floors",
                    processing="plancher × context.amount_cad",
                    currency="CAD",
                ),
            )
    for tag, (cap, why) in plan.sector_caps.items():
        run.add(
            "result",
            _Fact(
                f"strat.sector_cap.{tag}",
                f"plafond d'exposition {tag} (look-through)",
                cap,
                "%",
                path="sectors",
                processing=why,
            ),
        )
