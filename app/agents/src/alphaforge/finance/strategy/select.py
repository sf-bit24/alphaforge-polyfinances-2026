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
from .rules import Candidate, Plan, Ranked, apply_to_policy, degrade_steps, rank_scores, sector_caps, shortlist
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


@traced_tool(
    "strategy.select",
    lambda r: {
        "style": r.decision.style,
        "applied": r.applied,
        "n_shortlist": len(r.shortlist),
        "n_fallback": len(r.fallback),
    },
)
def apply_strategy(
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
    inputs = inputs or StyleInputs()
    if preference and not inputs.explicit_preference:
        inputs = StyleInputs(**{**inputs.__dict__, "explicit_preference": preference})
    base = comp.policy
    if base is None:
        raise ValueError("apply_strategy : aucun mandat (statut incomplet ou protection)")
    ds = cfg.ref
    ids: dict[str, list[str]] = {"rule": [], "band": [], "ranking": [], "result": []}

    def add(group, key, label, value, unit, *, path, status="HYPOTHESE", processing=None, currency=None):
        fid = book.add(
            key,
            label,
            value,
            unit,
            dataset=f"{ds}#{path}",
            status=status,
            processing=processing,
            as_of=as_of,
            currency=currency,
        )
        ids[group].append(fid)
        return fid

    with book.step(
        "s0b.strategy", tool="strategy.derive_style", inputs={"level": comp.level, "preference": preference}
    ):
        d = derive_style(comp, inputs, profile=profile, cfg=cfg)
        add(
            "rule",
            "strat.style",
            "style de composition retenu (étape 0)",
            d.style,
            "texte",
            path="level_to_style",
            processing=f"niveau {comp.level} → {d.from_level}, décalage {d.shift:+d}",
        )
        add(
            "rule",
            "strat.style_from_level",
            "style tiré du niveau (convention d'équipe)",
            d.from_level,
            "texte",
            path="level_to_style",
        )
        add(
            "rule",
            "strat.preference",
            "préférence de style",
            d.preference or "aucune",
            "texte",
            path="preference",
            processing=d.preference_source,
        )
        for i, r in enumerate(d.refused):
            add(
                "rule",
                f"strat.preference_refused.{i}",
                "préférence refusée ou plafonnée",
                r,
                "texte",
                path="preference",
            )
        for i, c in enumerate(d.contradictions):
            add(
                "rule",
                f"strat.contradiction.{i}",
                "contradiction réglée par la réponse la plus prudente",
                c,
                "texte",
                path="preference",
            )
        for f in d.flags.active():
            add(
                "rule",
                f"strat.flag.{f}",
                f"signal de comportement : {f} (garde-fou, jamais une allocation)",
                " ; ".join(d.flags.evidence.get(f, [])),
                "texte",
                path="profile_codes",
            )
        g_lim = limit(comp, "alloc.growth")
        add(
            "band",
            "strat.e_min",
            "part actions minimale du niveau",
            _pct(g_lim.min if g_lim else None),
            "%",
            path="band",
            status="FAIT",
            processing="risk_levels.yaml#levels.<niveau>.equity",
        )
        add(
            "band",
            "strat.e_cap",
            "part actions maximale (règle des dollars)",
            _pct(comp.e_cap),
            "%",
            path="band",
            status="FAIT",
            processing="risk_levels.yaml#dollar_rule.e_cap",
        )
        add(
            "band",
            "strat.pi",
            "position visée dans la bande d'actions (0 = plancher, 1 = plafond)",
            round(d.pi, 4),
            "ratio",
            path="band",
            processing=d.pi_reason,
        )
        add("band", "strat.K", "nombre de titres individuels visé", d.k, "titres", path="k", processing=d.k_reason)

    with book.step("s0b.scoring", tool="strategy.score_stocks", inputs={"n_universe": len(base.universe)}):
        cands = candidates if candidates is not None else compute_candidates(base, as_of, cfg)
        ranked = rank_scores(cands, d.style, inputs, base.excluded, cfg, _employer_tickers(profile))
        by_t = {c.ticker: c for c in cands}
        add(
            "ranking",
            "strat.n_candidates",
            "titres individuels classés",
            len(cands),
            "titres",
            path="weights",
            status="FAIT",
        )
        for c in cands:
            for f, v in c.features.items():
                if f not in FEATURE_UNITS or v is None:
                    continue
                add(
                    "ranking",
                    f"strat.feat.{c.ticker}.{f}",
                    f"{FEATURE_LABELS[f]} ({c.ticker})",
                    round(float(v), 6),
                    FEATURE_UNITS[f],
                    path="features",
                    status=c.status.get(f, "HYPOTHESE"),
                    processing=c.details.get("mdd_long_source")
                    if f == "mdd_long"
                    else c.details.get("beta_index")
                    if f == "beta"
                    else None,
                    currency="CAD" if f == "liquidity_cad" else None,
                )
        mom = sorted(
            [c for c in cands if c.features.get("momentum") is not None],
            key=lambda c: (-c.features["momentum"], c.ticker),
        )
        for i, c in enumerate(mom):
            add(
                "ranking",
                f"strat.sens.mom.rank.{c.ticker}",
                f"rang de {c.ticker} au seul momentum (sensibilité)",
                i + 1,
                "rang",
                path="features.momentum_months",
            )
        for r in ranked:
            add(
                "ranking",
                f"strat.score.{r.ticker}",
                f"score du style {d.style} ({r.ticker})",
                round(r.score, 6),
                "ratio",
                path=f"weights.{d.style}",
                processing="rangs en percentile pondérés + bonus",
            )
            add(
                "ranking",
                f"strat.rank.{r.ticker}",
                f"rang de {r.ticker} sur {len(ranked)}",
                r.rank,
                "rang",
                path=f"weights.{d.style}",
            )
            if not r.eligible:
                add(
                    "ranking",
                    f"strat.ineligible.{r.ticker}",
                    f"{r.ticker} écarté",
                    " ; ".join(r.reasons),
                    "texte",
                    path="eligibility",
                )

    with book.step("s0b.select", tool="strategy.select", inputs={"style": d.style, "k": d.k}):
        chosen = shortlist(ranked, d.k, cfg)
        floors, notes = _stock_floors(chosen, comp, d, inputs, cfg)
        sel_tags = {t for tk in floors for t in by_t[tk].tags if t in cfg.sectors.tags}  # titres réellement gardés
        for i, n in enumerate(notes):
            add(
                "result", f"strat.note.{i}", "titre retenu puis retiré (plancher trop petit)", n, "texte", path="floors"
            )
        caps = sector_caps(comp, d.style, inputs, sel_tags, cfg)
        g = band_target(comp, d.pi, cfg)
        keep = set(floors) | set(protect)
        excl = {}
        if cfg.non_shortlisted == "exclude":
            for c in cands:
                if c.ticker not in keep and c.ticker not in base.excluded:
                    excl[c.ticker] = f"strat.shortlist (fact strat.rank.{c.ticker})"
        plan = Plan(growth_floor=g, floors=floors, sector_caps=caps, exclusions=excl)

    with book.step("s0b.feasibility", tool="optimize+check", inputs={"n_limits": len(plan.floors) + len(caps)}):
        feas = _Feasibility(base, as_of)
        fallback: list[str] = []
        policy = apply_to_policy(base, plan, cfg)
        ok, res, new_viol = feas(policy)
        if not ok:
            for label, p2 in degrade_steps(plan, float(g_lim.min or 0.0) if g_lim else 0.0, cfg.band.rounding):
                fallback.append(f"{label} (violations : {sorted(new_viol) or 'optimiseur'})")
                if inputs.amount_cad:  # le repli ne crée jamais de ligne sous le minimum en dollars
                    lmin = cfg.eligibility.min_line_cad
                    p2 = replace(p2, floors={t: f for t, f in p2.floors.items() if f * inputs.amount_cad >= lmin})
                plan, policy = p2, apply_to_policy(base, p2, cfg)
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
        for i, f in enumerate(fallback):
            add("result", f"strat.fallback.{i}", "palier de repli de l'étape 0", f, "texte", path="floors")
        if plan.growth_floor is not None:
            add(
                "result",
                "strat.band_target",
                "part actions visée, placée par la tolérance et plafonnée par la capacité (hors crypto)",
                plan.growth_floor,
                "%",
                path="band",
                processing="e_min + π·(e_cap − e_min), arrondi au 5 % inférieur",
            )
        for t, f in plan.floors.items():
            add(
                "result",
                f"strat.floor.{t}",
                f"plancher du satellite {t}",
                f,
                "%",
                path="floors",
                processing="min(φ·min(w_each, w_total/K), f_abs)",
            )
        if inputs.amount_cad:
            for t, f in plan.floors.items():
                add(
                    "result",
                    f"strat.floor_cad.{t}",
                    f"plancher du satellite {t} en dollars",
                    round(f * inputs.amount_cad, 2),
                    "CAD",
                    path="floors",
                    processing="plancher × context.amount_cad",
                    currency="CAD",
                )
        for tag, (cap, why) in plan.sector_caps.items():
            add(
                "result",
                f"strat.sector_cap.{tag}",
                f"plafond d'exposition {tag} (look-through)",
                cap,
                "%",
                path="sectors",
                processing=why,
            )
        if b_res.risk_value is not None:
            add(
                "result",
                "strat.base_risk",
                "risque minimisé du mandat sans l'étape 0",
                round(b_res.risk_value, 6),
                "%",
                path="band",
                status="FAIT",
                processing="optimiseur F2 sur le mandat de base (CVaR mensuelle)",
            )
        if rc is not None:
            add(
                "result",
                "strat.risk_cost",
                "écart de risque (CVaR mensuelle) dû au style, sans rendement",
                round(rc, 6),
                "%",
                path="band",
                processing="CVaR95 optimisée avec stratégie − sans stratégie",
            )
        add(
            "result",
            "strat.applied",
            "étape 0 appliquée au mandat",
            "oui" if applied else "non",
            "texte",
            path="non_shortlisted",
        )

    return StrategyResult(
        policy=policy,
        base_policy=base,
        decision=d,
        candidates=cands,
        ranking=ranked,
        shortlist=list(plan.floors),
        plan=plan,
        fallback=fallback,
        applied=applied,
        risk_cost=rc,
        version=cfg.version,
        sha256=cfg.sha256,
        notes=notes,
        fact_ids=ids,
    )
