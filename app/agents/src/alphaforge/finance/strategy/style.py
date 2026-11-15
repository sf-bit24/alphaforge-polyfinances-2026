"""Étape 0, partie pure : style (étiquette de composition), position dans la bande d'actions, nombre de titres.

Règles (strategy.yaml, toutes HYPOTHESE) :
- le style vient du niveau F1 (convention d'équipe) ; une préférence le décale d'au plus un cran vers le haut
  (descente toujours admise) et ne change que la COMPOSITION : jamais R, le niveau, e_cap, l* ni un budget risk.* ;
- la tolérance mesurée place le portefeuille dans sa bande, la capacité la plafonne (rapport « Investor
  profiling », Wealthsimple, 31-368) : π = 1 si la capacité ou un plafond lie, sinon position de R dans le niveau ;
- les signaux de comportement deviennent des garde-fous (surconfiance, FOMO/attention, faible sang-froid,
  faible littératie), jamais une allocation ; une contradiction se règle par la réponse la plus prudente.

Pur : bibliothèque standard + contrats + YAML. Aucun nombre ne vient d'un LLM. Simulation seulement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

from alphaforge.finance.policy.compiler import DEFAULT_YAML, _bias_key
from alphaforge.finance.policy.models import CompileResult

from .config import LEVELS, STYLES, StrategyConfig, StyleId, load_strategy
from .labels import style_fr


@dataclass(frozen=True)
class StyleInputs:
    """Variables du profil court (Brain 3993936) utiles à l'étape 0. Toutes facultatives : une valeur absente
    ne déclenche rien (aucune valeur par défaut chiffrée n'est inventée ici)."""

    explicit_preference: StyleId | None = None  # paramètre d'appel (prioritaire sur objective.goal)
    goal: str | None = None  # objective.goal
    approach: str | None = None  # preferences.approach
    interests: tuple[str, ...] = ()  # preferences.interests
    favored_tickers: tuple[str, ...] = ()  # preferences.favored_tickers (titres individuels de l'univers)
    exclusions: tuple[str, ...] = ()  # preferences.exclusions
    exclusion_strictness: str | None = None  # preferences.exclusion_strictness
    esg_importance: int | None = None  # preferences.esg_importance (1-5)
    employment_sector: str | None = None  # risk_capacity.employment_sector
    currency_preference: str | None = None  # constraints.currency_preference
    account_types: tuple[str, ...] = ()  # constraints.account_types
    amount_cad: float | None = None  # context.amount_cad
    portfolio_flags: tuple[str, ...] = ()  # context.portfolio_flags
    concentrated_sectors: tuple[str, ...] = ()  # secteurs déjà concentrés dans le portefeuille existant
    knowledge_level: str | None = None  # knowledge.level (beginner | intermediate | advanced)
    self_assessment: str | None = None  # knowledge.self_assessment
    quiz: dict[str, str] = field(default_factory=dict)  # knowledge.quiz_* → réponse
    products_known: tuple[str, ...] = ()  # knowledge.products_known
    news_frequency: str | None = None  # knowledge.news_frequency
    hype_reaction: str | None = None  # behavior.hype_reaction
    hype_position_share: str | None = None  # behavior.hype_position_share
    drop_reaction: str | None = None  # risk_tolerance.drop_reaction
    past_drop_behavior: str | None = None  # risk_tolerance.past_drop_behavior
    sell_threshold_pct: str | None = None  # risk_tolerance.sell_threshold_pct


@dataclass(frozen=True)
class BehaviorFlags:
    overconfidence: bool = False
    fomo: bool = False
    attention: bool = False
    low_composure: bool = False
    low_literacy: bool = False
    evidence: dict[str, list[str]] = field(default_factory=dict)

    def active(self) -> list[str]:
        return [k for k in ("overconfidence", "fomo", "attention", "low_composure", "low_literacy") if getattr(self, k)]


@dataclass(frozen=True)
class StyleDecision:
    style: StyleId
    from_level: StyleId
    preference: StyleId | None
    preference_source: str | None  # « paramètre » | « objective.goal=… » | None
    shift: int
    refused: tuple[str, ...]  # raisons d'une montée refusée ou plafonnée
    contradictions: tuple[str, ...]
    flags: BehaviorFlags
    pi: float  # position visée dans la bande d'actions, [0, 1]
    pi_reason: str
    capacity_binds: bool
    k: int
    k_reason: str
    floor_fraction: float
    trace: tuple[dict[str, Any], ...]  # {"rule", "inputs", "output", "yaml_path"} comme compiler._Ctx


# --------------------------------------------------------------------------- utilitaires


def floor_step(x: float, s: float) -> float:
    return math.floor(x / s + 1e-9) * s


def _idx(st: StyleId) -> int:
    return STYLES.index(st)


@lru_cache(maxsize=4)
def _risk_levels(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def level_R_range(level: str) -> tuple[float, float]:
    lv = _risk_levels(str(DEFAULT_YAML))["levels"][level]
    lo, hi = lv["R"]
    return float(lo), float(hi)


def limit(comp: CompileResult, rule_id: str):
    for lim in comp.limits:
        if lim.rule_id == rule_id:
            return lim
    return None


def profile_biases(profile: Any) -> set[str]:
    if profile is None:
        return set()
    return {k for k in (_bias_key(b.kind_label) for b in getattr(profile, "biases", []) or []) if k}


class _T:
    def __init__(self, cfg: StrategyConfig):
        self.cfg, self.rows = cfg, []

    def t(self, rule: str, inputs: dict, output: Any, path: str) -> Any:
        self.rows.append({"rule": rule, "inputs": inputs, "output": output, "yaml_path": self.cfg.src(path)})
        return output


# --------------------------------------------------------------------------- garde-fous de comportement


def behavior_flags(
    inputs: StyleInputs, profile: Any = None, comp: CompileResult | None = None, cfg: StrategyConfig | None = None
) -> BehaviorFlags:
    cfg = cfg or load_strategy()
    pc = cfg.profile_codes
    ev: dict[str, list[str]] = {}
    biases = profile_biases(profile)

    wrong = [q for q, ok in pc["quiz_correct"].items() if q in inputs.quiz and inputs.quiz[q] != ok]
    over = inputs.self_assessment in pc["overconfident_self"] and bool(wrong)
    if over:
        ev["overconfidence"] = [
            f"knowledge.self_assessment={inputs.self_assessment}",
            *(f"knowledge.{q}" for q in wrong),
        ]
    if "surconfiance" in biases:
        over = True
        ev.setdefault("overconfidence", []).append("profile.biases[surconfiance]")

    fomo = inputs.hype_reaction in pc["fomo_hype_reaction"] or inputs.hype_position_share in pc["fomo_hype_share"]
    if fomo:
        ev["fomo"] = [
            f"behavior.hype_reaction={inputs.hype_reaction}",
            f"behavior.hype_position_share={inputs.hype_position_share}",
        ]
    if "FOMO" in biases:
        fomo = True
        ev.setdefault("fomo", []).append("profile.biases[FOMO]")

    attention = inputs.news_frequency in pc["attention_news"] and inputs.hype_reaction in pc["attention_hype_reaction"]
    if attention:
        ev["attention"] = [
            f"knowledge.news_frequency={inputs.news_frequency}",
            f"behavior.hype_reaction={inputs.hype_reaction}",
        ]

    lc_ev = []
    if inputs.drop_reaction in pc["low_composure_drop_reaction"]:
        lc_ev.append(f"risk_tolerance.drop_reaction={inputs.drop_reaction}")
    if inputs.past_drop_behavior in pc["low_composure_past"]:
        lc_ev.append(f"risk_tolerance.past_drop_behavior={inputs.past_drop_behavior}")
    if inputs.sell_threshold_pct in pc["low_composure_sell_threshold"]:
        lc_ev.append(f"risk_tolerance.sell_threshold_pct={inputs.sell_threshold_pct}")
    if "aversion_perte" in biases:
        lc_ev.append("profile.biases[aversion_perte]")
    if comp is not None and limit(comp, "risk.cdar_m") is not None:
        lc_ev.append("risk.cdar_m (aversion aux pertes ou composure < 40, risk_levels.yaml#biases)")
    if lc_ev:
        ev["low_composure"] = lc_ev

    kl = inputs.knowledge_level or (
        getattr(profile, "knowledge_level", None)
        and {"debutant": "beginner", "intermediaire": "intermediate", "avance": "advanced"}.get(
            str(getattr(profile.knowledge_level, "value", profile.knowledge_level))
        )
    )
    lit_ev = []
    if kl == "beginner":
        lit_ev.append("knowledge.level=beginner")
    if inputs.products_known and pc["products_stocks"] not in inputs.products_known:
        lit_ev.append("knowledge.products_known sans « stocks »")
    if lit_ev:
        ev["low_literacy"] = lit_ev
    return BehaviorFlags(
        overconfidence=over,
        fomo=fomo,
        attention=attention,
        low_composure=bool(lc_ev),
        low_literacy=bool(lit_ev),
        evidence=ev,
    )


# --------------------------------------------------------------------------- style


def _capacity_binds(comp: CompileResult) -> tuple[bool, str]:
    iL, iR = LEVELS.index(comp.level), LEVELS.index(comp.level_from_R)
    if iL < iR:
        return (
            True,
            f"niveau {comp.level} sous niveau(R) {comp.level_from_R} : un plafond (horizon, seau, statut, dollars) lie",
        )
    T, C = float(comp.tolerance["T"]), float(comp.capacity["C"])
    if C < T:
        return True, f"capacité C={C:.1f} < tolérance T={T:.1f}"
    return False, f"la tolérance T={T:.1f} lie (C={C:.1f})"


def band_position(
    comp: CompileResult, flags: BehaviorFlags, cfg: StrategyConfig, tr: _T | None = None
) -> tuple[float, str, bool]:
    """π ∈ [0, 1] : 1 = e_cap (le plus haut que permettent tolérance ET capacité), 0 = e_min."""
    binds, why = _capacity_binds(comp)
    if comp.status != "COMPLETE":
        pi, reason = cfg.band.incomplete_pi, f"statut {comp.status} : position d'attente"
    elif binds:
        pi, reason = 1.0, why
    else:
        lo, hi = level_R_range(comp.level)
        pi = min(1.0, max(0.0, (float(comp.R) - lo) / (hi - lo))) if hi > lo else 1.0
        reason = f"{why} ; R={float(comp.R):.1f} dans [{lo:g}, {hi:g}] du niveau {comp.level}"
    if flags.low_composure and pi > cfg.band.low_composure_pi_max:
        pi, reason = cfg.band.low_composure_pi_max, reason + " ; faible sang-froid : π plafonné"
    if tr:
        tr.t(
            "strategy.band_position",
            {
                "level": comp.level,
                "R": comp.R,
                "T": comp.tolerance["T"],
                "C": comp.capacity["C"],
                "status": comp.status,
                "low_composure": flags.low_composure,
            },
            round(pi, 4),
            "band",
        )
    return pi, reason, binds


def band_target(comp: CompileResult, pi: float, cfg: StrategyConfig | None = None) -> float | None:
    """Plancher de la part actions hors crypto ; None s'il ne dépasse pas e_min (aucun effet)."""
    cfg = cfg or load_strategy()
    g_lim, c_lim = limit(comp, "alloc.growth"), limit(comp, "alloc.crypto")
    if g_lim is None or comp.e_cap is None:
        return None
    e_min = float(g_lim.min or 0.0)
    e_cap = float(g_lim.max if g_lim.max is not None else comp.e_cap)
    c_max = float(c_lim.max or 0.0) if c_lim is not None else 0.0
    g = floor_step(e_min + pi * (e_cap - e_min), cfg.band.rounding)
    g = round(min(g, e_cap - c_max), 6)
    return g if g > e_min + 1e-9 else None


def k_rule(
    comp: CompileResult, style: StyleId, inputs: StyleInputs, flags: BehaviorFlags, cfg: StrategyConfig | None = None
) -> tuple[int, str]:
    cfg = cfg or load_strategy()
    each, total = limit(comp, "conc.single_each"), limit(comp, "conc.single_total")
    w_each = float(each.max or 0.0) if each else 0.0
    w_total = float(total.max or 0.0) if total else 0.0
    pc = cfg.profile_codes["approach"]
    if comp.level == "N0":
        return 0, "niveau N0 : aucun titre individuel"
    if comp.status != "COMPLETE":
        return 0, f"statut {comp.status} : aucun titre individuel"
    if w_each <= 0 or w_total <= 0:
        return 0, "plafond conc.single_each ou conc.single_total nul (risk_levels.yaml)"
    if flags.low_literacy:
        return 0, "faible littératie ou débutant : FNB diversifiés seulement"
    if inputs.approach in pc["passive"]:
        return 0, "preferences.approach = fonds indiciels : FNB seulement"
    k_cap = math.floor(w_total / w_each + 1e-9)
    base = cfg.k.k_max if inputs.approach in pc["single"] else cfg.k.k_default
    k = min(base, k_cap)
    reason = f"min({'k_max' if base == cfg.k.k_max else 'k_default'}={base}, ⌊{w_total:g}/{w_each:g}⌋={k_cap})"
    if flags.overconfidence and k > 0:
        k -= 1
        reason += " ; surconfiance : K − 1"
    return max(k, 0), reason


def derive_style(
    comp: CompileResult, inputs: StyleInputs | None = None, *, profile: Any = None, cfg: StrategyConfig | None = None
) -> StyleDecision:
    cfg = cfg or load_strategy()
    inputs = inputs or StyleInputs()
    tr = _T(cfg)
    flags = behavior_flags(inputs, profile, comp, cfg)
    base: StyleId = cfg.level_to_style[comp.level]
    tr.t("strategy.style_from_level", {"level": comp.level}, base, "level_to_style")

    pref, pref_src = None, None
    if inputs.explicit_preference and inputs.explicit_preference not in STYLES:
        # préférence invalide (charge utile) : ignorée, jamais une erreur ; tracée pour l'explication
        tr.t("strategy.preference_invalid", {"style_preference": inputs.explicit_preference}, None, "styles")
    if inputs.explicit_preference in STYLES:
        pref, pref_src = inputs.explicit_preference, "paramètre style_preference"
    elif inputs.goal in cfg.preference.goal_to_preference:
        pref, pref_src = cfg.preference.goal_to_preference[inputs.goal], f"objective.goal={inputs.goal}"

    contradictions: list[str] = []
    P = cfg.preference
    if pref == "offensive" and comp.level_from_R in P.low_tolerance_levels:
        contradictions.append("tolérance faible × préférence de croissance (règle des ACVM)")
    if flags.low_literacy and comp.level_from_R in P.high_tolerance_levels:
        contradictions.append("connaissance faible × tolérance agressive")
    if pref == "offensive" and comp.horizon_years is not None and comp.horizon_years < P.short_horizon_years:
        contradictions.append("horizon court × préférence pour le style offensif")

    binds, _ = _capacity_binds(comp)
    refused: list[str] = []
    if inputs.explicit_preference and inputs.explicit_preference not in STYLES:
        refused.append("préférence de style inconnue, ignorée")
    shift = 0
    if pref is not None:
        want = _idx(pref) - _idx(base)
        if want < 0:
            shift = want
        elif want > 0:
            blocks = []
            if comp.status != "COMPLETE":
                blocks.append(f"statut {comp.status}")
            if comp.level == "N0":
                blocks.append("niveau N0")
            if flags.fomo:
                blocks.append("signal FOMO")
            if flags.attention:
                blocks.append("signal d'attention (actualité quotidienne et titre médiatisé)")
            if flags.low_composure:
                blocks.append("faible sang-froid ou aversion aux pertes")
            if binds:
                blocks.append("la capacité lie")
            blocks += contradictions
            if blocks:
                refused += [f"montée refusée : {b}" for b in blocks]
            else:
                shift = min(want, P.max_up)
                if want > P.max_up:
                    refused.append("montée plafonnée à un cran")
    style: StyleId = STYLES[_idx(base) + shift]
    if flags.low_literacy and _idx(style) > _idx(P.beginner_max_style):
        refused.append(f"débutant ou faible littératie : style plafonné à {style_fr(P.beginner_max_style)}")
        style = P.beginner_max_style
        shift = _idx(style) - _idx(base)
    tr.t(
        "strategy.style",
        {
            "from_level": base,
            "preference": pref,
            "preference_source": pref_src,
            "refused": refused,
            "contradictions": contradictions,
            "flags": flags.active(),
        },
        style,
        "preference",
    )

    pi, pi_reason, _ = band_position(comp, flags, cfg, tr)
    if flags.low_literacy and comp.level_from_R in P.high_tolerance_levels and pi > cfg.band.low_composure_pi_max:
        # contradiction non résolue : la réponse la plus prudente l'emporte pour la position dans la bande
        pi = cfg.band.low_composure_pi_max
        pi_reason += " ; contradiction connaissance × tolérance : π plafonné (réponse la plus prudente)"
        tr.t("strategy.band_position.capped", {"reason": "contradiction connaissance × tolérance"}, pi, "band")
    k, k_reason = k_rule(comp, style, inputs, flags, cfg)
    tr.t("strategy.k", {"style": style, "approach": inputs.approach}, k, "k")
    phi = cfg.floors.phi[style] * (cfg.floors.overconfidence_mult if flags.overconfidence else 1.0)
    return StyleDecision(
        style=style,
        from_level=base,
        preference=pref,
        preference_source=pref_src,
        shift=shift,
        refused=tuple(refused),
        contradictions=tuple(contradictions),
        flags=flags,
        pi=pi,
        pi_reason=pi_reason,
        capacity_binds=binds,
        k=k,
        k_reason=k_reason,
        floor_fraction=phi,
        trace=tuple(tr.rows),
    )
