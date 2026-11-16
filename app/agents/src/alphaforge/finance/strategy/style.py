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

from .config import LEVELS, STYLES, Preference, StrategyConfig, StyleId, load_strategy
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


def level_r_range(level: str) -> tuple[float, float]:
    """Intervalle de R du niveau (risk_levels.yaml#levels.<niveau>.R)."""
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


class _RuleTrace:
    """Trace des règles appliquées, une ligne par règle, comme ``compiler._Ctx`` (devient ``StyleDecision.trace``)."""

    def __init__(self, cfg: StrategyConfig):
        self.cfg, self.rows = cfg, []

    def record(self, rule: str, inputs: dict, output: Any, path: str) -> Any:
        self.rows.append({"rule": rule, "inputs": inputs, "output": output, "yaml_path": self.cfg.src(path)})
        return output


# --------------------------------------------------------------------------- garde-fous de comportement


def behavior_flags(
    inputs: StyleInputs, profile: Any = None, comp: CompileResult | None = None, cfg: StrategyConfig | None = None
) -> BehaviorFlags:
    """Chaque signal est actif dès qu'il a au moins une preuve (réponse du profil court ou biais du profil)."""
    cfg = cfg or load_strategy()
    pc = cfg.profile_codes
    biases = profile_biases(profile)
    evidence = {
        "overconfidence": _overconfidence_evidence(inputs, pc, biases),
        "fomo": _fomo_evidence(inputs, pc, biases),
        "attention": _attention_evidence(inputs, pc),
        "low_composure": _low_composure_evidence(inputs, pc, biases, comp),
        "low_literacy": _low_literacy_evidence(inputs, pc, profile),
    }
    return BehaviorFlags(
        **{flag: bool(proof) for flag, proof in evidence.items()},
        evidence={flag: proof for flag, proof in evidence.items() if proof},
    )


def _overconfidence_evidence(inputs: StyleInputs, pc: dict, biases: set[str]) -> list[str]:
    """Auto-évaluation « avancée » contredite par le quiz, ou biais de surconfiance déclaré."""
    wrong = [q for q, ok in pc["quiz_correct"].items() if q in inputs.quiz and inputs.quiz[q] != ok]
    proof = []
    if inputs.self_assessment in pc["overconfident_self"] and wrong:
        proof = [f"knowledge.self_assessment={inputs.self_assessment}", *(f"knowledge.{q}" for q in wrong)]
    if "surconfiance" in biases:
        proof.append("profile.biases[surconfiance]")
    return proof


def _fomo_evidence(inputs: StyleInputs, pc: dict, biases: set[str]) -> list[str]:
    proof = []
    if inputs.hype_reaction in pc["fomo_hype_reaction"] or inputs.hype_position_share in pc["fomo_hype_share"]:
        proof = [
            f"behavior.hype_reaction={inputs.hype_reaction}",
            f"behavior.hype_position_share={inputs.hype_position_share}",
        ]
    if "FOMO" in biases:
        proof.append("profile.biases[FOMO]")
    return proof


def _attention_evidence(inputs: StyleInputs, pc: dict) -> list[str]:
    if inputs.news_frequency in pc["attention_news"] and inputs.hype_reaction in pc["attention_hype_reaction"]:
        return [f"knowledge.news_frequency={inputs.news_frequency}", f"behavior.hype_reaction={inputs.hype_reaction}"]
    return []


def _low_composure_evidence(inputs: StyleInputs, pc: dict, biases: set[str], comp: CompileResult | None) -> list[str]:
    answers = (
        ("drop_reaction", inputs.drop_reaction, "low_composure_drop_reaction"),
        ("past_drop_behavior", inputs.past_drop_behavior, "low_composure_past"),
        ("sell_threshold_pct", inputs.sell_threshold_pct, "low_composure_sell_threshold"),
    )
    proof = [f"risk_tolerance.{name}={value}" for name, value, codes in answers if value in pc[codes]]
    if "aversion_perte" in biases:
        proof.append("profile.biases[aversion_perte]")
    if comp is not None and limit(comp, "risk.cdar_m") is not None:
        proof.append("risk.cdar_m (aversion aux pertes ou composure < 40, risk_levels.yaml#biases)")
    return proof


def _knowledge_level(inputs: StyleInputs, profile: Any) -> str | None:
    """Niveau du profil court, sinon celui du profil complet (debutant | intermediaire | avance) traduit."""
    return inputs.knowledge_level or (
        getattr(profile, "knowledge_level", None)
        and {"debutant": "beginner", "intermediaire": "intermediate", "avance": "advanced"}.get(
            str(getattr(profile.knowledge_level, "value", profile.knowledge_level))
        )
    )


def _low_literacy_evidence(inputs: StyleInputs, pc: dict, profile: Any) -> list[str]:
    proof = []
    if _knowledge_level(inputs, profile) == "beginner":
        proof.append("knowledge.level=beginner")
    if inputs.products_known and pc["products_stocks"] not in inputs.products_known:
        proof.append("knowledge.products_known sans « stocks »")
    return proof


# --------------------------------------------------------------------------- style


def _capacity_binds(comp: CompileResult) -> tuple[bool, str]:
    if LEVELS.index(comp.level) < LEVELS.index(comp.level_from_R):
        return (
            True,
            f"niveau {comp.level} sous niveau(R) {comp.level_from_R} : un plafond (horizon, seau, statut, dollars) lie",
        )
    tolerance, capacity = float(comp.tolerance["T"]), float(comp.capacity["C"])
    if capacity < tolerance:
        return True, f"capacité C={capacity:.1f} < tolérance T={tolerance:.1f}"
    return False, f"la tolérance T={tolerance:.1f} lie (C={capacity:.1f})"


def band_position(
    comp: CompileResult, flags: BehaviorFlags, cfg: StrategyConfig, tr: _RuleTrace | None = None
) -> tuple[float, str, bool]:
    """π ∈ [0, 1] : 1 = e_cap (le plus haut que permettent tolérance ET capacité), 0 = e_min."""
    binds, why = _capacity_binds(comp)
    if comp.status != "COMPLETE":
        pi, reason = cfg.band.incomplete_pi, f"statut {comp.status} : position d'attente"
    elif binds:
        pi, reason = 1.0, why
    else:
        lo, hi = level_r_range(comp.level)
        pi = min(1.0, max(0.0, (float(comp.R) - lo) / (hi - lo))) if hi > lo else 1.0
        reason = f"{why} ; R={float(comp.R):.1f} dans [{lo:g}, {hi:g}] du niveau {comp.level}"
    if flags.low_composure and pi > cfg.band.low_composure_pi_max:
        pi, reason = cfg.band.low_composure_pi_max, reason + " ; faible sang-froid : π plafonné"
    if tr:
        tr.record(
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


@dataclass(frozen=True)
class _StyleChoice:
    """Style retenu et ce qui l'explique (préférence, refus, contradictions), avant la position dans la bande."""

    style: StyleId
    from_level: StyleId
    preference: StyleId | None
    preference_source: str | None
    shift: int
    refused: list[str]
    contradictions: list[str]
    capacity_binds: bool


def _is_unknown_style(preference: str | None) -> bool:
    """Préférence invalide (charge utile) : ignorée, jamais une erreur ; tracée pour l'explication."""
    return bool(preference) and preference not in STYLES


def _preference(inputs: StyleInputs, cfg: StrategyConfig, tr: _RuleTrace) -> tuple[StyleId | None, str | None]:
    """(préférence, source) : le paramètre d'appel l'emporte sur ``objective.goal``."""
    if _is_unknown_style(inputs.explicit_preference):
        tr.record("strategy.preference_invalid", {"style_preference": inputs.explicit_preference}, None, "styles")
    if inputs.explicit_preference in STYLES:
        return inputs.explicit_preference, "paramètre style_preference"
    if inputs.goal in cfg.preference.goal_to_preference:
        return cfg.preference.goal_to_preference[inputs.goal], f"objective.goal={inputs.goal}"
    return None, None


def _contradictions(
    comp: CompileResult, pref: StyleId | None, flags: BehaviorFlags, pref_rules: Preference
) -> list[str]:
    """Contradictions du profil (règles des ACVM) ; chacune bloque une montée de style."""
    out: list[str] = []
    if pref == "offensive" and comp.level_from_R in pref_rules.low_tolerance_levels:
        out.append("tolérance faible × préférence de croissance (règle des ACVM)")
    if flags.low_literacy and comp.level_from_R in pref_rules.high_tolerance_levels:
        out.append("connaissance faible × tolérance agressive")
    if pref == "offensive" and comp.horizon_years is not None and comp.horizon_years < pref_rules.short_horizon_years:
        out.append("horizon court × préférence pour le style offensif")
    return out


def _upgrade_blocks(comp: CompileResult, flags: BehaviorFlags, *, binds: bool) -> list[str]:
    """Ce qui interdit de monter d'un cran au-dessus du style du niveau (prudence)."""
    checks = (
        (comp.status != "COMPLETE", f"statut {comp.status}"),
        (comp.level == "N0", "niveau N0"),
        (flags.fomo, "signal FOMO"),
        (flags.attention, "signal d'attention (actualité quotidienne et titre médiatisé)"),
        (flags.low_composure, "faible sang-froid ou aversion aux pertes"),
        (binds, "la capacité lie"),
    )
    return [why for hit, why in checks if hit]


def _preference_shift(want: int, blocks: list[str], max_up: int) -> tuple[int, list[str]]:
    """(décalage admis, raisons) : une descente est toujours admise, une montée bloquée ou plafonnée est expliquée."""
    if want < 0:
        return want, []
    if want == 0:
        return 0, []
    if blocks:
        return 0, [f"montée refusée : {b}" for b in blocks]
    return min(want, max_up), ["montée plafonnée à un cran"] if want > max_up else []


def _choose_style(
    comp: CompileResult, inputs: StyleInputs, flags: BehaviorFlags, cfg: StrategyConfig, tr: _RuleTrace
) -> _StyleChoice:
    pref_rules = cfg.preference
    base: StyleId = cfg.level_to_style[comp.level]
    tr.record("strategy.style_from_level", {"level": comp.level}, base, "level_to_style")
    pref, pref_src = _preference(inputs, cfg, tr)
    contradictions = _contradictions(comp, pref, flags, pref_rules)
    binds, _ = _capacity_binds(comp)
    refused = ["préférence de style inconnue, ignorée"] if _is_unknown_style(inputs.explicit_preference) else []
    want = 0 if pref is None else _idx(pref) - _idx(base)
    shift, why = _preference_shift(want, _upgrade_blocks(comp, flags, binds=binds) + contradictions, pref_rules.max_up)
    refused += why
    style: StyleId = STYLES[_idx(base) + shift]
    if flags.low_literacy and _idx(style) > _idx(pref_rules.beginner_max_style):
        refused.append(f"débutant ou faible littératie : style plafonné à {style_fr(pref_rules.beginner_max_style)}")
        style = pref_rules.beginner_max_style
        shift = _idx(style) - _idx(base)
    tr.record(
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
    return _StyleChoice(style, base, pref, pref_src, shift, refused, contradictions, binds)


def _capped_band_position(
    comp: CompileResult, flags: BehaviorFlags, cfg: StrategyConfig, tr: _RuleTrace
) -> tuple[float, str]:
    """π et sa raison ; une contradiction connaissance × tolérance non résolue plafonne π (réponse la plus prudente)."""
    pi, pi_reason, _ = band_position(comp, flags, cfg, tr)
    if (
        flags.low_literacy
        and comp.level_from_R in cfg.preference.high_tolerance_levels
        and pi > cfg.band.low_composure_pi_max
    ):
        pi = cfg.band.low_composure_pi_max
        pi_reason += " ; contradiction connaissance × tolérance : π plafonné (réponse la plus prudente)"
        tr.record("strategy.band_position.capped", {"reason": "contradiction connaissance × tolérance"}, pi, "band")
    return pi, pi_reason


def derive_style(
    comp: CompileResult, inputs: StyleInputs | None = None, *, profile: Any = None, cfg: StrategyConfig | None = None
) -> StyleDecision:
    cfg = cfg or load_strategy()
    inputs = inputs or StyleInputs()
    tr = _RuleTrace(cfg)
    flags = behavior_flags(inputs, profile, comp, cfg)
    choice = _choose_style(comp, inputs, flags, cfg, tr)
    pi, pi_reason = _capped_band_position(comp, flags, cfg, tr)
    k, k_reason = k_rule(comp, choice.style, inputs, flags, cfg)
    tr.record("strategy.k", {"style": choice.style, "approach": inputs.approach}, k, "k")
    phi = cfg.floors.phi[choice.style] * (cfg.floors.overconfidence_mult if flags.overconfidence else 1.0)
    return StyleDecision(
        style=choice.style,
        from_level=choice.from_level,
        preference=choice.preference,
        preference_source=choice.preference_source,
        shift=choice.shift,
        refused=tuple(choice.refused),
        contradictions=tuple(choice.contradictions),
        flags=flags,
        pi=pi,
        pi_reason=pi_reason,
        capacity_binds=choice.capacity_binds,
        k=k,
        k_reason=k_reason,
        floor_fraction=phi,
        trace=tuple(tr.rows),
    )
