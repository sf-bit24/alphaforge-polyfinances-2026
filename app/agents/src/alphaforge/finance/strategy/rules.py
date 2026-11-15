"""Étape 0, partie pure : classement des titres, sélection, plafonds sectoriels, planchers, limites ``strat.*``.

Toutes les limites émises ici sont ``blocking=False`` et préfixées ``strat.`` : l'optimiseur les applique comme
contraintes (compile.py ignore ``blocking``), le Judge les affiche sans jamais refuser à cause du style.
Elles ne relâchent rien : un plancher (min) ou un plafond plus strict que la limite de base. Les budgets
``risk.*`` ne sont jamais touchés. Bibliothèque standard + contrats seulement (sûr en CI). Simulation seulement.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass, field, replace

from alphaforge.finance.contracts import Limit, PolicySpec, Selector
from alphaforge.finance.policy.models import CompileResult

from .config import StrategyConfig, StyleId, load_strategy
from .style import StyleDecision, StyleInputs, floor_step, limit

STRAT = "strat."


@dataclass(frozen=True)
class Candidate:
    ticker: str
    sector: str  # secteur du starter (assets_universe.csv), un seul titre par secteur
    tags: tuple[str, ...]  # tags du moteur (data/long/assets.csv)
    currency: str
    features: dict[str, float | None]
    status: dict[str, str] = field(default_factory=dict)  # FAIT | HYPOTHESE par indicateur
    details: dict = field(default_factory=dict)  # fenêtre, indice du bêta, proxy de la baisse longue


@dataclass(frozen=True)
class Ranked:
    ticker: str
    sector: str
    score: float
    rank: int  # 1 = premier
    utility: dict[str, float]  # rang en percentile par indicateur (0..1)
    bonuses: tuple[str, ...]
    eligible: bool
    reasons: tuple[str, ...]  # raisons d'inéligibilité ou remarques


@dataclass(frozen=True)
class Plan:
    """Ce que l'étape 0 ajoute au mandat de base ; transformé par le repli."""

    growth_floor: float | None
    floors: dict[str, float]  # ticker -> plancher (ordre = rang)
    sector_caps: dict[str, tuple[float, str]]
    exclusions: dict[str, str]  # ticker -> raison (titres non retenus)

    def empty(self) -> bool:
        return self.growth_floor is None and not self.floors and not self.sector_caps and not self.exclusions


# --------------------------------------------------------------------------- classement


def style_weights(style: StyleId, inputs: StyleInputs, cfg: StrategyConfig) -> dict[str, tuple[int, float]]:
    w = {f: (int(p[0]), float(p[1])) for f, p in cfg.weights[style].items()}
    for interest in inputs.interests:
        spec = cfg.bonus.interests.get(interest) or {}
        feat = spec.get("weight_feature")
        if feat:
            sign, cur = w.get(feat, (1, 0.0))
            w[feat] = (sign, cur + float(spec.get("extra_weight", 1)))
    return w


def _utilities(cands: list[Candidate], feat: str, sign: int) -> dict[str, float]:
    vals = [(c.ticker, c.features.get(feat)) for c in cands]
    known = [(t, v) for t, v in vals if v is not None and not (isinstance(v, float) and math.isnan(v))]
    out = {t: 0.0 for t, _ in vals}  # valeur manquante → score minimal (signalé)
    if feat == "dividend_yield":  # FTSE §5.8 : rendement nul → score minimal
        known = [(t, v) for t, v in known if v > 0]
    n = len(known)
    order = sorted(known, key=lambda tv: (-sign * tv[1], tv[0]))
    for r, (t, _) in enumerate(order):
        out[t] = 1.0 - r / (n - 1) if n > 1 else 1.0
    return out


def bonuses_for(c: Candidate, style: StyleId, inputs: StyleInputs, cfg: StrategyConfig) -> list[str]:
    out = [f"style:{t}" for t in cfg.bonus.style_tags[style] if t in c.tags]
    emp_tag = cfg.sectors.employment_to_tag.get(inputs.employment_sector or "")
    for interest in inputs.interests:
        tag = (cfg.bonus.interests.get(interest) or {}).get("tag")
        if tag and tag in c.tags and tag != emp_tag:
            out.append(f"interest:{interest}")
    return [b for b in out if not (emp_tag and b == f"style:{emp_tag}")]


def eligibility(
    c: Candidate,
    excluded: dict[str, str],
    inputs: StyleInputs,
    cfg: StrategyConfig,
    employer_tickers: set[str] | None = None,
) -> tuple[bool, list[str]]:
    why: list[str] = []
    pc = cfg.profile_codes
    if c.ticker in excluded:
        why.append(f"exclu par le mandat : {excluded[c.ticker]}")
    mdd = c.features.get("mdd_long")
    if mdd is None:
        why.append("baisse maximale longue inconnue")
    elif mdd > cfg.eligibility.mdd_long_max + 1e-12:
        why.append(f"baisse maximale longue {mdd:.0%} > {cfg.eligibility.mdd_long_max:.0%} (δ des titres individuels)")
    liq = c.features.get("liquidity_cad")
    if liq is not None and liq < cfg.eligibility.min_median_dollar_volume_cad:
        why.append("liquidité insuffisante")
    if employer_tickers and c.ticker in employer_tickers:
        why.append("titre de l'employeur (concentration du capital humain)")
    emp = inputs.employment_sector or ""
    if emp in cfg.sectors.employment_to_sector and (
        c.sector == cfg.sectors.employment_to_sector[emp] or cfg.sectors.employment_to_tag[emp] in c.tags
    ):
        why.append(f"secteur d'emploi ({emp}) : capital humain déjà exposé")
    if inputs.currency_preference == pc["currency_cad_only"] and c.currency != "CAD":
        why.append("préférence de devise : CAD seulement")
    strict = pc["exclusion_strictness"]
    for ex in inputs.exclusions:
        tag = pc["exclusion_tags"].get(ex)
        if tag and tag in c.tags and inputs.exclusion_strictness != strict["preference"]:
            why.append(f"exclusion de valeurs : {ex}")
    if c.sector in inputs.concentrated_sectors:
        why.append("secteur déjà concentré dans le portefeuille existant")
    return not why, why


def rank_scores(
    cands: list[Candidate],
    style: StyleId,
    inputs: StyleInputs,
    excluded: dict[str, str],
    cfg: StrategyConfig | None = None,
    employer_tickers: set[str] | None = None,
) -> list[Ranked]:
    cfg = cfg or load_strategy()
    w = style_weights(style, inputs, cfg)
    util = {f: _utilities(cands, f, sign) for f, (sign, _) in w.items()}
    wsum = sum(v for _, v in w.values()) or 1.0
    pc = cfg.profile_codes
    rows = []
    for c in cands:
        base = sum(wt * util[f][c.ticker] for f, (_, wt) in w.items()) / wsum
        bon = bonuses_for(c, style, inputs, cfg)
        score = base + cfg.bonus.size * len(bon)
        notes: list[str] = []
        if inputs.exclusion_strictness == pc["exclusion_strictness"]["preference"]:
            for ex in inputs.exclusions:
                tag = pc["exclusion_tags"].get(ex)
                if tag and tag in c.tags:
                    score += cfg.bonus.preference_penalty
                    notes.append(f"préférence d'exclusion ({ex}) : pénalité de score")
        ok, why = eligibility(c, excluded, inputs, cfg, employer_tickers)
        rows.append(
            (c, round(score, 6), {f: round(util[f][c.ticker], 6) for f in w}, tuple(bon), ok, tuple(why + notes))
        )
    rows.sort(key=lambda r: (-r[1], r[0].ticker))
    return [Ranked(c.ticker, c.sector, s, i + 1, u, b, ok, why) for i, (c, s, u, b, ok, why) in enumerate(rows)]


def shortlist(ranked: list[Ranked], k: int, cfg: StrategyConfig | None = None) -> list[Ranked]:
    cfg = cfg or load_strategy()
    out: list[Ranked] = []
    seen: set[str] = set()
    for r in ranked:
        if len(out) >= k:
            break
        if not r.eligible or (cfg.k.one_per_sector and r.sector in seen):
            continue
        out.append(r)
        seen.add(r.sector)
    return out


# --------------------------------------------------------------------------- plafonds sectoriels et planchers


def sector_caps(
    comp: CompileResult, style: StyleId, inputs: StyleInputs, selected_tags: set[str], cfg: StrategyConfig | None = None
) -> dict[str, tuple[float, str]]:
    """cap_t = e_cap·s_ref_t·(1+τ) + φ·l*/δ_t (généralisation de satellites.theme_tech) ; émis seulement s'il est
    plus strict que la limite de base sur le même tag. Capital humain : cap au poids du marché (sans satellite)."""
    cfg = cfg or load_strategy()
    S = cfg.sectors
    e_cap, l_star = float(comp.e_cap or 0.0), float(comp.l_star or 0.0)
    emp_tag = S.employment_to_tag.get(inputs.employment_sector or "")
    abs_tags = set()
    pc = cfg.profile_codes
    if inputs.exclusion_strictness == pc["exclusion_strictness"]["absolute"]:
        for ex in inputs.exclusions:
            if pc["exclusion_tags"].get(ex) == "fossil_fuel":
                abs_tags.add("energy")
    out: dict[str, tuple[float, str]] = {}
    for tag, spec in S.tags.items():
        tau = S.tau[style].get(tag, 0.0)
        if tag == emp_tag or tag in abs_tags:
            cap = floor_step(e_cap * spec.s_ref, S.rounding)
            why = (
                "capital humain : exposition au poids du marché, sans satellite"
                if tag == emp_tag
                else "exclusion absolue : exposition indirecte au plus au poids du marché"
            )
        elif tau < 0 or tag in selected_tags:
            cap = floor_step(e_cap * spec.s_ref * (1 + tau) + S.phi * l_star / spec.delta, S.rounding)
            why = f"style {style} (τ={tau:+g})" if tau < 0 else "secteur d'un titre retenu : plafond affiché (Brain D7)"
        else:
            continue
        cap = round(max(cap, 0.0), 6)
        base = limit(comp, f"exp.{tag}")
        if base is not None and base.max is not None and cap >= float(base.max) - 1e-9:
            continue
        out[tag] = (cap, why)
    return out


def stock_floors(
    chosen: list[Ranked],
    comp: CompileResult,
    decision: StyleDecision,
    inputs: StyleInputs,
    cfg: StrategyConfig | None = None,
) -> tuple[dict[str, float], list[str]]:
    cfg = cfg or load_strategy()
    if not chosen:
        return {}, []
    each, total = limit(comp, "conc.single_each"), limit(comp, "conc.single_total")
    w_each, w_total = float(each.max or 0.0), float(total.max or 0.0)
    room = min(w_each, w_total / len(chosen))
    out, notes = {}, []
    for r in chosen:
        f = min(floor_step(decision.floor_fraction * room, 0.0025), cfg.floors.f_abs)
        f = round(f, 6)
        if f < cfg.floors.min_floor:
            notes.append(f"{r.ticker} : plancher {f:.4f} sous le minimum, retiré")
            continue
        if inputs.amount_cad and f * inputs.amount_cad < cfg.eligibility.min_line_cad:
            line, lmin = f * inputs.amount_cad, cfg.eligibility.min_line_cad
            notes.append(f"{r.ticker} : ligne de {line:.0f} $ sous {lmin:.0f} $, retirée")
            continue
        out[r.ticker] = f
    return out, notes


# --------------------------------------------------------------------------- limites et mandat


def build_limits(plan: Plan, cfg: StrategyConfig | None = None) -> list[Limit]:
    cfg = cfg or load_strategy()
    lims: list[Limit] = []
    if plan.growth_floor is not None:
        lims.append(
            Limit(
                rule_id="strat.growth_floor",
                kind="group_weight",
                selector=Selector(classes=list(cfg.band.growth_classes)),
                min=plan.growth_floor,
                blocking=False,
                derived_from="étape 0 : position dans la bande (tolérance, capacité)",
                source=cfg.src("band"),
                description_fr="part actions visée, placée par la tolérance et plafonnée par la capacité (hors crypto)",
            )
        )
    for t, f in plan.floors.items():
        lims.append(
            Limit(
                rule_id=f"strat.floor.{t}",
                kind="asset_weight",
                selector=Selector(assets=[t]),
                min=f,
                blocking=False,
                derived_from="étape 0 : titre retenu par le classement du style",
                source=cfg.src("floors"),
                description_fr=f"plancher du satellite {t}",
            )
        )
    for tag, (cap, why) in plan.sector_caps.items():
        lims.append(
            Limit(
                rule_id=f"strat.sector_cap.{tag}",
                kind="exposure",
                selector=Selector(exposure_tag=tag),
                max=cap,
                blocking=False,
                derived_from=f"étape 0 : {why}",
                source=cfg.src("sectors"),
                description_fr=f"plafond d'exposition {tag} (look-through)",
            )
        )
    return lims


def apply_to_policy(base: PolicySpec, plan: Plan, cfg: StrategyConfig | None = None) -> PolicySpec:
    """Ajoute les limites ``strat.*`` et les exclusions de la sélection ; ne touche à rien d'autre."""
    data = base.model_dump()
    keep = [lim for lim in base.limits if not lim.rule_id.startswith(STRAT)]
    data["limits"] = [lim.model_dump() for lim in [*keep, *build_limits(plan, cfg)]]
    excl = dict(base.excluded)
    for t, why in plan.exclusions.items():
        if t in base.universe and t not in excl:
            excl[t] = why
    data["excluded"] = excl
    return PolicySpec.model_validate(data)


def _max_of(policy: PolicySpec, rule_id: str) -> float | None:
    for lim in policy.limits:
        if lim.rule_id == rule_id:
            return lim.max
    return None


def clamp_strategy_floors(policy: PolicySpec) -> tuple[PolicySpec, list[str]]:
    """Après un amendement qui baisse un plafond, abaisse les planchers liés : la prudence l'emporte sur le style."""
    notes: list[str] = []
    g_max, c_max = _max_of(policy, "alloc.growth"), _max_of(policy, "alloc.crypto") or 0.0
    each, total = _max_of(policy, "conc.single_each"), _max_of(policy, "conc.single_total")
    lims = []
    floors = {lim.rule_id: lim for lim in policy.limits if lim.rule_id.startswith("strat.floor.")}
    asset_caps: dict[str, float] = {}
    for lim in policy.limits:
        if lim.kind == "asset_weight" and lim.max is not None and not lim.rule_id.startswith(STRAT):
            for a in lim.selector.assets:
                asset_caps[a] = min(asset_caps.get(a, 1.0), float(lim.max))
    new_floor: dict[str, float] = {}
    for rid, lim in floors.items():
        a = lim.selector.assets[0]
        cap = min(x for x in (lim.min, each, asset_caps.get(a)) if x is not None)
        if a in policy.excluded:
            notes.append(f"{rid} retiré : {a} exclu")
            continue
        if cap < lim.min - 1e-12:
            notes.append(f"{rid} abaissé de {lim.min:g} à {cap:g}")
        new_floor[rid] = cap
    s = sum(new_floor.values())
    if total is not None and s > total + 1e-12 and s > 0:
        k = total / s
        new_floor = {r: floor_step(v * k, 0.0025) for r, v in new_floor.items()}
        notes.append(f"planchers des titres ramenés sous conc.single_total ({total:g})")
    for lim in policy.limits:
        if lim.rule_id in floors:
            v = new_floor.get(lim.rule_id)
            if v and v > 0:
                lims.append(lim.model_copy(update={"min": round(v, 6)}))
            continue
        if lim.rule_id == "strat.growth_floor" and g_max is not None:
            cap = round(g_max - c_max, 6)
            if lim.min is not None and lim.min > cap + 1e-12:
                notes.append(f"strat.growth_floor abaissé de {lim.min:g} à {cap:g}")
                if cap <= 0:
                    continue
                lim = lim.model_copy(update={"min": cap})
        lims.append(lim)
    data = policy.model_dump()
    data["limits"] = [lim.model_dump() for lim in lims]
    return PolicySpec.model_validate(data), notes


def degrade_steps(plan: Plan, e_min: float, rounding: float = 0.05) -> Iterator[tuple[str, Plan]]:
    """Repli quand le mandat avec stratégie est infaisable (optimize puis Judge). Ordre : planchers ÷ 2, retrait
    des titres du dernier rang, π qui descend, retrait des plafonds sectoriels, retour au mandat de base. Les
    exclusions de valeurs du mandat de base ne sont jamais retirées (seules celles de la sélection le sont)."""
    cur = plan
    if cur.floors:
        cur = replace(cur, floors={t: floor_step(f / 2, 0.0025) for t, f in cur.floors.items() if f / 2 >= 0.0025})
        yield "planchers des titres divisés par 2", cur
    while cur.floors:
        last = list(cur.floors)[-1]
        cur = replace(cur, floors={t: f for t, f in cur.floors.items() if t != last})
        yield f"plancher de {last} retiré (dernier rang)", cur
    while cur.growth_floor is not None:
        g = round(cur.growth_floor - rounding, 6)
        cur = replace(cur, growth_floor=g if g > e_min + 1e-9 else None)
        yield ("part actions visée abaissée" if cur.growth_floor is not None else "part actions visée retirée"), cur
    if cur.sector_caps:
        cur = replace(cur, sector_caps={})
        yield "plafonds sectoriels du style retirés", cur
    if cur.exclusions:
        cur = replace(cur, exclusions={})
        yield "sélection abandonnée : mandat de base", cur
